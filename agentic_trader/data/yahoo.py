"""Yahoo Finance provider (``pip install yfinance``).

Point-in-time caveats, handled conservatively:
  * Prices: dividend- and split-adjusted closes (``auto_adjust=True``), i.e.
    total-return prices. Fine historically.
  * News: Yahoo only serves recent headlines. Historical dates are served from
    the SEC EDGAR filing stream instead (8-K events, periodic reports, ownership
    and insider filings; see ``data/edgar.py``), which is point-in-time by
    construction; Yahoo headlines are added for the last month.
  * Fundamentals: EDGAR XBRL facts filed on or before ``as_of`` (first prints),
    combined with the close *as traded* on ``as_of``: the adjusted history above
    is rescaled by every split after ``as_of`` (from a second, unadjusted download
    made once per symbol and cached), and the same split table brings EDGAR's
    per-share prints to the ``as_of`` basis. ``Ticker.info`` is a *current*
    snapshot, so it is used only when EDGAR has nothing and ``as_of`` is within
    7 days of today.
  * FX macro: point-in-time FRED rates (see ``data/fred.py`` and ``base.fx_macro``).

EDGAR needs a contact User-Agent (``EDGAR_USER_AGENT``); without one both fall
back to the Yahoo-only behaviour with a single warning.
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any

import numpy as np
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
        self._actions: dict[str, pd.DataFrame] = {}  # unadjusted close + splits, per symbol, lazily
        self._lock = threading.RLock()   # history() misses download once even from worker threads
        from .edgar import EdgarClient
        self.edgar = EdgarClient.from_config(config)

    def _corporate_actions(self, sym: str) -> pd.DataFrame:
        """``RawClose`` (split-adjusted to today, not dividend-adjusted) and ``Split`` (the
        ratio on ex-dates, 0 elsewhere), downloaded once per symbol."""
        with self._lock:
            if sym not in self._actions:
                df = _yf().download(sym, start="1990-01-01", end=(date.today() + timedelta(days=1)).isoformat(),
                                    auto_adjust=False, actions=True, progress=False)
                if df is None or df.empty:
                    raise ValueError(f"no Yahoo corporate-action history for {sym}")
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = df.columns.get_level_values(0)
                out = pd.DataFrame({"RawClose": pd.to_numeric(df["Close"], errors="coerce"),
                                    "Split": pd.to_numeric(df.get("Stock Splits", 0.0), errors="coerce").fillna(0.0)})
                out.index = pd.to_datetime(out.index).tz_localize(None) if getattr(out.index, "tz", None) else pd.to_datetime(out.index)
                self._actions[sym] = out.sort_index()
            return self._actions[sym]

    def splits(self, instrument: Instrument) -> dict[date, float]:
        """Split ex-date -> ratio (4.0 for a 4-for-1) from Yahoo's action history."""
        a = self._corporate_actions(instrument.yahoo_symbol)
        s = a.loc[a["Split"] > 0, "Split"]
        return {ts.date(): float(r) for ts, r in s.items()}

    def as_traded_close(self, instrument: Instrument, as_of: date) -> float | None:
        """The last close on or before ``as_of`` in the share units of that day: Yahoo's
        split-adjusted close multiplied back by every split after ``as_of``."""
        try:
            a = self._corporate_actions(instrument.yahoo_symbol)
        except Exception as e:  # a corporate-action outage must not take the fundamentals down
            log.warning("yahoo corporate actions failed for %s: %s", instrument.symbol, e)
            return None
        upto = a.loc[a.index <= pd.Timestamp(as_of), "RawClose"].dropna()
        if upto.empty:
            return None
        later = a.loc[a.index > pd.Timestamp(as_of), "Split"]
        factor = float(np.prod(later[later > 0].to_numpy())) if (later > 0).any() else 1.0
        return float(upto.iloc[-1]) * factor

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
        with self._lock:
            return self._history_locked(sym, start, end)

    def _history_locked(self, sym: str, start: date, end: date) -> pd.DataFrame:
        cov = self._covered.get(sym)
        if cov is None or start < cov[0] or end > cov[1]:
            # Download the union of what was asked before and now, so repeated calls
            # (walk-forward backtests) hit the cache even before a listing date. The
            # end is always extended to today: a walk-forward caller asks for a window
            # ending at each successive as-of date, and without this every step would be
            # a new download (found when the cross-sectional analyst fetched 45 peers per
            # decision). clip_history keeps the point-in-time cut at the requested end.
            today = date.today()
            lo, hi = (start, max(end, today)) if cov is None else (min(start, cov[0]), max(end, cov[1], today))
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
        filings: list[NewsItem] = []
        if self.edgar is not None and not instrument.is_fx:
            try:
                filings = self.edgar.news(instrument.symbol, as_of, lookback_days)
            except Exception as e:  # EDGAR outages must not kill the pipeline either
                log.warning("edgar news failed for %s: %s", instrument.symbol, e)
        if (date.today() - as_of).days > self.NEWS_HORIZON_DAYS:
            return filings
        return filings + self._yahoo_news(instrument, as_of, lookback_days)

    def _yahoo_news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
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
        if instrument.is_fx:
            return {}
        if self.edgar is not None:
            try:
                price = self.as_traded_close(instrument, as_of)
                f = self.edgar.fundamentals(instrument.symbol, as_of, price=price,
                                            splits=self.splits(instrument) if price is not None else None)
            except Exception as e:
                log.warning("edgar fundamentals failed for %s: %s", instrument.symbol, e)
                f = {}
            if f:
                return f
        if (date.today() - as_of).days > 7:
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
