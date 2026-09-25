"""Local CSV provider: ``<csv_dir>/<SYMBOL>.csv`` with Date,Open,High,Low,Close[,Volume].

Optional ``<SYMBOL>_news.csv`` with columns Date,Headline[,Source,Sentiment]
supplies point-in-time news.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from ..instruments import Instrument
from .base import MarketDataProvider, NewsItem, clip_history, static_fx_macro


class CSVProvider(MarketDataProvider):
    name = "csv"

    def __init__(self, config: dict):
        self.config = config
        self.dir = Path(config.get("csv_dir", "data"))
        self._cache: dict[str, pd.DataFrame] = {}

    def _load(self, instrument: Instrument) -> pd.DataFrame:
        if instrument.symbol not in self._cache:
            path = self.dir / f"{instrument.symbol}.csv"
            if not path.exists():
                raise FileNotFoundError(f"missing price file {path}")
            df = pd.read_csv(path, parse_dates=[0], index_col=0).sort_index()
            df.columns = [c.strip().title() for c in df.columns]
            if "Close" not in df and "Adj Close" in df:
                df["Close"] = df["Adj Close"]
            for col in ("Open", "High", "Low"):
                if col not in df:
                    df[col] = df["Close"]
            if "Volume" not in df:
                df["Volume"] = 0.0
            self._cache[instrument.symbol] = df[["Open", "High", "Low", "Close", "Volume"]]
        return self._cache[instrument.symbol]

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        return clip_history(self._load(instrument), start, end)

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        path = self.dir / f"{instrument.symbol}_news.csv"
        if not path.exists():
            return []
        df = pd.read_csv(path, parse_dates=["Date"])
        lo = pd.Timestamp(as_of - timedelta(days=lookback_days))
        df = df[(df["Date"] >= lo) & (df["Date"] <= pd.Timestamp(as_of))]
        return [NewsItem(r.Date.date(), r.Headline, getattr(r, "Source", "") or "",
                         sentiment=getattr(r, "Sentiment", None)) for r in df.itertuples()]

    def macro(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        return static_fx_macro(instrument, self.config) if instrument.is_fx else {}
