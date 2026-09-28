"""Local CSV provider: ``<csv_dir>/<SYMBOL>.csv`` with Date,Open,High,Low,Close[,Adj Close][,Volume].

Column names are case-insensitive; rows may be in any order and may contain
duplicates or blank closes (see ``clean_ohlcv``). All four price columns of a bar
are always served on one basis:

* ``Close`` and ``Adj Close`` both present: every price column is put on the adjusted
  (total-return, split-adjusted) basis by the row's ``Adj Close / Close`` factor, the
  same basis the Yahoo provider serves, so a split is not a -75% day, and ``Volume`` is
  divided by the split component of that factor only (a split is a day-over-day jump of
  the factor of more than ``SPLIT_JUMP``; the dividend drift between splits never touches
  ``Volume``, so shares stay on Yahoo's split-adjusted basis and a dividend payer's
  volume is served as traded) so that ``Close * Volume`` (the dollar volume, and the ADV
  the impact model and the execution planner read) stays as traded across a split; a
  row whose ``Adj Close`` is blank keeps its ``Close`` and takes the factor of the nearest
  dated row that has one (with a warning), so a missing cell is not a missing bar;
* only ``Adj Close``: it becomes ``Close`` and any raw ``Open``/``High``/``Low`` are
  dropped (they cannot be rescaled without the raw close) and filled from ``Close``
  by ``clean_ohlcv``, with a warning that intraday levels are unavailable for the file;
* only ``Close``: served as is.

Optional ``<SYMBOL>_news.csv`` with columns Date,Headline[,Source,Sentiment] supplies
point-in-time news.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from ..instruments import Instrument
from .base import MarketDataProvider, NewsItem, cash_rates, clean_ohlcv, clip_history

log = logging.getLogger(__name__)

SPLIT_JUMP = 0.05   # a day-over-day move of the Adj Close / Close factor above this is a split, not a dividend


def split_factor(factor: pd.Series) -> tuple[pd.Series, pd.Index]:
    """The split component of an adjustment factor, relative to the last dated row, and the
    dates of the splits found.

    ``factor`` is ``Adj Close / Close`` per row (NaN where unknown). Between corporate actions
    it is constant; a dividend moves it by its yield (a few percent at most) and a split by
    the split ratio, so a jump of more than ``SPLIT_JUMP`` between consecutive dated rows is
    read as a split and only those jumps are accumulated: the result is ``factor`` with the
    dividend drift removed (0.5 before a 2:1 split, 1 after it, 1 everywhere for a dividend
    payer with no split). Rows are taken in date order; duplicate dates share one value."""
    known = factor.dropna()
    known = known[~known.index.duplicated(keep="last")].sort_index()
    if known.empty:
        return pd.Series(1.0, index=factor.index), known.index
    jump = known / known.shift(1)
    is_split = ((jump - 1.0).abs() > SPLIT_JUMP).to_numpy()
    ratio = pd.Series(np.where(is_split, 1.0 / jump.to_numpy(), 1.0), index=known.index)  # pre / post at a split
    after = ratio.iloc[::-1].cumprod().iloc[::-1]                  # product over rows >= t
    comp = after.shift(-1, fill_value=1.0)                         # product over rows > t
    return comp.reindex(factor.index).fillna(1.0), known.index[is_split]


def one_basis(df: pd.DataFrame, name: str = "") -> pd.DataFrame:
    """Put Open/High/Low/Close on the basis of ``Adj Close`` when that column exists; ``Volume``
    is divided by the split component of the factor only (``split_factor``), so the share
    count stays on the split-adjusted basis Yahoo serves and the dollar volume of every bar
    stays as traded across a split, while a dividend never changes the volume."""
    if "Adj Close" not in df:
        return df
    df = df.copy()
    adj = pd.to_numeric(df["Adj Close"], errors="coerce")
    if "Close" in df:
        close = pd.to_numeric(df["Close"], errors="coerce")
        factor = (adj / close).where((close > 0) & (adj > 0) & np.isfinite(adj) & np.isfinite(close))
        gap = factor.isna() & (close > 0) & np.isfinite(close)
        if gap.any():
            known = factor.dropna()
            known = known[~known.index.duplicated(keep="last")].sort_index()
            if known.empty:
                factor = pd.Series(1.0, index=factor.index)
                log.warning("%s: Adj Close is blank on every row with a Close; served on the raw Close basis",
                            name or "price file")
            else:
                # Nearest dated row with a factor: a split is a step, so the neighbour's factor
                # is exact away from ex-dates and the closest guess on one.
                pos = known.index.get_indexer(factor.index[gap], method="nearest")
                factor.loc[gap] = known.to_numpy()[pos]
                log.warning("%s: Adj Close blank on %d row(s) with a valid Close (first %s); adjusted with "
                            "the nearest dated row's factor", name or "price file", int(gap.sum()),
                            factor.index[gap][0])
        for col in ("Open", "High", "Low"):
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce") * factor
        df["Close"] = adj.where(~gap, close * factor)
        if "Volume" in df:
            comp, splits = split_factor(factor)
            if len(splits):
                log.info("%s: %d split(s) detected from the adjustment factor (%s); Volume rescaled across them",
                         name or "price file", len(splits), ", ".join(str(d)[:10] for d in splits[:5]))
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce") / comp
    else:
        dropped = [c for c in ("Open", "High", "Low") if c in df]
        if dropped:
            log.warning("%s has Adj Close but no Close: %s dropped (they cannot be put on the adjusted "
                        "basis), so intraday levels are unavailable for this file", name or "price file",
                        "/".join(dropped))
            df = df.drop(columns=dropped)
        df["Close"] = adj
    return df.drop(columns=["Adj Close"])


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
            df = one_basis(df, str(path))
            if "Close" not in df:
                raise ValueError(f"{path} needs a Close or Adj Close column")
            self._cache[instrument.symbol] = clean_ohlcv(df)
        return self._cache[instrument.symbol]

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        return clip_history(self._load(instrument), start, end)

    def risk_free_series(self, dates: pd.DatetimeIndex) -> np.ndarray:
        """Local files carry no rate data: ``config["risk_free_annual"]`` at every date
        (``cash_leg`` "off" -> NaN; "fred" -> DTB3 as on any provider)."""
        mode = self.config.get("cash_leg", "auto")
        return cash_rates(dates, self.config, self.real_world, "static" if mode == "auto" else mode)

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
