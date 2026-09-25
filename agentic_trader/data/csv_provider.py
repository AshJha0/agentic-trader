"""Local CSV provider: ``<csv_dir>/<SYMBOL>.csv`` with Date,Open,High,Low,Close[,Volume].

Column names are case-insensitive; ``Adj Close`` is used when ``Close`` is
missing; rows may be in any order and may contain duplicates or blank closes
(see ``clean_ohlcv``). Optional ``<SYMBOL>_news.csv`` with columns
Date,Headline[,Source,Sentiment] supplies point-in-time news.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from ..instruments import Instrument
from .base import MarketDataProvider, NewsItem, clean_ohlcv, clip_history


class CSVProvider(MarketDataProvider):
    name = "csv"

    def __init__(self, config: dict):
        super().__init__(config)
        self.dir = Path(config.get("csv_dir", "data"))
        self._cache: dict[str, pd.DataFrame] = {}

    def _load(self, instrument: Instrument) -> pd.DataFrame:
        if instrument.symbol not in self._cache:
            path = self.dir / f"{instrument.symbol}.csv"
            if not path.exists():
                raise FileNotFoundError(f"missing price file {path}")
            df = pd.read_csv(path, index_col=0)
            df.index = pd.to_datetime(df.index, errors="coerce")
            df = df[df.index.notna()]
            df.columns = [c.strip().title() for c in df.columns]
            if "Close" not in df and "Adj Close" in df:
                df["Close"] = df["Adj Close"]
            if "Close" not in df:
                raise ValueError(f"{path} needs a Close or Adj Close column")
            self._cache[instrument.symbol] = clean_ohlcv(df)
        return self._cache[instrument.symbol]

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        return clip_history(self._load(instrument), start, end)

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        path = self.dir / f"{instrument.symbol}_news.csv"
        if not path.exists():
            return []
        df = pd.read_csv(path)
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        lo = pd.Timestamp(as_of - timedelta(days=lookback_days))
        df = df[(df["Date"] >= lo) & (df["Date"] <= pd.Timestamp(as_of))]
        out = []
        for r in df.itertuples():
            if not isinstance(r.Headline, str) or not r.Headline.strip():
                continue
            s = getattr(r, "Sentiment", None)
            s = None if s is None or (isinstance(s, float) and math.isnan(s)) else float(s)
            src = getattr(r, "Source", "")
            out.append(NewsItem(r.Date.date(), r.Headline.strip(),
                                src if isinstance(src, str) else "", sentiment=s))
        return out
