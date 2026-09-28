"""SEC EDGAR: free, keyless, *point-in-time* fundamentals and corporate-event news.

Three public JSON endpoints (the SEC asks for a descriptive ``User-Agent`` with a
contact and at most 10 requests per second; both are enforced here):

* ``www.sec.gov/files/company_tickers.json``            ticker -> CIK
* ``data.sec.gov/submissions/CIK##########.json``        every filing, with its filing date
* ``data.sec.gov/api/xbrl/companyfacts/CIK##########.json``  every XBRL fact, with the
  date of the filing that reported it

The point-in-time rule is the same everywhere: a filing or a fact exists at
``as_of`` iff its ``filed`` date is ``<= as_of``. Where a span was printed more than
once by then (a comparative in a later filing, a restatement), the value used is the
one *known at as_of*: the latest print filed on or before ``as_of`` within one
reporting basis. A material change to a span must be corroborated (a filing that recasts
its comparatives opens a new basis, see ``quarterly_table``); an uncorroborated material
re-print is ignored. For the newest quarter that is its first print, so no later
information enters; for an older quarter it is what the market held at the time,
restated comparatives included.

Fundamentals are derived from the raw facts rather than taken from a vendor
snapshot: quarterly flows are reconstructed from the reported spans (10-Q values
are year-to-date for cash-flow items, and Q4 is only ever reported inside the
10-K), summed to trailing-twelve-month figures and combined with the price the
caller passes in. Reconstruction never mixes concepts (a filer that reports gross
revenue under one tag and net revenue under another gets one concept per trailing
window; a renamed tag is recognised by an identical span printed under both names)
nor reporting bases (see ``quarterly_table``). Consensus data (EPS surprise)
is not available from EDGAR and is reported as ``None`` rather than guessed.

News is the filing stream itself: 8-K item codes map to short headlines with a
conservative tone score, periodic reports and ownership filings are announced as
events, and insider (Form 4) filings are counted. Social media has no free
point-in-time archive, so that analyst still abstains on real data.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from .base import NewsItem

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/{name}"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
USER_AGENT_ENV = "EDGAR_USER_AGENT"


def edgar_user_agent(config: dict | None = None) -> str | None:
    """The contact string the SEC requires (``"Name email@domain"``), or None.

    Read from ``config["edgar_user_agent"]``, then the ``EDGAR_USER_AGENT``
    environment variable (``.env`` is loaded by the CLI). The SEC's fair-access
    policy rejects requests whose User-Agent names no e-mail contact, so a value
    without an ``@`` is treated as absent and EDGAR is skipped with a warning
    rather than hammering the endpoint with requests that will be refused.
    """
    ua = (config or {}).get("edgar_user_agent") or os.environ.get(USER_AGENT_ENV)
    return ua if ua and "@" in ua else None

# 8-K items (17 CFR 249.308) -> (headline, tone in [-1, 1]). Tone is deliberately
# mild: the filing says *that* something happened, rarely whether it was good.
ITEM_8K: dict[str, tuple[str, float]] = {
    "1.01": ("Entry into a material definitive agreement", 0.10),
    "1.02": ("Termination of a material definitive agreement", -0.20),
    "1.03": ("Bankruptcy or receivership", -1.00),
    "1.04": ("Mine safety - reporting of shutdowns", -0.20),
    "1.05": ("Material cybersecurity incident", -0.40),
    "2.01": ("Completion of acquisition or disposition of assets", 0.10),
    "2.02": ("Results of operations and financial condition (earnings release)", 0.00),
    "2.03": ("Creation of a direct financial obligation", -0.05),
    "2.04": ("Triggering events that accelerate a financial obligation", -0.50),
    "2.05": ("Costs associated with exit or disposal activities (restructuring)", -0.20),
    "2.06": ("Material impairments", -0.40),
    "3.01": ("Notice of delisting or failure to satisfy a listing rule", -0.50),
    "3.02": ("Unregistered sales of equity securities", -0.10),
    "3.03": ("Material modification to rights of security holders", -0.10),
    "4.01": ("Changes in registrant's certifying accountant", -0.20),
    "4.02": ("Non-reliance on previously issued financial statements (restatement)", -0.60),
    "5.01": ("Changes in control of registrant", 0.00),
    "5.02": ("Departure or appointment of directors or officers", -0.05),
    "5.03": ("Amendments to articles of incorporation or bylaws; change in fiscal year", 0.00),
    "5.04": ("Temporary suspension of trading under employee benefit plans", 0.00),
    "5.05": ("Amendments to code of ethics", 0.00),
    "5.06": ("Change in shell company status", 0.00),
    "5.07": ("Submission of matters to a vote of security holders", 0.00),
    "5.08": ("Shareholder director nominations", 0.00),
    "6.01": ("ABS informational and computational material", 0.00),
    "7.01": ("Regulation FD disclosure", 0.00),
    "8.01": ("Other events", 0.00),
    "9.01": ("Financial statements and exhibits", 0.00),
}
_EXHIBIT_ONLY = {"9.01"}

OTHER_FORMS: dict[str, tuple[str, float]] = {
    "10-K": ("Annual report (10-K) filed", 0.0),
    "10-Q": ("Quarterly report (10-Q) filed", 0.0),
    "10-K/A": ("Annual report amended (10-K/A)", -0.1),
    "10-Q/A": ("Quarterly report amended (10-Q/A)", -0.1),
    "SC 13D": ("Activist / >5% beneficial ownership disclosed (13D)", 0.2),
    "SC 13D/A": ("Beneficial ownership (13D) amended", 0.05),
    "SC 13G": ("Passive >5% beneficial ownership disclosed (13G)", 0.1),
    "DEF 14A": ("Proxy statement filed", 0.0),
    # 424B* prospectus supplements and S-3/S-8 registrations are deliberately absent: banks
    # file thousands of structured-note supplements a quarter, and none of it is news.
    "NT 10-K": ("Late filing notice for the annual report", -0.4),
    "NT 10-Q": ("Late filing notice for the quarterly report", -0.4),
}
INSIDER_FORMS = ("4", "4/A")

REVENUE_TAGS = ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueGoodsNet",
                "RevenuesNetOfInterestExpense")   # banks and brokers
NET_INCOME_TAGS = ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic")
EPS_TAGS = ("EarningsPerShareDiluted", "EarningsPerShareBasic",
            "IncomeLossFromContinuingOperationsPerDilutedShare", "IncomeLossFromContinuingOperationsPerBasicShare")
OCF_TAGS = ("NetCashProvidedByUsedInOperatingActivities",
            "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations")
CAPEX_TAGS = ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets")
EQUITY_TAGS = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
DEBT_TAGS = ("LongTermDebt", "LongTermDebtNoncurrent", "DebtInstrumentCarryingAmount", "LongTermDebtAndCapitalLeaseObligations")
SHARES_TAGS = ("dei:EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding",
               "CommonStockSharesOutstanding")

# Tickers whose current SEC filer is a new holding company; history is under the predecessor.
PREDECESSOR_CIKS: dict[str, str] = {"XOM": "0000034088"}   # Exxon Mobil Corp -> ExxonMobil Holdings (2026)

# Multi-class filers whose non-dimensional per-share facts (companyfacts drops the
# per-class dimension) are stated per share of a *different* class than the ticker:
# ticker -> shares of the ticker's class per share of the reported class. Berkshire's
# EPS and share count are per Class A share; one A share equals 1,500 B shares.
SHARE_CLASS_RATIO: dict[str, float] = {"BRK-B": 1500.0}

# Days in a quarter: 13 weeks normally, 12 weeks for 52/53-week fiscal calendars (Costco,
# PepsiCo) whose fourth quarter then has 16 weeks (112 days).
_QUARTER = (75, 120)
# Filers that are funds or trusts, not operating companies: their XBRL facts are not
# fundamentals in the analyst's sense, so they return nothing rather than nonsense.
NON_OPERATING_SIC = {"6221"}   # commodity contracts brokers & dealers (GLD, SLV, USO, DBC)
_YEAR = (350, 380)
# Four consecutive quarters span this many days from the first end to the last.
_TTM_SPAN = (240, 300)
# Recency guards: a balance-sheet instant older than this (relative to the report period) is
# not the company's current balance sheet; a flow series that no filing of the last
# MAX_FLOW_LAG_DAYS (one skipped periodic report) printed any span of has stopped being
# reported (a dead per-class series, a retired tag). A live series whose latest complete
# window lags the report period is kept and the lag reported (``revenue_period_end``).
MAX_INSTANT_AGE_DAYS = 400
MAX_FLOW_LAG_DAYS = _QUARTER[1]
# A re-print of a span differing from the value held by more than BASIS_CHANGE_TOLERANCE is
# a material change; within that it is a revision and the later print wins. A material
# change must be corroborated: a filing that recasts at least BASIS_CHANGE_MIN_SPANS spans
# of one concept, or the year-earlier comparative of a span it prints for the first time,
# has moved its comparatives onto a new reporting basis (discontinued operations, a
# restatement) and opens a new generation, provided its quarters reconcile with its own
# annual span (ANNUAL_CHECK_TOLERANCE). A lone material re-print, or a recast whose quarters
# do not add up to its annual figure (mis-tagged comparatives), is ignored; a later filing
# repeating an ignored value within the tolerance confirms it as a correction, taken in
# place. See ``_tag_quarters``.
BASIS_CHANGE_TOLERANCE = 0.05
BASIS_CHANGE_MIN_SPANS = 2
# Two tags are one concept for a filer (a rename) when every span they both print agrees
# within this fraction; gross and net revenue tags differ by far more on every shared span.
TAG_EQUIVALENCE_TOLERANCE = 0.01
# The four quarters of a fiscal year must agree with its annual span within this fraction of
# the year's scale (the annual figure or the quarters' total magnitude, whichever is larger:
# a year netting to nearly nothing is judged on the size of its quarters, not on a rounding
# unit); otherwise the audited annual figure less the three quarters is Q4. Only additive
# flows are checked: quarterly per-share figures do not sum to the annual one
# (weighted-average shares and anti-dilution differ by period), so a per-share recast is
# judged mis-tagged only when its quarters miss its annual figure by more than
# PER_SHARE_CHECK_TOLERANCE of that scale, and a direct per-share Q4 print is never overridden.
ANNUAL_CHECK_TOLERANCE = 0.02
PER_SHARE_CHECK_TOLERANCE = 0.15


def _http_fetch(url: str, user_agent: str, timeout: float = 30.0) -> bytes:
    req = Request(url, headers={"User-Agent": user_agent})
    with urlopen(req, timeout=timeout) as r:  # noqa: S310 - fixed https hosts
        return r.read()


class EdgarClient:
    """Cached EDGAR reader. ``fetch(url) -> bytes`` can be injected for tests."""

    def __init__(self, user_agent: str | None = None, cache_dir: str | os.PathLike | None = None,
                 fetch: Callable[[str], bytes] | None = None, min_interval: float = 0.11,
                 ciks: dict[str, str] | None = None, cache_max_age_days: float | None = 7.0):
        self.user_agent = user_agent or edgar_user_agent()
        # A cached endpoint file older than this is re-fetched: the ticker table, the filing
        # index and the company facts all change daily, so a reused cache directory would
        # otherwise hide every filing made after it was written from a live decision.
        # None keeps files forever (a frozen historical backtest).
        self.cache_max_age_days = cache_max_age_days
        # Ticker -> CIK overrides. The SEC's ticker table points at the *current* filer;
        # after a holding-company reorganisation the historical filings and facts live
        # under the predecessor's CIK, which is what a backtest needs.
        self.ciks = {k.upper(): v for k, v in {**PREDECESSOR_CIKS, **(ciks or {})}.items()}
        if self.user_agent is None and fetch is None:
            raise ValueError(f"EDGAR needs a contact User-Agent: set {USER_AGENT_ENV}=\"Name email@domain\" "
                             "(in .env or the environment) or config['edgar_user_agent']")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._fetch = fetch
        self.min_interval = min_interval
        self._last_call = 0.0
        self._lock = threading.Lock()
        self._mem: dict[str, Any] = {}
        self._tickers: dict[str, str] | None = None
        self._warned: set[str] = set()
        self.requests = 0

    @classmethod
    def from_config(cls, config: dict) -> "EdgarClient | None":
        """A client when EDGAR is enabled and a contact is configured; else None (with one warning)."""
        if not config.get("edgar", True):
            return None
        ua = edgar_user_agent(config)
        if ua is None:
            log.warning("EDGAR fundamentals/news disabled: set %s=\"Name email@domain\" (the SEC requires "
                        "a contact) or config['edgar_user_agent']", USER_AGENT_ENV)
            return None
        return cls(user_agent=ua, cache_dir=config.get("edgar_cache_dir"), ciks=config.get("edgar_ciks"),
                   cache_max_age_days=config.get("edgar_cache_max_age_days", 7.0))

    # ------------------------------------------------------------ transport
    def _get_json(self, url: str) -> Any:
        # submissions and companyfacts both end in CIK##########.json: key on the whole path
        key = url.split("//", 1)[-1].replace("/", "_")
        with self._lock:
            if key in self._mem:
                return self._mem[key]
            path = self.cache_dir / key if self.cache_dir else None
            fresh = (path is not None and path.exists()
                     and (self.cache_max_age_days is None
                          or time.time() - path.stat().st_mtime <= self.cache_max_age_days * 86400.0))
            if fresh:
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                wait = self.min_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    time.sleep(wait)
                self._last_call = time.monotonic()
                self.requests += 1
                missing = False
                try:
                    raw = (self._fetch or (lambda u: _http_fetch(u, self.user_agent)))(url)
                except HTTPError as e:
                    if e.code != 404:   # an index fund has no company facts: that is "no data"
                        raise
                    raw, missing = b"{}", True
                data = json.loads(raw)
                if path is not None and not missing:   # a 404 is remembered for this process only
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(data), encoding="utf-8")
            self._mem[key] = data
            return data

    # ------------------------------------------------------------- lookups
    def cik(self, ticker: str) -> str | None:
        if self._tickers is None:
            table = self._get_json(TICKERS_URL)
            rows = table.values() if isinstance(table, dict) else table
            self._tickers = {str(r["ticker"]).upper(): f"{int(r['cik_str']):010d}" for r in rows}
        t = ticker.upper()
        override = self.ciks.get(t)
        if override:
            return f"{int(override):010d}"
        for cand in (t, t.replace("-", "."), t.replace(".", "-")):  # BRK-B is listed as BRK-B; others as X.Y
            if cand in self._tickers:
                return self._tickers[cand]
        return None

    def profile(self, ticker: str) -> dict[str, Any]:
        """Name, SIC code and description of the filer (empty when unknown)."""
        cik = self.cik(ticker)
        if cik is None:
            return {}
        sub = self._get_json(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"))
        return {"name": sub.get("name"), "sic": str(sub.get("sic") or ""), "sic_description": sub.get("sicDescription"),
                "fiscal_year_end": sub.get("fiscalYearEnd")} if sub else {}

    def filings(self, ticker: str) -> pd.DataFrame:
        """All filings for ``ticker``: form, filed, report, items, accession (sorted by filed)."""
        cik = self.cik(ticker)
        if cik is None:
            return pd.DataFrame(columns=["form", "filed", "report", "items", "accession"])
        key = f"filings:{cik}"
        if key not in self._mem:
            sub = self._get_json(SUBMISSIONS_URL.format(name=f"CIK{cik}.json"))
            if not sub:
                self._mem[key] = pd.DataFrame(columns=["form", "filed", "report", "items", "accession"])
                return self._mem[key]
            pages = [sub["filings"]["recent"]]
            for extra in sub["filings"].get("files", []):  # older filings: flat pages of the same arrays
                pages.append(self._get_json(SUBMISSIONS_URL.format(name=extra["name"])))
            frames = []
            for p in pages:
                p = p.get("filings", {}).get("recent", p) if "form" not in p else p
                if not p or "form" not in p:   # a missing or malformed page loses its filings, not the ticker
                    log.warning("EDGAR submissions page for %s is missing or malformed; skipped", ticker)
                    continue
                n = len(p["form"])
                frames.append(pd.DataFrame({
                    "form": p["form"], "filed": pd.to_datetime(p["filingDate"]),
                    "report": pd.to_datetime(p.get("reportDate", [""] * n), errors="coerce"),
                    "items": p.get("items", [""] * n), "accession": p["accessionNumber"]}))
            if not frames:
                self._mem[key] = pd.DataFrame(columns=["form", "filed", "report", "items", "accession"])
                return self._mem[key]
            df = pd.concat(frames, ignore_index=True).sort_values("filed", kind="stable").reset_index(drop=True)
            self._mem[key] = df
        return self._mem[key]

    def facts(self, ticker: str) -> pd.DataFrame:
        """Every XBRL fact as a long frame: tag, unit, start, end, val, filed, form, fy, fp."""
        cik = self.cik(ticker)
        if cik is None:
            return pd.DataFrame(columns=["tag", "unit", "start", "end", "val", "filed", "form", "fy", "fp"])
        key = f"facts:{cik}"
        if key not in self._mem:
            raw = self._get_json(FACTS_URL.format(cik=cik)) or {}
            rows = []
            for taxonomy, tags in raw.get("facts", {}).items():
                for tag, body in tags.items():
                    name = tag if taxonomy == "us-gaap" else f"{taxonomy}:{tag}"
                    for unit, entries in body.get("units", {}).items():
                        for e in entries:
                            rows.append((name, unit, e.get("start"), e["end"], e["val"], e["filed"],
                                         e.get("form", ""), e.get("fy"), e.get("fp", "")))
            df = pd.DataFrame(rows, columns=["tag", "unit", "start", "end", "val", "filed", "form", "fy", "fp"])
            for c in ("start", "end", "filed"):
                df[c] = pd.to_datetime(df[c], errors="coerce")
            df["val"] = pd.to_numeric(df["val"], errors="coerce")
            self._mem[key] = df.dropna(subset=["end", "filed", "val"]).reset_index(drop=True)
        return self._mem[key]

    # ---------------------------------------------------------------- news
    def news(self, ticker: str, as_of: date, lookback_days: int) -> list[NewsItem]:
        df = self.filings(ticker)
        if df.empty:
            return []
        lo, hi = pd.Timestamp(as_of - timedelta(days=lookback_days)), pd.Timestamp(as_of)
        win = df[(df["filed"] > lo) & (df["filed"] <= hi)]
        out: list[NewsItem] = []
        insiders: dict[date, int] = {}
        for r in win.itertuples(index=False):
            d = r.filed.date()
            if r.form == "8-K" or r.form == "8-K/A":
                codes = [c.strip() for c in str(r.items or "").split(",") if c.strip()]
                codes = [c for c in codes if c not in _EXHIBIT_ONLY] or codes
                for c in codes:
                    text, tone = ITEM_8K.get(c, (f"8-K item {c}", 0.0))
                    out.append(NewsItem(d, f"8-K: {text}", source="SEC EDGAR", sentiment=tone,
                                        tags=["8-K", c, r.accession]))
            elif r.form in INSIDER_FORMS:
                insiders[d] = insiders.get(d, 0) + 1
            elif r.form in OTHER_FORMS:
                text, tone = OTHER_FORMS[r.form]
                out.append(NewsItem(d, text, source="SEC EDGAR", sentiment=tone, tags=[r.form, r.accession]))
        for d, n in sorted(insiders.items()):
            out.append(NewsItem(d, f"{n} insider transaction filing{'s' if n > 1 else ''} (Form 4)",
                                source="SEC EDGAR", sentiment=0.0, tags=["4"]))
        out.sort(key=lambda i: i.published, reverse=True)
        return out

    # -------------------------------------------------------- fundamentals
    def fundamentals(self, ticker: str, as_of: date, price: float | None = None,
                     splits: dict[date, float] | None = None) -> dict[str, Any]:
        """Fundamentals known at ``as_of`` (facts filed on or before it; a span's value is its
        latest print within one reporting basis, see ``quarterly_table``).

        ``price`` must be the close *as traded* on ``as_of`` (not a split-adjusted history),
        and ``splits`` maps split ex-dates to their ratios (4.0 for a 4-for-1). Per-share
        prints are in the share units of the filing that reported them, so every EPS and
        share-count fact is brought to the ``as_of`` basis before quarters are mixed: an EPS
        printed before a split is divided by the ratio, a share count multiplied. With
        ``splits`` omitted nothing is rescaled, which is only right for a company that has
        never split.

        Per-share ratios are dropped when the inputs cannot describe the ticker's share:
        a share count or EPS window that has stopped updating (recency guards in
        ``_fundamentals_core``), a market capitalisation below 1% of trailing revenue, or
        trailing EPS above half the price (a per-share fact of another share class);
        ``SHARE_CLASS_RATIO`` converts the known multi-class filers first.

        The price-independent part only changes when a new filing arrives (or a split
        passes), so it is memoised per (ticker, last filing date on or before ``as_of``,
        splits so far): a walk-forward backtest pays for the reconstruction once per filing.
        """
        df = self.facts(ticker)
        if df.empty or self.profile(ticker).get("sic") in NON_OPERATING_SIC:
            return {}
        cutoff = df.loc[df["filed"] <= pd.Timestamp(as_of), "filed"].max()
        if pd.isna(cutoff):
            return {}
        past_splits = sorted((pd.Timestamp(d), float(r)) for d, r in (splits or {}).items()
                             if pd.Timestamp(d) <= pd.Timestamp(as_of) and r and r > 0)
        key = f"fund:{ticker.upper()}:{cutoff.date().isoformat()}:{len(past_splits)}"
        core = self._mem.get(key)
        if core is None:
            core = self._fundamentals_core(df[df["filed"] <= cutoff], past_splits)
            self._mem[key] = core
        if not core:
            return {}
        out = dict(core)
        out["lag_days"] = int((pd.Timestamp(as_of) - pd.Timestamp(out["filed"])).days) if out.get("filed") else None
        eps_ttm, shares, fcf = out.pop("_eps_ttm", None), out.pop("_shares", None), out.pop("_fcf_ttm", None)
        for note in out.pop("_notes", ()):
            kind, tag = note[0], note[1]
            if kind == "annual":
                _, _, end, quarters, annual = note
                self._warn_once(ticker, f"annual-mismatch:{tag}:{end}",
                                f"{tag} quarters of the year ending {end} sum to {quarters:.4g} against an annual span "
                                f"of {annual:.4g}: Q4 taken as the annual figure less the three quarters")
            elif kind == "ignored":
                _, _, start, end, held, printed, filed = note
                self._warn_once(ticker, f"ignored-reprint:{tag}:{start}:{end}:{filed}",
                                f"{tag} {start}..{end} re-printed as {printed:.4g} on {filed} against {held:.4g} held: "
                                "a material change no other span corroborates; ignored")
            elif kind == "confirmed":
                _, _, start, end, held, printed, filed = note
                self._warn_once(ticker, f"confirmed-reprint:{tag}:{start}:{end}:{filed}",
                                f"{tag} {start}..{end} re-printed as {printed:.4g} on {filed}, repeating a print ignored "
                                f"earlier: a correction confirmed by repetition; taken in place of {held:.4g}")
            else:
                _, _, filed, end, quarters, annual = note
                self._warn_once(ticker, f"rejected-recast:{tag}:{filed}",
                                f"{tag} comparatives recast on {filed} do not reconcile: its quarters of the year ending "
                                f"{end} sum to {quarters:.4g} against its own annual span of {annual:.4g}: mis-tagged; ignored")
        ratio = SHARE_CLASS_RATIO.get(ticker.upper().replace(".", "-"))
        if ratio:
            eps_ttm = None if eps_ttm is None else eps_ttm / ratio
            shares = None if shares is None else shares * ratio
        rev_ttm = out.get("revenue_ttm")
        if price and shares and rev_ttm and price * shares < 0.01 * rev_ttm:
            self._warn_once(ticker, "market-cap", f"market cap {price * shares:.3g} below 1% of trailing revenue "
                            f"{rev_ttm:.3g}: the share count is not this ticker's class; per-share ratios dropped")
            shares = None
        if price and eps_ttm is not None and eps_ttm > 0.5 * price:
            self._warn_once(ticker, "eps-class", f"trailing EPS {eps_ttm:.4g} above half the price {price:.4g}: "
                            "the EPS facts are not per share of this ticker's class; P/E dropped")
            eps_ttm = None
        if eps_ttm is not None:
            out["eps_ttm"] = round(eps_ttm, 4)
            if price:
                out["pe_ratio"] = round(price / eps_ttm, 2) if eps_ttm > 0 else -1.0
        if fcf is not None and price and shares:
            out["fcf_yield"] = round(fcf / (price * shares), 4)
        return out

    def _warn_once(self, ticker: str, kind: str, msg: str) -> None:
        key = f"{ticker.upper()}:{kind}"
        if key not in self._warned:
            self._warned.add(key)
            log.warning("EDGAR %s: %s", ticker.upper(), msg)

    def _fundamentals_core(self, known: pd.DataFrame, past_splits: list[tuple[pd.Timestamp, float]] = ()) -> dict[str, Any]:
        """The price-independent fundamentals from the facts known at a cutoff, per-share
        facts rescaled to the share basis after ``past_splits``."""
        if known.empty:
            return {}
        if past_splits:
            known = rebase_per_share(known, past_splits)
        notes: list[tuple] = []
        rev_t = quarterly_table(known, REVENUE_TAGS, positive=True, notes=notes)
        ni_t = quarterly_table(known, NET_INCOME_TAGS, notes=notes)
        eps = quarterly_series(known, EPS_TAGS, units=("USD/shares",), notes=notes)
        ocf = quarterly_series(known, OCF_TAGS, notes=notes)
        capex = quarterly_series(known, CAPEX_TAGS, notes=notes)
        capex_reported = bool(known["tag"].isin(CAPEX_TAGS).any())
        rev, ni = rev_t["val"], ni_t["val"]
        if rev.empty and ni.empty:   # no income statement at all: not an operating company
            return {}
        ends = [s.index.max() for s in (rev, ni, eps) if not s.empty]
        period_end = max(ends)
        not_before = period_end - pd.Timedelta(days=MAX_INSTANT_AGE_DAYS)
        equity = latest_instant(known, EQUITY_TAGS, not_before=not_before)
        debt = latest_instant(known, DEBT_TAGS, not_before=not_before)
        shares = latest_instant(known, SHARES_TAGS, units=("shares",), not_before=not_before)
        latest_filed = known.loc[known["end"] == period_end, "filed"].min()
        out: dict[str, Any] = {
            "report_period_end": period_end.date().isoformat(),
            "filed": latest_filed.date().isoformat() if pd.notna(latest_filed) else None,
            "sector_pe": None, "eps_surprise": None, "insider_net_buying": None,
            "source": "sec_edgar (point-in-time, as known at as_of)",
        }

        newest_filing = known["filed"].max()

        def fresh(s: pd.Series, tags: tuple[str, ...], units: tuple[str, ...] | None = None) -> pd.Series:
            """A flow series some filing of the last ``MAX_FLOW_LAG_DAYS`` printed a span of;
            one no recent filing prints is dead (a per-class series, a retired tag): empty."""
            if s.empty:
                return s
            printed = _pick(known, tags, units).dropna(subset=["start"])["filed"].max()
            return s if (newest_filing - printed).days <= MAX_FLOW_LAG_DAYS else pd.Series(dtype=float)

        rev, ni, eps, ocf, capex = (fresh(s, t, u) for s, t, u in (
            (rev, REVENUE_TAGS, None), (ni, NET_INCOME_TAGS, None), (eps, EPS_TAGS, ("USD/shares",)),
            (ocf, OCF_TAGS, None), (capex, CAPEX_TAGS, None)))
        rev_ttm, rev_prev = ttm(rev), ttm(rev, back=4)
        ni_ttm = ttm(ni)
        eps_ttm = ttm(eps)
        # A live series' latest complete window can end behind the report period (a basis or
        # tag change not yet covering the newest quarters): say so rather than pass it off as
        # the period's figure, and never divide it into a figure from another window.
        ocf_ttm, capex_ttm = ttm(ocf), ttm(capex)
        for name, s, total in (("revenue", rev, rev_ttm), ("net_income", ni, ni_ttm), ("eps", eps, eps_ttm),
                               ("ocf", ocf, ocf_ttm)):
            if total is not None and s.index.max() != period_end:
                out[f"{name}_period_end"] = s.index.max().date().isoformat()
        if rev_ttm is not None:
            out["revenue_ttm"] = rev_ttm
        # Year over year only when the two four-quarter windows are exactly a year apart (a
        # missing quarter would otherwise compare across a 15-month gap) and are the same
        # concept on one reporting basis: another tag is another concept (gross vs net
        # revenue), and the same tag in another basis generation is a recast, not growth.
        if rev_ttm and rev_prev and len(rev) >= 8 and _YEAR[0] <= (rev.index[-1] - rev.index[-5]).days <= _YEAR[1]:
            cur, prev = rev_t.iloc[-1], rev_t.iloc[-5]
            if cur["tag"] == prev["tag"] and cur["gen"] == prev["gen"]:
                out["revenue_growth_yoy"] = round(rev_ttm / rev_prev - 1.0, 4)
        if rev_ttm and ni_ttm is not None and rev.index.max() == ni.index.max():
            out["net_margin"] = round(ni_ttm / rev_ttm, 4)
        if eps_ttm is not None:
            out["_eps_ttm"] = eps_ttm
        if debt is not None and equity:
            out["debt_to_equity"] = round(debt / equity, 3)
        # A filer that reports capital expenditure but has no four-quarter window of it ending
        # with the operating cash flow window (a dead or renamed tag, a recast of one series)
        # has no free cash flow figure: neither operating cash flow alone nor a difference of
        # two windows. Only a filer that never reports capex has free cash flow equal to it.
        if ocf_ttm is not None and shares and (not capex_reported
                                               or (capex_ttm is not None and capex.index.max() == ocf.index.max())):
            out["_fcf_ttm"], out["_shares"] = ocf_ttm - (capex_ttm or 0.0), shares
        if notes:
            out["_notes"] = notes
        return out


# ------------------------------------------------------------------ helpers
def _pick(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None) -> pd.DataFrame:
    """Facts for the given tags, in preference order (a company switches tags over the
    years -- Apple's revenue is ``SalesRevenueNet`` before 2018 -- so all are kept and the
    earlier tag in the list is preferred where two cover the same trailing window)."""
    sub = known[known["tag"].isin(tags)]
    sub = sub[sub["unit"].isin(units)] if units is not None else sub[sub["unit"] == "USD"]
    if sub.empty:
        return sub
    rank = {t: i for i, t in enumerate(tags)}
    return sub.assign(_rank=sub["tag"].map(rank)).sort_values("_rank", kind="stable")


def _material(a: float, b: float) -> bool:
    return abs(a - b) > BASIS_CHANGE_TOLERANCE * max(abs(a), abs(b))


def _comparative(old: tuple[int, int], new: tuple[int, int]) -> bool:
    """``old`` is the year-earlier comparative of ``new``: the same length, ending a year before."""
    (s0, e0), (s1, e1) = old, new
    return _YEAR[0] <= e1 - e0 <= _YEAR[1] and abs((e1 - s1) - (e0 - s0)) <= 14


def _inconsistent(rows: list[tuple[int, int, float]], additive: bool) -> list[tuple[int, int, float, float]]:
    """The annual spans a filing prints whose four quarters, printed by the same filing and
    tiling the year, do not sum to it (within ``ANNUAL_CHECK_TOLERANCE`` of the year's scale
    for an ``additive`` flow, ``PER_SHARE_CHECK_TOLERANCE`` of it for a per-share one, the
    scale being the annual figure or the quarters' total magnitude, whichever is larger: a
    year netting to nearly nothing is still checked against the size of its quarters), each
    as ``(start_day, end_day, four_quarter_sum, annual)``."""
    vals = {(s, e): v for s, e, v in rows}
    quarters = sorted((s, e) for s, e in vals if _QUARTER[0] <= e - s <= _QUARTER[1])
    bad = []
    for (s, e), v in vals.items():
        if not _YEAR[0] <= e - s <= _YEAR[1]:
            continue
        inside = [q for q in quarters if s <= q[0] and q[1] <= e]
        if (len(inside) != 4 or inside[-1][1] != e or inside[0][0] - s > 3
                or not all(0 <= b[0] - a[1] <= 3 for a, b in zip(inside, inside[1:]))):
            continue
        total = sum(vals[q] for q in inside)
        scale = max(abs(v), sum(abs(vals[q]) for q in inside))
        tolerance = (ANNUAL_CHECK_TOLERANCE if additive else PER_SHARE_CHECK_TOLERANCE) * scale
        if abs(total - v) > tolerance:
            bad.append((s, e, total, v))
    return bad


def _tag_quarters(starts: list[int], ends: list[int], vals: list[float], filed: list[int],
                  positive: bool, notes: list[tuple] | None = None, additive: bool = True) -> dict[int, dict[int, float]]:
    """Quarter candidates of one concept: ``{period_end_day: {generation: value}}``.

    *Generations.* Prints are replayed filing by filing. Within a generation the latest
    print of a span wins while it differs immaterially (within ``BASIS_CHANGE_TOLERANCE``)
    from the value held: an ordinary revision. A material change must be corroborated. A
    filing that re-prints spans known in the current generation with materially different
    values has recast its comparatives when at least ``BASIS_CHANGE_MIN_SPANS`` such spans
    agree that the basis moved, or one of them is the year-earlier comparative of a span
    the filing prints for the first time (a first-quarter 10-Q restates exactly one); it
    then opens a new generation, on which it and every later filing report (discontinued
    operations, a restatement), provided the recast is internally consistent: where the
    filing prints a year's annual span and its four quarters, they must reconcile
    (``_inconsistent``: within ``ANNUAL_CHECK_TOLERANCE`` for an additive flow, loosely for
    a per-share series), or the "recast" is a filing whose quarterly comparatives are
    mis-tagged. A lone material re-print (one erroneous fact) and an inconsistent recast are
    ignored, the held values stand, and each case is appended to ``notes`` as
    ``("ignored", start, end, held, printed, filing_day)`` or
    ``("rejected", filing_day, year_end, four_quarter_sum, annual)``. First prints of such
    a filing are still taken (nothing contradicts them), except the quarters of a year it
    mis-tagged: that year's Q4 is its annual span less the quarters already held.

    *Corroboration by repetition.* Every ignored print is remembered. A later filing that
    re-prints the span within ``BASIS_CHANGE_TOLERANCE`` of an ignored value has confirmed a
    correction (an amended quarter that every later comparative repeats): it is taken in
    place within the current generation, the latest confirmed print winning, and noted as
    ``("confirmed", start, end, held, printed, filing_day)``. Such a re-print never counts
    towards a basis change: a first-quarter 10-Q re-printing the corrected comparative
    beside its new quarter is not a recast, so a generation only opens on spans no ignored
    print anticipated.

    *Reconstruction*, separately per generation so no difference ever straddles a basis
    change: direct ~90-day spans are taken as they are; longer spans sharing a start date
    (year-to-date 10-Q values, the 10-K annual figure) are differenced against the next
    shorter span with the same start, which recovers Q4 (annual minus nine months) and
    quarterly cash flows (H1 minus Q1, 9M minus H1); an annual span with no nine-month
    sibling has the direct quarters it contains subtracted, when they fill it. For an
    ``additive`` flow a direct Q4 print is cross-checked against the annual span: when the
    four direct quarters disagree with it by more than ``ANNUAL_CHECK_TOLERANCE`` of the
    year's scale (the annual figure or the quarters' total magnitude, whichever is larger),
    Q4 is the audited annual figure less the three quarters, and the case is appended to
    ``notes`` as ``("annual", end_day, generation, four_quarter_sum, annual)``. Per-share
    series are not additive across quarters and keep their direct prints.
    """
    by_filing: dict[int, list[tuple[int, int, float]]] = {}
    for s, e, v, f in zip(starts, ends, vals, filed):
        by_filing.setdefault(f, []).append((s, e, v))
    spans: dict[tuple[int, int], dict[int, float]] = {}
    ignored: dict[tuple[int, int], list[float]] = {}
    g = 0
    for f in sorted(by_filing):
        rows = by_filing[f]
        recast = {(s, e) for s, e, v in rows if g in spans.get((s, e), {}) and _material(spans[(s, e)][g], v)}
        # A material re-print agreeing with one ignored earlier is a correction two filings
        # confirm: taken in place, and never the comparative a basis change is read from.
        confirmed = {(s, e) for s, e, v in rows if (s, e) in recast
                     and any(not _material(u, v) for u in ignored.get((s, e), ()))}
        if notes is not None:
            notes.extend(("confirmed", s, e, spans[(s, e)][g], v, f) for s, e, v in rows if (s, e) in confirmed)
        recast -= confirmed
        if recast:
            first = [(s, e) for s, e, _ in rows if (s, e) not in spans]
            corroborated = (len(recast) >= BASIS_CHANGE_MIN_SPANS
                            or any(_comparative(r, n) for r in recast for n in first))
            bad = _inconsistent(rows, additive) if corroborated else []
            if corroborated and not bad:
                g += 1
            else:
                # Neither the material re-prints nor, in a mis-tagged year, the filing's own
                # quarter prints are taken: its Q4 comes from the annual span less what is held.
                drop = recast | {(s, e) for s, e, _ in rows if _QUARTER[0] <= e - s <= _QUARTER[1]
                                 and any(ys <= s and e <= ye for ys, ye, _, _ in bad)}
                if notes is not None:
                    if bad:
                        notes.append(("rejected", f, *bad[0][1:]))
                    else:
                        notes.extend(("ignored", s, e, spans[(s, e)][g], v, f) for s, e, v in rows if (s, e) in recast)
                if not bad:
                    for s, e, v in rows:
                        if (s, e) in recast:
                            ignored.setdefault((s, e), []).append(v)
                rows = [(s, e, v) for s, e, v in rows if (s, e) not in drop]
        for s, e, v in rows:
            spans.setdefault((s, e), {})[g] = v
    out: dict[int, dict[int, float]] = {}
    direct: set[tuple[int, int]] = set()
    by_start: dict[int, list[int]] = {}
    for (s, e), gens in spans.items():
        if _QUARTER[0] <= e - s <= _QUARTER[1]:
            for gg, v in gens.items():
                out.setdefault(e, {}).setdefault(gg, v)
                direct.add((e, gg))
        by_start.setdefault(s, []).append(e)
    for s, es in by_start.items():
        es.sort()
        for a, b in zip(es, es[1:]):
            if _QUARTER[0] <= b - a <= _QUARTER[1]:
                for gg in spans[(s, b)].keys() & spans[(s, a)].keys():
                    out.setdefault(b, {}).setdefault(gg, spans[(s, b)][gg] - spans[(s, a)][gg])
    for (s, e), gens in sorted(spans.items(), key=lambda kv: kv[0][1]):
        if e - s <= _QUARTER[1]:
            continue
        expected = max(round((e - s) / 91) - 1, 1)
        annual = _YEAR[0] <= e - s <= _YEAR[1]
        for gg, v in gens.items():
            have = out.get(e, {}).get(gg)
            if have is not None and not (additive and annual and (e, gg) in direct):
                continue
            inside = [q for q, qg in out.items() if s < q < e and gg in qg]
            if len(inside) != expected or not _QUARTER[0] <= e - max(inside) <= _QUARTER[1]:
                continue
            rest = v - sum(out[q][gg] for q in inside)
            if have is None:
                out.setdefault(e, {})[gg] = rest
            elif abs(have - rest) > ANNUAL_CHECK_TOLERANCE * max(abs(v), abs(have) + sum(abs(out[q][gg]) for q in inside)):
                out[e][gg] = rest
                if notes is not None:
                    notes.append(("annual", e, gg, v - rest + have, v))
    if positive:
        out = {e: {gg: v for gg, v in gens.items() if v > 0} for e, gens in out.items()}
        out = {e: gens for e, gens in out.items() if gens}
    return out


def _tag_classes(sub: pd.DataFrame, tags: tuple[str, ...]) -> list[list[str]]:
    """The tags present in ``sub`` grouped into concepts, each class in rank order and the
    classes ordered by their best rank. Two tags are one concept for a filer when they print
    identical spans (same start and end) and every such span's latest print under each tag
    agrees within ``TAG_EQUIVALENCE_TOLERANCE``: a renamed tag re-prints the comparatives it
    took over. Gross and net revenue share spans but never values; net income with and
    without the non-controlling interest agree on some spans but not all; both stay apart."""
    present = [t for t in tags if (sub["tag"] == t).any()]
    rank = {t: i for i, t in enumerate(present)}
    parent = {t: t for t in present}

    def root(t: str) -> str:
        while parent[t] != t:
            t = parent[t]
        return t

    latest = (sub[["tag", "start", "end", "val", "filed"]].sort_values("filed", kind="stable")
              .drop_duplicates(["tag", "start", "end"], keep="last"))
    for i, a in enumerate(present):
        ra = latest[latest["tag"] == a]
        for b in present[i + 1:]:
            m = ra.merge(latest[latest["tag"] == b], on=["start", "end"], suffixes=("_a", "_b"))
            if m.empty:
                continue
            scale = m[["val_a", "val_b"]].abs().max(axis=1)
            if ((m["val_a"] - m["val_b"]).abs() <= TAG_EQUIVALENCE_TOLERANCE * scale).all():
                lo, hi = sorted((root(a), root(b)), key=rank.get)
                parent[hi] = lo
    classes: dict[str, list[str]] = {}
    for t in present:
        classes.setdefault(root(t), []).append(t)
    return [classes[r] for r in present if r in classes]


def _window(quarters: dict[int, dict[int, float]], anchor: int) -> tuple[list[int], int] | None:
    """Four consecutive quarter ends of one tag ending at ``anchor`` that share a generation
    (the highest one), or None."""
    if anchor not in quarters:
        return None
    ends = [anchor]
    cur = anchor
    for _ in range(3):
        prev = [e for e in quarters if _QUARTER[0] <= cur - e <= _QUARTER[1]]
        if not prev:
            return None
        cur = max(prev)
        ends.append(cur)
    if not _TTM_SPAN[0] <= anchor - ends[-1] <= _TTM_SPAN[1]:
        return None
    gens = set(quarters[anchor])
    for e in ends[1:]:
        gens &= set(quarters[e])
    if not gens:
        return None
    return ends, max(gens)


def quarterly_table(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None = None,
                    positive: bool = False, notes: list[tuple] | None = None) -> pd.DataFrame:
    """Quarterly values by period end with the tag and basis generation each came from.

    Each concept is reconstructed on its own (``_tag_quarters``): a concept is one tag, or
    the tags a filer has shown to be one concept by printing an identical span under both
    (``_tag_classes``, a rename), and values of different concepts are never differenced or
    summed. The result is assembled from trailing four-quarter windows tiled back from the
    latest quarter end known under any concept, each window being four consecutive quarters
    of one concept on one reporting basis. The concept of a window is the one chosen for
    the previous window in time while it still covers the new one (continuity: a filer
    printing two revenue concepts side by side keeps reporting the same one); the tag rank
    decides only where no previous choice covers. Older windows are then re-expressed in
    the newer window's concept where it covers them. A quarter that belongs to no such window
    is left out, so ``ttm`` can only ever sum one concept on one basis. With ``positive`` a
    reconstructed quarter that is not positive (revenue) is rejected rather than reported.
    A per-share unit (``USD/shares``) is not additive across quarters, so its annual
    cross-check is skipped. ``notes`` collects the data-quality cases of ``_tag_quarters``
    with the concept's tag and ISO dates: ``("annual", tag, year_end, quarters, annual)``,
    ``("ignored", tag, start, end, held, printed, filed)``,
    ``("confirmed", tag, start, end, held, printed, filed)`` and
    ``("rejected", tag, filed, year_end, quarters, annual)``.

    Columns: ``val``; ``tag`` (the best-ranked tag of the concept); ``gen`` (0 = the filer's
    original basis, +1 per change).
    """
    empty = pd.DataFrame({"val": pd.Series(dtype=float), "tag": pd.Series(dtype=object),
                          "gen": pd.Series(dtype=int)})
    sub = _pick(known, tags, units)
    sub = sub.dropna(subset=["start"])
    if sub.empty:
        return empty
    epoch = pd.Timestamp("1970-01-01")
    additive = not any("/" in u for u in (units or ("USD",)))
    per_tag: list[tuple[str, dict[int, dict[int, float]]]] = []

    def day(d: int) -> str:
        return (epoch + pd.Timedelta(days=d)).date().isoformat()

    for members in _tag_classes(sub, tags):
        # The preferred tag's print of a span comes last within a filing, so it is the one kept.
        rows = sub[sub["tag"].isin(members)].sort_values("_rank", ascending=False, kind="stable")
        found: list[tuple] = []
        q = _tag_quarters(((rows["start"] - epoch).dt.days).tolist(), ((rows["end"] - epoch).dt.days).tolist(),
                          rows["val"].astype(float).tolist(), ((rows["filed"] - epoch).dt.days).tolist(), positive, found,
                          additive)
        for n in found if notes is not None else ():
            if n[0] == "annual":
                notes.append(("annual", members[0], day(n[1]), n[3], n[4]))
            elif n[0] in ("ignored", "confirmed"):
                notes.append((n[0], members[0], day(n[1]), day(n[2]), n[3], n[4], day(n[5])))
            else:
                notes.append(("rejected", members[0], day(n[1]), day(n[2]), n[3], n[4]))
        if q:
            per_tag.append((members[0], q))
    tiles: list[dict[str, tuple[list[int], int]]] = []
    covered: set[int] = set()
    for anchor in sorted({e for _, q in per_tag for e in q}, reverse=True):
        if any(abs(anchor - r) < _QUARTER[0] for r in covered):
            continue
        covers = {tag: w for tag, q in per_tag if (w := _window(q, anchor)) is not None}
        if not covers:
            continue
        tiles.append(covers)
        for ends, _ in covers.values():
            covered.update(ends)
    if not tiles:
        return empty
    chosen: list[str] = []
    for covers in reversed(tiles):
        chosen.append(chosen[-1] if chosen and chosen[-1] in covers else next(iter(covers)))
    chosen.reverse()
    # Older windows are re-expressed in the concept of the newer one where it covers them,
    # so growth compares like with like as far back as that concept goes.
    for i in range(1, len(tiles)):
        if chosen[i - 1] in tiles[i]:
            chosen[i] = chosen[i - 1]
    quarters = dict(per_tag)
    result: dict[int, tuple[float, str, int]] = {}
    for covers, tag in zip(tiles, chosen):
        ends, g = covers[tag]
        for e in ends:
            result[e] = (quarters[tag][e][g], tag, g)
    keys = sorted(result)
    return pd.DataFrame({"val": [result[k][0] for k in keys], "tag": [result[k][1] for k in keys],
                         "gen": [result[k][2] for k in keys]}, index=pd.to_datetime(keys, unit="D"))


def quarterly_series(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None = None,
                     positive: bool = False, notes: list[tuple] | None = None) -> pd.Series:
    """Quarterly values by period end: the ``val`` column of ``quarterly_table``."""
    return quarterly_table(known, tags, units, positive, notes)["val"]


def latest_instant(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None = None,
                   not_before: pd.Timestamp | None = None) -> float | None:
    """Latest print of the most recent balance-sheet instant, or None when the most recent
    instant is dated before ``not_before`` (the fact has stopped being reported)."""
    sub = _pick(known, tags, units)
    sub = sub[sub["start"].isna()]
    if sub.empty:
        return None
    sub = sub.sort_values(["end", "filed", "_rank"], kind="stable")
    latest_end = sub.iloc[-1]["end"]
    if not_before is not None and latest_end < not_before:
        return None
    at_end = sub[sub["end"] == latest_end].sort_values(["filed", "_rank"], ascending=[True, False], kind="stable")
    return float(at_end.iloc[-1]["val"])   # latest print; the preferred tag on the same day


PER_SHARE_DURATION_TAGS = set(EPS_TAGS) | {"WeightedAverageNumberOfDilutedSharesOutstanding",
                                          "WeightedAverageNumberOfBasicSharesOutstanding"}
SHARE_INSTANT_TAGS = {"dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"}


def rebase_per_share(known: pd.DataFrame, past_splits: list[tuple[pd.Timestamp, float]]) -> pd.DataFrame:
    """Bring per-share and share-count facts to the share basis after ``past_splits``.

    A print is in the units of the day it was made: an EPS filed before a 4-for-1 split is
    four times the post-split figure, a share count a quarter of it. Duration facts (EPS,
    weighted-average shares) are rescaled by the splits after their *filing* date; instant
    share counts by the splits after their *instant* date. Everything else is unchanged.
    """
    known = known.copy()
    ratios = [(d, r) for d, r in past_splits if r > 0]
    if not ratios:
        return known

    def factor(dates: pd.Series) -> np.ndarray:
        f = np.ones(len(dates))
        for d, r in ratios:
            f = np.where(dates.to_numpy() < np.datetime64(d), f * r, f)
        return f

    dur = known["tag"].isin(PER_SHARE_DURATION_TAGS)
    inst = known["tag"].isin(SHARE_INSTANT_TAGS) & known["start"].isna()
    eps_like = dur & known["tag"].isin(EPS_TAGS)
    shares_dur = dur & ~eps_like
    known.loc[eps_like, "val"] = known.loc[eps_like, "val"] / factor(known.loc[eps_like, "filed"])
    known.loc[shares_dur, "val"] = known.loc[shares_dur, "val"] * factor(known.loc[shares_dur, "filed"])
    known.loc[inst, "val"] = known.loc[inst, "val"] * factor(known.loc[inst, "end"])
    return known


def ttm(q: pd.Series, back: int = 0) -> float | None:
    """Sum of four consecutive quarters ending ``back`` quarters before the latest."""
    if q.empty:
        return None
    n = len(q)
    hi = n - back
    lo = hi - 4
    if lo < 0:
        return None
    window = q.iloc[lo:hi]
    span = (window.index[-1] - window.index[0]).days
    if len(window) < 4 or not _TTM_SPAN[0] <= span <= _TTM_SPAN[1]:  # four quarters must be contiguous
        return None
    return float(window.sum())


__all__ = ["EdgarClient", "ITEM_8K", "OTHER_FORMS", "quarterly_series", "quarterly_table", "latest_instant",
           "ttm", "rebase_per_share", "SHARE_CLASS_RATIO"]
