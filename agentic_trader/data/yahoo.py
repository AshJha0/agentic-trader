"""Yahoo Finance provider (``pip install yfinance``).

Point-in-time caveats, handled conservatively:
  * Prices: dividend- and split-adjusted closes (``auto_adjust=True``), i.e.
    total-return prices. Fine historically.
  * News: Yahoo only serves recent headlines, so historical dates get none.
  * Fundamentals: ``Ticker.info`` is a *current* snapshot. Using it for a past
    date would leak future information, so it is only returned when ``as_of``
    is within 7 days of today.
  * FX macro: point-in-time FRED rates (see ``data/fred.py`` and ``base.fx_macro``).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from ..instruments import Instrument
from .base import MarketDataProvider, NewsItem, clean_ohlcv, clip_history

log = logging.getLogger(__name__)


def _yf():
    try:
        import yfinance as yf  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError("YahooProvider needs `pip install yfinance`") from e
    return yf


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self, config: dict):
        super().__init__(config)
        self._cache: dict[str, pd.DataFrame] = {}
        self._covered: dict[str, tuple[date, date]] = {}  # requested range already downloaded
        self._news: dict[str, list] = {}  # one headline fetch per symbol per provider

    def _download(self, sym: str, start: date, end: date) -> pd.DataFrame:
        df = _yf().download(sym, start=start.isoformat(),
                            end=(end + timedelta(days=1)).isoformat(),
                            auto_adjust=True, progress=False)
        if df is None or df.empty:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return clean_ohlcv(df)

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        sym = instrument.yahoo_symbol
        cov = self._covered.get(sym)
        if cov is None or start < cov[0] or end > cov[1]:
            # Download the union of what was asked before and now, so repeated calls
            # (walk-forward backtests) hit the cache even before a listing date.
            lo, hi = (start, end) if cov is None else (min(start, cov[0]), max(end, cov[1]))
            df = self._download(sym, lo, hi)
            if df.empty:
                raise ValueError(f"no Yahoo data for {sym} between {lo} and {hi}")
            self._cache[sym] = df
            self._covered[sym] = (lo, hi)
        return clip_history(self._cache[sym], start, end)

    # Yahoo serves only the latest few days of headlines, so a request for an older
    # window can never return anything; skipping it keeps historical backtests from
    # making one network round trip per decision.
    NEWS_HORIZON_DAYS = 30

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        if (date.today() - as_of).days > self.NEWS_HORIZON_DAYS:
            return []
        sym = instrument.yahoo_symbol
        if sym not in self._news:
            try:
                self._news[sym] = _yf().Ticker(sym).news or []
            except Exception as e:  # network / schema issues must not kill the pipeline
                log.warning("yahoo news failed: %s", e)
                self._news[sym] = []
        raw = self._news[sym]
        lo = as_of - timedelta(days=lookback_days)
        out = []
        for item in raw:
            content = item.get("content", item)
            title = content.get("title")
            ts = content.get("pubDate") or item.get("providerPublishTime")
            if not title or ts is None:
                continue
            if isinstance(ts, (int, float)):
                d = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            else:
                d = pd.Timestamp(ts).date()
            if lo <= d <= as_of:
                provider = content.get("provider") or {}
                src = provider.get("displayName", "") if isinstance(provider, dict) else ""
                out.append(NewsItem(d, title, source=src or item.get("publisher", ""),
                                    summary=content.get("summary", "") or ""))
        return out

    def fundamentals(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        if instrument.is_fx or (date.today() - as_of).days > 7:
            return {}
        try:
            info = _yf().Ticker(instrument.yahoo_symbol).info or {}
        except Exception as e:
            log.warning("yahoo fundamentals failed: %s", e)
            return {}
        mc, fcf = info.get("marketCap"), info.get("freeCashflow")
        de = info.get("debtToEquity")
        return {
            "pe_ratio": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "sector": info.get("sector"),
            "sector_pe": None,
            "revenue_growth_yoy": info.get("revenueGrowth"),
            "net_margin": info.get("profitMargins"),
            "debt_to_equity": de / 100.0 if de is not None else None,  # Yahoo reports percent
            "fcf_yield": fcf / mc if fcf and mc else None,
            "eps_surprise": None,
            "source": "yahoo (current snapshot)",
        }
