"""SEC EDGAR: free, keyless, *point-in-time* fundamentals and corporate-event news.

Three public JSON endpoints (the SEC asks for a descriptive ``User-Agent`` with a
contact and at most 10 requests per second; both are enforced here):

* ``www.sec.gov/files/company_tickers.json``            ticker -> CIK
* ``data.sec.gov/submissions/CIK##########.json``        every filing, with its filing date
* ``data.sec.gov/api/xbrl/companyfacts/CIK##########.json``  every XBRL fact, with the
  date of the filing that reported it

The point-in-time rule is the same everywhere: a filing or a fact exists at
``as_of`` iff its ``filed`` date is ``<= as_of``. Where a value was later restated,
the *first* print is used, so a backtest sees the numbers the market saw.

Fundamentals are derived from the raw facts rather than taken from a vendor
snapshot: quarterly flows are reconstructed from the reported spans (10-Q values
are year-to-date for cash-flow items, and Q4 is only ever reported inside the
10-K), summed to trailing-twelve-month figures and combined with the price the
caller passes in. Consensus data (EPS surprise) is not available from EDGAR and is
reported as ``None`` rather than guessed.

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

# Days in a quarter: 13 weeks normally, 12 weeks for 52/53-week fiscal calendars (Costco,
# PepsiCo) whose fourth quarter then has 16 weeks (112 days).
_QUARTER = (75, 120)
# Filers that are funds or trusts, not operating companies: their XBRL facts are not
# fundamentals in the analyst's sense, so they return nothing rather than nonsense.
NON_OPERATING_SIC = {"6221"}   # commodity contracts brokers & dealers (GLD, SLV, USO, DBC)
_YEAR = (350, 380)


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
        """Fundamentals known at ``as_of`` (facts filed on or before it; first prints).

        ``price`` must be the close *as traded* on ``as_of`` (not a split-adjusted history),
        and ``splits`` maps split ex-dates to their ratios (4.0 for a 4-for-1). Per-share
        prints are in the share units of the filing that reported them, so every EPS and
        share-count fact is brought to the ``as_of`` basis before quarters are mixed: an EPS
        first-printed before a split is divided by the ratio, a share count multiplied. With
        ``splits`` omitted nothing is rescaled, which is only right for a company that has
        never split.

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
        if eps_ttm is not None:
            out["eps_ttm"] = round(eps_ttm, 4)
            if price:
                out["pe_ratio"] = round(price / eps_ttm, 2) if eps_ttm > 0 else -1.0
        if fcf is not None and price and shares:
            out["fcf_yield"] = round(fcf / (price * shares), 4)
        return out

    def _fundamentals_core(self, known: pd.DataFrame, past_splits: list[tuple[pd.Timestamp, float]] = ()) -> dict[str, Any]:
        """The price-independent fundamentals from the facts known at a cutoff, per-share
        facts rescaled to the share basis after ``past_splits``."""
        if known.empty:
            return {}
        if past_splits:
            known = rebase_per_share(known, past_splits)
        rev = quarterly_series(known, REVENUE_TAGS)
        ni = quarterly_series(known, NET_INCOME_TAGS)
        eps = quarterly_series(known, EPS_TAGS, units=("USD/shares",))
        ocf = quarterly_series(known, OCF_TAGS)
        capex = quarterly_series(known, CAPEX_TAGS)
        equity = latest_instant(known, EQUITY_TAGS)
        debt = latest_instant(known, DEBT_TAGS)
        shares = latest_instant(known, SHARES_TAGS, units=("shares",))
        if rev.empty and ni.empty:   # no income statement at all: not an operating company
            return {}
        ends = [s.index.max() for s in (rev, ni, eps) if not s.empty]
        period_end = max(ends)
        latest_filed = known.loc[known["end"] == period_end, "filed"].min()
        out: dict[str, Any] = {
            "report_period_end": period_end.date().isoformat(),
            "filed": latest_filed.date().isoformat() if pd.notna(latest_filed) else None,
            "sector_pe": None, "eps_surprise": None, "insider_net_buying": None,
            "source": "sec_edgar (point-in-time, first prints)",
        }
        rev_ttm, rev_prev = ttm(rev), ttm(rev, back=4)
        ni_ttm = ttm(ni)
        eps_ttm = ttm(eps)
        if rev_ttm is not None:
            out["revenue_ttm"] = rev_ttm
        # Year over year only when the two four-quarter windows are exactly a year apart
        # (a missing quarter would otherwise compare across a 15-month gap).
        if rev_ttm and rev_prev and len(rev) >= 8 and 350 <= (rev.index[-1] - rev.index[-5]).days <= 380:
            out["revenue_growth_yoy"] = round(rev_ttm / rev_prev - 1.0, 4)
        if rev_ttm and ni_ttm is not None:
            out["net_margin"] = round(ni_ttm / rev_ttm, 4)
        if eps_ttm is not None:
            out["_eps_ttm"] = eps_ttm
        if debt is not None and equity:
            out["debt_to_equity"] = round(debt / equity, 3)
        ocf_ttm, capex_ttm = ttm(ocf), ttm(capex)
        if ocf_ttm is not None and shares:
            out["_fcf_ttm"], out["_shares"] = ocf_ttm - (capex_ttm or 0.0), shares
        return out


# ------------------------------------------------------------------ helpers
def _pick(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None) -> pd.DataFrame:
    """Facts for the given tags, in preference order (a company switches tags over the
    years -- Apple's revenue is ``SalesRevenueNet`` before 2018 -- so all are kept and the
    earlier tag in the list wins where two report the same span)."""
    sub = known[known["tag"].isin(tags)]
    sub = sub[sub["unit"].isin(units)] if units is not None else sub[sub["unit"] == "USD"]
    if sub.empty:
        return sub
    rank = {t: i for i, t in enumerate(tags)}
    return sub.assign(_rank=sub["tag"].map(rank)).sort_values("_rank", kind="stable")


def quarterly_series(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None = None) -> pd.Series:
    """Quarterly values by period end, first print of each span.

    Direct ~90-day spans are taken as they are. Longer spans that share a start
    date (year-to-date 10-Q values, and the 10-K annual figure) are differenced
    against the shorter span with the same start, which recovers Q4 (annual minus
    nine months) and quarterly cash flows (H1 minus Q1, 9M minus H1).
    """
    sub = _pick(known, tags, units)
    sub = sub.dropna(subset=["start"])
    if sub.empty:
        return pd.Series(dtype=float)
    first = sub.sort_values(["filed", "_rank"], kind="stable")   # earliest print of a span wins; tag rank breaks ties
    # Work in integer days (numpy) rather than per-row pandas objects: this runs once per
    # filing per tag inside a walk-forward backtest.
    epoch = pd.Timestamp("1970-01-01")
    starts = ((first["start"] - epoch).dt.days).to_numpy()
    ends = ((first["end"] - epoch).dt.days).to_numpy()
    vals = first["val"].to_numpy(dtype=float)
    span: dict[tuple[int, int], float] = {}
    for s, e, v in zip(starts.tolist(), ends.tolist(), vals.tolist()):
        span.setdefault((s, e), v)                       # first print wins (sorted by rank, filed)
    out: dict[int, float] = {}
    by_start: dict[int, list[int]] = {}
    for (s, e), v in span.items():
        if _QUARTER[0] <= e - s <= _QUARTER[1]:
            out.setdefault(e, v)
        by_start.setdefault(s, []).append(e)
    for s, es in by_start.items():
        es.sort()
        for a, b in zip(es, es[1:]):
            if _QUARTER[0] <= b - a <= _QUARTER[1] and b not in out:
                out[b] = span[(s, b)] - span[(s, a)]
    # A longer span whose shorter sibling was never reported (an annual figure with no
    # nine-month value): subtract the direct quarters it contains, when they fill it.
    for (s, e), v in sorted(span.items(), key=lambda kv: kv[0][1]):
        if e - s <= _QUARTER[1] or e in out:
            continue
        inside = [q for q in out if s < q < e]
        expected = max(round((e - s) / 91) - 1, 1)
        if len(inside) == expected and _QUARTER[0] <= e - max(inside) <= _QUARTER[1]:
            out[e] = v - sum(out[q] for q in inside)
    idx = pd.to_datetime(sorted(out), unit="D")
    return pd.Series([out[k] for k in sorted(out)], index=idx, dtype=float)


def latest_instant(known: pd.DataFrame, tags: tuple[str, ...], units: tuple[str, ...] | None = None) -> float | None:
    sub = _pick(known, tags, units)
    sub = sub[sub["start"].isna()]
    if sub.empty:
        return None
    sub = sub.sort_values(["end", "filed", "_rank"], kind="stable")
    latest_end = sub.iloc[-1]["end"]
    return float(sub[sub["end"] == latest_end].iloc[0]["val"])   # first print of the latest instant


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
    if len(window) < 4 or not 240 <= span <= 300:  # four quarters must be contiguous
        return None
    return float(window.sum())


__all__ = ["EdgarClient", "ITEM_8K", "OTHER_FORMS", "quarterly_series", "latest_instant", "ttm", "rebase_per_share"]
