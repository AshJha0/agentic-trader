"""Data-provider interface.

Every method takes an ``as_of`` date and must only return information that was
available at the close of that date. The graph additionally clips price history
to ``<= as_of`` so a provider bug cannot leak future prices into a decision.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd

from ..instruments import Instrument

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
        return {}


def clip_history(df: pd.DataFrame, start: date | None, end: date) -> pd.DataFrame:
    idx = df.index
    mask = idx <= pd.Timestamp(end)
    if start is not None:
        mask &= idx >= pd.Timestamp(start)
    return df.loc[mask]


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
