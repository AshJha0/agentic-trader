"""Point-in-time policy rates and inflation from FRED / ALFRED (no API key needed).

Three rules keep FRED data honest in a backtest:

* **Publication lag.** A value is visible only once it would have been
  published: daily rates the next day, monthly averages about 40 days after the
  first of the month they describe, quarterly CPI about 120 days after.
* **Staleness.** A series whose latest visible value is older than its
  ``max_age_days`` is treated as unavailable rather than carried forward
  (several OECD series stop updating; a 2021 value must not stand in for 2024).
* **Vintages** (optional, ``FredClient(vintages=True)``). FRED serves the latest
  data vintage, so revised series (CPI) can differ from what was first published.
  ALFRED keeps every vintage; with vintages on, a revised series is read from
  the ALFRED vintage that was current at the as-of date, so the backtest sees
  the numbers as first published. Vintages are sampled on a monthly grid (one
  download per series per month of history, cached in memory and optionally on
  disk), so a value becomes visible at the first sampled vintage after its
  publication: the effective lag can be up to a month longer than the exact
  one, which is the conservative side. Policy rates are never revised and
  always come from the single latest download.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

log = logging.getLogger(__name__)

_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
_VINTAGE_URL = "https://alfred.stlouisfed.org/graph/alfredgraph.csv?id={sid}&vintage_date={vd}"
_VINTAGE_ANCHOR = date(2000, 1, 1)


@dataclass(frozen=True)
class FredSeries:
    series_id: str
    lag_days: int       # observation date + lag = first date the value is known
    max_age_days: int   # older than this (relative to as_of) -> unavailable
    yoy_from_index: bool = False  # transform an index level into % change over 12 obs
    revised: bool = False         # published values get revised later (use vintages when on)


# Overnight / policy rates, percent. Never revised.
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

# Consumer-price inflation, percent year over year. Revised (seasonal factors, base years).
CPI_SERIES: dict[str, FredSeries] = {
    "USD": FredSeries("CPIAUCSL", 45, 120, yoy_from_index=True, revised=True),
    "GBP": FredSeries("CPALTT01GBM659N", 45, 120, revised=True),
    "CAD": FredSeries("CPALTT01CAM659N", 45, 120, revised=True),
    "JPY": FredSeries("CPALTT01JPM659N", 45, 120, revised=True),
    "AUD": FredSeries("CPALTT01AUQ659N", 120, 220, revised=True),
}

Fetcher = Callable[[str], pd.DataFrame]


def _http_fetch(url: str) -> pd.DataFrame:
    return pd.read_csv(url, index_col=0, parse_dates=True)


class FredClient:
    """Downloads each series (or vintage) once per process and answers as-of queries."""

    def __init__(self, vintages: bool = False, vintage_step_days: int = 31,
                 cache_dir: str | Path | None = None, fetch: Fetcher | None = None):
        if vintage_step_days < 1:
            raise ValueError("vintage_step_days must be >= 1")
        self.vintages = bool(vintages)
        self.vintage_step_days = int(vintage_step_days)
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._fetch = fetch or _http_fetch
        self._cache: dict[str, pd.Series | None] = {}
        self._vintage_cache: dict[tuple[str, date], pd.Series | None] = {}

    # ------------------------------------------------------------ loading
    def _prepare(self, raw: pd.DataFrame, spec: FredSeries) -> pd.Series:
        s = pd.to_numeric(raw.iloc[:, 0], errors="coerce").dropna().sort_index()
        if spec.yoy_from_index:
            s = (s / s.shift(12) - 1.0).dropna() * 100.0
        # Shift the index to the date each value became public.
        s.index = s.index + pd.Timedelta(days=spec.lag_days)
        return s

    def _read_cached(self, key: str) -> pd.DataFrame | None:
        if self.cache_dir is None:
            return None
        f = self.cache_dir / f"{key}.csv"
        if f.exists():
            try:
                return pd.read_csv(f, index_col=0, parse_dates=True)
            except Exception:  # a corrupt cache file is just re-downloaded
                return None
        return None

    def _write_cached(self, key: str, raw: pd.DataFrame) -> None:
        if self.cache_dir is None:
            return
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            raw.to_csv(self.cache_dir / f"{key}.csv")
        except OSError as e:
            log.warning("FRED cache write failed: %s", e)

    def _load(self, spec: FredSeries) -> pd.Series | None:
        """The latest vintage of a series."""
        if spec.series_id not in self._cache:
            try:
                raw = self._read_cached(spec.series_id)
                if raw is None:
                    raw = self._fetch(_URL.format(sid=spec.series_id))
                    self._write_cached(spec.series_id, raw)
                self._cache[spec.series_id] = self._prepare(raw, spec)
            except Exception as e:  # network, schema change, discontinued series
                log.warning("FRED %s unavailable: %s", spec.series_id, e)
                self._cache[spec.series_id] = None
        return self._cache[spec.series_id]

    def vintage_date(self, as_of: date) -> date:
        """The sampled ALFRED vintage used for ``as_of``: the last grid date on or before it."""
        n = (as_of - _VINTAGE_ANCHOR).days // self.vintage_step_days
        return _VINTAGE_ANCHOR + timedelta(days=max(n, 0) * self.vintage_step_days)

    def _load_vintage(self, spec: FredSeries, vd: date) -> pd.Series | None:
        key = (spec.series_id, vd)
        if key not in self._vintage_cache:
            try:
                ck = f"{spec.series_id}_v{vd.isoformat()}"
                raw = self._read_cached(ck)
                if raw is None:
                    raw = self._fetch(_VINTAGE_URL.format(sid=spec.series_id, vd=vd.isoformat()))
                    self._write_cached(ck, raw)
                self._vintage_cache[key] = self._prepare(raw, spec)
            except Exception as e:
                log.warning("ALFRED %s vintage %s unavailable: %s", spec.series_id, vd, e)
                self._vintage_cache[key] = None
        return self._vintage_cache[key]

    def _series_for(self, spec: FredSeries, as_of: date) -> pd.Series | None:
        if self.vintages and spec.revised:
            return self._load_vintage(spec, self.vintage_date(as_of))
        return self._load(spec)

    # ------------------------------------------------------------ queries
    @staticmethod
    def _asof(s: pd.Series | None, spec: FredSeries, as_of: date) -> float | None:
        if s is None or s.empty:
            return None
        ts = pd.Timestamp(as_of)
        i = s.index.searchsorted(ts, side="right") - 1  # last value published by as_of
        if i < 0 or (ts - s.index[i]).days > spec.max_age_days:
            return None
        return float(s.iloc[i])

    def value_asof(self, spec: FredSeries, as_of: date) -> float | None:
        return self._asof(self._series_for(spec, as_of), spec, as_of)

    @staticmethod
    def _series_asof_from(s: pd.Series | None, spec: FredSeries, dates: pd.DatetimeIndex) -> pd.Series:
        if s is None or s.empty:
            return pd.Series(float("nan"), index=dates)
        pub = pd.Series(s.index, index=s.index)
        vals = s.reindex(dates, method="ffill")
        last_pub = pub.reindex(dates, method="ffill")
        age = (pd.Series(dates, index=dates) - last_pub).dt.days
        return vals.where(age <= spec.max_age_days)

    def series_asof(self, spec: FredSeries, dates: pd.DatetimeIndex) -> pd.Series:
        """Value known at each date (NaN where unavailable or stale), vectorised."""
        if not (self.vintages and spec.revised):
            return self._series_asof_from(self._load(spec), spec, dates)
        out = pd.Series(float("nan"), index=dates)
        groups: dict[date, list[pd.Timestamp]] = {}
        for ts in dates:
            groups.setdefault(self.vintage_date(ts.date()), []).append(ts)
        for vd, members in groups.items():
            idx = pd.DatetimeIndex(members)
            out.loc[idx] = self._series_asof_from(self._load_vintage(spec, vd), spec, idx)
        return out

    def rate(self, ccy: str, as_of: date) -> float | None:
        spec = RATE_SERIES.get(ccy)
        return self.value_asof(spec, as_of) if spec else None

    def inflation(self, ccy: str, as_of: date) -> float | None:
        spec = CPI_SERIES.get(ccy)
        return self.value_asof(spec, as_of) if spec else None


_defaults: dict[tuple[bool, int, str | None], FredClient] = {}
_default: FredClient | None = None  # kept for tests that inject a client


def default_client(config: dict | None = None) -> FredClient:
    """Process-wide client per setting, so every provider shares one download cache.

    ``config["fred_vintages"]`` turns ALFRED vintages on for revised series;
    ``config["fred_vintage_step_days"]`` sets the sampling grid and
    ``config["fred_cache_dir"]`` an on-disk cache for the downloaded CSVs.
    """
    global _default
    if _default is not None and not config:
        return _default
    cfg = config or {}
    key = (bool(cfg.get("fred_vintages", False)), int(cfg.get("fred_vintage_step_days", 31)),
           cfg.get("fred_cache_dir"))
    if _default is not None and key == (False, 31, None):
        return _default
    if key not in _defaults:
        _defaults[key] = FredClient(*key)
    return _defaults[key]
