"""Point-in-time policy rates and inflation from FRED (no API key needed).

Two rules keep FRED data honest in a backtest:

* **Publication lag.** A value is visible only once it would have been
  published: daily rates the next day, monthly averages about 40 days after the
  first of the month they describe, quarterly CPI about 120 days after.
* **Staleness.** A series whose latest visible value is older than its
  ``max_age_days`` is treated as unavailable rather than carried forward
  (several OECD series stop updating; a 2021 value must not stand in for 2024).

FRED serves the latest data vintage, so revised series (CPI) can differ slightly
from what was first published. Policy rates are not revised.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

log = logging.getLogger(__name__)

_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    lag_days: int       # observation date + lag = first date the value is known
    max_age_days: int   # older than this (relative to as_of) -> unavailable
    yoy_from_index: bool = False  # transform an index level into % change over 12 obs


# Overnight / policy rates, percent.
RATE_SERIES: dict[str, FredSeries] = {
    "USD": FredSeries("DFF", 1, 10),
    "EUR": FredSeries("ECBDFR", 1, 10),
    "GBP": FredSeries("IUDSOIA", 1, 10),
    "JPY": FredSeries("IRSTCI01JPM156N", 40, 100),
    "CHF": FredSeries("IRSTCI01CHM156N", 40, 100),
    "AUD": FredSeries("IRSTCI01AUM156N", 40, 100),
    "CAD": FredSeries("IRSTCI01CAM156N", 40, 100),
    "NZD": FredSeries("IRSTCI01NZM156N", 40, 100),
}

# Consumer-price inflation, percent year over year.
CPI_SERIES: dict[str, FredSeries] = {
    "USD": FredSeries("CPIAUCSL", 45, 120, yoy_from_index=True),
    "GBP": FredSeries("CPALTT01GBM659N", 45, 120),
    "CAD": FredSeries("CPALTT01CAM659N", 45, 120),
    "JPY": FredSeries("CPALTT01JPM659N", 45, 120),
    "AUD": FredSeries("CPALTT01AUQ659N", 120, 220),
}


class FredClient:
    """Downloads each series once per process and answers as-of queries."""

    def __init__(self):
        self._cache: dict[str, pd.Series | None] = {}

    def _load(self, spec: FredSeries) -> pd.Series | None:
        if spec.series_id not in self._cache:
            try:
                raw = pd.read_csv(_URL.format(sid=spec.series_id), index_col=0, parse_dates=True)
                s = pd.to_numeric(raw.iloc[:, 0], errors="coerce").dropna().sort_index()
                if spec.yoy_from_index:
                    s = (s / s.shift(12) - 1.0).dropna() * 100.0
                # Shift the index to the date each value became public.
                s.index = s.index + pd.Timedelta(days=spec.lag_days)
                self._cache[spec.series_id] = s
            except Exception as e:  # network, schema change, discontinued series
                log.warning("FRED %s unavailable: %s", spec.series_id, e)
                self._cache[spec.series_id] = None
        return self._cache[spec.series_id]

    def value_asof(self, spec: FredSeries, as_of: date) -> float | None:
        s = self._load(spec)
        if s is None:
            return None
        ts = pd.Timestamp(as_of)
        i = s.index.searchsorted(ts, side="right") - 1  # last value published by as_of
        if i < 0 or (ts - s.index[i]).days > spec.max_age_days:
            return None
        return float(s.iloc[i])

    def series_asof(self, spec: FredSeries, dates: pd.DatetimeIndex) -> pd.Series:
        """Value known at each date (NaN where unavailable or stale), vectorised."""
        s = self._load(spec)
        if s is None or s.empty:
            return pd.Series(float("nan"), index=dates)
        pub = pd.Series(s.index, index=s.index)
        vals = s.reindex(dates, method="ffill")
        last_pub = pub.reindex(dates, method="ffill")
        age = (pd.Series(dates, index=dates) - last_pub).dt.days
        return vals.where(age <= spec.max_age_days)

    def rate(self, ccy: str, as_of: date) -> float | None:
        spec = RATE_SERIES.get(ccy)
        return self.value_asof(spec, as_of) if spec else None

    def inflation(self, ccy: str, as_of: date) -> float | None:
        spec = CPI_SERIES.get(ccy)
        return self.value_asof(spec, as_of) if spec else None


_default: FredClient | None = None


def default_client() -> FredClient:
    """Process-wide client so every provider shares one download cache."""
    global _default
    if _default is None:
        _default = FredClient()
    return _default
