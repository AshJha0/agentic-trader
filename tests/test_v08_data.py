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
    # The same -18% re-print in a filing where it is the comparative of nothing new (the
    # FY2023 10-K) is a material change no other span corroborates: it is ignored and the
    # figure held stands (v0.8 first cut let it replace the earlier print, so an annual span
    # re-printed alone on a new basis was differenced against old-basis quarters).
    lone = base + [_f("2022-04-01", "2022-06-30", 90, "2024-02-01", "10-K")]
    k = _edgar({G: lone}).fundamentals("TST", date(2024, 3, 1))
    assert k["revenue_ttm"] == 620 and k["report_period_end"] == "2023-12-31"
    assert k["revenue_growth_yoy"] == pytest.approx(620 / (100 + 110 + 120 + 130) - 1, abs=1e-4)


def _nvda_shaped(h1_reprint=2.230, q3_reprint=2.636):
    """NVIDIA FY2017-FY2018 (calendar-quarter stand-in): the FY2018 10-K re-prints the six-month
    span 2017-01..06 as 2.230 (the second quarter's value; every other print is 4.167), a lone
    erroneous fact, and everything else unchanged."""
    r = _quarters(G, 2016, [1.305, 1.428, 2.004, 2.173], ["2016-05-20", "2016-08-19", "2016-11-22", "2017-03-01"])
    r += [_f("2016-01-01", "2016-12-31", 6.910, "2017-03-01", "10-K"),
          _f("2017-01-01", "2017-03-31", 1.937, "2017-05-23"),
          _f("2017-04-01", "2017-06-30", 2.230, "2017-08-23"), _f("2017-01-01", "2017-06-30", 4.167, "2017-08-23"),
          _f("2017-07-01", "2017-09-30", 2.636, "2017-11-21"), _f("2017-01-01", "2017-09-30", 6.803, "2017-11-21"),
          _f("2017-01-01", "2017-12-31", 9.714, "2018-02-28", "10-K"), _f("2017-10-01", "2017-12-31", 2.911, "2018-02-28", "10-K"),
          _f("2017-01-01", "2017-03-31", 1.937, "2018-02-28", "10-K"), _f("2017-07-01", "2017-09-30", q3_reprint, "2018-02-28", "10-K"),
          _f("2017-01-01", "2017-06-30", h1_reprint, "2018-02-28", "10-K")]
    return {G: r}


def test_lone_divergent_reprint_is_a_revision_not_a_new_basis():
    c = _edgar(_nvda_shaped())
    f = c.fundamentals("TST", date(2018, 5, 15))
    # v0.8 first cut: the lone re-print opened a generation whose only H1 was 2.230, Q2 became
    # 2.230 - 1.937 = 0.293 and the trailing year 7.777 (+12.6%) instead of 9.714 (+40.6%).
    assert f["revenue_ttm"] == pytest.approx(9.714) and f["revenue_growth_yoy"] == pytest.approx(9.714 / 6.910 - 1, abs=1e-4)
    t = quarterly_table(_known(c, date(2018, 5, 15)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t["gen"]) == {0} and t.loc[pd.Timestamp("2017-06-30"), "val"] == pytest.approx(2.230)
    # Two spans re-printed materially in one filing recast the comparatives: a new basis, on
    # which the audited annual figure still governs the trailing year.
    g = _edgar(_nvda_shaped(q3_reprint=2.0))
    t2 = quarterly_table(_known(g, date(2018, 5, 15)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t2["gen"].iloc[-4:]) == {1} and set(t2["gen"].iloc[:4]) == {0}
    h = g.fundamentals("TST", date(2018, 5, 15))
    assert h["revenue_ttm"] == pytest.approx(9.714) and "revenue_growth_yoy" not in h


def _q1_restatement():
    """A basis change effective from the first quarter: the Q1-2022 10-Q restates its single
    comparative (Q1-2021, -20%) alongside the new quarter; later filings restate the rest."""
    r = _quarters(G, 2021, [10, 11, 12, 13], ["2021-04-28", "2021-07-28", "2021-10-27", "2022-02-01"])
    r += [_f("2021-01-01", "2021-12-31", 46, "2022-02-01", "10-K"),
          _f("2022-01-01", "2022-03-31", 9, "2022-04-28"), _f("2021-01-01", "2021-03-31", 8, "2022-04-28"),
          _f("2022-04-01", "2022-06-30", 9.5, "2022-07-28"), _f("2022-01-01", "2022-06-30", 18.5, "2022-07-28"),
          _f("2021-04-01", "2021-06-30", 8.8, "2022-07-28"), _f("2021-01-01", "2021-06-30", 16.8, "2022-07-28"),
          _f("2022-07-01", "2022-09-30", 10, "2022-10-27"), _f("2022-01-01", "2022-09-30", 28.5, "2022-10-27"),
          _f("2021-07-01", "2021-09-30", 9.6, "2022-10-27"), _f("2021-01-01", "2021-09-30", 26.4, "2022-10-27"),
          _f("2022-01-01", "2022-12-31", 39, "2023-02-01", "10-K"), _f("2022-10-01", "2022-12-31", 10.5, "2023-02-01", "10-K"),
          _f("2021-01-01", "2021-12-31", 36.8, "2023-02-01", "10-K"), _f("2021-10-01", "2021-12-31", 10.4, "2023-02-01", "10-K")]
    r += _quarters(G, 2022, [9, 9.5, 10], ["2023-02-01"] * 3, ["10-K"] * 3)
    r += _quarters(G, 2021, [8, 8.8, 9.6], ["2023-02-01"] * 3, ["10-K"] * 3)
    return {G: r}


def test_first_quarter_restatement_of_its_single_comparative_opens_a_basis():
    c = _edgar(_q1_restatement())
    # After the Q1 10-Q the new quarter is on the new basis: it is not summed with three old-basis
    # quarters (11 + 12 + 13 + 9 = 45, which a two-span-only rule would report); the last complete
    # year on one basis stands until the new basis has four quarters.
    f = c.fundamentals("TST", date(2022, 5, 15))
    assert f["revenue_ttm"] == 46 and f["report_period_end"] == "2021-12-31"
    assert c.fundamentals("TST", date(2022, 8, 15))["revenue_ttm"] == 46
    g = c.fundamentals("TST", date(2023, 3, 1))
    assert g["revenue_ttm"] == 39 and g["revenue_growth_yoy"] == pytest.approx(39 / 36.8 - 1, abs=1e-4)
    t = quarterly_table(_known(c, date(2023, 3, 1)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t["gen"].iloc[-8:]) == {1}


def _amzn_shaped(consistent_10k=False):
    """Amazon FY2012: the 10-K tags the 2012 quarter spans with the 2011 values and the 2011
    quarter spans with the 2012 values (the annual spans are right); the 2013 10-Qs then
    re-print the 2012 comparatives correctly."""
    y11 = [9.857, 9.913, 10.876, 17.431]
    y12 = [13.185, 12.834, 13.806, 21.268]
    r = _quarters("SalesRevenueNet", 2011, y11, ["2011-04-27", "2011-07-27", "2011-10-26", "2012-02-01"])
    r += [_f("2011-01-01", "2011-12-31", 48.077, "2012-02-01", "10-K"),
          _f("2012-01-01", "2012-03-31", 13.185, "2012-04-27"),
          _f("2012-04-01", "2012-06-30", 12.834, "2012-07-27"), _f("2012-01-01", "2012-06-30", 26.019, "2012-07-27"),
          _f("2012-07-01", "2012-09-30", 13.806, "2012-10-26"), _f("2012-01-01", "2012-09-30", 39.825, "2012-10-26"),
          _f("2012-01-01", "2012-12-31", 61.093, "2013-01-30", "10-K"), _f("2011-01-01", "2011-12-31", 48.077, "2013-01-30", "10-K")]
    r += _quarters("SalesRevenueNet", 2012, y12 if consistent_10k else y11, ["2013-01-30"] * 4, ["10-K"] * 4)
    r += _quarters("SalesRevenueNet", 2011, y11 if consistent_10k else y12, ["2013-01-30"] * 4, ["10-K"] * 4)
    r += [_f("2013-01-01", "2013-03-31", 16.070, "2013-04-26"), _f("2012-01-01", "2012-03-31", 13.185, "2013-04-26"),
          _f("2013-04-01", "2013-06-30", 15.704, "2013-07-26"), _f("2013-01-01", "2013-06-30", 31.774, "2013-07-26"),
          _f("2012-04-01", "2012-06-30", 12.834, "2013-07-26"), _f("2012-01-01", "2012-06-30", 26.019, "2013-07-26")]
    return {"SalesRevenueNet": r}


def test_mis_tagged_10k_comparatives_yield_the_audited_annual_figure(caplog):
    c = _edgar(_amzn_shaped())
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        f = c.fundamentals("TST", date(2013, 2, 15))
        c.fundamentals("TST", date(2013, 3, 1))
    # v0.8 first cut: the four mis-tagged direct quarters summed to exactly FY2011 (48.077, growth
    # -21.3%) with the same filing's 61.093 annual span ignored. Second cut: the re-prints opened
    # a "new basis" of swapped quarters. Now the recast fails its own annual reconciliation, is
    # rejected as mis-tagged and logged once; Q4-2012 is the audited annual less the held nine months.
    assert f["revenue_ttm"] == pytest.approx(61.093) and f["revenue_growth_yoy"] == pytest.approx(61.093 / 48.077 - 1, abs=1e-4)
    msgs = [r.getMessage() for r in caplog.records if "SalesRevenueNet" in r.getMessage()]
    assert len(msgs) == 1 and "mis-tagged" in msgs[0] and "2013-01-30" in msgs[0]
    # The quarters stay as first printed on the one basis; the 2013 10-Qs' comparatives agree with
    # them; the trailing year is FY less the year-earlier quarters plus the new ones (63.978 =
    # 61.093 - 13.185 + 16.070).
    assert c.fundamentals("TST", date(2013, 5, 15))["revenue_ttm"] == pytest.approx(61.093 - 13.185 + 16.070)
    assert c.fundamentals("TST", date(2013, 8, 15))["revenue_ttm"] == pytest.approx(61.093 - 13.185 - 12.834 + 16.070 + 15.704)
    t = quarterly_table(_known(c, date(2013, 8, 15)), edgar_mod.REVENUE_TAGS, positive=True)
    assert set(t["gen"]) == {0}
    # a 10-K whose quarters agree with its annual span is taken as printed, with nothing logged
    caplog.clear()
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        g = _edgar(_amzn_shaped(consistent_10k=True)).fundamentals("TST", date(2013, 2, 15))
    assert g["revenue_ttm"] == pytest.approx(61.093) and not [r for r in caplog.records if "SalesRevenueNet" in r.getMessage()]


# ================== regression review of v0.8: material changes must be corroborated
def _ko_shaped():
    """Coca-Cola 2018-2019: an 8-K (2019-09-20) re-prints FY2018 alone on a new basis (+7.7%),
    the Q3-2019 10-Q recasts Q3/9M-2018 (a corroborated new basis) and the FY2019 10-K prints
    both years' annual spans and quarters on it. Net income is not recast."""
    f18 = ["2018-04-25", "2018-07-26", "2018-10-30", "2019-02-21"]
    f19 = ["2019-04-25", "2019-07-25", "2019-10-24", "2020-02-24"]
    r = _quarters(N, 2018, [7.626, 8.927, 8.245], f18[:3]) + [
        _f("2018-01-01", "2018-09-30", 24.798, f18[2]), _f("2018-01-01", "2018-12-31", 31.856, f18[3], "10-K"),
        _f("2019-01-01", "2019-03-31", 8.020, f19[0]), _f("2019-04-01", "2019-06-30", 9.997, f19[1]),
        _f("2019-01-01", "2019-06-30", 18.017, f19[1]),
        _f("2018-01-01", "2018-12-31", 34.300, "2019-09-20", "8-K"),                # the lone re-print
        _f("2019-07-01", "2019-09-30", 9.507, f19[2]), _f("2019-01-01", "2019-09-30", 28.198, f19[2]),
        _f("2018-07-01", "2018-09-30", 8.775, f19[2]), _f("2018-01-01", "2018-09-30", 26.494, f19[2]),
        _f("2019-01-01", "2019-12-31", 37.266, f19[3], "10-K"), _f("2018-01-01", "2018-12-31", 34.300, f19[3], "10-K")]
    r += _quarters(N, 2019, [8.694, 9.997, 9.507, 9.068], [f19[3]] * 4, ["10-K"] * 4)
    r += _quarters(N, 2018, [8.303, 9.416, 8.775, 7.806], [f19[3]] * 4, ["10-K"] * 4)
    ni = _quarters("NetIncomeLoss", 2018, [1.4, 2.3, 1.9, 0.9], f18) + _quarters("NetIncomeLoss", 2019, [1.7, 2.6, 2.6, 2.0], f19)
    return {N: r, "NetIncomeLoss": ni}


def test_lone_material_reprint_is_ignored_never_spliced_into_the_held_basis(caplog):
    c = _edgar(_ko_shaped())
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        f = c.fundamentals("TST", date(2019, 10, 25))
        c.fundamentals("TST", date(2019, 11, 25))
    t = quarterly_table(_known(c, date(2019, 10, 25)), edgar_mod.REVENUE_TAGS, positive=True)
    # v0.8 first cut: the 8-K's FY2018 replaced the held figure inside the old basis, so Q4-2018 was
    # 34.300 (new basis) - 24.798 (old-basis nine months) = 9.502 against 7.058 printed, and the
    # trailing year 35.764 was on no basis. The lone re-print is ignored and logged once.
    assert t.loc[pd.Timestamp("2018-12-31"), "val"] == pytest.approx(31.856 - 24.798)
    assert 9.502 not in set(t["val"].round(3)) and set(t["gen"]) == {0}
    assert f["revenue_ttm"] == pytest.approx(8.245 + 7.058 + 8.020 + 9.997)
    assert f["report_period_end"] == "2019-09-30" and f["revenue_period_end"] == "2019-06-30" and "net_margin" not in f
    msgs = [r.getMessage() for r in caplog.records if "2018-01-01..2018-12-31" in r.getMessage()]
    assert len(msgs) == 1 and "ignored" in msgs[0] and "2019-09-20" in msgs[0]
    # On the corroborated basis the same annual figure is differenced against the recast nine
    # months: Q4-2018 is 7.806, the 2019 year 37.266 and growth is measured on one basis.
    g = c.fundamentals("TST", date(2020, 3, 1))
    t2 = quarterly_table(_known(c, date(2020, 3, 1)), edgar_mod.REVENUE_TAGS, positive=True)
    assert t2.loc[pd.Timestamp("2018-12-31"), "val"] == pytest.approx(34.300 - 26.494) and set(t2["gen"].iloc[-8:]) == {1}
    assert g["revenue_ttm"] == pytest.approx(37.266) and g["revenue_growth_yoy"] == pytest.approx(37.266 / 34.300 - 1, abs=1e-4)
    assert "revenue_period_end" not in g


def _jpm_shaped(reprint=4.924, repeat=None):
    """JPMorgan 2012-2013: Q1-2012 net income first printed 5.383 (10-Q 2012-05-10); the 10-Q/A of
    2012-08-09 re-prints it alone as 4.924 (the London Whale restatement, -8.5%), and the Q1-2013
    10-Q prints ``repeat`` (4.924 again) as the comparative of its first-print quarter. Every later
    span is on the restated basis; revenue is unchanged."""
    ni_tag = "NetIncomeLoss"
    f11 = ["2011-05-06", "2011-08-05", "2011-11-04", "2012-02-29"]
    f12 = ["2012-05-10", "2012-08-09", "2012-11-08", "2013-02-28"]
    f13 = ["2013-05-08", "2013-08-07", "2013-11-01"]
    ni = _quarters(ni_tag, 2011, [5.555, 5.431, 4.262, 3.728], f11)
    ni += [_f("2012-01-01", "2012-03-31", 5.383, f12[0]),
           _f("2012-01-01", "2012-03-31", reprint, "2012-08-09", "10-Q/A"),
           _f("2012-04-01", "2012-06-30", 4.960, f12[1]), _f("2012-01-01", "2012-06-30", 9.884, f12[1]),
           _f("2012-07-01", "2012-09-30", 5.708, f12[2]), _f("2012-01-01", "2012-09-30", 15.592, f12[2]),
           _f("2012-01-01", "2012-12-31", 21.284, f12[3], "10-K"),                     # Q4 = 5.692
           _f("2013-01-01", "2013-03-31", 6.529, f13[0]), _f("2012-01-01", "2012-03-31", reprint if repeat is None else repeat, f13[0]),
           _f("2013-04-01", "2013-06-30", 6.496, f13[1]), _f("2012-04-01", "2012-06-30", 4.960, f13[1]),
           _f("2013-07-01", "2013-09-30", -0.380, f13[2]), _f("2012-07-01", "2012-09-30", 5.708, f13[2])]
    rev = _quarters(N, 2011, [24.0] * 4, f11) + _quarters(N, 2012, [24.0] * 4, f12) + _quarters(N, 2013, [24.0] * 3, f13)
    return {ni_tag: ni, N: rev}


def test_correction_confirmed_by_repetition_is_taken_in_place_and_opens_no_generation(caplog):
    """Final review of v0.8 (edgar.py:633): an ignored lone re-print was forgotten, so the same
    corrected value printed a year later as the comparative of a first-print quarter opened a
    two-span generation and the concept had no window for three quarters (JPM 2013, MSFT FY2017,
    NVDA FY2018 lost net_margin and served a frozen eps_ttm)."""
    c = _edgar(_jpm_shaped())
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        early = c.fundamentals("TST", date(2012, 8, 15))
        f = c.fundamentals("TST", date(2013, 5, 15))
        c.fundamentals("TST", date(2013, 6, 15))
    # the amendment alone is a lone material re-print: ignored, the first print held
    t0 = quarterly_table(_known(c, date(2012, 8, 15)), edgar_mod.NET_INCOME_TAGS)
    assert t0.loc[pd.Timestamp("2012-03-31"), "val"] == pytest.approx(5.383)
    assert early["net_margin"] == pytest.approx((4.262 + 3.728 + 5.383 + 4.960) / 96, abs=1e-4)
    # the Q1-2013 10-Q repeats it: a correction confirmed by repetition, taken in place on the one
    # basis; the window runs to the new quarter and the margin is served
    t = quarterly_table(_known(c, date(2013, 5, 15)), edgar_mod.NET_INCOME_TAGS)
    assert set(t["gen"]) == {0} and t.loc[pd.Timestamp("2012-03-31"), "val"] == pytest.approx(4.924)
    assert t.loc[pd.Timestamp("2012-12-31"), "val"] == pytest.approx(21.284 - 15.592)
    assert f["report_period_end"] == "2013-03-31" and "net_income_period_end" not in f
    assert f["net_margin"] == pytest.approx((4.960 + 5.708 + 5.692 + 6.529) / 96, abs=1e-4)
    assert c.fundamentals("TST", date(2013, 11, 15))["net_margin"] == pytest.approx((5.692 + 6.529 + 6.496 - 0.380) / 96, abs=1e-4)
    msgs = [r.getMessage() for r in caplog.records if "2012-01-01..2012-03-31" in r.getMessage()]
    assert len(msgs) == 2 and "ignored" in msgs[0] and "2012-08-09" in msgs[0]
    assert "confirmed by repetition" in msgs[1] and "2013-05-08" in msgs[1] and "4.924" in msgs[1]
    # a comparative that repeats nothing ignored is still a restatement of the single comparative
    # a first-quarter 10-Q prints: a new basis, with no window on it yet
    d = _edgar(_jpm_shaped(repeat=4.5))
    g = d.fundamentals("TST", date(2013, 5, 15))
    assert g["net_income_period_end"] == "2012-12-31" and "net_margin" not in g
    assert quarterly_table(_known(d, date(2013, 5, 15)), edgar_mod.NET_INCOME_TAGS).index.max() == pd.Timestamp("2012-12-31")


def _near_zero_recast(new18_q4=241e6):
    """A genuine continuing-operations recast printed by the FY2019 10-K (every 2018 and 2019 span
    re-printed materially) in a year whose net income nets to nearly nothing: the new-basis 2018
    quarters, tagged in millions, sum to -9M against an annual re-printed as -8M."""
    ni = "NetIncomeLoss"
    f18 = ["2018-04-25", "2018-07-26", "2018-10-30", "2019-02-21"]
    f19 = ["2019-04-25", "2019-07-25", "2019-10-24", "2020-02-24"]
    facts = _quarters(ni, 2018, [400e6, -900e6, 300e6, 180e6], f18) + [
        _f("2018-01-01", "2018-09-30", -200e6, f18[2]), _f("2018-01-01", "2018-12-31", -20e6, f18[3], "10-K"),
        _f("2019-01-01", "2019-03-31", 500e6, f19[0]),
        _f("2019-04-01", "2019-06-30", -700e6, f19[1]), _f("2019-01-01", "2019-06-30", -200e6, f19[1]),
        _f("2019-07-01", "2019-09-30", 250e6, f19[2]), _f("2019-01-01", "2019-09-30", 50e6, f19[2]),
        _f("2019-01-01", "2019-12-31", 130e6, f19[3], "10-K"), _f("2018-01-01", "2018-12-31", -8e6, f19[3], "10-K"),
        _f("2019-01-01", "2019-09-30", 30e6, f19[3], "10-K"), _f("2018-01-01", "2018-09-30", -250e6, f19[3], "10-K")]
    facts += _quarters(ni, 2019, [420e6, -600e6, 210e6, 100e6], [f19[3]] * 4, ["10-K"] * 4)
    facts += _quarters(ni, 2018, [300e6, -800e6, 250e6, new18_q4], [f19[3]] * 4, ["10-K"] * 4)
    rev = _quarters(N, 2018, [8e9] * 4, f18) + _quarters(N, 2019, [8.5e9] * 4, f19)
    return {ni: facts, N: rev}


def test_near_zero_annual_figure_is_reconciled_on_the_scale_of_its_quarters(caplog):
    """Final review of v0.8 (edgar.py:583): the additive tolerance was 2% of the annual figure
    alone, so a 1M rounding difference against an -8M year rejected a genuine recast as mis-tagged,
    spliced Q4-2019 across bases (130M new-basis annual less 50M of old-basis quarters) and warned
    twice against a correct filing. The reconstruction's Q4 cross-check (edgar.py:684) had the same
    fragility: it overrode the printed 241M Q4-2018 with 242M (AMZN NetIncomeLoss Q4-2012, 97M
    printed, was served as 98M with a warning at every cutoff from 2014)."""
    d = pd.Timestamp("2018-01-01") - pd.Timestamp("1970-01-01")
    y = [(d.days, d.days + 364, -8.0), (d.days, d.days + 89, 300.0), (d.days + 90, d.days + 180, -800.0),
         (d.days + 181, d.days + 272, 250.0), (d.days + 273, d.days + 364, 241.0)]
    assert edgar_mod._inconsistent(y, additive=True) == []
    assert edgar_mod._inconsistent(y[:-1] + [(d.days + 273, d.days + 364, 141.0)], additive=True) == [(d.days, d.days + 364, -109.0, -8.0)]
    c = _edgar(_near_zero_recast())
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        f = c.fundamentals("TST", date(2020, 3, 1))
    t = quarterly_table(_known(c, date(2020, 3, 1)), edgar_mod.NET_INCOME_TAGS)
    assert t.loc["2019"]["val"].tolist() == pytest.approx([420e6, -600e6, 210e6, 100e6]) and set(t["gen"].iloc[-8:]) == {1}
    assert t.loc["2018"]["val"].tolist() == pytest.approx([300e6, -800e6, 250e6, 241e6])
    assert f["net_margin"] == pytest.approx(130e6 / 34e9, abs=1e-4) and not caplog.records
    # quarters that miss the year by more than the tolerance of their own scale are still mis-tagged
    e = _edgar(_near_zero_recast(new18_q4=141e6))
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        e.fundamentals("TST", date(2020, 3, 1))
    te = quarterly_table(_known(e, date(2020, 3, 1)), edgar_mod.NET_INCOME_TAGS)
    assert set(te["gen"]) == {0} and sum("mis-tagged" in r.getMessage() for r in caplog.records) == 1


def test_mis_tagged_recast_is_rejected_and_never_manufactures_a_quarter(caplog):
    """The AMZN FY2012 10-K (2011 and 2012 quarter values swapped) recasts seven spans, enough
    to corroborate a basis change by count, but its quarters do not add up to its own annual
    spans: v0.8 second cut opened a generation of swapped quarters and the annual cross-check
    then set Q4-2011 := 48.077 - 39.825 = 8.252 and Q4-2012 := 30.447, so growth ran 9-24pp high
    for three quarters."""
    c = _edgar(_amzn_shaped())
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        t = quarterly_table(_known(c, date(2013, 2, 15)), edgar_mod.REVENUE_TAGS, positive=True)
        f = c.fundamentals("TST", date(2013, 4, 27))
    assert t.loc["2011"]["val"].round(3).tolist() == [9.857, 9.913, 10.876, 17.431]
    assert t.loc["2012"]["val"].round(3).tolist() == [13.185, 12.834, 13.806, 21.268]
    assert set(t["gen"]) == {0} and not {8.252, 30.447} & set(t["val"].round(3))
    assert f["revenue_growth_yoy"] == pytest.approx(0.2446, abs=0.01)            # v0.8 second cut: +33.1%
    msgs = [r.getMessage() for r in caplog.records if r.name == "agentic_trader.data.edgar"]
    assert len(msgs) == 1 and "mis-tagged" in msgs[0]                          # no "Q4 taken as" note either


def _eps_shaped(swap=False):
    """Diluted EPS of two years with the quarters of the second summing 17% short of its annual
    figure (Johnson & Johnson 2017: a tax-charge quarter and share-count changes), the 10-K
    printing Q4 directly. With ``swap`` the 10-K tags each year's quarters with the other's
    values (Amazon 2012), the annual spans right."""
    y1, y2 = [1.59, 1.43, 1.53, 1.38], [1.61, 1.40, 1.37, -3.99]
    f1 = ["2016-04-26", "2016-07-26", "2016-10-25", "2017-02-21"]
    f2 = ["2017-04-25", "2017-07-25", "2017-10-24", "2018-02-21"]
    e = _quarters("EarningsPerShareDiluted", 2016, y1, f1) + [_f("2016-01-01", "2016-12-31", 5.93, f1[3], "10-K")]
    e += _quarters("EarningsPerShareDiluted", 2017, y2[:3], f2[:3]) + [
        _f("2017-01-01", "2017-09-30", 4.38, f2[2]), _f("2017-01-01", "2017-12-31", 0.47, f2[3], "10-K")]
    e += _quarters("EarningsPerShareDiluted", 2017, y1 if swap else y2, [f2[3]] * 4, ["10-K"] * 4)
    e += _quarters("EarningsPerShareDiluted", 2016, y2 if swap else y1, [f2[3]] * 4, ["10-K"] * 4)
    rev = _quarters(N, 2016, [17.0] * 4, f1) + _quarters(N, 2017, [19.0] * 4, f2)
    return {"EarningsPerShareDiluted": e, N: rev}


def test_annual_cross_check_never_overrides_a_per_share_print(caplog):
    c = _edgar(_eps_shaped())
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        f = c.fundamentals("TST", date(2018, 3, 1), price=130.0)
    t = quarterly_table(_known(c, date(2018, 3, 1)), edgar_mod.EPS_TAGS, units=("USD/shares",))
    # v0.8 first cut: Q4 became 0.47 - 4.38 = -3.91 with a warning asserting mis-tagged comparatives
    assert t.loc[pd.Timestamp("2017-12-31"), "val"] == pytest.approx(-3.99)
    assert f["eps_ttm"] == pytest.approx(0.39) and not caplog.records
    # a per-share recast whose quarters are swapped between years is still rejected as mis-tagged
    # (gross inconsistency, far beyond what share counts explain): Q4 is the annual span less
    # the held nine months, and no swapped year is ever served
    d = _edgar(_eps_shaped(swap=True))
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        g = d.fundamentals("TST", date(2018, 3, 1), price=130.0)
    td = quarterly_table(_known(d, date(2018, 3, 1)), edgar_mod.EPS_TAGS, units=("USD/shares",))
    assert set(td["gen"]) == {0} and td.loc[pd.Timestamp("2017-12-31"), "val"] == pytest.approx(0.47 - 4.38)
    assert g["eps_ttm"] == pytest.approx(0.47) and sum("mis-tagged" in r.getMessage() for r in caplog.records) == 1


OCF, CAPEX = "NetCashProvidedByUsedInOperatingActivities", "PaymentsToAcquirePropertyPlantAndEquipment"


def _lly_shaped(recast=N, cash=False):
    """Eli Lilly 2018-2019: the 2019 10-Qs recast the 2018 comparatives of one series to continuing
    operations (-13%) one quarter at a time (a corroborated basis from the Q1 10-Q), so that
    series has no four-quarter window on the new basis until the Q3 10-Q; the others are unchanged.
    With ``cash`` the operating cash flow and capex series (direct quarters) are reported too."""
    f17 = ["2017-04-25", "2017-07-25", "2017-10-24", "2018-02-20"]
    f18 = ["2018-04-24", "2018-07-24", "2018-10-23", "2019-02-19"]
    facts = {}
    series = [(N, 1.0), ("NetIncomeLoss", 0.2), ("EarningsPerShareDiluted", 0.02)]
    if cash:
        series += [(OCF, 0.3e9), (CAPEX, 0.1e9)]
    for tag, scale in series:
        v = [x * scale for x in (5.2, 5.8, 5.7, 6.2, 5.70, 6.36, 6.06, 6.44, 6.0, 6.3)]
        facts[tag] = _quarters(tag, 2017, v[:4], f17) + _quarters(tag, 2018, v[4:8], f18) + [
            _f("2019-01-01", "2019-03-31", v[8], "2019-04-30"), _f("2019-04-01", "2019-06-30", v[9], "2019-08-01")]
        if tag == recast:
            facts[tag] += [_f("2018-01-01", "2018-03-31", 0.87 * v[4], "2019-04-30"),
                           _f("2018-04-01", "2018-06-30", 0.87 * v[5], "2019-08-01")]
    facts["dei:EntityCommonStockSharesOutstanding"] = [_f(None, "2019-06-30", 1e9, "2019-08-01")]
    return facts


def test_live_series_with_a_lagging_window_is_kept_and_flagged_not_dropped_as_dead():
    c = _edgar(_lly_shaped())
    f = c.fundamentals("TST", date(2019, 8, 3), price=100.0)
    # v0.8 first cut: the revenue window (to 2018-12-31) lagged the EPS-driven period end by 181 days
    # and was dropped as "stopped being reported" although the Q2 10-Q had just printed revenue.
    assert f["report_period_end"] == "2019-06-30" and f["revenue_period_end"] == "2018-12-31"
    assert f["revenue_ttm"] == pytest.approx(5.70 + 6.36 + 6.06 + 6.44)
    assert f["revenue_growth_yoy"] == pytest.approx(24.56 / 22.9 - 1, abs=1e-4)      # both years on the held basis
    assert "net_margin" not in f and f["eps_ttm"] == pytest.approx(0.02 * (6.06 + 6.44 + 6.0 + 6.3))
    # the lag of another series is reported under its own key, and the margin is never mixed
    g = _edgar(_lly_shaped(recast="NetIncomeLoss")).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert g["net_income_period_end"] == "2018-12-31" and "net_margin" not in g and "revenue_period_end" not in g
    assert g["revenue_ttm"] == pytest.approx(6.06 + 6.44 + 6.0 + 6.3)
    h = _edgar(_lly_shaped(recast="EarningsPerShareDiluted")).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert h["eps_period_end"] == "2018-12-31" and h["eps_ttm"] == pytest.approx(0.02 * 24.56)
    # a series no filing of the last MAX_FLOW_LAG_DAYS printed any span of is dead, whatever its window
    facts = _lly_shaped()
    facts["EarningsPerShareDiluted"] = [x for x in facts["EarningsPerShareDiluted"] if x["filed"] <= "2019-02-19"]
    k = _edgar(facts).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert "eps_ttm" not in k and k["report_period_end"] == "2019-06-30"


def test_fcf_needs_ocf_and_capex_windows_ending_together_and_flags_a_lagging_ocf_window():
    """Final review of v0.8 (edgar.py:536): free cash flow was operating cash flow of one window
    less capex of another (NVDA served OCF to 2016-07-31 less capex to 2012-10-28; KO an OCF window
    817 days stale), with no flag a consumer could read."""
    ocf_ttm, capex_ttm, cap = 0.3e9 * 24.8, 0.1e9 * 24.8, 100.0 * 1e9
    f = _edgar(_lly_shaped(cash=True)).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert f["fcf_yield"] == pytest.approx((ocf_ttm - capex_ttm) / cap, abs=1e-4) and "ocf_period_end" not in f
    # capex recast one comparative at a time: its window ends 2018-12-31, OCF's 2019-06-30
    g = _edgar(_lly_shaped(recast=CAPEX, cash=True)).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert "fcf_yield" not in g and "ocf_period_end" not in g and g["report_period_end"] == "2019-06-30"
    # the mirror case: the OCF window lags, and the lag is reported under its own key
    h = _edgar(_lly_shaped(recast=OCF, cash=True)).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert "fcf_yield" not in h and h["ocf_period_end"] == "2018-12-31" and "revenue_period_end" not in h
    # a filer that never reports capex has free cash flow equal to operating cash flow, flagged
    # when that window lags the report period
    facts = _lly_shaped(recast=OCF, cash=True)
    del facts[CAPEX]
    k = _edgar(facts).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert k["fcf_yield"] == pytest.approx(0.3e9 * (5.70 + 6.36 + 6.06 + 6.44) / cap, abs=1e-4)
    assert k["ocf_period_end"] == "2018-12-31"
    # once both windows are current again the flag is gone and the figure is back
    del facts[OCF]
    facts[OCF] = _lly_shaped(cash=True)[OCF]
    m = _edgar(facts).fundamentals("TST", date(2019, 8, 3), price=100.0)
    assert m["fcf_yield"] == pytest.approx(ocf_ttm / cap, abs=1e-4) and "ocf_period_end" not in m


# ==================================== finding 7 / 34: tag equivalence and concept continuity
def _renamed_tag(shared_q3=4.726, shared_q2=None):
    """NVIDIA FY2020-FY2021 shape: the 10-Qs print ``Revenues`` (direct quarters and year to
    date), the 10-K prints the annual span and one quarter (optionally two) under the new tag only."""
    filed20 = ["2020-05-21", "2020-08-19", "2020-11-18", "2021-02-26"]
    n = _quarters(N, 2019, [3.0, 3.1, 3.0, 3.1], ["2019-05-20", "2019-08-20", "2019-11-20", "2020-02-20"])
    n += [_f("2019-01-01", "2019-12-31", 12.2, "2020-02-20", "10-K"),
          _f("2020-01-01", "2020-03-31", 3.08, filed20[0]),
          _f("2020-04-01", "2020-06-30", 3.866, filed20[1]), _f("2020-01-01", "2020-06-30", 6.946, filed20[1]),
          _f("2020-07-01", "2020-09-30", 4.726, filed20[2]), _f("2020-01-01", "2020-09-30", 11.672, filed20[2])]
    g = [_f("2020-01-01", "2020-12-31", 16.675, filed20[3], "10-K"), _f("2020-07-01", "2020-09-30", shared_q3, filed20[3], "10-K")]
    if shared_q2 is not None:
        g.append(_f("2020-04-01", "2020-06-30", shared_q2, filed20[3], "10-K"))
    return {N: n, G: g}


def test_tag_rename_with_an_identical_span_is_one_concept_gross_and_net_are_not():
    c = _edgar(_renamed_tag())
    known = _known(c, date(2021, 3, 1))
    t = quarterly_table(known, edgar_mod.REVENUE_TAGS, positive=True)
    # v0.8 first cut: no tag held both the annual and the nine-month span, Q4 was lost and the
    # trailing year stayed at the September window (14.772) for as long as the 10-K was the
    # only source of Q4.
    assert t.loc[pd.Timestamp("2020-12-31"), "val"] == pytest.approx(16.675 - 11.672)
    assert set(t["tag"]) == {G} and len(t) == 8                     # one concept, labelled by its best-ranked tag
    f = c.fundamentals("TST", date(2021, 3, 1))
    assert f["revenue_ttm"] == pytest.approx(16.675) and f["revenue_growth_yoy"] == pytest.approx(16.675 / 12.2 - 1, abs=1e-4)
    sub = edgar_mod._pick(known, edgar_mod.REVENUE_TAGS, None).dropna(subset=["start"])
    assert edgar_mod._tag_classes(sub, edgar_mod.REVENUE_TAGS) == [[G, N]]
    # a shared span that differs by 3% is another concept: the tags stay apart and Q4 is not built
    d = _edgar(_renamed_tag(shared_q3=4.726 * 1.03))
    kd = _known(d, date(2021, 3, 1))
    assert edgar_mod._tag_classes(edgar_mod._pick(kd, edgar_mod.REVENUE_TAGS, None).dropna(subset=["start"]),
                                  edgar_mod.REVENUE_TAGS) == [[G], [N]]
    assert d.fundamentals("TST", date(2021, 3, 1))["revenue_ttm"] == pytest.approx(3.1 + 3.08 + 3.866 + 4.726)
    # ...and so do tags that agree on one shared span but not on another (net income with and
    # without the non-controlling interest, which is nil in some quarters): every shared span must agree
    e = _edgar(_renamed_tag(shared_q2=3.866 * 1.03))
    ke = _known(e, date(2021, 3, 1))
    assert edgar_mod._tag_classes(edgar_mod._pick(ke, edgar_mod.REVENUE_TAGS, None).dropna(subset=["start"]),
                                  edgar_mod.REVENUE_TAGS) == [[G], [N]]
    assert e.fundamentals("TST", date(2021, 3, 1))["revenue_ttm"] == pytest.approx(3.1 + 3.08 + 3.866 + 4.726)
    # Mastercard's gross and net tags share every quarter span and agree on none of them
    ma = edgar_mod._pick(_known(_edgar(_ma_shaped()), date(2023, 3, 1)), edgar_mod.REVENUE_TAGS, None).dropna(subset=["start"])
    assert edgar_mod._tag_classes(ma, edgar_mod.REVENUE_TAGS) == [[G], [N]]


def test_concept_is_stable_across_consecutive_filings():
    """Berkshire 2018-2019: ``Revenues`` has years of quarters; the rank-0 tag appears with three
    2018 quarters and covers its first trailing year at the Q1-2019 10-Q, at 70% of the level."""
    rev = []
    for y, base in ((2016, 50.0), (2017, 54.0), (2018, 58.0)):
        rev += _quarters(N, y, [base, base + 1, base + 2, base + 3], [f"{y}-05-06", f"{y}-08-06", f"{y}-11-05", f"{y + 1}-02-25"])
    rev += [_f("2019-01-01", "2019-03-31", 63.0, "2019-05-06"), _f("2019-04-01", "2019-06-30", 64.0, "2019-08-05"),
            _f("2019-07-01", "2019-09-30", 65.0, "2019-11-04")]
    other = [_f("2018-04-01", "2018-06-30", 0.7 * 59, "2018-08-06"), _f("2018-07-01", "2018-09-30", 0.7 * 60, "2018-11-05"),
             _f("2018-10-01", "2018-12-31", 0.7 * 61, "2019-02-25", "10-K"), _f("2019-01-01", "2019-03-31", 0.7 * 63, "2019-05-06"),
             _f("2019-04-01", "2019-06-30", 0.7 * 64, "2019-08-05"), _f("2019-07-01", "2019-09-30", 0.7 * 65, "2019-11-04")]
    c = _edgar({N: rev, G: other})
    seen = []
    for d in (date(2019, 3, 1), date(2019, 5, 8), date(2019, 8, 10), date(2019, 11, 10)):
        f = c.fundamentals("TST", d)
        t = quarterly_table(_known(c, d), edgar_mod.REVENUE_TAGS, positive=True)
        seen.append((f["revenue_ttm"], f.get("revenue_growth_yoy"), set(t["tag"].iloc[-4:])))
    # v0.8 first cut: 2019-05-08 flipped to the rank-0 tag (176.4 = 0.7 x 252, no growth) and back
    # only when it stopped covering; now the concept already reported is kept while it covers.
    assert [s[0] for s in seen] == pytest.approx([58 + 59 + 60 + 61, 59 + 60 + 61 + 63, 60 + 61 + 63 + 64, 61 + 63 + 64 + 65])
    assert all(s[1] is not None and s[2] == {N} for s in seen)
    # with no history under any tag the rank decides, and the choice then persists
    late = _edgar({N: [r for r in rev if r["end"] >= "2018-04-01"], G: other})
    assert set(quarterly_table(_known(late, date(2019, 5, 8)), edgar_mod.REVENUE_TAGS, positive=True)["tag"]) == {G}
    assert set(quarterly_table(_known(late, date(2019, 11, 10)), edgar_mod.REVENUE_TAGS, positive=True)["tag"]) == {G}


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


def test_stale_capex_removes_fcf_rather_than_capex():
    current = dict(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=1.4e9, eps_vals=(2.0, 1.8, 2.1, 2.0))
    capex = "PaymentsToAcquirePropertyPlantAndEquipment"
    dead = []
    for y in range(2012, 2022):
        dead += _quarters(capex, y, [1e9] * 4, [f"{y}-05-05", f"{y}-08-05", f"{y}-11-05", f"{y + 1}-02-25"])
    facts = _brk_shaped(**current)
    facts[capex] = dead                                             # last capex quarter 2021-12-31, OCF runs to 2023-12-31
    f = _edgar(facts).fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert "fcf_yield" not in f                                     # v0.8 first cut: OCF alone, 36e9 / market cap
    assert f["eps_ttm"] == pytest.approx(7.9) and f["revenue_ttm"] == pytest.approx(246e9)
    facts[capex] = dead + [q for y in (2022, 2023) for q in
                           _quarters(capex, y, [1e9] * 4, [f"{y}-05-05", f"{y}-08-05", f"{y}-11-05", f"{y + 1}-02-25"])]
    g = _edgar(facts).fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert g["fcf_yield"] == pytest.approx((36e9 - 4e9) / (300.0 * 1.4e9), abs=1e-4)
    del facts[capex]                                                # never reported: free cash flow is operating cash flow
    assert _edgar(facts).fundamentals("TST", date(2024, 3, 1), price=300.0)["fcf_yield"] == pytest.approx(36e9 / (300.0 * 1.4e9), abs=1e-4)


def test_net_margin_needs_revenue_and_net_income_windows_ending_together():
    current = dict(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=1.4e9, eps_vals=(2.0, 1.8, 2.1, 2.0))
    facts = _brk_shaped(**current)
    facts[N] = [r for r in facts[N] if r["end"] <= "2023-09-30"]   # Q4-2023 revenue not printed yet, net income is
    f = _edgar(facts).fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert f["report_period_end"] == "2023-12-31" and f["revenue_period_end"] == "2023-09-30"
    assert f["revenue_ttm"] == pytest.approx(246e9) and "revenue_growth_yoy" in f
    assert "net_margin" not in f                                    # v0.8 first cut: NI to December over revenue to September
    g = _edgar(_brk_shaped(**current)).fundamentals("TST", date(2024, 3, 1), price=300.0)
    assert g["net_margin"] == pytest.approx(20e9 / 246e9, abs=1e-4) and "revenue_period_end" not in g


def test_share_class_ratio_by_normalised_ticker_and_one_warning_per_kind(monkeypatch, caplog):
    facts = _brk_shaped(share_end="2023-12-31", share_filed="2024-02-25", eps_years=(2023,), shares=941_481.0)
    monkeypatch.setitem(edgar_mod.SHARE_CLASS_RATIO, "TS-T", 1500.0)
    c = _edgar(facts, ticker="TS-T")
    dash = c.fundamentals("TS-T", date(2024, 3, 1), price=300.0)
    dot = c.fundamentals("ts.t", date(2024, 3, 1), price=300.0)      # Instrument.parse keeps BRK.B as typed
    assert dash["eps_ttm"] == pytest.approx(11849 / 1500, abs=1e-4)
    assert dot["eps_ttm"] == dash["eps_ttm"] and dot["fcf_yield"] == dash["fcf_yield"]   # v0.8 first cut: no ratio for the dotted spelling
    d = _edgar(facts)                                               # no ratio: both sanity checks trip on every bar
    with caplog.at_level("WARNING", logger="agentic_trader.data.edgar"):
        for i, p in enumerate([300.0, 301.0, 302.5, 299.0, 310.0]):
            d.fundamentals("TST", date(2024, 3, 1) + timedelta(days=i), price=p)
    msgs = [r.getMessage() for r in caplog.records if r.name == "agentic_trader.data.edgar"]
    assert sum("market cap" in m for m in msgs) == 1                 # v0.8 first cut: once per distinct price
    assert sum("trailing EPS" in m for m in msgs) == 1


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
                    cache_max_age_days=None, ciks={"MA": "0001141391", "BRK-B": "0001067983", "JNJ": "0000200406",
                                                   "NVDA": "0001045810", "AMZN": "0001018724", "CVX": "0000093410",
                                                   "PG": "0000080424", "XOM": "0000034088", "KO": "0000021344",
                                                   "LLY": "0000059478", "JPM": "0000019617", "MSFT": "0000789019",
                                                   "MRK": "0000310158"})
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
    # (d) the concept already reported is kept while it covers: no flip to a tag with four quarters
    b19 = c.fundamentals("BRK-B", date(2019, 5, 8))
    assert b19["revenue_ttm"] == pytest.approx(250.042e9, rel=1e-3) and "revenue_growth_yoy" in b19   # was 176.3e9, no growth
    ma19 = c.fundamentals("MA", date(2019, 2, 15))
    assert ma19["revenue_ttm"] == pytest.approx(14.95e9, rel=1e-3) and "revenue_growth_yoy" in ma19    # net revenue as reported; was 21.8e9 gross
    cvx = c.fundamentals("CVX", date(2019, 5, 10))
    assert cvx["revenue_ttm"] == pytest.approx(163.775e9, rel=1e-3) and "revenue_growth_yoy" in cvx    # was 157.1e9, no growth
    # (a) NVDA FY2018: the 10-K's one erroneous six-month print is a revision, not a basis change
    nv = c.fundamentals("NVDA", date(2018, 5, 15))
    assert nv["revenue_ttm"] == pytest.approx(9.714e9, rel=1e-4) and nv["revenue_growth_yoy"] == pytest.approx(0.4058, abs=2e-3)
    # (c) the FY2020 annual span under the new tag completes Q4 with the nine months under the old one
    assert c.fundamentals("NVDA", date(2020, 11, 15))["revenue_ttm"] == pytest.approx(13.065e9, rel=1e-3)   # was absent
    # (b) AMZN FY2012 10-K with the 2011/2012 quarter values swapped: the audited annual figure governs
    am = c.fundamentals("AMZN", date(2013, 2, 15))
    assert am["revenue_ttm"] == pytest.approx(61.093e9, rel=1e-4) and am["revenue_growth_yoy"] == pytest.approx(0.2707, abs=2e-3)
    assert c.fundamentals("AMZN", date(2013, 5, 15))["revenue_ttm"] == pytest.approx(63.978e9, rel=1e-4)
    # (e) AMZN's capex moved to a tag with no complete window yet: no free cash flow, not OCF alone
    assert "fcf_yield" not in c.fundamentals("AMZN", date(2018, 3, 1), price=1512.5)
    # (f) JNJ in the Kenvue transition: the revenue window is a quarter behind the net income window
    j = c.fundamentals("JNJ", date(2023, 11, 1))
    assert j["report_period_end"] == "2023-10-01" and j["revenue_period_end"] == "2023-07-02" and "net_margin" not in j
    # Regression review of v0.8 (material changes must be corroborated):
    # (g) KO: the 2019-09-20 8-K's lone FY2018 re-print (34.300e9 against 31.856e9) is ignored, so
    # Q4-2018 is 7.058e9 as printed and the trailing year stays on the held basis (window to
    # 2019-06-28, flagged) rather than 35.764e9 summed across bases
    ko = c.fundamentals("KO", date(2019, 10, 25))
    assert ko["revenue_ttm"] == pytest.approx(33.320e9, rel=1e-4) and ko["revenue_period_end"] == "2019-06-28"
    q = quarterly_table(_known(c, date(2019, 10, 25), "KO"), edgar_mod.REVENUE_TAGS, positive=True)
    assert q.loc[pd.Timestamp("2018-12-31"), "val"] == pytest.approx(7.058e9, rel=1e-4)
    # (h) LLY: the Elanco recast left revenue without a new-basis window for two quarters; every
    # 10-Q still printed revenue, so the last window is kept and flagged (was dropped as dead)
    lly = c.fundamentals("LLY", date(2019, 8, 3))
    assert lly["revenue_ttm"] == pytest.approx(24.5557e9, rel=1e-4) and lly["revenue_period_end"] == "2018-12-31"
    assert "net_margin" not in lly and lly["eps_ttm"] == pytest.approx(7.97)
    assert c.fundamentals("LLY", date(2019, 11, 1))["revenue_ttm"] == pytest.approx(21.8431e9, rel=1e-4)
    # (i) AMZN: the mis-tagged FY2012 10-K is rejected for every concept; growth and EPS through
    # 2013 come from the first-print quarters (was +33.1% growth and a frozen swapped EPS window)
    am13 = c.fundamentals("AMZN", date(2013, 4, 27))
    assert am13["revenue_growth_yoy"] == pytest.approx(0.2446, abs=2e-3) and am13["eps_ttm"] == pytest.approx(-0.20, abs=1e-2)
    # (j) JNJ FY2017: the direct Q4 EPS print (-3.99) stands although the four quarters sum to 0.39
    # against an annual 0.47 (was -3.91, with a warning asserting mis-tagged comparatives)
    assert c.fundamentals("JNJ", date(2018, 3, 1))["eps_ttm"] == pytest.approx(0.39)
    # (k) JNJ / Kenvue: revenue is served at every filing cutoff through the transition
    assert all(c.fundamentals("JNJ", cut).get("revenue_ttm") for cut in
               (date(2023, 8, 1), date(2023, 10, 28), date(2024, 2, 17), date(2024, 5, 2)))
    # Final review of v0.8:
    # (l) a single-quarter restatement repeated by later filings is a confirmed correction: the
    # Q1 10-Q re-printing it beside its new quarter opens no generation, so the net income
    # window is current and the margin served (the round-2 code lost these nine cutoffs)
    for ticker, cut, margin, eps in (("JPM", date(2013, 5, 15), 0.2382, 5.59), ("JPM", date(2013, 11, 15), 0.1888, 4.41),
                                     ("MSFT", date(2016, 10, 21), 0.1942, 2.08), ("MSFT", date(2017, 4, 28), 0.2042, 2.26),
                                     ("NVDA", date(2017, 5, 24), 0.2605, 3.02), ("NVDA", date(2017, 11, 22), 0.2878, 4.03)):
        r = c.fundamentals(ticker, cut, price=100.0)
        assert r["report_period_end"] > "2013" and "net_income_period_end" not in r and "eps_period_end" not in r, (ticker, cut)
        assert r["net_margin"] == pytest.approx(margin, abs=2e-4) and r["eps_ttm"] == pytest.approx(eps, abs=1e-2), (ticker, cut)
    # (m) free cash flow needs the operating cash flow and capex windows to end together: NVDA's
    # capex window (to 2012-10-28) no longer backs a figure at 2016-08-24, KO's OCF window to
    # 2017-12-31 is flagged rather than differenced against 2019 capex
    assert "fcf_yield" not in c.fundamentals("NVDA", date(2016, 8, 24), price=100.0)
    ko20 = c.fundamentals("KO", date(2020, 4, 25), price=100.0)
    assert "fcf_yield" not in ko20 and ko20["ocf_period_end"] == "2017-12-31"
    assert "fcf_yield" not in c.fundamentals("MRK", date(2024, 11, 7), price=100.0)
    assert c.fundamentals("JNJ", date(2024, 3, 1), price=100.0)["fcf_yield"] == pytest.approx(0.0758, abs=1e-4)


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
