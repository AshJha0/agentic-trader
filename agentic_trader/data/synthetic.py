"""Deterministic synthetic market data for offline development and tests.

Prices follow a regime-switching random walk with fat tails; news and social
posts are generated from each day's realised move (so they carry information
known at that day's close, never later); fundamentals are reported quarterly
with a 30-day publication lag. Nothing here is real market data.
"""
from __future__ import annotations

import zlib
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..instruments import Instrument
from .base import MarketDataProvider, NewsItem, clip_history

_EPOCH = "2015-01-01"
_END = "2030-12-31"

_FX_START = {
    "EURUSD": 1.10, "GBPUSD": 1.27, "USDJPY": 145.0, "AUDUSD": 0.66, "USDCHF": 0.90,
    "USDCAD": 1.36, "NZDUSD": 0.60, "EURGBP": 0.86, "EURJPY": 158.0,
}

_NEWS = {
    "equity": {
        "pos": ["{s} beats earnings estimates as revenue growth accelerates",
                "Analysts upgrade {s} citing strong demand and record margins",
                "{s} raises full-year guidance on robust sales",
                "{s} shares rally after new product launch wins praise"],
        "neg": ["{s} misses estimates as margins decline",
                "{s} downgraded on weak demand and rising costs",
                "{s} cuts guidance amid slowdown concerns",
                "Regulators open probe into {s}; shares fall"],
        "neu": ["{s} to present at industry conference next week",
                "{s} announces board appointment",
                "{s} trading volume in line with average"],
    },
    "fx": {
        "pos": ["{b} strengthens as {b} central bank signals further tightening",
                "Strong {b} data beats expectations, lifting {s}",
                "{q} weakens after dovish comments from policymakers",
                "Risk appetite improves; {s} rallies"],
        "neg": ["{b} slides as growth data disappoints",
                "{b} central bank hints at rate cuts; {s} falls",
                "Hawkish {q} policymakers boost {q}, pressuring {s}",
                "{s} drops amid rising recession fears"],
        "neu": ["{s} range-bound ahead of central bank meeting",
                "Traders await {q} inflation data",
                "{s} liquidity thin in holiday trading"],
    },
}

_SOCIAL = {
    "pos": ["$SYM looking bullish, loading calls", "$SYM breakout! strong buy",
            "$SYM to the moon, great momentum", "accumulating more $SYM on this strength"],
    "neg": ["$SYM looks weak, buying puts", "$SYM breakdown, sell before it gets worse",
            "$SYM dump incoming, bearish", "cutting my $SYM loss here, ugly chart"],
    "neu": ["anyone watching $SYM today?", "$SYM chop, waiting for a setup",
            "no position in $SYM yet"],
}


class SyntheticProvider(MarketDataProvider):
    name = "synthetic"
    real_world = False  # the static macro table is part of the synthetic world

    def __init__(self, config: dict):
        super().__init__(config)
        self.seed = int(config.get("synthetic_seed", 7))
        self._cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------ helpers
    def _key(self, instrument: Instrument) -> int:
        return zlib.crc32(instrument.symbol.encode())

    def _frame(self, instrument: Instrument) -> pd.DataFrame:
        if instrument.symbol in self._cache:
            return self._cache[instrument.symbol]
        rng = np.random.default_rng([self.seed, self._key(instrument)])
        dates = pd.bdate_range(_EPOCH, _END)
        n = len(dates)
        ppy = instrument.periods_per_year
        fx = instrument.is_fx
        base_vol = rng.uniform(0.06, 0.10) if fx else rng.uniform(0.18, 0.40)
        p0 = _FX_START.get(instrument.symbol, rng.uniform(0.8, 1.5)) if fx else rng.uniform(40, 300)

        drift, volmult = np.zeros(n), np.ones(n)
        i = 0
        while i < n:
            length = int(rng.integers(40, 120))
            drift[i:i + length] = rng.normal(0.0, 0.08) if fx else rng.normal(0.08, 0.30)
            volmult[i:i + length] = rng.uniform(0.7, 1.5)
            i += length
        dvol = base_vol * volmult / np.sqrt(ppy)
        eps = rng.standard_t(5, n) / np.sqrt(5.0 / 3.0)  # unit-variance fat tails
        r = drift / ppy - 0.5 * dvol**2 + dvol * eps
        close = p0 * np.exp(np.cumsum(r))
        prev = np.concatenate([[p0], close[:-1]])
        open_ = prev * np.exp(dvol * 0.2 * rng.standard_normal(n))
        high = np.maximum(open_, close) * np.exp(np.abs(rng.standard_normal(n)) * dvol * 0.6)
        low = np.minimum(open_, close) * np.exp(-np.abs(rng.standard_normal(n)) * dvol * 0.6)
        if fx:
            volume = np.zeros(n)
        else:
            volume = rng.lognormal(np.log(rng.uniform(2e6, 3e7)), 0.3, n) * (1 + 2 * np.abs(eps))
        df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close,
                           "Volume": volume.round()}, index=dates)
        df["_z"] = eps  # standardised daily move, used to generate news tone
        self._cache[instrument.symbol] = df
        return df

    def _day_rng(self, instrument: Instrument, d: date, salt: int) -> np.random.Generator:
        return np.random.default_rng([self.seed, self._key(instrument), d.toordinal(), salt])

    def _posts(self, instrument, as_of, lookback_days, salt, per_day, noise, make):
        df = self._frame(instrument)
        window = clip_history(df, as_of - timedelta(days=lookback_days), as_of)
        items = []
        for ts, z in window["_z"].items():
            d = ts.date()
            rng = self._day_rng(instrument, d, salt)
            for _ in range(per_day):
                if rng.random() > 0.6:
                    continue
                tone = np.tanh(0.8 * z + noise * rng.standard_normal())
                bucket = "pos" if tone > 0.25 else "neg" if tone < -0.25 else "neu"
                items.append(make(d, bucket, rng))
        return items

    # ------------------------------------------------------------ interface
    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        return clip_history(self._frame(instrument), start, end).drop(columns="_z")

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        t = _NEWS["fx" if instrument.is_fx else "equity"]
        fmt = dict(s=instrument.display, b=instrument.base or "", q=instrument.quote or "")

        def make(d, bucket, rng):
            text = t[bucket][int(rng.integers(len(t[bucket])))].format(**fmt)
            return NewsItem(d, text, source="SyntheticWire")

        return self._posts(instrument, as_of, lookback_days, 1, 1, 0.6, make)

    def social(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        sym = instrument.symbol

        def make(d, bucket, rng):
            text = _SOCIAL[bucket][int(rng.integers(len(_SOCIAL[bucket])))].replace("SYM", sym)
            return NewsItem(d, text, source="SyntheticSocial")

        return self._posts(instrument, as_of, lookback_days, 2, 3, 1.2, make)

    def fundamentals(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        if instrument.is_fx:
            return {}
        df = self._frame(instrument)
        # Latest quarter whose report (quarter end + 30 days) is public by as_of.
        q_end = (pd.Timestamp(as_of) - pd.Timedelta(days=30)).to_period("Q").start_time - pd.Timedelta(days=1)
        q_start = q_end - pd.offsets.QuarterBegin(startingMonth=1)
        closes = df["Close"]
        q = closes[(closes.index > q_start) & (closes.index <= q_end)]
        if len(q) < 2:
            return {}
        q_ret = float(q.iloc[-1] / q.iloc[0] - 1.0)
        rng = np.random.default_rng([self.seed, self._key(instrument), q_end.toordinal()])
        base = np.random.default_rng([self.seed, self._key(instrument)])
        base_pe, base_g, base_m = base.uniform(12, 40), base.uniform(0.0, 0.2), base.uniform(0.05, 0.3)
        return {
            "report_period_end": q_end.date().isoformat(),
            "pe_ratio": round(float(base_pe * np.exp(0.15 * rng.standard_normal() + q_ret)), 2),
            "sector_pe": 22.0,
            "revenue_growth_yoy": round(float(base_g + 0.4 * q_ret + 0.03 * rng.standard_normal()), 4),
            "net_margin": round(float(base_m + 0.02 * rng.standard_normal()), 4),
            "debt_to_equity": round(float(abs(base.normal(0.8, 0.5)) + 0.1 * rng.standard_normal()), 3),
            "fcf_yield": round(float(0.04 + 0.02 * rng.standard_normal()), 4),
            "eps_surprise": round(float(0.02 + 0.2 * q_ret + 0.03 * rng.standard_normal()), 4),
            "insider_net_buying": int(rng.integers(-5, 6)),
            "source": "synthetic",
        }
