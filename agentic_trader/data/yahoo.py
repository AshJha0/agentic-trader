"""Yahoo Finance provider (``pip install yfinance``).

Point-in-time caveats, handled conservatively:
  * Prices: fine historically.
  * News: Yahoo only serves recent headlines, so historical dates get none.
  * Fundamentals: ``Ticker.info`` is a *current* snapshot. Using it for a past
    date would leak future information, so it is only returned when ``as_of``
    is within 7 days of today.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd

from ..instruments import Instrument
from .base import OHLCV, MarketDataProvider, NewsItem, clip_history, static_fx_macro

log = logging.getLogger(__name__)

# FRED series for policy / overnight rates (percent). Used when fx_macro_source == "fred".
_FRED_RATES = {
    "USD": "DFF", "EUR": "ECBDFR", "GBP": "IRSTCI01GBM156N", "JPY": "IRSTCI01JPM156N",
    "CHF": "IRSTCI01CHM156N", "AUD": "IRSTCI01AUM156N", "CAD": "IRSTCI01CAM156N",
    "NZD": "IRSTCI01NZM156N",
}


def _yf():
    try:
        import yfinance as yf  # type: ignore
    except ImportError as e:  # pragma: no cover
        raise ImportError("YahooProvider needs `pip install yfinance`") from e
    return yf


class YahooProvider(MarketDataProvider):
    name = "yahoo"

    def __init__(self, config: dict):
        self.config = config
        self._cache: dict[str, pd.DataFrame] = {}
        self._fred: dict[str, pd.Series] = {}

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        sym = instrument.yahoo_symbol
        cached = self._cache.get(sym)
        if cached is None or cached.index.min() > pd.Timestamp(start) or cached.index.max() < pd.Timestamp(end) - pd.Timedelta(days=5):
            df = _yf().download(sym, start=start.isoformat(),
                                end=(end + timedelta(days=1)).isoformat(),
                                auto_adjust=True, progress=False)
            if df is None or df.empty:
                raise ValueError(f"no Yahoo data for {sym}")
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df[[c for c in OHLCV if c in df.columns]].dropna(subset=["Close"])
            if "Volume" not in df:
                df["Volume"] = 0.0
            df.index = pd.to_datetime(df.index).tz_localize(None)
            if cached is not None:
                df = pd.concat([cached, df]).groupby(level=0).last().sort_index()
            self._cache[sym] = df
            cached = df
        return clip_history(cached, start, end)

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        try:
            raw = _yf().Ticker(instrument.yahoo_symbol).news or []
        except Exception as e:  # network / schema issues must not kill the pipeline
            log.warning("yahoo news failed: %s", e)
            return []
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

    def _fred_rate(self, ccy: str, as_of: date) -> float | None:
        sid = _FRED_RATES.get(ccy)
        if not sid:
            return None
        if sid not in self._fred:
            url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
            s = pd.read_csv(url, index_col=0, parse_dates=True).iloc[:, 0]
            self._fred[sid] = pd.to_numeric(s, errors="coerce").dropna()
        s = self._fred[sid]
        s = s[s.index <= pd.Timestamp(as_of)]
        return float(s.iloc[-1]) if len(s) else None

    def macro(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        if not instrument.is_fx:
            return {}
        out = static_fx_macro(instrument, self.config)
        if self.config.get("fx_macro_source") == "fred":
            try:
                b = self._fred_rate(instrument.base, as_of)
                q = self._fred_rate(instrument.quote, as_of)
                if b is not None and q is not None:
                    out.update(base_rate=b, quote_rate=q, rate_diff=b - q, source="FRED")
            except Exception as e:
                log.warning("FRED fetch failed, using static rates: %s", e)
        return out
