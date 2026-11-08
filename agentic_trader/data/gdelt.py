"""GDELT headlines: a free, keyless news archive, behind a config flag (PLAN.md 3.3).

The GDELT DOC 2.0 API (``api.gdeltproject.org/api/v2/doc/doc``, ``mode=artlist``) returns
article titles with the time GDELT first saw them (``seendate``, UTC). That time is the
point-in-time stamp: a headline is visible at ``as_of`` iff it was seen on or before it.

Off by default (``config["gdelt"]["enabled"]``). When on, headlines are de-duplicated (the
same story syndicated to many outlets would otherwise count many times), filtered to one
language (English by default; the lexicon is English) and scored by the rules lexicon in
``sentiment.py``. Headlines are third-party text: callers that put them in a prompt fence
them with ``state.untrusted_block`` as every other news source is.
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import urlencode

from ..sentiment import score_text
from .base import NewsItem

log = logging.getLogger(__name__)

DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def _norm_title(t: str) -> str:
    t = re.sub(r"\s+[-|–—]\s+[^-|–—]{2,40}$", "", t.strip())   # trailing " - Outlet"
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", t.lower())).strip()


def _seen(s: str) -> datetime | None:
    try:
        return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def clean_articles(articles: list[dict[str, Any]], language: str = "English") -> list[dict[str, Any]]:
    """Language filter, then de-duplication on the normalised title (first seen wins)."""
    seen: set[str] = set()
    out = []
    for a in sorted(articles, key=lambda a: a.get("seendate", "")):
        if language and str(a.get("language", "")).lower() != language.lower():
            continue
        key = _norm_title(str(a.get("title", "")))
        if not key or key in seen or _seen(a.get("seendate", "")) is None:
            continue
        seen.add(key)
        out.append(a)
    return out


class GdeltProvider:
    """Headlines for a query, point in time by ``seendate``. ``fetch`` injectable for tests."""

    def __init__(self, fetch: Callable[[str], bytes] | None = None, language: str = "English",
                 max_records: int = 250, min_interval: float = 5.0):
        self._fetch = fetch or self._http
        self.language = language
        self.max_records = max_records
        self.min_interval = min_interval   # GDELT asks for at most one request every 5 seconds
        self._last = 0.0
        self.requests = 0

    @classmethod
    def from_config(cls, config: dict) -> "GdeltProvider | None":
        g = config.get("gdelt") or {}
        if not g.get("enabled", False):
            return None
        return cls(language=g.get("language", "English"), max_records=int(g.get("max_records", 250)))

    @staticmethod
    def _http(url: str) -> bytes:
        from urllib.request import Request, urlopen
        with urlopen(Request(url, headers={"User-Agent": "AgenticTrader research"}), timeout=30) as r:  # noqa: S310
            return r.read()

    def url(self, query: str, start: datetime, end: datetime) -> str:
        return DOC_API + "?" + urlencode({
            "query": query, "mode": "artlist", "format": "json", "maxrecords": self.max_records,
            "startdatetime": start.strftime("%Y%m%d%H%M%S"), "enddatetime": end.strftime("%Y%m%d%H%M%S"),
            "sort": "datedesc"})

    def articles(self, query: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0 and self.requests:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        raw = self._fetch(self.url(query, start, end))
        try:
            data = json.loads(raw or b"{}")
        except json.JSONDecodeError:   # GDELT answers some bad queries with plain text
            log.warning("GDELT returned non-JSON for %r", query)
            return []
        return clean_articles(data.get("articles", []) or [], self.language)

    def news(self, query: str, as_of: datetime, lookback_days: int = 7) -> list[NewsItem]:
        """Scored headlines seen in ``(as_of - lookback_days, as_of]``; nothing after ``as_of``."""
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        out = []
        for a in self.articles(query, as_of - timedelta(days=lookback_days), as_of):
            t = _seen(a["seendate"])
            if t is None or t > as_of:
                continue
            title = str(a["title"])
            out.append(NewsItem(published=t.date(), headline=title, source=f"gdelt:{a.get('domain', '')}",
                                sentiment=score_text(title), tags=["gdelt", "untrusted"]))
        return out


def daily_tone(items: list[NewsItem]) -> dict[date, float]:
    """Mean lexicon score per day: the series a GDELT trial measures."""
    acc: dict[date, list[float]] = {}
    for it in items:
        acc.setdefault(it.published, []).append(it.sentiment if it.sentiment is not None else score_text(it.headline))
    return {d: sum(v) / len(v) for d, v in sorted(acc.items())}
