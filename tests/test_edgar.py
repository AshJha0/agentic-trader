"""SEC EDGAR point-in-time layer, tested offline against an injected fetch: ticker
lookup, facts as known at as_of, quarter reconstruction (year-to-date differencing, Q4 from
the 10-K, 12/16-week fiscal quarters), the filing-stream news, and the provider fallbacks.
Restatement / reporting-basis semantics are in tests/test_v08_data.py."""
import json
from datetime import date

import pandas as pd
import pytest

from agentic_trader import Instrument, make_config
from agentic_trader.data import edgar as edgar_mod
from agentic_trader.data.edgar import EdgarClient, quarterly_series, ttm

CIK = "0000000123"


def _fact(start, end, val, filed, form="10-Q", frame=None):
    d = {"end": end, "val": val, "filed": filed, "form": form, "fy": int(end[:4]), "fp": "Q1"}
    if start is not None:
        d["start"] = start
    return d


def _payloads():
    """A two-year company: 13-week quarters in 2022, 12/12/12/16-week quarters in 2023."""
    rev = [
        # 2022: Q1-Q3 direct, Q4 only inside the 10-K (annual span)
        _fact("2022-01-01", "2022-03-31", 100, "2022-04-28"),
        _fact("2022-04-01", "2022-06-30", 110, "2022-07-28"),
        _fact("2022-07-01", "2022-09-30", 120, "2022-10-27"),
        _fact("2022-01-01", "2022-12-31", 460, "2023-02-01", "10-K"),      # Q4 = 130
        # 2023 (52-week calendar, 12/12/12/16 weeks)
        _fact("2023-01-01", "2023-03-26", 140, "2023-04-27"),
        _fact("2023-03-27", "2023-06-18", 150, "2023-07-27"),
        _fact("2023-06-19", "2023-09-10", 160, "2023-10-26"),
        _fact("2023-01-01", "2023-12-31", 620, "2024-02-01", "10-K"),      # Q4 = 170 (16 weeks)
        # 2022 Q1 re-printed unchanged as the comparative in the 2023 Q1 10-Q
        _fact("2022-01-01", "2022-03-31", 100, "2023-04-27"),
    ]
    ni = [_fact(s, e, v / 10, f, fm) for s, e, v, f, fm in [
        ("2022-01-01", "2022-03-31", 100, "2022-04-28", "10-Q"), ("2022-04-01", "2022-06-30", 110, "2022-07-28", "10-Q"),
        ("2022-07-01", "2022-09-30", 120, "2022-10-27", "10-Q"), ("2022-01-01", "2022-12-31", 460, "2023-02-01", "10-K"),
        ("2023-01-01", "2023-03-26", 140, "2023-04-27", "10-Q"), ("2023-03-27", "2023-06-18", 150, "2023-07-27", "10-Q"),
        ("2023-06-19", "2023-09-10", 160, "2023-10-26", "10-Q"), ("2023-01-01", "2023-12-31", 620, "2024-02-01", "10-K")]]
    # cash flow: year-to-date in every 10-Q
    ocf = [_fact("2022-01-01", "2022-03-31", 30, "2022-04-28"), _fact("2022-01-01", "2022-06-30", 65, "2022-07-28"),
           _fact("2022-01-01", "2022-09-30", 105, "2022-10-27"), _fact("2022-01-01", "2022-12-31", 150, "2023-02-01", "10-K"),
           _fact("2023-01-01", "2023-03-26", 40, "2023-04-27"), _fact("2023-01-01", "2023-06-18", 85, "2023-07-27"),
           _fact("2023-01-01", "2023-09-10", 135, "2023-10-26"), _fact("2023-01-01", "2023-12-31", 190, "2024-02-01", "10-K")]
    eps = [_fact(f["start"], f["end"], round(f["val"] / 100, 2), f["filed"], f["form"]) for f in ni]
    equity = [_fact(None, "2022-12-31", 1000, "2023-02-01", "10-K"), _fact(None, "2023-09-10", 1200, "2023-10-26")]
    debt = [_fact(None, "2022-12-31", 400, "2023-02-01", "10-K"), _fact(None, "2023-09-10", 300, "2023-10-26")]
    shares = [_fact(None, "2023-09-10", 50, "2023-10-26")]
    facts = {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": rev}},
        "NetIncomeLoss": {"units": {"USD": ni}},
        "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": ocf}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": eps}},
        "StockholdersEquity": {"units": {"USD": equity}},
        "LongTermDebt": {"units": {"USD": debt}},
    }, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": shares}}}}}
    forms = ["8-K", "4", "4", "424B2", "10-Q", "8-K", "SC 13D", "8-K"]
    dates = ["2023-10-20", "2023-10-23", "2023-10-23", "2023-10-24", "2023-10-26", "2023-10-26", "2023-10-27", "2023-11-02"]
    items = ["2.02,9.01", "", "", "", "", "5.02", "", "4.02"]
    subs = {"name": "Test Co", "sic": "3571", "sicDescription": "Electronic Computers",
            "filings": {"recent": {"form": forms, "filingDate": dates, "reportDate": dates, "items": items,
                                   "accessionNumber": [f"0000000123-23-{i:06d}" for i in range(len(forms))]},
                        "files": [{"name": f"CIK{CIK}-submissions-001.json"}]}}
    older = {"form": ["10-K"], "filingDate": ["2015-02-01"], "reportDate": ["2014-12-31"], "items": [""],
             "accessionNumber": ["0000000123-15-000001"]}
    tickers = {"0": {"cik_str": 123, "ticker": "TST", "title": "Test Co"},
               "1": {"cik_str": 124, "ticker": "BRK-B", "title": "Berkshire"},
               "2": {"cik_str": 125, "ticker": "GLDX", "title": "Gold Trust"}}
    return {
        edgar_mod.TICKERS_URL: tickers,
        edgar_mod.SUBMISSIONS_URL.format(name=f"CIK{CIK}.json"): subs,
        edgar_mod.SUBMISSIONS_URL.format(name=f"CIK{CIK}-submissions-001.json"): older,
        edgar_mod.FACTS_URL.format(cik=CIK): facts,
        edgar_mod.SUBMISSIONS_URL.format(name="CIK0000000125.json"): {"name": "Gold Trust", "sic": "6221",
                                                                       "filings": {"recent": {"form": [], "filingDate": [],
                                                                                              "accessionNumber": []}}},
        edgar_mod.FACTS_URL.format(cik="0000000125"): {"facts": {"us-gaap": {"NetIncomeLoss": {"units": {"USD": ni}}}}},
    }


@pytest.fixture
def client(tmp_path):
    payloads = _payloads()
    calls = []

    def fetch(url):
        calls.append(url)
        if url not in payloads:
            from urllib.error import HTTPError
            raise HTTPError(url, 404, "Not Found", {}, None)
        return json.dumps(payloads[url]).encode()

    c = EdgarClient(user_agent="test test@example.com", cache_dir=tmp_path, fetch=fetch, min_interval=0)
    c.calls = calls
    return c


# ---------------------------------------------------------------- lookups
def test_cik_lookup_handles_share_classes_and_overrides(client):
    assert client.cik("tst") == CIK
    assert client.cik("BRK-B") == "0000000124" and client.cik("BRK.B") == "0000000124"
    assert client.cik("NOPE") is None
    assert EdgarClient(user_agent="x x@y", fetch=lambda u: b"{}", ciks={"foo": "42"}).cik("FOO") == "0000000042"
    assert "XOM" in edgar_mod.PREDECESSOR_CIKS


def test_requests_are_cached_on_disk_and_keyed_by_full_path(client, tmp_path):
    client.filings("TST")
    client.facts("TST")
    assert len({u for u in client.calls}) == len(client.calls)          # no URL fetched twice
    files = sorted(p.name for p in tmp_path.iterdir())
    assert any("submissions_CIK" in f for f in files) and any("companyfacts_CIK" in f for f in files)
    again = EdgarClient(user_agent="test test@example.com", cache_dir=tmp_path, fetch=lambda u: (_ for _ in ()).throw(AssertionError(u)))
    assert len(again.filings("TST")) == 9                              # served from disk, older page merged


# ----------------------------------------------------------- fundamentals
def test_quarters_are_reconstructed_from_ytd_and_annual_spans(client):
    known = client.facts("TST")
    rev = quarterly_series(known, edgar_mod.REVENUE_TAGS)
    assert rev.round(6).to_dict() == {pd.Timestamp(k): v for k, v in {
        "2022-03-31": 100, "2022-06-30": 110, "2022-09-30": 120, "2022-12-31": 130,
        "2023-03-26": 140, "2023-06-18": 150, "2023-09-10": 160, "2023-12-31": 170}.items()}
    ocf = quarterly_series(known, edgar_mod.OCF_TAGS)
    assert ocf.round(6).tolist() == [30, 35, 40, 45, 40, 45, 50, 55]   # YTD differenced
    assert ttm(rev) == 620 and ttm(rev, back=4) == 460 and ttm(rev.iloc[:3]) is None


def test_fundamentals_are_point_in_time_and_first_print(client):
    # Before the 2023 10-K: latest quarter is Q3-2023 (filed 2023-10-26); TTM = 130+140+150+160.
    f = client.fundamentals("TST", date(2023, 12, 1), price=20.0)
    assert f["report_period_end"] == "2023-09-10" and f["filed"] == "2023-10-26" and f["lag_days"] == 36
    assert f["revenue_ttm"] == 580
    assert "revenue_growth_yoy" not in f                                      # only 7 quarters known: no YoY yet
    assert f["net_margin"] == pytest.approx(0.1, abs=1e-4)
    assert f["eps_ttm"] == pytest.approx(0.58, abs=1e-4) and f["pe_ratio"] == pytest.approx(20 / 0.58, abs=1e-2)
    assert f["debt_to_equity"] == pytest.approx(300 / 1200, abs=1e-3)
    assert f["fcf_yield"] == pytest.approx((45 + 40 + 45 + 50) / (20 * 50), abs=1e-4)
    assert f["eps_surprise"] is None and f["insider_net_buying"] is None       # not available: not guessed
    # After the 2023 10-K, eight quarters are known and the trailing year compares 620 with 460.
    k = client.fundamentals("TST", date(2024, 3, 1), price=20.0)
    assert k["report_period_end"] == "2023-12-31" and k["revenue_growth_yoy"] == pytest.approx(620 / 460 - 1, abs=1e-4)
    # The day before the Q3 filing, Q3 does not exist yet.
    g = client.fundamentals("TST", date(2023, 10, 25), price=20.0)
    assert g["report_period_end"] == "2023-06-18" and g["revenue_ttm"] == 130 + 140 + 150 + 120
    # Before anything was filed: nothing.
    assert client.fundamentals("TST", date(2021, 1, 1)) == {}
    # An unchanged comparative re-print (2022-Q1 again in the 2023-Q1 10-Q) changes nothing.
    h = client.fundamentals("TST", date(2023, 6, 1), price=20.0)
    assert h["revenue_ttm"] == 110 + 120 + 130 + 140


def test_funds_and_unknown_filers_return_nothing(client):
    assert client.fundamentals("GLDX", date(2024, 1, 1), price=1.0) == {}      # SIC 6221: a trust
    assert client.fundamentals("BRK-B", date(2024, 1, 1), price=1.0) == {}     # 404 on company facts
    assert client.fundamentals("NOPE", date(2024, 1, 1)) == {}
    assert client.news("BRK-B", date(2024, 1, 1), 30) == []


# ------------------------------------------------------------------- news
def test_filing_stream_news_is_point_in_time_and_scored(client):
    items = client.news("TST", date(2023, 10, 27), 10)
    heads = sorted(((i.published.isoformat(), i.headline, i.sentiment) for i in items), reverse=True)
    assert heads == sorted([
        ("2023-10-27", "Activist / >5% beneficial ownership disclosed (13D)", 0.2),
        ("2023-10-26", "8-K: Departure or appointment of directors or officers", -0.05),
        ("2023-10-26", "Quarterly report (10-Q) filed", 0.0),
        ("2023-10-23", "2 insider transaction filings (Form 4)", 0.0),
        ("2023-10-20", "8-K: Results of operations and financial condition (earnings release)", 0.0),
    ], reverse=True)
    assert all(i.source == "SEC EDGAR" for i in items)
    assert not any("424B" in t for i in items for t in i.tags)                 # routine supplements are not news
    later = client.news("TST", date(2023, 11, 3), 3)
    assert [i.headline for i in later] == ["8-K: Non-reliance on previously issued financial statements (restatement)"]
    assert later[0].sentiment == -0.6
    assert client.news("TST", date(2023, 10, 19), 30) == [] or all(i.published <= date(2023, 10, 19)
                                                                    for i in client.news("TST", date(2023, 10, 19), 30))


# -------------------------------------------------------- configuration
def test_contact_user_agent_is_required(monkeypatch):
    monkeypatch.delenv(edgar_mod.USER_AGENT_ENV, raising=False)
    with pytest.raises(ValueError, match="contact"):
        EdgarClient()
    assert EdgarClient.from_config({"edgar": True}) is None                  # skipped with a warning
    assert EdgarClient.from_config({"edgar": False, "edgar_user_agent": "a a@b"}) is None
    assert EdgarClient.from_config({"edgar_user_agent": "no-contact-here"}) is None
    monkeypatch.setenv(edgar_mod.USER_AGENT_ENV, "Name name@example.com")
    assert edgar_mod.edgar_user_agent() == "Name name@example.com"
    c = EdgarClient.from_config({"edgar": True, "edgar_ciks": {"xom": "34088"}})
    assert c is not None and c.cik("XOM") == "0000034088"


def test_yahoo_provider_uses_edgar_and_falls_back(monkeypatch, client):
    from agentic_trader.data.yahoo import YahooProvider
    monkeypatch.delenv(edgar_mod.USER_AGENT_ENV, raising=False)
    p = YahooProvider(make_config(data_provider="yahoo"))
    assert p.edgar is None                                                  # no contact: Yahoo-only behaviour
    p.edgar = client
    ins = Instrument.parse("TST")
    idx = pd.bdate_range("2023-11-01", "2023-12-01")
    p._cache[ins.yahoo_symbol] = pd.DataFrame({"Open": 20.0, "High": 21.0, "Low": 19.0, "Close": 20.0, "Volume": 1.0}, index=idx)
    # the unadjusted close and split table would come from a second download; injected here
    p._actions[ins.yahoo_symbol] = pd.DataFrame({"RawClose": 20.0, "Split": 0.0}, index=idx)
    f = p.fundamentals(ins, date(2023, 12, 1))
    assert f["source"].startswith("sec_edgar") and f["pe_ratio"] == pytest.approx(20 / 0.58, abs=1e-2)
    # a 4-for-1 split after as_of: Yahoo's split-adjusted close is a quarter of the price that traded,
    # and the as-traded price is what the as-of P/E must use
    later = pd.bdate_range("2023-11-01", "2024-03-01")
    p._actions[ins.yahoo_symbol] = pd.DataFrame({"RawClose": 5.0, "Split": [4.0 if d == pd.Timestamp("2024-02-01") else 0.0 for d in later]}, index=later)
    assert p.as_traded_close(ins, date(2023, 12, 1)) == pytest.approx(20.0)
    assert p.as_traded_close(ins, date(2024, 2, 15)) == pytest.approx(5.0)
    assert p.splits(ins) == {date(2024, 2, 1): 4.0}
    assert p.fundamentals(ins, date(2023, 12, 1))["pe_ratio"] == pytest.approx(20 / 0.58, abs=1e-2)
    assert p.fundamentals(Instrument.parse("EURUSD"), date(2023, 12, 1)) == {}
    news = p.news(ins, date(2023, 10, 27), 10)                              # historical: filings only, no Yahoo call
    assert len(news) == 5 and all(i.source == "SEC EDGAR" for i in news)
    p.edgar = EdgarClient(user_agent="a a@b", fetch=lambda u: (_ for _ in ()).throw(RuntimeError("down")))
    assert p.news(ins, date(2023, 10, 27), 10) == []                        # an outage degrades, never raises
    assert p.fundamentals(ins, date(2023, 12, 1)) == {}


# --------------------------------------------------------------- splits
def test_per_share_prints_are_rebased_across_a_split(client):
    """EPS printed before a 4-for-1 split is in old share units; after the split the 10-K prints
    the annual figure in new units. Mixing them raw made Q4 = annual - 9M go negative; rebasing
    every print to the as-of basis keeps the trailing year right, and the share count too."""
    from agentic_trader.data.edgar import rebase_per_share
    known = client.facts("TST")
    split = [(pd.Timestamp("2023-08-01"), 4.0)]          # between the Q2 filing (07-27) and the Q3 filing (10-26)
    rb = rebase_per_share(known, split)
    eps = rb[rb.tag == "EarningsPerShareDiluted"].set_index("filed")["val"]
    raw = known[known.tag == "EarningsPerShareDiluted"].set_index("filed")["val"]
    assert eps.loc["2023-07-27"] == pytest.approx(raw.loc["2023-07-27"] / 4)     # pre-split print rescaled
    assert eps.loc["2023-10-26"] == pytest.approx(raw.loc["2023-10-26"])         # post-split print untouched
    sh = rb[rb.tag == "dei:EntityCommonStockSharesOutstanding"]["val"].iloc[0]
    assert sh == pytest.approx(50.0)                                               # instant dated 2023-09-10, after the split
    # three pre-split quarters rebased (0.13 + 0.14 + 0.15) / 4 plus the post-split Q3 print 0.16
    f = client.fundamentals("TST", date(2023, 12, 1), price=5.0, splits={date(2023, 8, 1): 4.0})
    assert f["eps_ttm"] == pytest.approx(0.265, abs=1e-4) and f["pe_ratio"] == pytest.approx(5 / 0.265, abs=1e-2)
    # without the split table nothing is rescaled (documented: only right for a company that never split)
    assert client.fundamentals("TST", date(2023, 12, 1), price=20.0)["eps_ttm"] == pytest.approx(0.58, abs=1e-4)
    # the memo key includes the splits so far: the same cutoff with and without a split are different entries
    assert client.fundamentals("TST", date(2023, 12, 1), price=20.0, splits={date(2023, 8, 1): 4.0})["eps_ttm"] == pytest.approx(0.265, abs=1e-4)


def test_growth_needs_adjacent_years_and_tags_are_never_mixed(tmp_path):
    payloads = _payloads()
    facts = payloads[edgar_mod.FACTS_URL.format(cik=CIK)]["facts"]["us-gaap"]
    rev = facts["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"]
    # drop 2022-Q3 (a gap): the 2022 trailing year cannot be built, so no YoY
    facts["RevenueFromContractWithCustomerExcludingAssessedTax"]["units"]["USD"] = [
        f for f in rev if not (f.get("start") == "2022-07-01" and f["end"] == "2022-09-30")]
    # the same 2022-Q1 span also printed under a lower-ranked tag (another concept)
    facts["SalesRevenueNet"] = {"units": {"USD": [_fact("2022-01-01", "2022-03-31", 90, "2022-04-20")]}}
    fetch = lambda u: json.dumps(payloads[u]).encode()  # noqa: E731
    c = EdgarClient(user_agent="t t@x", cache_dir=tmp_path, fetch=fetch, min_interval=0)
    known = c.facts("TST")
    q = edgar_mod.quarterly_table(known, edgar_mod.REVENUE_TAGS)
    # only complete single-tag trailing years survive: the 2023 quarters of the preferred tag;
    # the stray lower-ranked print is never stitched in (v0.6 kept it as "earliest print")
    assert list(q.index) == list(pd.to_datetime(["2023-03-26", "2023-06-18", "2023-09-10", "2023-12-31"]))
    assert set(q["tag"]) == {"RevenueFromContractWithCustomerExcludingAssessedTax"}
    f = c.fundamentals("TST", date(2024, 3, 1), price=20.0)
    assert "revenue_growth_yoy" not in f and f["revenue_ttm"] == 620


def test_missing_submissions_page_and_cache_age(tmp_path):
    payloads = _payloads()
    del payloads[edgar_mod.SUBMISSIONS_URL.format(name=f"CIK{CIK}-submissions-001.json")]   # the older page 404s
    calls = []

    def fetch(url):
        calls.append(url)
        if url not in payloads:
            from urllib.error import HTTPError
            raise HTTPError(url, 404, "Not Found", {}, None)
        return json.dumps(payloads[url]).encode()
    c = EdgarClient(user_agent="t t@x", cache_dir=tmp_path, fetch=fetch, min_interval=0)
    assert len(c.filings("TST")) == 8                                                 # the recent page alone
    assert not any("submissions-001" in p.name for p in tmp_path.iterdir())          # a 404 is not written to disk
    # a stale cache file is re-fetched when older than the configured age
    import os
    import time
    stale = EdgarClient(user_agent="t t@x", cache_dir=tmp_path, fetch=fetch, min_interval=0, cache_max_age_days=1)
    f = next(p for p in tmp_path.iterdir() if "company_tickers" in p.name)
    os.utime(f, (time.time() - 3 * 86400, time.time() - 3 * 86400))
    before = len(calls)
    stale.cik("TST")
    assert len(calls) == before + 1
    forever = EdgarClient(user_agent="t t@x", cache_dir=tmp_path, fetch=fetch, min_interval=0, cache_max_age_days=None)
    before = len(calls)
    forever.cik("TST")
    assert len(calls) == before
