"""Data-provider interface.

Every method takes an ``as_of`` date and must only return information that was
available at the close of that date. The graph additionally clips price history
to ``<= as_of`` so a provider bug cannot leak future prices into a decision.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from ..instruments import Instrument

log = logging.getLogger(__name__)

OHLCV = ["Open", "High", "Low", "Close", "Volume"]


@dataclass
class NewsItem:
    published: date
    headline: str
    source: str = ""
    summary: str = ""
    sentiment: float | None = None  # optional pre-computed score in [-1, 1]
    tags: list[str] = field(default_factory=list)


class MarketDataProvider(ABC):
    name = "base"
    # False for generated data: its static macro table is part of the synthetic
    # world, so it applies at every date. Real-world providers must not use
    # today's illustrative rates for historical dates (see fx_macro).
    real_world = True

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        """Daily OHLCV indexed by date (DatetimeIndex), inclusive of start and end."""

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        return []

    def social(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        """Social-media style posts (StockTwits/Reddit). Default: none available."""
        return []

    def fundamentals(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        """Point-in-time company fundamentals (equities only)."""
        return {}

    def macro(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        """Macro inputs (FX: policy rates and inflation of both currencies)."""
        if not instrument.is_fx:
            return {}
        return fx_macro(instrument, as_of, self.config, real_world=self.real_world)

    def carry_series(self, instrument: Instrument, dates: pd.DatetimeIndex) -> np.ndarray:
        """Annual carry (base rate - quote rate, decimal) known at each date; NaN if unknown."""
        if not instrument.is_fx:
            return np.zeros(len(dates))
        if self.real_world and _macro_source(self.config, True) == "fred":
            from .fred import RATE_SERIES, default_client
            b, q = RATE_SERIES.get(instrument.base), RATE_SERIES.get(instrument.quote)
            if b and q:
                c = default_client(self.config)
                diff = c.series_asof(b, dates) - c.series_asof(q, dates)
                return (diff / 100.0).to_numpy(dtype=float)
        out = [self.macro(instrument, ts.date()).get("rate_diff", float("nan")) for ts in dates]
        return np.asarray(out, dtype=float) / 100.0


def clip_history(df: pd.DataFrame, start: date | None, end: date) -> pd.DataFrame:
    idx = df.index
    mask = idx <= pd.Timestamp(end)
    if start is not None:
        mask &= idx >= pd.Timestamp(start)
    return df.loc[mask]


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a raw OHLCV frame: sorted unique dates, no bad closes, sane ranges.

    * rows without a positive Close are dropped (holidays, bad ticks, placeholders);
    * duplicate dates keep the last row; the index is sorted;
    * missing Open/High/Low are filled from Close, and High/Low are widened to
      contain Open and Close so intraday stop logic never sees an impossible bar;
    * missing Volume becomes 0.
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    df = df[pd.to_numeric(df["Close"], errors="coerce") > 0]
    for col in ("Open", "High", "Low"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df else np.nan
        df[col] = df[col].where(df[col] > 0).fillna(df["Close"])
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0) if "Volume" in df else 0.0
    return df[OHLCV].astype(float)


def _macro_source(config: dict, real_world: bool) -> str:
    src = config.get("fx_macro_source", "auto")
    if src == "auto":
        return "fred" if real_world else "static"
    return src


def static_fx_macro(instrument: Instrument, config: dict) -> dict[str, Any]:
    rates, cpi = config["fx_policy_rates"], config["fx_inflation"]
    b, q = instrument.base, instrument.quote
    if b not in rates or q not in rates:
        return {}
    return {
        "base": b, "quote": q,
        "base_rate": rates[b], "quote_rate": rates[q],
        "rate_diff": rates[b] - rates[q],
        "base_inflation": cpi.get(b), "quote_inflation": cpi.get(q),
        "source": "static config (illustrative - update fx_policy_rates/fx_inflation)",
    }


def fx_macro(instrument: Instrument, as_of: date, config: dict, real_world: bool) -> dict[str, Any]:
    """Point-in-time FX macro inputs.

    ``static``: the illustrative config table at every date.
    ``fred``:   FRED values known at ``as_of`` (publication-lagged, staleness-checked);
                the static table is used only for dates within
                ``static_macro_max_age_days`` of today, where it is plausibly current.
    ``auto`` (default): ``static`` for synthetic data, ``fred`` for real-world data.
    """
    src = _macro_source(config, real_world)
    if src == "static":
        return static_fx_macro(instrument, config)
    if src != "fred":
        raise ValueError(f"unknown fx_macro_source {src!r} (auto, static or fred)")

    from .fred import default_client
    c = default_client(config)
    b, q = instrument.base, instrument.quote
    br, qr = c.rate(b, as_of), c.rate(q, as_of)
    recent = (date.today() - as_of).days <= config.get("static_macro_max_age_days", 180)
    if br is None or qr is None:
        if recent:
            return static_fx_macro(instrument, config)
        return {}
    out: dict[str, Any] = {"base": b, "quote": q, "base_rate": br, "quote_rate": qr,
                           "rate_diff": br - qr, "source": "FRED (point-in-time)"}
    bi, qi = c.inflation(b, as_of), c.inflation(q, as_of)
    if bi is not None and qi is not None:
        out.update(base_inflation=bi, quote_inflation=qi)
    return out
