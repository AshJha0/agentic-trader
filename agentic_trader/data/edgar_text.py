"""EDGAR full text: filing sections, point in time by acceptance timestamp (PLAN.md 3.1).

The structured feeds in ``edgar.py`` carry numbers and item codes; this module reads the
filing documents themselves and cuts out the sections a reader of the text cares about:

* 10-K: Item 1A (risk factors) and Item 7 (MD&A);
* 10-Q: Part II Item 1A (risk factors, labelled "1A") and Part I Item 2 (MD&A, labelled "7"
  so a 10-K and a 10-Q MD&A compare like for like);
* 8-K: Items 2.02 (results), 7.01 (Reg FD) and 8.01 (other events).

Point in time: a section is visible at ``as_of`` iff its filing's SEC acceptance timestamp
(UTC) is ``<= as_of``. A filing with no acceptance time is never visible (the SEC feed always
carries one; guessing a time would be a lookahead risk).

Every section's text is third-party content and is **untrusted**: it can contain anything,
including text written to look like instructions. Two defences apply. At ingest any attempt
to open or close the fence tag is neutralised (``state.untrusted_block`` does the same at
prompt time), and ``fence()`` is the only supported way to put a section into a prompt.

Documents are cached on disk keyed by accession number (a filing never changes once
accepted, so the cache never expires). The SEC asks for a descriptive User-Agent and at most
10 requests per second; the client's rate limiter (0.11 s between calls) enforces the second,
and the default User-Agent is a generic research string, configurable via
``config["edgar_text_user_agent"]`` or ``EDGAR_USER_AGENT``.
"""
from __future__ import annotations

import html
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..state import untrusted_block

log = logging.getLogger(__name__)

DEFAULT_USER_AGENT = "AgenticTrader research contact@example.invalid"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accn}/{doc}"
FORMS = ("10-K", "10-Q", "8-K")
ITEMS_8K = ("2.02", "7.01", "8.01")
_FENCE_RE = re.compile(r"<\s*/?\s*untrusted_data\b[^>]*>?", re.I)


@dataclass(frozen=True)
class FilingSection:
    """One section of one filing. SHARED CONTRACT (the RAG lane builds on it): do not change
    the fields. ``visible_date`` is the UTC acceptance time; ``text`` is untrusted."""
    symbol: str
    accession: str
    form: str
    section: str
    visible_date: datetime
    text: str


def fence(section: FilingSection) -> str:
    """The section ready for a prompt: inside an ``<untrusted_data>`` block, labelled."""
    label = f"EDGAR {section.form} {section.accession} item {section.section}"
    return untrusted_block(label, [section.text])


def neutralise(text: str) -> str:
    return _FENCE_RE.sub("[removed tag]", text)


# ------------------------------------------------------------------ text extraction
_BLOCK_TAGS = re.compile(r"(?i)<\s*(br|/p|/div|/tr|/li|/h\d|/table)\b[^>]*>")


def html_to_text(raw: str) -> str:
    """Plain text from an EDGAR HTML/TXT document: scripts, styles and tags removed,
    entities decoded, whitespace collapsed (paragraph breaks kept)."""
    t = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    t = re.sub(r"(?is)<ix:header\b.*?</ix:header>", " ", t)
    t = _BLOCK_TAGS.sub("\n", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t\r\f\v]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n\n", re.sub(r" *\n *", "\n", t))
    return t.strip()


def _item_re(code: str) -> str:
    return r"(?im)^\s*item\s*" + re.escape(code).replace(r"\.", r"\s*\.\s*") + r"\b\s*[\.:\-—–]?"


# section label -> (start code, end codes) per form
_PERIODIC: dict[str, dict[str, tuple[str, tuple[str, ...]]]] = {
    "10-K": {"1A": ("1A", ("1B", "1C", "2")), "7": ("7", ("7A", "8"))},
    "10-Q": {"7": ("2", ("3", "4")), "1A": ("1A", ("2", "6"))},
}


# A line that starts with "Item 7" is not always a heading: real filings wrap cross-references
# onto a new line ("Item 7 of this Form 10-K under the heading ...", "Item 1A. Risk Factors for a
# more complete discussion of risks.", "Item 1A: Risk Factors in JPMorgan Chase's 2016 Annual
# Report on Form 10-K ..."). Taken as headings they started or ended sections in the wrong place
# (found on the 2015-2021 filings of the core names; tests/test_v15_edgar_real.py).
_CROSS_REF = re.compile(r"(?i)\b(of this|in this|in our|for a|see|refer|referenced|included in|set forth|"
                        r"contained in|annual report|form\s*10-?[kq]|incorporated|discussed)\b")
_MAX_HEADING_LINE = 150
# A periodic-report section shorter than this is a pointer elsewhere ("appears on pages 40-145",
# "see Exhibit 99", "no material changes"), not text whose tone can be compared; omitted.
MIN_PERIODIC_CHARS = 1000


def _is_heading(text: str, m: re.Match) -> bool:
    eol = text.find("\n", m.start() + 1)
    line = text[m.start(): eol if eol != -1 else len(text)].strip()
    return len(line) <= _MAX_HEADING_LINE and not _CROSS_REF.search(line)


# 10-Q "Item 2" is both Part I MD&A and Part II "Unregistered Sales of Equity Securities"; a
# filer whose MD&A carries no Item 2 heading (JPM) otherwise had Part II Item 2 cut as its MD&A.
_NOT_MDNA = re.compile(r"(?i)unregistered\s+sales")


def _cut(text: str, start: str, ends: tuple[str, ...], exclude: re.Pattern | None = None) -> str:
    """The longest span from an ``Item <start>`` heading to the next end heading. The longest
    is taken so the table of contents (heading followed at once by the next heading) loses.
    Lines that are cross-references, not headings, neither start nor end a span."""
    best = ""
    end_re = re.compile("|".join(_item_re(e)[len("(?im)"):] for e in ends) + r"|^\s*signatures?\s*$",
                        re.I | re.M)
    for m in re.finditer(_item_re(start), text):
        if not _is_heading(text, m):
            continue
        if exclude is not None and exclude.search(text, m.end(), m.end() + 120):
            continue
        pos, e = m.end(), None
        while True:
            e = end_re.search(text, pos)
            if e is None or _is_heading(text, e):
                break
            pos = e.end()
        span = text[m.end(): e.start() if e else len(text)].strip()
        if len(span) > len(best):
            best = span
    return best


def extract_sections(text: str, form: str) -> dict[str, str]:
    """``{section label: text}`` for the sections this module keeps; empty sections omitted."""
    out: dict[str, str] = {}
    base = form.split("/")[0]
    if base in _PERIODIC:
        for label, (start, ends) in _PERIODIC[base].items():
            s = _cut(text, start, ends, _NOT_MDNA if (base, label) == ("10-Q", "7") else None)
            if len(s) >= MIN_PERIODIC_CHARS:
                out[label] = s
    elif base == "8-K":
        for code in ITEMS_8K:
            s = _cut(text, code, tuple(c for c in ("1.01", "2.01", "2.02", "2.03", "3.01", "5.02", "5.07",
                                                   "7.01", "8.01", "9.01") if c != code))
            if s:
                out[code] = s
    return out


def chunk_text(text: str, max_chars: int = 4000, overlap: int = 200) -> list[str]:
    """Split ``text`` into chunks of at most ``max_chars``, on paragraph boundaries where
    possible, consecutive chunks sharing ``overlap`` characters of context."""
    if max_chars <= overlap:
        raise ValueError("max_chars must exceed overlap")
    if len(text) <= max_chars:
        return [text] if text else []
    chunks: list[str] = []
    i = 0
    while i < len(text):
        j = min(i + max_chars, len(text))
        if j < len(text):
            k = text.rfind("\n\n", i + max_chars // 2, j)
            if k == -1:
                k = text.rfind(" ", i + max_chars // 2, j)
            j = k if k > i else j
        chunks.append(text[i:j].strip())
        if j >= len(text):
            break
        i = max(j - overlap, i + 1)
    return [c for c in chunks if c]


# ------------------------------------------------------------------ provider
def _http_fetch(url: str, user_agent: str, timeout: float = 30.0) -> bytes:
    from urllib.request import Request, urlopen
    req = Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    with urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https hosts
        return r.read()


def _parse_accepted(s: Any) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None
    # The submissions feed's acceptanceDateTime is UTC (see edgar.visible_dates).
    return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)


class EdgarProvider:
    """Filing sections for a ticker, point in time. ``fetch(url) -> bytes`` is injectable so
    tests run offline from fixtures."""

    def __init__(self, user_agent: str | None = None, cache_dir: str | os.PathLike | None = None,
                 fetch: Callable[[str], bytes] | None = None, min_interval: float = 0.11,
                 forms: tuple[str, ...] = FORMS, ciks: dict[str, str] | None = None):
        self.user_agent = user_agent or os.environ.get("EDGAR_USER_AGENT") or DEFAULT_USER_AGENT
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._fetch = fetch or (lambda u: _http_fetch(u, self.user_agent))
        self.min_interval = min_interval
        self.forms = forms
        self.ciks = {k.upper(): f"{int(v):010d}" for k, v in (ciks or {}).items()}
        self._lock = threading.Lock()
        self._last = 0.0
        self._mem: dict[str, Any] = {}
        self.requests = 0

    @classmethod
    def from_config(cls, config: dict) -> "EdgarProvider | None":
        if not config.get("edgar_text", False):
            return None
        return cls(user_agent=config.get("edgar_text_user_agent"),
                   cache_dir=config.get("edgar_text_cache_dir", "results/edgar_text_cache"),
                   ciks=config.get("edgar_ciks"))

    # transport -----------------------------------------------------------------
    def _get(self, url: str) -> bytes:
        with self._lock:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
        return self._fetch(url)

    def _json(self, url: str) -> Any:
        if url not in self._mem:
            self._mem[url] = json.loads(self._get(url))
        return self._mem[url]

    def cik(self, symbol: str) -> str | None:
        s = symbol.upper()
        if s in self.ciks:
            return self.ciks[s]
        table = self._json(TICKERS_URL)
        rows = table.values() if isinstance(table, dict) else table
        for r in rows:
            if str(r["ticker"]).upper() in (s, s.replace("-", "."), s.replace(".", "-")):
                return f"{int(r['cik_str']):010d}"
        return None

    def company_names(self, symbol: str) -> list[str]:
        """``entityName`` and every ``formerNames[].name`` from the submissions JSON (the same
        document ``filing_index`` reads, so cached), for the anonymiser's name map."""
        cik = self.cik(symbol)
        if cik is None:
            return []
        sub = self._json(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"))
        names = [sub.get("name") or sub.get("entityName")]
        names += [f.get("name") for f in sub.get("formerNames") or [] if isinstance(f, dict)]
        return [n for n in names if isinstance(n, str) and n.strip()]

    def filing_index(self, symbol: str) -> list[dict[str, Any]]:
        """Filings of the kept forms: accession, form, primary document, accepted (UTC)."""
        key = f"index:{symbol.upper()}"
        if key in self._mem:
            return self._mem[key]
        cik = self.cik(symbol)
        rows: list[dict[str, Any]] = []
        if cik is not None:
            sub = self._json(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"))
            pages = [sub.get("filings", {}).get("recent", {})]
            pages += [self._json(SUBMISSIONS_URL.format(name=f["name"]))
                      for f in sub.get("filings", {}).get("files", [])]
            for p in pages:
                n = len(p.get("form", []))
                for i in range(n):
                    form = p["form"][i]
                    if form not in self.forms:
                        continue
                    items = (p.get("items") or [""] * n)[i] or ""
                    if form == "8-K" and not any(c in items.split(",") for c in ITEMS_8K):
                        continue
                    rows.append({"cik": cik, "accession": p["accessionNumber"][i], "form": form,
                                 "doc": (p.get("primaryDocument") or [""] * n)[i],
                                 "accepted": _parse_accepted((p.get("acceptanceDateTime") or [None] * n)[i])})
        rows.sort(key=lambda r: (r["accepted"] is None, r["accepted"] or datetime.min.replace(tzinfo=timezone.utc)))
        self._mem[key] = rows
        return rows

    def document(self, row: dict[str, Any]) -> str:
        """The plain text of a filing, from the disk cache (keyed by accession) or EDGAR."""
        path = self.cache_dir / f"{row['accession']}.txt" if self.cache_dir else None
        if path is not None and path.exists():
            return path.read_text(encoding="utf-8")
        url = DOC_URL.format(cik=int(row["cik"]), accn=row["accession"].replace("-", ""), doc=row["doc"])
        text = html_to_text(self._get(url).decode("utf-8", errors="replace"))
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        return text

    def filing_sections(self, symbol: str, row: dict[str, Any]) -> list[FilingSection]:
        key = f"sec:{row['accession']}"
        if key not in self._mem:
            try:
                secs = extract_sections(self.document(row), row["form"])
            except Exception as e:  # one unreadable document loses its sections, not the ticker
                log.warning("EDGAR document %s unreadable: %s", row["accession"], e)
                secs = {}
            self._mem[key] = [FilingSection(symbol.upper(), row["accession"], row["form"], label,
                                            row["accepted"], neutralise(t)) for label, t in secs.items()]
        return self._mem[key]

    def sections(self, symbol: str, as_of: datetime) -> list[FilingSection]:
        """Every kept section of ``symbol`` accepted at or before ``as_of`` (a naive datetime
        is read as UTC), oldest first. Documents after ``as_of`` are never fetched."""
        if as_of.tzinfo is None:
            as_of = as_of.replace(tzinfo=timezone.utc)
        out: list[FilingSection] = []
        for row in self.filing_index(symbol):
            if row["accepted"] is None or row["accepted"] > as_of:
                continue
            out.extend(s for s in self.filing_sections(symbol, row) if s.visible_date <= as_of)
        return out
