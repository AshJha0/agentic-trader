"""v0.8 data-layer fixes (review findings 7, 8, 15, 34, 35, 36, 37, 68, 69, 88 and the cash-leg
contract of finding 14), each with the case that failed on v0.7 code."""
import json
import os
import sys
import time
import types
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, make_config
from agentic_trader.data import CSVProvider, SyntheticProvider
from agentic_trader.data import edgar as edgar_mod
from agentic_trader.data import fred as fred_mod
from agentic_trader.data import yahoo as yahoo_mod
from agentic_trader.data.base import MACRO_SOURCE_STATIC, fx_macro
from agentic_trader.data.edgar import EdgarClient, quarterly_table, ttm
from agentic_trader.data.fred import CASH_SERIES, FredClient, FredSeries, default_client
from agentic_trader.data.synthetic import fx_start_level
from agentic_trader.evaluation import UNIVERSES
from agentic_trader.sentiment import score_fx_headline

NAN = float("nan")
G = "RevenueFromContractWithCustomerExcludingAssessedTax"   # rank 0 in REVENUE_TAGS
N = "Revenues"                                              # rank 1
EDGAR_CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "build", "edgar_cache")


# ------------------------------------------------------------------ helpers
def _f(start, end, val, filed, form="10-Q"):
    d = {"end": end, "val": val, "filed": filed, "form": form, "fy": int(end[:4]), "fp": "Q1"}
    if start is not None:
        d["start"] = start
    return d


def _edgar(facts_by_tag: dict, cik: str = "0000000777", ticker: str = "TST") -> EdgarClient:
    """An offline EdgarClient serving one filer whose facts are given per tag."""
    us_gaap, dei = {}, {}
    for tag, entries in facts_by_tag.items():
        unit = "USD/shares" if tag.startswith("EarningsPerShare") else "shares" if "Shares" in tag else "USD"
        (dei if tag.startswith("dei:") else us_gaap)[tag.split(":", 1)[-1]] = {"units": {unit: entries}}
    payloads = {
        edgar_mod.TICKERS_URL: {"0": {"cik_str": int(cik), "ticker": ticker, "title": "Test"}},
        edgar_mod.SUBMISSIONS_URL.format(name=f"CIK{cik}.json"): {
            "name": "Test", "sic": "3571",
            "filings": {"recent": {"form": [], "filingDate": [], "accessionNumber": []}}},
        edgar_mod.FACTS_URL.format(cik=cik): {"facts": {"us-gaap": us_gaap, "dei": dei}},
    }
    return EdgarClient(user_agent="t t@x", fetch=lambda u: json.dumps(payloads[u]).encode(), min_interval=0)


def _known(c: EdgarClient, as_of: date, ticker: str = "TST") -> pd.DataFrame:
    df = c.facts(ticker)
    return df[df["filed"] <= pd.Timestamp(as_of)]


def _quarters(tag_prefix, year, vals, filed, forms=("10-Q", "10-Q", "10-Q", "10-K")):
    """Direct quarterly spans of a calendar year (Q4 as a direct span inside the 10-K)."""
    q = [(f"{year}-01-01", f"{year}-03-31"), (f"{year}-04-01", f"{year}-06-30"),
         (f"{year}-07-01", f"{year}-09-30"), (f"{year}-10-01", f"{year}-12-31")]
    return [_f(s, e, v, f, fm) for (s, e), v, f, fm in zip(q, vals, filed, forms)]


# ============================================================ finding 7: tags never mixed
def _ma_shaped(fy2022_under_gross: bool = False):
    """Mastercard 2021-2022: the 10-Qs print gross revenue under the rank-0 tag and net revenue
    under ``Revenues``; the 10-K carries only ``Revenues`` (net)."""
    filed21 = ["2021-04-29", "2021-07-29", "2021-10-28", "2022-02-15"]
    filed22 = ["2022-04-28", "2022-07-28", "2022-10-27", "2023-02-14"]
    gross = (_quarters(G, 2021, [7.0, 7.6, 8.2, 8.372], filed21) +
             _quarters(G, 2022, [8.025, 8.704, 9.167], filed22[:3]))
    gross += [_f("2022-01-01", "2022-09-30", 25.896, "2022-10-27")]                 # gross nine months
    gross += [_f("2021-01-01", "2021-12-31", 31.172, "2022-02-15", "10-K")]
    net = (_quarters(N, 2021, [4.2, 4.5, 5.0, 5.2], filed21) +
           _quarters(N, 2022, [5.167, 5.497, 5.756], filed22[:3]))
    net += [_f("2022-01-01", "2022-09-30", 16.420, "2022-10-27"),                    # net nine months
            _f("2021-01-01", "2021-12-31", 18.9, "2022-02-15", "10-K"),
            _f("2022-01-01", "2022-12-31", 22.237, "2023-02-14", "10-K")]
    if fy2022_under_gross:
        gross += [_f("2022-01-01", "2022-12-31", 35.0, "2023-02-14", "10-K")]
    return {G: gross, N: net}


def test_quarters_are_reconstructed_per_tag_and_one_concept_per_window():
    c = _edgar(_ma_shaped())
    t = quarterly_table(_known(c, date(2023, 3, 1)), edgar_mod.REVENUE_TAGS, positive=True)
    # v0.7: Q4-2022 = 22.237 (net 10-K) - 25.896 (gross 9M) = -3.659 and a 22.237 TTM stitched
    # from four quarters of two concepts. Now: no negative quarter, one tag per window.
    assert (t["val"] > 0).all()
    assert set(t["tag"]) == {N}                                   # gross has no Q4 -> the net tag covers
    assert t.loc[pd.Timestamp("2022-12-31"), "val"] == pytest.approx(22.237 - 16.420)
    assert ttm(t["val"]) == pytest.approx(22.237) and ttm(t["val"], back=4) == pytest.approx(18.9)
    f = c.fundamentals("TST", date(2023, 3, 1))
    assert f["revenue_ttm"] == pytest.approx(22.237)
    assert f["revenue_growth_yoy"] == pytest.approx(22.237 / 18.9 - 1, abs=1e-4)   # net vs net, not net vs gross
    # With the 10-K also printing the preferred tag, that tag covers and wins by rank.
    c2 = _edgar(_ma_shaped(fy2022_under_gross=True))
    t2 = quarterly_table(_known(c2, date(2023, 3, 1)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t2["tag"]) == {G} and ttm(t2["val"]) == pytest.approx(35.0)


def test_year_to_date_spans_of_another_tag_are_not_stitched_into_a_window():
    """Berkshire 2018: the excluding-tax tag has only YTD spans plus a Q3 direct print, so v0.7
    took Q3 from it (45.4B) and the other three quarters from ``Revenues``."""
    filed = ["2018-05-07", "2018-08-06", "2018-11-05", "2019-02-25"]
    rev = _quarters(N, 2018, [58.473, 62.200, 63.450, 63.714], filed) + [
        _f("2018-01-01", "2018-06-30", 120.673, filed[1]), _f("2018-01-01", "2018-09-30", 184.123, filed[2]),
        _f("2018-01-01", "2018-12-31", 247.837, filed[3], "10-K")]
    other = [_f("2018-01-01", "2018-06-30", 85.764, filed[1]), _f("2018-01-01", "2018-09-30", 131.191, filed[2]),
             _f("2018-07-01", "2018-09-30", 45.427, filed[2]), _f("2018-01-01", "2018-12-31", 175.445, filed[3], "10-K")]
    c = _edgar({N: rev, G: other})
    t = quarterly_table(_known(c, date(2019, 3, 1)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t["tag"]) == {N} and len(t) == 4
    assert ttm(t["val"]) == pytest.approx(247.837)
    assert 45.427 not in set(t["val"].round(3))


def test_non_positive_reconstructed_revenue_quarter_is_rejected_not_reported():
    filed = ["2022-04-28", "2022-07-28", "2022-10-27", "2023-02-14"]
    bad = _quarters(G, 2022, [8.025, 8.704, 9.167], filed[:3]) + [
        _f("2022-01-01", "2022-09-30", 25.896, filed[2]), _f("2022-01-01", "2022-12-31", 22.237, filed[3], "10-K")]
    known = _known(_edgar({G: bad}), date(2023, 3, 1))
    assert quarterly_table(known, edgar_mod.REVENUE_TAGS, positive=True).empty        # no window survives
    assert "revenue_ttm" not in _edgar({G: bad}).fundamentals("TST", date(2023, 3, 1))
    q = quarterly_table(known, edgar_mod.REVENUE_TAGS, positive=False)["val"]           # a signed flow may be negative
    assert q.loc[pd.Timestamp("2022-12-31")] == pytest.approx(22.237 - 25.896)


# ===================================================== finding 34: as known at as_of
def _jnj_shaped(restate_2022_in_10k: bool = True):
    """Revenue prints around a spin-off: 2023 Q1/Q2 first printed including the unit, the Q3 10-Q
    on the continuing basis (with restated Q3/9M-2022 comparatives), the FY2023 10-K restating
    Q1/Q2-2023, FY2022 and (optionally) the 2022 quarters."""
    r = _quarters(G, 2022, [23.4, 24.0, 23.8], ["2022-04-26", "2022-07-26", "2022-10-25"]) + [
        _f("2022-01-01", "2022-06-30", 47.4, "2022-07-26"), _f("2022-01-01", "2022-09-30", 71.2, "2022-10-25"),
        _f("2022-01-01", "2022-12-31", 94.9, "2023-02-16", "10-K"),
        _f("2023-01-01", "2023-03-31", 24.7, "2023-04-25"), _f("2023-04-01", "2023-06-30", 25.5, "2023-07-25"),
        _f("2023-01-01", "2023-06-30", 50.2, "2023-07-25"),
        # Q3-2023 10-Q: continuing operations, comparatives restated
        _f("2023-07-01", "2023-09-30", 21.35, "2023-10-27"), _f("2023-01-01", "2023-09-30", 63.75, "2023-10-27"),
        _f("2022-07-01", "2022-09-30", 20.0, "2023-10-27"), _f("2022-01-01", "2022-09-30", 60.04, "2023-10-27"),
        # FY2023 10-K: full year plus quarterly data on the continuing basis
        _f("2023-01-01", "2023-12-31", 85.15, "2024-02-16", "10-K"),
        _f("2023-01-01", "2023-03-31", 20.9, "2024-02-16", "10-K"), _f("2023-04-01", "2023-06-30", 21.5, "2024-02-16", "10-K"),
        _f("2023-07-01", "2023-09-30", 21.35, "2024-02-16", "10-K"), _f("2023-10-01", "2023-12-31", 21.4, "2024-02-16", "10-K"),
        _f("2022-01-01", "2022-12-31", 79.94, "2024-02-16", "10-K")]
    if restate_2022_in_10k:
        r += [_f("2022-01-01", "2022-03-31", 19.84, "2024-02-16", "10-K"), _f("2022-04-01", "2022-06-30", 20.2, "2024-02-16", "10-K"),
              _f("2022-07-01", "2022-09-30", 20.0, "2024-02-16", "10-K"), _f("2022-10-01", "2022-12-31", 19.9, "2024-02-16", "10-K")]
    return {G: r}


def test_restated_comparatives_public_at_as_of_are_used_and_bases_are_never_mixed():
    c = _edgar(_jnj_shaped())
    # After the 10-K (filed 2024-02-16 <= as_of): the trailing year is the four continuing-ops
    # quarters (85.15), not first prints incl. the unit + continuing Q3/Q4 (v0.7: 93.0-shaped mix).
    f = c.fundamentals("TST", date(2024, 3, 1))
    assert f["revenue_ttm"] == pytest.approx(20.9 + 21.5 + 21.35 + 21.4)
    assert f["revenue_growth_yoy"] == pytest.approx(85.15 / (19.84 + 20.2 + 20.0 + 19.9) - 1, abs=1e-4)
    t = quarterly_table(_known(c, date(2024, 3, 1)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t["gen"]) == {1} and len(t) == 8
    # Between the Q3 10-Q and the 10-K only Q3-2023 is on the new basis: the mixed trailing year
    # (Q4-22 + Q1/Q2-23 incl. the unit + Q3-23 continuing) is not summed; the latest year on one
    # basis is, and Q4-2022 is differenced from two prints of the same basis (94.9 - 71.2), not
    # from the 10-K FY and the restated nine months (which would have been a 34.9B quarter).
    g = c.fundamentals("TST", date(2023, 11, 1))
    assert g["report_period_end"] == "2023-06-30"
    assert g["revenue_ttm"] == pytest.approx(23.8 + (94.9 - 71.2) + 24.7 + 25.5)
    assert g["revenue_ttm"] != pytest.approx((94.9 - 71.2) + 24.7 + 25.5 + 21.35)
    # The day before the 10-K nothing of it is visible (point-in-time).
    assert c.fundamentals("TST", date(2024, 2, 15))["revenue_ttm"] == g["revenue_ttm"]
    # Without the 10-K's restated 2022 quarters the prior year exists only on the old basis:
    # the trailing year is reported, growth across bases is not.
    h = _edgar(_jnj_shaped(restate_2022_in_10k=False)).fundamentals("TST", date(2024, 3, 1))
    assert h["revenue_ttm"] == pytest.approx(85.15) and "revenue_growth_yoy" not in h


def test_small_revision_replaces_earlier_print_material_one_opens_a_new_basis():
    base = (_quarters(G, 2022, [100, 110, 120, 130], ["2022-04-28", "2022-07-28", "2022-10-27", "2023-02-01"]) +
            _quarters(G, 2023, [140, 150, 160, 170], ["2023-04-27", "2023-07-27", "2023-10-26", "2024-02-01"]))
    mild = base + [_f("2022-04-01", "2022-06-30", 111, "2023-07-27")]      # Q2-22 comparative revised by 0.9%
    f = _edgar({G: mild}).fundamentals("TST", date(2024, 3, 1))
    assert f["revenue_ttm"] == 140 + 150 + 160 + 170
    assert f["revenue_growth_yoy"] == pytest.approx(620 / (100 + 111 + 120 + 130) - 1, abs=1e-4)   # latest print
    material = base + [_f("2022-04-01", "2022-06-30", 90, "2023-07-27")]   # -18%: a recast, not a revision
    g = _edgar({G: material}).fundamentals("TST", date(2024, 3, 1))
    # Q2/Q3/Q4-2023 are on the new basis and Q1-2023 only on the old one: no trailing year of 2023
    # is on one basis, so the latest single-basis year is reported and no growth across bases.
    assert g["revenue_ttm"] == 110 + 120 + 130 + 140 and g["report_period_end"] == "2023-03-31"
    assert "revenue_growth_yoy" not in g
    # a revision filed after as_of is invisible either way
    h = _edgar({G: material}).fundamentals("TST", date(2023, 7, 26))
    assert h["revenue_ttm"] == 110 + 120 + 130 + 140 and h["report_period_end"] == "2023-03-31"


# =================================================== finding 8: recency / share class
def _brk_shaped(share_end="2011-04-29", share_filed="2011-05-06", eps_years=(2013,), shares=941_481.0,
                eps_vals=(2977.0, 2763.0, 3074.0, 3035.0)):
    rev, ni, ocf, eps = [], [], [], []
    for y in range(2012, 2024):
        filed = [f"{y}-05-05", f"{y}-08-05", f"{y}-11-05", f"{y + 1}-02-25"]
        rev += _quarters(N, y, [60e9, 61e9, 62e9, 63e9], filed)
        ni += _quarters("NetIncomeLoss", y, [5e9, 5e9, 5e9, 5e9], filed)
        ocf += _quarters("NetCashProvidedByUsedInOperatingActivities", y, [9e9, 9e9, 9e9, 9e9], filed)
        if y in eps_years:
            eps += _quarters("EarningsPerShareBasic", y, list(eps_vals), filed)
    return {N: rev, "NetIncomeLoss": ni, "NetCashProvidedByUsedInOperatingActivities": ocf,
            "EarningsPerShareBasic": eps,
            "dei:EntityCommonStockSharesOutstanding": [_f(None, share_end, shares, share_filed)]}


def test_decade_old_share_count_and_dead_eps_series_yield_no_per_share_ratios():
    c = _edgar(_brk_shaped())
    f = c.fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert f["report_period_end"] == "2023-12-31" and f["revenue_ttm"] == pytest.approx(246e9)
    assert "fcf_yield" not in f and "eps_ttm" not in f and "pe_ratio" not in f    # v0.7: fcf_yield 105, P/E 0.03
    # a current share count restores the FCF yield; a current EPS window restores the P/E
    g = _edgar(_brk_shaped(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=1.4e9,
                           eps_vals=(2.0, 1.8, 2.1, 2.0)))
    h = g.fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert h["fcf_yield"] == pytest.approx(36e9 / (300.0 * 1.4e9), abs=1e-4)
    assert h["eps_ttm"] == pytest.approx(7.9)
    assert h["pe_ratio"] == pytest.approx(300 / 7.9, abs=1e-2)


def test_market_cap_and_eps_sanity_checks_drop_other_class_ratios(monkeypatch):
    # fresh facts, but stated per Class A share while the price is a Class B price
    c = _edgar(_brk_shaped(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=941_481.0))
    f = c.fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert "fcf_yield" not in f and "pe_ratio" not in f and "eps_ttm" not in f
    # ...unless the filer's class ratio is known: EPS / 1500 and shares x 1500
    monkeypatch.setitem(edgar_mod.SHARE_CLASS_RATIO, "TST", 1500.0)
    g = _edgar(_brk_shaped(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=941_481.0))
    h = g.fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert h["eps_ttm"] == pytest.approx((2977 + 2763 + 3074 + 3035) / 1500, abs=1e-4)
    assert h["fcf_yield"] == pytest.approx(36e9 / (300.0 * 941_481.0 * 1500), abs=1e-4)
    assert "BRK-B" in edgar_mod.SHARE_CLASS_RATIO


def test_balance_sheet_instants_older_than_400_days_are_not_current():
    facts = _brk_shaped(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=1.4e9)
    facts["StockholdersEquity"] = [_f(None, "2020-12-31", 400e9, "2021-02-25", "10-K")]
    facts["LongTermDebt"] = [_f(None, "2020-12-31", 100e9, "2021-02-25", "10-K")]
    assert "debt_to_equity" not in _edgar(facts).fundamentals("TST", date(2024, 3, 1), price=300.0)
    facts["StockholdersEquity"].append(_f(None, "2023-12-31", 500e9, "2024-02-25", "10-K"))
    facts["LongTermDebt"].append(_f(None, "2023-12-31", 125e9, "2024-02-25", "10-K"))
    assert _edgar(facts).fundamentals("TST", date(2024, 3, 1), price=300.0)["debt_to_equity"] == pytest.approx(0.25)


@pytest.mark.skipif(not os.path.isdir(EDGAR_CACHE), reason="no offline EDGAR cache in build/")
def test_cached_filers_offline_regression():
    """MA / BRK-B / JNJ from the frozen companyfacts cache, no network (the fetch raises)."""
    def no_net(url):
        raise AssertionError("network blocked")
    c = EdgarClient(user_agent="offline offline@example.com", cache_dir=EDGAR_CACHE, fetch=no_net,
                    cache_max_age_days=None, ciks={"MA": "0001141391", "BRK-B": "0001067983", "JNJ": "0000200406"})
    try:
        ma = c.fundamentals("MA", date(2023, 3, 1))
    except AssertionError:
        pytest.skip("cache incomplete")
    assert ma["revenue_ttm"] == pytest.approx(22.237e9, rel=1e-4)                # one concept
    assert ma["revenue_growth_yoy"] == pytest.approx(0.178, abs=0.01)             # reported +17.8%, v0.7 gave -25.5%
    q = quarterly_table(_known(c, date(2023, 3, 1), "MA"), edgar_mod.REVENUE_TAGS, positive=True)
    assert (q["val"] > 0).all() and q["tag"].iloc[-8:].nunique() == 1 and q["gen"].iloc[-8:].nunique() == 1
    brk = c.fundamentals("BRK-B", date(2024, 3, 1), price=300.0)
    assert brk["revenue_ttm"] > 2e11 and "pe_ratio" not in brk and "fcf_yield" not in brk and "eps_ttm" not in brk
    assert c.fundamentals("BRK-B", date(2019, 3, 1))["revenue_ttm"] == pytest.approx(247.837e9, rel=1e-4)
    jnj = c.fundamentals("JNJ", date(2024, 3, 1))
    assert jnj["revenue_ttm"] == pytest.approx(85.159e9, rel=1e-4)              # v0.7: 93.022e9 on two bases
    assert jnj["revenue_growth_yoy"] == pytest.approx(0.0646, abs=2e-3)


# ================================================ finding 15: one FX rate resolver
class _RealWorldSynthetic(SyntheticProvider):
    real_world = True


@pytest.fixture
def fake_fred(monkeypatch):
    """DFF daily through today; the JPY monthly series stops (stale from +100 days); CHF missing."""
    today = date.today()
    dff_idx = pd.date_range(today - timedelta(days=400), today, freq="D")
    jpy_idx = pd.date_range(today - timedelta(days=400), today - timedelta(days=170), freq="MS")

    def fetch(url):
        sid = url.split("id=")[1].split("&")[0]
        if sid == "DFF":
            return pd.DataFrame({"DFF": 4.0}, index=dff_idx)
        if sid == "IRSTCI01JPM156N":
            return pd.DataFrame({"v": 0.75}, index=jpy_idx)
        if sid == "DTB3":
            return pd.DataFrame({"DTB3": 5.0}, index=dff_idx)
        raise RuntimeError(f"{sid} unavailable")
    client = FredClient(fetch=fetch)
    monkeypatch.setattr(fred_mod, "_default", client)
    return client


def test_desk_macro_and_credited_carry_agree_on_every_bar_and_never_use_static(fake_fred):
    cfg = make_config()
    p = _RealWorldSynthetic(cfg)
    today = date.today()
    for sym in ("USDJPY", "USDCHF", "USDSEK"):
        ins = Instrument.parse(sym)
        df = p.history(ins, today - timedelta(days=120), today)
        carry = p.carry_series(ins, df.index)
        shown = [p.macro(ins, ts.date()).get("rate_diff") for ts in df.index]
        for rd, c in zip(shown, carry):
            if rd is None:
                assert np.isnan(c)
            else:
                assert c == pytest.approx(rd / 100.0, abs=1e-12)
        assert MACRO_SOURCE_STATIC not in p.macro_sources
    # USDJPY: FRED while the JPY leg is fresh, then nothing (v0.7: the static table, weight +0.5,
    # while the backtester credited 0 for the same bars).
    ins = Instrument.parse("USDJPY")
    dates = pd.bdate_range(today - timedelta(days=120), today)
    carry = p.carry_series(ins, dates)
    assert np.isnan(carry[-1]) and np.isfinite(carry[0]) and carry[0] == pytest.approx((4.0 - 0.75) / 100)
    assert p.macro(ins, today) == {} and p.macro(ins, dates[0].date())["macro_source"] == "fred"
    assert p.macro_sources["fred"] > 0 and p.macro_sources["none"] > 0
    # the answer for a date is a function of the data, not of the wall clock
    assert fx_macro(Instrument.parse("USDCHF"), today, cfg, real_world=True) == {}
    assert fx_macro(Instrument.parse("USDCHF"), today - timedelta(days=365), cfg, real_world=True) == {}
    # synthetic data keeps its static world, and macro() records it
    s = SyntheticProvider(cfg)
    assert s.macro(ins, today)["macro_source"] == "static" and s.macro_sources == {"static": 1}
    with pytest.raises(ValueError):
        fx_macro(ins, today, make_config(fx_macro_source="bogus"), real_world=True)


# ===================================================== finding 14 (data side): cash leg
def test_risk_free_series_modes_and_point_in_time_tbill(monkeypatch):
    dates = pd.bdate_range("2024-01-02", "2024-01-08")
    cfg = make_config()
    assert np.array_equal(SyntheticProvider(cfg).risk_free_series(dates), np.zeros(len(dates)))
    assert np.allclose(SyntheticProvider(make_config(risk_free_annual=0.03)).risk_free_series(dates), 0.03)
    assert np.isnan(SyntheticProvider(make_config(cash_leg="off")).risk_free_series(dates)).all()
    with pytest.raises(ValueError):
        SyntheticProvider(make_config(cash_leg="bogus")).risk_free_series(dates)
    # DTB3 is published the next business day: the 5.20 observed on 01-02 is known from 01-03.
    obs = pd.DataFrame({"DTB3": [5.20, 5.25, 5.30]}, index=pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-05"]))
    client = FredClient(fetch=lambda url: obs)
    monkeypatch.setattr(fred_mod, "_default", client)
    rf = _RealWorldSynthetic(cfg).risk_free_series(dates)                       # auto -> FRED on real-world data
    assert np.isnan(rf[0])
    assert rf[1:].tolist() == pytest.approx([0.0520, 0.0525, 0.0525, 0.0530])
    assert CASH_SERIES["USD"].series_id == "DTB3" and CASH_SERIES["USD"].lag_days == 1
    assert np.allclose(_RealWorldSynthetic(make_config(cash_leg="static", risk_free_annual=0.02)).risk_free_series(dates), 0.02)
    assert np.allclose(SyntheticProvider(make_config(cash_leg="fred")).risk_free_series(dates)[1:], rf[1:])
    # a stale series is unknown, not carried forward
    late = pd.bdate_range("2024-02-01", "2024-02-02")
    assert np.isnan(_RealWorldSynthetic(cfg).risk_free_series(late)).all()


def test_csv_provider_cash_leg_is_the_constant_unless_forced(tmp_path, monkeypatch):
    (tmp_path / "ABC.csv").write_text("Date,Close\n2024-01-02,10\n2024-01-03,11\n")
    dates = pd.bdate_range("2024-01-02", "2024-01-03")
    assert np.allclose(CSVProvider(make_config(csv_dir=str(tmp_path), risk_free_annual=0.04)).risk_free_series(dates), 0.04)
    assert np.isnan(CSVProvider(make_config(csv_dir=str(tmp_path), cash_leg="off")).risk_free_series(dates)).all()
    obs = pd.DataFrame({"DTB3": [5.0]}, index=pd.to_datetime(["2024-01-01"]))
    monkeypatch.setattr(fred_mod, "_default", FredClient(fetch=lambda url: obs))
    assert np.allclose(CSVProvider(make_config(csv_dir=str(tmp_path), cash_leg="fred")).risk_free_series(dates), 0.05)


# ================================================= finding 35: FRED cache hygiene
def _dff(end: date, days: int = 60) -> pd.DataFrame:
    idx = pd.date_range(end - timedelta(days=days), end, freq="D")
    return pd.DataFrame({"DFF": 4.33}, index=pd.Index(idx, name="observation_date"))


def test_fred_disk_cache_expires_and_stale_cache_no_longer_yields_static_rates(tmp_path, monkeypatch):
    today = date.today()
    march = today - timedelta(days=200)
    calls = []

    def fetch(url):
        calls.append(url)
        return _dff(today - timedelta(days=1))
    # a cache written 200 days ago (an old `evaluate --fred-cache` run)
    old = FredClient(cache_dir=tmp_path, fetch=lambda url: _dff(march))
    assert old.rate("USD", march) == 4.33
    stamp = time.mktime((march + timedelta(days=1)).timetuple())
    os.utime(tmp_path / "DFF.csv", (stamp, stamp))
    # v0.7: served forever -> rate None today -> fx_macro fell back to the static table
    fresh = FredClient(cache_dir=tmp_path, fetch=fetch)
    assert fresh.rate("USD", today) == 4.33 and len(calls) == 1
    assert (time.time() - (tmp_path / "DFF.csv").stat().st_mtime) < 60          # rewritten
    again = FredClient(cache_dir=tmp_path, fetch=fetch)
    assert again.rate("USD", today) == 4.33 and len(calls) == 1                  # within the day: no download
    forever = FredClient(cache_dir=tmp_path, fetch=fetch, cache_max_age_days=None)
    os.utime(tmp_path / "DFF.csv", (stamp, stamp))
    assert forever.rate("USD", today) == 4.33 and len(calls) == 1                # None keeps files forever
    # the config key reaches default_client and is part of its identity
    monkeypatch.setattr(fred_mod, "_default", None)
    monkeypatch.setattr(fred_mod, "_defaults", {})
    a = default_client(make_config(fred_cache_dir=str(tmp_path)))
    b = default_client(make_config(fred_cache_dir=str(tmp_path), fred_cache_max_age_days=None))
    assert a.cache_max_age_days == 1.0 and b.cache_max_age_days is None and a is not b
    # and a live EURUSD decision on a stale cache with no download possible has no macro at all
    monkeypatch.setattr(fred_mod, "_default", FredClient(cache_dir=tmp_path, fetch=lambda u: (_ for _ in ()).throw(RuntimeError("offline"))))
    os.utime(tmp_path / "DFF.csv", (stamp, stamp))
    assert fx_macro(Instrument.parse("EURUSD"), today, make_config(), real_world=True) == {}


def test_fred_download_is_validated_before_it_is_persisted(tmp_path):
    import io
    html = "<!DOCTYPE html>\n<html><head><title>Service Unavailable</title></head><body><h1>down</h1></body></html>\n"
    n = []

    def html_fetch(url):
        n.append(url)
        return pd.read_csv(io.StringIO(html), index_col=0, parse_dates=True)   # what a 200 HTML body parses to
    c = FredClient(cache_dir=tmp_path, fetch=html_fetch)
    assert c.rate("USD", date.today()) is None and len(n) == 1
    assert not (tmp_path / "DFF.csv").exists()                                  # v0.7 wrote the poison file
    good = FredClient(cache_dir=tmp_path, fetch=lambda url: _dff(date.today() - timedelta(days=1)))
    assert good.rate("USD", date.today()) == 4.33 and (tmp_path / "DFF.csv").exists()
    empty = FredClient(cache_dir=tmp_path / "e", fetch=lambda url: pd.DataFrame({"X": []}, index=pd.DatetimeIndex([])))
    assert empty.rate("USD", date.today()) is None and not (tmp_path / "e" / "DFF.csv").exists()
    # vintage snapshots are immutable and never expire
    v = FredClient(vintages=True, cache_dir=tmp_path, fetch=lambda url: _dff(date(2020, 1, 1)))
    spec = FredSeries("CPIAUCSL", 45, 120, revised=True)
    v.value_asof(spec, date(2020, 3, 1))
    f = next(p for p in tmp_path.iterdir() if p.name.startswith("CPIAUCSL_v"))
    stamp = time.time() - 400 * 86400
    os.utime(f, (stamp, stamp))
    calls = []
    v2 = FredClient(vintages=True, cache_dir=tmp_path, fetch=lambda url: calls.append(url) or _dff(date(2020, 1, 1)))
    v2.value_asof(spec, date(2020, 3, 1))
    assert calls == []


def test_http_fetch_uses_a_timeout(monkeypatch):
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"observation_date,DFF\n2024-01-02,5.33\n"

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return _Resp()
    monkeypatch.setattr(fred_mod, "urlopen", fake_urlopen)
    df = fred_mod._http_fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFF")
    assert seen["timeout"] and seen["timeout"] > 0
    assert float(df.iloc[0, 0]) == 5.33 and isinstance(df.index, pd.DatetimeIndex)


def test_http_fetch_identifies_itself_and_retries_one_transient_failure(monkeypatch):
    """Measured 2026-09-27: FRED stalls "agentic-trader (pandas)" for the whole timeout and
    closes the connection on a browser UA, but serves "agentic-trader/<version> (+url)" in
    0.1 s -- so the UA is part of availability, and one dropped connection is retried."""
    calls = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"observation_date,DTB3\n2024-01-02,5.20\n"

    def flaky_urlopen(req, timeout=None):
        calls.append(req.get_header("User-agent"))
        if len(calls) == 1:
            raise ConnectionResetError("Remote end closed connection without response")
        return _Resp()

    def dead_urlopen(req, timeout=None):
        calls.append(req.get_header("User-agent"))
        raise ConnectionResetError("Remote end closed connection without response")

    monkeypatch.setattr(fred_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(fred_mod, "urlopen", flaky_urlopen)
    df = fred_mod._http_fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3")
    assert len(calls) == 2 and float(df.iloc[0, 0]) == 5.20
    ua = calls[0]
    product, _, rest = ua.partition("/")
    assert product == "agentic-trader" and rest[0].isdigit(), ua
    assert rest.endswith(" (+https://github.com/AshJha0/agentic-trader)"), ua
    assert ua == fred_mod.USER_AGENT
    calls.clear()
    monkeypatch.setattr(fred_mod, "urlopen", dead_urlopen)
    with pytest.raises(ConnectionResetError):
        fred_mod._http_fetch("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3")
    assert len(calls) == 2


# ======================================== finding 36: no in-progress bar from Yahoo
class _FakeYF:
    def __init__(self, today: date):
        self.today = today
        self.calls: list[tuple] = []
        self.partial_close = 100.0

    def download(self, sym, start=None, end=None, auto_adjust=True, progress=False, actions=False):
        self.calls.append((sym, start, end, auto_adjust, actions))
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        last = min(e - pd.Timedelta(days=1), pd.Timestamp(self.today) - pd.Timedelta(days=1))
        idx = pd.bdate_range(s, last)
        if e > pd.Timestamp(self.today):                       # the session in progress today
            idx = idx.append(pd.DatetimeIndex([pd.Timestamp(self.today)]))
        n = len(idx)
        close = 100.0 + 0.01 * np.arange(n)
        df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close,
                           "Volume": np.full(n, 5e7)}, index=idx)
        if not auto_adjust:
            df["Stock Splits"] = 0.0
        if n and idx[-1].date() == self.today:
            df.loc[idx[-1], ["Open", "High", "Low", "Close"]] = self.partial_close
            df.loc[idx[-1], "Volume"] = 1000.0
        return df

    def Ticker(self, sym):
        return types.SimpleNamespace(news=[], info={})


@pytest.fixture
def fake_yahoo(monkeypatch):
    today = date(2026, 9, 23)                                   # a Wednesday
    yf = _FakeYF(today)
    monkeypatch.setitem(sys.modules, "yfinance", yf)
    monkeypatch.setattr(yahoo_mod, "_today", lambda: yf.today)
    from agentic_trader.data.yahoo import YahooProvider
    p = YahooProvider(make_config(data_provider="yahoo", edgar=False))
    return p, yf


def test_yahoo_never_serves_or_caches_todays_partial_bar(fake_yahoo):
    p, yf = fake_yahoo
    ins = Instrument.parse("AAPL")
    today = yf.today
    h1 = p.history(ins, today - timedelta(days=120), today)
    assert len(yf.calls) == 1 and h1.index[-1].date() == today - timedelta(days=1)
    assert not (h1.index >= pd.Timestamp(today)).any()
    # later the same day the market has moved: still no partial bar and no re-download
    yf.partial_close = 137.0
    h2 = p.history(ins, today - timedelta(days=120), today)
    assert len(yf.calls) == 1 and h2.index[-1].date() == today - timedelta(days=1)
    pd.testing.assert_frame_equal(h1, h2)
    assert p.history(ins, today - timedelta(days=30), today - timedelta(days=1)).index[-1].date() == today - timedelta(days=1)
    assert len(yf.calls) == 1
    assert p._covered[ins.yahoo_symbol][1] == today - timedelta(days=1)
    # a request only for today is empty rather than a stub bar
    assert p.history(ins, today, today).empty
    # tomorrow, today's bar is complete and is fetched exactly once
    yf.today = today + timedelta(days=1)
    h3 = p.history(ins, today - timedelta(days=120), yf.today)
    assert len(yf.calls) == 2 and h3.index[-1].date() == today
    assert float(h3["Close"].iloc[-1]) != 137.0                # the complete bar, not the morning stub
    assert p.history(ins, today - timedelta(days=120), yf.today).index[-1].date() == today and len(yf.calls) == 2


def test_yahoo_corporate_actions_refresh_daily_and_exclude_today(fake_yahoo):
    p, yf = fake_yahoo
    ins = Instrument.parse("AAPL")
    today = yf.today
    a = p._corporate_actions(ins.yahoo_symbol)
    assert a.index[-1].date() == today - timedelta(days=1) and len(yf.calls) == 1
    assert p.as_traded_close(ins, today) == float(a["RawClose"].iloc[-1])
    p.as_traded_close(ins, today)
    assert len(yf.calls) == 1                                    # same day: cached
    yf.today = today + timedelta(days=1)
    b = p._corporate_actions(ins.yahoo_symbol)
    assert len(yf.calls) == 2 and b.index[-1].date() == today   # new day: refreshed, yesterday now complete
    # a table supplied directly (tests, replays) is trusted as is
    p._actions[ins.yahoo_symbol] = pd.DataFrame({"RawClose": [1.0], "Split": [0.0]}, index=pd.to_datetime(["2024-01-02"]))
    p._actions_day.pop(ins.yahoo_symbol)
    assert p.as_traded_close(ins, date(2024, 1, 3)) == 1.0 and len(yf.calls) == 2


# =================================================== finding 37: CSV on one basis
def _write(tmp_path, name, rows, header):
    (tmp_path / name).write_text(header + "\n" + "\n".join(rows) + "\n")


def test_csv_adj_close_without_close_drops_raw_ohl(tmp_path, caplog):
    rows = [f"2024-01-{i + 1:02d},{100 + i},{102 + i},{99 + i},{round(0.606 * (100 + i), 4)},1000" for i in range(10)]
    _write(tmp_path, "XYZ.csv", rows, "Date,Open,High,Low,Adj Close,Volume")
    with caplog.at_level("WARNING"):
        h = CSVProvider(make_config(csv_dir=str(tmp_path))).history(Instrument.parse("XYZ"), date(2024, 1, 1), date(2024, 1, 31))
    assert (h["Open"] == h["Close"]).all() and (h["High"] == h["Close"]).all() and (h["Low"] == h["Close"]).all()
    assert h["Close"].iloc[0] == pytest.approx(60.6)                           # v0.7: Open 100 / Close 60.6
    assert any("intraday levels are unavailable" in r.message for r in caplog.records)


def test_csv_close_and_adj_close_put_every_price_column_on_the_adjusted_basis(tmp_path):
    rows = [f"2024-01-{i + 1:02d},{100 + i},{104 + i},{98 + i},{101 + i},{round(0.5 * (101 + i), 4)},1000" for i in range(10)]
    _write(tmp_path, "ADJ.csv", rows, "Date,Open,High,Low,Close,Adj Close,Volume")
    h = CSVProvider(make_config(csv_dir=str(tmp_path))).history(Instrument.parse("ADJ"), date(2024, 1, 1), date(2024, 1, 31))
    assert h["Close"].iloc[0] == pytest.approx(50.5)
    assert (h["Open"] / h["Close"]).round(6).tolist() == pytest.approx([(100 + i) / (101 + i) for i in range(10)])
    assert (h["High"] / h["Close"]).round(6).tolist() == pytest.approx([(104 + i) / (101 + i) for i in range(10)])
    assert (h["Low"] / h["Close"]).round(6).tolist() == pytest.approx([(98 + i) / (101 + i) for i in range(10)])
    # Close only: served as is
    _write(tmp_path, "RAW.csv", [f"2024-01-{i + 1:02d},{100 + i},{104 + i},{98 + i},{101 + i}" for i in range(3)],
           "Date,Open,High,Low,Close")
    r = CSVProvider(make_config(csv_dir=str(tmp_path))).history(Instrument.parse("RAW"), date(2024, 1, 1), date(2024, 1, 31))
    assert r["Close"].tolist() == [101, 102, 103] and r["Open"].tolist() == [100, 101, 102]


# ============================================ finding 68: synthetic FX start levels
def test_synthetic_fx_spread_is_sane_for_every_pair_and_classic_pairs_are_unchanged():
    cfg = make_config()
    p = SyntheticProvider(cfg)
    start = date(2022, 1, 3)
    pips = cfg["costs"]["fx_spread_pips"]
    for sym in [s for s in UNIVERSES["all"] if Instrument.parse(s).is_fx] + ["NZDJPY", "CHFJPY"]:
        ins = Instrument.parse(sym)
        p0 = float(p.history(ins, start, date(2022, 3, 1))["Close"].iloc[0])
        half_spread_bps = pips * ins.pip_size / p0 * 1e4 / 2                    # backtest_config_for's formula
        assert 0.1 <= half_spread_bps <= 2.0, (sym, p0, half_spread_bps)      # v0.7: GBPJPY 45 bp, AUDJPY 38, CADJPY 24
    for sym in ("GBPJPY", "AUDJPY", "CADJPY", "NZDJPY", "CHFJPY", "USDSEK", "USDNOK", "EURAUD"):
        ins = Instrument.parse(sym)
        level = fx_start_level(ins, 1.0)
        assert (60 < level < 250) if ins.quote == "JPY" else (0.4 < level < 12), (sym, level)
    # the classic pairs start where they did, so every published synthetic path is unchanged
    first = {s: round(float(p.history(Instrument.parse(s), start, date(2022, 3, 1))["Close"].iloc[0]), 4)
             for s in ("EURUSD", "USDJPY", "GBPUSD", "EURJPY", "EURGBP")}
    assert first == {"EURUSD": 1.0102, "USDJPY": 160.0664, "GBPUSD": 0.9468, "EURJPY": 133.535, "EURGBP": 0.825}


# ================================================== finding 69: FX headline subjects
@pytest.mark.parametrize("headline,base,quote,sign", [
    ("Dollar surges as Fed signals further tightening", "EUR", "USD", -1),
    ("Yen weakens as BoJ stays dovish", "USD", "JPY", +1),
    ("Dollar weakens; yen strengthens on hawkish BoJ", "USD", "JPY", -1),
    ("Greenback gains; euro falls to two-week low", "EUR", "USD", -1),
    ("Euro strengthens vs dollar", "EUR", "USD", +1),
    ("Sterling falls after BoE cuts", "GBP", "USD", -1),
    ("Pound rallies as Bank of England hikes", "EUR", "GBP", -1),
    ("Loonie gains as Bank of Canada hikes", "USD", "CAD", -1),
    ("Aussie weakens after RBA cuts", "AUD", "USD", -1),
    ("Kiwi surges on hawkish RBNZ", "NZD", "USD", +1),
    ("Swiss franc strengthens as SNB tightens", "USD", "CHF", -1),
    ("Krona slumps after Riksbank eases", "USD", "SEK", +1),
    ("Norges Bank hikes; krone climbs", "EUR", "NOK", -1),
    ("Fed cuts rates; dollar tumbles", "EUR", "USD", +1),
    ("ECB hikes as euro area growth beats", "EUR", "USD", +1),
    ("Australian dollar slides as US dollar firms", "AUD", "USD", -1),
    ("USD/JPY drops amid recession fears", "USD", "JPY", -1),
    ("JPY weakens after dovish comments", "USD", "JPY", +1),
    ("USD strengthens on strong data", "USD", "JPY", +1),
])
def test_fx_headlines_name_currencies_in_words_with_the_right_sign(headline, base, quote, sign):
    assert np.sign(score_fx_headline(headline, base, quote)) == sign, headline


def test_fx_currency_codes_match_whole_words_only():
    assert score_fx_headline("Audit finds strong growth at Cadence", "USD", "CAD") > 0   # "CADENCE" is not CAD
    assert score_fx_headline("CAD strengthens on strong jobs data", "USD", "CAD") < 0
    assert score_fx_headline("Traders await USD inflation data", "EUR", "USD") == 0.0
    assert score_fx_headline("Hawkish JPY policymakers boost JPY, pressuring USD/JPY", "USD", "JPY") < 0


# =========================================== finding 88: independent fundamentals RNG
def test_synthetic_valuation_is_not_a_function_of_volatility():
    p = SyntheticProvider(make_config())
    as_of = date(2024, 2, 15)
    rows = []
    for sym in UNIVERSES["all"]:
        ins = Instrument.parse(sym)
        if ins.is_fx:
            continue
        h = p.history(ins, date(2023, 2, 15), as_of)
        f = p.fundamentals(ins, as_of)
        rows.append((float(np.log(h["Close"]).diff().std() * np.sqrt(252)), float(h["Close"].iloc[0]),
                     f["pe_ratio"], f["revenue_growth_yoy"]))
    df = pd.DataFrame(rows, columns=["rvol", "p0", "pe", "g"])
    rho_pe = df["rvol"].rank().corr(df["pe"].rank())
    rho_g = df["p0"].rank().corr(df["g"].rank())
    assert len(df) == 45
    assert abs(rho_pe) < 0.3, rho_pe                            # v0.7: 0.76 (P/E was an affine map of base vol)
    assert abs(rho_g) < 0.3, rho_g                              # v0.7: 0.53 (growth was an affine map of p0)
    # not monotone: the P/E ranking is not the volatility ranking in either direction
    assert not df.sort_values("rvol")["pe"].is_monotonic_increasing
    assert not df.sort_values("rvol")["pe"].is_monotonic_decreasing
    # still deterministic and seed-sensitive, with the publication lag intact
    assert p.fundamentals(Instrument.parse("MSFT"), as_of) == SyntheticProvider(make_config()).fundamentals(Instrument.parse("MSFT"), as_of)
    assert p.fundamentals(Instrument.parse("MSFT"), as_of)["report_period_end"] == "2023-12-31"
    assert SyntheticProvider(make_config(synthetic_seed=8)).fundamentals(Instrument.parse("MSFT"), as_of)["pe_ratio"] != \
        p.fundamentals(Instrument.parse("MSFT"), as_of)["pe_ratio"]
