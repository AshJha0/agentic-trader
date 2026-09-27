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

MACRO_SOURCE_FRED = "fred"
MACRO_SOURCE_STATIC = "static"
MACRO_SOURCE_NONE = "none"


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
        # Tally of macro() answers by source ("fred" / "static" / "none"), so a run can
        # state whether any decision was sized on the illustrative static table.
        self.macro_sources: dict[str, int] = {}

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
        out = fx_macro(instrument, as_of, self.config, real_world=self.real_world)
        src = out.get("macro_source", MACRO_SOURCE_NONE)
        self.macro_sources[src] = self.macro_sources.get(src, 0) + 1
        return out

    def carry_series(self, instrument: Instrument, dates: pd.DatetimeIndex) -> np.ndarray:
        """Annual carry (base rate - quote rate, decimal) known at each date; NaN if unknown.

        Resolved by the same function as ``macro()`` (``fx_rates``), so on every bar the
        differential the desk is shown equals the one the backtester credits, or both are
        absent (``macro`` returns ``{}`` and the carry is NaN, which the engine treats as 0).
        """
        if not instrument.is_fx:
            return np.zeros(len(dates))
        b, q, _ = fx_rates(instrument, dates, self.config, real_world=self.real_world)
        return ((b - q) / 100.0).to_numpy(dtype=float)

    def risk_free_series(self, dates: pd.DatetimeIndex) -> np.ndarray:
        """Annual risk-free rate (fraction, 0.04 = 4%) known at each date; NaN where unknown.

        ``config["cash_leg"]``:

        * ``"auto"`` (default): real-world providers use the FRED 3-month T-bill (DTB3,
          percent, published the next business day, so the value at ``t`` is the last one
          public by ``t``); generated data returns ``config["risk_free_annual"]``;
        * ``"fred"``: DTB3 on any provider;
        * ``"static"``: ``config["risk_free_annual"]`` everywhere;
        * ``"off"``: NaN everywhere (the engine credits nothing).
        """
        return cash_rates(dates, self.config, self.real_world)


def cash_rates(dates: pd.DatetimeIndex, config: dict, real_world: bool,
               mode: str | None = None) -> np.ndarray:
    """``MarketDataProvider.risk_free_series`` for a config; ``mode`` overrides ``config["cash_leg"]``."""
    mode = mode or config.get("cash_leg", "auto")
    n = len(dates)
    if mode == "off":
        return np.full(n, np.nan)
    if mode == "auto":
        mode = MACRO_SOURCE_FRED if real_world else MACRO_SOURCE_STATIC
    if mode == MACRO_SOURCE_STATIC:
        return np.full(n, float(config.get("risk_free_annual", 0.0) or 0.0))
    if mode != MACRO_SOURCE_FRED:
        raise ValueError(f"unknown cash_leg {mode!r} (auto, fred, static or off)")
    from .fred import CASH_SERIES, default_client
    s = default_client(config).series_asof(CASH_SERIES["USD"], pd.DatetimeIndex(dates))
    return (s / 100.0).to_numpy(dtype=float)


def clip_history(df: pd.DataFrame, start: date | None, end: date) -> pd.DataFrame:
    idx = df.index
    mask = idx <= pd.Timestamp(end)
    if start is not None:
        mask &= idx >= pd.Timestamp(start)
    return df.loc[mask]


def clean_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise a raw OHLCV frame: sorted unique dates, no bad closes, sane ranges.

    * rows without a positive, finite Close are dropped (holidays, bad ticks, placeholders);
    * duplicate dates keep the last row; the index is sorted;
    * missing or non-finite Open/High/Low are filled from Close, and High/Low are widened
      to contain Open and Close so intraday stop logic never sees an impossible bar;
    * missing Volume becomes 0.
    """
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    df = df[~df.index.duplicated(keep="last")].sort_index()
    close = pd.to_numeric(df["Close"], errors="coerce")
    df = df[(close > 0) & np.isfinite(close)]
    for col in ("Open", "High", "Low"):
        df[col] = pd.to_numeric(df[col], errors="coerce") if col in df else np.nan
        df[col] = df[col].where((df[col] > 0) & np.isfinite(df[col])).fillna(df["Close"])
    df["High"] = df[["High", "Open", "Close"]].max(axis=1)
    df["Low"] = df[["Low", "Open", "Close"]].min(axis=1)
    df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0) if "Volume" in df else 0.0
    return df[OHLCV].astype(float)


def _macro_source(config: dict, real_world: bool) -> str:
    src = config.get("fx_macro_source", "auto")
    if src == "auto":
        return MACRO_SOURCE_FRED if real_world else MACRO_SOURCE_STATIC
    if src not in (MACRO_SOURCE_FRED, MACRO_SOURCE_STATIC):
        raise ValueError(f"unknown fx_macro_source {src!r} (auto, static or fred)")
    return src


STATIC_SOURCE_LABEL = "static config (illustrative - update fx_policy_rates/fx_inflation)"
FRED_SOURCE_LABEL = "FRED (point-in-time)"


def fx_rates(instrument: Instrument, dates: pd.DatetimeIndex, config: dict,
             real_world: bool) -> tuple[pd.Series, pd.Series, str]:
    """The one resolver of "what policy rates were known at each date" (percent).

    Returns ``(base_rate, quote_rate, source)`` indexed by ``dates``; a leg that is not
    known at a date is NaN. ``source`` is ``"static"`` (the illustrative config table,
    the same at every date: generated data, or ``fx_macro_source="static"``) or
    ``"fred"`` (FRED values published on or before each date and not older than the
    series' ``max_age_days``). In FRED mode a stale, discontinued or unlisted leg is
    NaN at that date -- never today's static table -- so the answer for a given date
    does not depend on when the question is asked.
    """
    idx = pd.DatetimeIndex(dates)
    src = _macro_source(config, real_world)
    b, q = instrument.base, instrument.quote
    if src == MACRO_SOURCE_STATIC:
        rates = config["fx_policy_rates"]
        return (pd.Series(float(rates[b]) if b in rates else np.nan, index=idx),
                pd.Series(float(rates[q]) if q in rates else np.nan, index=idx), src)
    from .fred import RATE_SERIES, default_client
    c = default_client(config)

    def leg(ccy: str) -> pd.Series:
        spec = RATE_SERIES.get(ccy)
        return c.series_asof(spec, idx) if spec else pd.Series(np.nan, index=idx)

    return leg(b), leg(q), src


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
        "source": STATIC_SOURCE_LABEL, "macro_source": MACRO_SOURCE_STATIC,
    }


def fx_macro(instrument: Instrument, as_of: date, config: dict, real_world: bool) -> dict[str, Any]:
    """Point-in-time FX macro inputs, from the same resolver as ``carry_series``.

    ``static``: the illustrative config table at every date.
    ``fred``:   FRED values known at ``as_of`` (publication-lagged, staleness-checked).
                When either leg is unknown the result is ``{}``: the macro analyst
                abstains and the FX strategic weight is 0, which is exactly what the
                backtester credits for a NaN carry. The static table is never
                substituted, whatever the wall-clock date.
    ``auto`` (default): ``static`` for synthetic data, ``fred`` for real-world data.
    """
    src = _macro_source(config, real_world)
    if src == MACRO_SOURCE_STATIC:
        return static_fx_macro(instrument, config)
    idx = pd.DatetimeIndex([pd.Timestamp(as_of)])
    bs, qs, _ = fx_rates(instrument, idx, config, real_world)
    br, qr = float(bs.iloc[0]), float(qs.iloc[0])
    b, q = instrument.base, instrument.quote
    if np.isnan(br) or np.isnan(qr):
        log.info("no point-in-time FRED policy rate for %s at %s (%s%s); macro abstains",
                 instrument.display, as_of, "" if not np.isnan(br) else f"{b} missing ",
                 "" if not np.isnan(qr) else f"{q} missing")
        return {}
    out: dict[str, Any] = {"base": b, "quote": q, "base_rate": br, "quote_rate": qr,
                           "rate_diff": br - qr, "source": FRED_SOURCE_LABEL,
                           "macro_source": MACRO_SOURCE_FRED}
    from .fred import default_client
    c = default_client(config)
    bi, qi = c.inflation(b, as_of), c.inflation(q, as_of)
    if bi is not None and qi is not None:
        out.update(base_inflation=bi, quote_inflation=qi)
    return out
