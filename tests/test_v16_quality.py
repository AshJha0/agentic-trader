"""v0.16 quality pass: edge cases, refusals and error paths the earlier suites left untested.

Offline and $0: providers are driven through injected fetchers or a fake ``yfinance``
module, never the network. No thread-timing assertions.
"""

from __future__ import annotations

import builtins
import math
import subprocess
import sys
import types
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic_trader import provenance, validate
from agentic_trader.agentic.governance import (
    MemoryTool,
    MemoryToolError,
    OutcomeRow,
    _phi,
    governance_report,
    render_report,
    weekly_rollup,
)
from agentic_trader.agentic.tracing import Metrics, SLOReport
from agentic_trader.config import make_config
from agentic_trader.data import fred as fred_mod
from agentic_trader.data import yahoo as yahoo_mod
from agentic_trader.data.fred import FredClient, FredSeries
from agentic_trader.data.yahoo import YahooProvider
from agentic_trader.instruments import Instrument
from agentic_trader.memory import DecisionMemory
from agentic_trader.oms import OMS, KillSwitch, MarketSnapshot, OrderState, reconcile

UTC = timezone.utc
FRI_1555 = datetime(2026, 11, 6, 20, 55, tzinfo=UTC)  # 15:55 New York, a Friday session


# --------------------------------------------------------------------------- validate
def _bars(idx, close=100.0):
    n = len(idx)
    c = np.full(n, close)
    return pd.DataFrame({"Open": c, "High": c + 1, "Low": c - 1, "Close": c}, index=pd.DatetimeIndex(idx))


def test_bar_problems_refuses_unknown_class_and_missing_columns():
    with pytest.raises(ValueError, match="unknown asset class"):
        validate.bar_problems(_bars(pd.bdate_range("2024-01-01", periods=3)), "crypto")
    assert validate.bar_problems(pd.DataFrame({"Close": [1.0]}), "equity") == ["missing price columns ['Open', 'High', 'Low']"]
    with pytest.raises(ValueError, match="unknown asset class"):
        validate.session_close_utc(date(2024, 1, 2), "bond")


def test_bar_problems_reports_each_defect_once_with_its_first_date():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-03", "2024-01-04"])
    df = _bars(idx)
    df.loc[df.index[1], "Close"] = np.nan
    df.iloc[3, df.columns.get_loc("High")] = 50.0  # High below Low on the 4th
    reasons = validate.bar_problems(df, "equity")
    assert any(r.startswith("NaN Close on 2024-01-03") for r in reasons)
    assert "High below Low on 2024-01-04" in reasons and "duplicate date 2024-01-03" in reasons
    with pytest.raises(validate.BarValidationError) as e:
        validate.require_valid_bars(df, "equity", "AAPL")
    assert e.value.reasons == reasons and str(e.value).startswith("refusing AAPL: ")


def test_bar_gap_limit_and_out_of_order():
    gap = _bars(pd.to_datetime(["2024-01-02", "2024-01-12"]))
    assert "gap of 10 days" in validate.bar_problems(gap, "equity")[0]
    assert validate.bar_problems(gap, "equity", max_gap_days=10) == []
    back = _bars(pd.to_datetime(["2024-01-03", "2024-01-02"]))
    assert validate.bar_problems(back, "fx") == ["dates out of order at 2024-01-02"]


def test_common_sessions_empty_and_intersection():
    assert len(validate.common_sessions({})) == 0
    a = _bars(pd.bdate_range("2024-01-01", periods=5))
    b = _bars(pd.to_datetime(["2024-01-03 17:00", "2024-01-02 17:00", "2024-01-09 00:00"]))
    assert list(validate.common_sessions({"a": a, "b": b}).strftime("%F")) == ["2024-01-02", "2024-01-03"]


@given(w=st.floats(-5, 5, allow_nan=False), cap=st.floats(0, 3, allow_nan=False))
@settings(max_examples=200, deadline=None)
def test_cap_short_notional_properties(w, cap):
    out = validate.cap_short_notional(w, cap)
    assert out >= -cap - 1e-15 or w >= 0  # never a short larger than the cap
    assert out == w if w >= 0 else out >= w  # longs untouched; shorts only shrink
    assert validate.cap_short_notional(w, None) == w


@pytest.mark.parametrize("cap", [float("nan"), float("inf"), -0.1])
def test_cap_short_notional_refuses_bad_caps(cap):
    with pytest.raises(ValueError, match="finite non-negative"):
        validate.cap_short_notional(-0.2, cap)
    assert validate.cap_short_notional(0.2, cap) == 0.2  # a long never reads the cap


def test_ledger_round_trip_and_match(tmp_path):
    idx = pd.bdate_range("2024-01-01", periods=4)
    a = pd.DataFrame({"x": [0.1 + 0.2, 1 / 3, np.nan, 1e-300]}, index=idx)
    validate.write_ledger_csv(a, tmp_path / "l.csv")
    b = validate.read_ledger_csv(tmp_path / "l.csv")
    assert validate.ledgers_match(a, b, tol=0.0)
    assert not validate.ledgers_match(a, b.rename(columns={"x": "y"}))
    assert not validate.ledgers_match(a, b.iloc[:3])
    c = b.copy()
    c.iloc[0, 0] += 1e-9
    assert not validate.ledgers_match(a, c) and validate.ledgers_match(a, c, tol=1e-6)


# --------------------------------------------------------------------------- OMS
@pytest.fixture
def cfg():
    c = make_config(data_provider="synthetic", memory_path=None)
    c["oms"] = {"max_order_notional": 100_000, "max_order_quantity": 5_000, "borrow_list": ["MSFT"]}
    return c


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", True),
        ("quantity", 0),
        ("quantity", -1),
        ("quantity", float("nan")),
        ("price", float("inf")),
        ("last_close", "199"),
    ],
)
def test_oms_submit_refuses_non_numeric_or_non_positive_inputs(cfg, field, value):
    kw = {"quantity": 10, "price": 200.0, "last_close": 199.0}
    kw[field] = value
    with pytest.raises(ValueError, match=f"{field} must be a positive finite number"):
        OMS(cfg).submit("o1", "AAPL", "buy", kw["quantity"], kw["price"], kw["last_close"], FRI_1555)


def test_oms_submit_accepts_numpy_scalars_and_refuses_bad_side_and_naive_time(cfg):
    """Regression: np.int64 quantities were refused (not an ``int``) and ``True`` was a 1-share order."""
    o = OMS(cfg).submit("o1", "AAPL", "buy", np.int64(10), np.float64(200.0), 199.0, FRI_1555)
    assert o.state is OrderState.ACKED and o.quantity == 10.0
    with pytest.raises(ValueError, match="side"):
        OMS(cfg).submit("o2", "AAPL", "hold", 10, 200.0, 199.0, FRI_1555)
    with pytest.raises(ValueError, match="timezone-aware"):
        OMS(cfg).submit("o3", "AAPL", "buy", 10, 200.0, 199.0, FRI_1555.replace(tzinfo=None))


def test_oms_execute_zero_capacity_and_fx_flat_clears_value_date(cfg):
    oms = OMS(cfg)
    oms.submit("o1", "AAPL", "buy", 10, 200.0, 199.0, FRI_1555)
    assert oms.execute("o1", MarketSnapshot(200.0, adv=0.0, impact_k=None), FRI_1555) is None
    assert oms.orders["o1"].state is OrderState.ACKED  # nothing filled, still working
    fx = OMS(cfg, positions={"EURUSD": 1000.0})
    fx.fx_value_dates["EURUSD"] = date(2026, 11, 10)
    fx.submit("f1", "EURUSD", "sell", 1000, 1.10, 1.10, FRI_1555)
    fill = fx.execute("f1", MarketSnapshot(1.10, adv=None, impact_k=None), FRI_1555)
    assert fill is not None and fx.positions["EURUSD"] == 0.0 and "EURUSD" not in fx.fx_value_dates


def test_oms_empty_cash_projection_and_kill_switch_file_absent(cfg, tmp_path):
    oms = OMS(cfg)
    proj = oms.cash_projection()
    assert proj.empty and list(proj.columns) == ["currency", "settle_date", "amount", "balance"]
    ks = KillSwitch(tmp_path / "nested" / "ks.json")
    assert ks.engaged() == {}  # no file yet: nothing halted
    ks.release("global")  # releasing nothing is harmless
    ks.engage(" aapl ", "fat finger", at=FRI_1555)
    assert ks.blocking(Instrument.parse("AAPL")).startswith("kill_switch: AAPL halted")
    assert ks.blocking(Instrument.parse("MSFT")) is None


def test_reconcile_zero_ledger_price_is_a_break_not_a_crash(cfg):
    """Regression: a ledger price of 0 raised ZeroDivisionError and lost the whole report."""
    oms = OMS(cfg)
    oms.submit("o1", "AAPL", "buy", 10, 200.0, 199.0, FRI_1555)
    oms.execute("o1", MarketSnapshot(200.0, adv=None, impact_k=None), FRI_1555)
    rep = reconcile(oms, {"AAPL": 10}, ledger_prices={"aapl": 0.0, "MSFT": 1.0})
    assert [b.kind for b in rep.breaks] == ["price"] and rep.checked == 2
    rep = reconcile(oms, {"AAPL": 10}, ledger_prices={"AAPL": float("nan")})
    assert [b.kind for b in rep.breaks] == ["price"]


# --------------------------------------------------------------------------- governance
def _row(as_of, role="trader", weight=0.5, pnl=0.01, failed=()):
    return OutcomeRow("t", "AAPL", as_of, role, weight, pnl, pnl is not None, False, tuple(failed))


def test_phi_edges_and_report_rendering():
    assert _phi([], []) is None and _phi([True, True], [True, False]) is None
    assert _phi([True, False], [True, False]) == pytest.approx(1.0)
    rows = [
        _row("2024-03-04", failed=["c1"]),
        _row("2024-03-05", pnl=-0.02),
        _row("2024-03-12", pnl=None),
        _row("2024-03-12", role="pm", weight=0.0),
    ]
    rep = governance_report(rows, checks=["never_fired"])
    assert rep["by_check"]["never_fired"]["false_positive_rate"] is None
    weeks = weekly_rollup(rows)
    assert [w["week"] for w in weeks] == ["2024-W10", "2024-W11"] and weeks[1]["pnl_sum"] is None
    text = render_report(rep, weeks)
    assert "| pm | 1 | 0 | 0 | n/a | n/a |" in text
    assert "| trader | 3 | 2 | 1 | 50.0% | -0.0050 |" in text
    assert "| c1 | 1 | 1 | 1 | 100.0% |" in text and "| 2024-W11 | 2 | 0 | 0 | n/a | n/a | 0 |" in text


@pytest.mark.parametrize("horizon", ["10", 2.5, True, float("nan")])
def test_memory_tool_bad_horizon_is_an_audited_refusal(tmp_path, horizon):
    """Regression: a non-integer horizon raised a bare ValueError (or was truncated) and
    skipped the audit trail every call is documented to write."""
    tool = MemoryTool(DecisionMemory(tmp_path / "m.jsonl"), date(2024, 3, 20))
    with pytest.raises(MemoryToolError, match="horizon_days"):
        tool.remember("AAPL", "BUY", 0.2, 50.0, "x", horizon_days=horizon)
    assert tool.audit[-1]["allowed"] is False and tool._writes == 0
    assert tool.remember("AAPL", "BUY", 0.2, 50.0, "x", horizon_days=10.0) == "AAPL|2024-03-20|"


def test_memory_tool_refuses_blank_symbol_and_bad_price(tmp_path):
    tool = MemoryTool(DecisionMemory(tmp_path / "m.jsonl"), date(2024, 3, 20))
    with pytest.raises(MemoryToolError, match="universe"):
        tool.recall("  ")
    with pytest.raises(MemoryToolError, match="price must be positive"):
        tool.remember("AAPL", "BUY", 0.2, 0.0, "x")
    with pytest.raises(MemoryToolError, match="finite"):
        tool.remember("AAPL", "BUY", True, 1.0, "x")
    assert [a["allowed"] for a in tool.audit] == [False, False, False]


def test_decision_memory_skips_blank_and_malformed_lines(tmp_path):
    p = tmp_path / "m.jsonl"
    p.write_text('\n[1, 2]\n{"not": "an entry"}\nnot json\n', encoding="utf-8")
    m = DecisionMemory(p)
    assert m.entries == []
    m.record("AAPL", date(2024, 3, 4), "BUY", 0.5, 100.0, "why", provider="synthetic")
    assert len(DecisionMemory(p).entries) == 1


# --------------------------------------------------------------------------- tracing
def test_stage_quantile_and_slo_markdown():
    m = Metrics()
    assert m.stage_quantile("analyst", 0.5) is None
    for v in (1.0, 2.0, 3.0):
        m.observe("stage_latency_ms", v, stage="analyst")
    assert m.stage_quantile("analyst", 1.0) == 3.0  # capped at the observed max
    rep = SLOReport(
        [
            {
                "stage": "a",
                "runs": 1,
                "latency_ms": None,
                "latency_objective_ms": None,
                "failure_rate": 0.0,
                "failure_objective": None,
                "breaches": [],
                "judged": False,
            },
            {
                "stage": "b",
                "runs": 9,
                "latency_ms": 5.0,
                "latency_objective_ms": 1.0,
                "failure_rate": 0.5,
                "failure_objective": 0.1,
                "breaches": ["slow"],
                "judged": True,
            },
        ]
    )
    md = rep.to_markdown()
    assert "too few runs" in md and "BREACH: slow" in md and not rep.ok
    assert rep.to_dict()["ok"] is False and len(rep.breaches) == 1


# --------------------------------------------------------------------------- provenance
def test_version_from_pyproject_edges(tmp_path):
    assert provenance._version_from_pyproject(tmp_path / "missing.toml") is None
    other = tmp_path / "other.toml"
    other.write_text('[project]\nname = "something-else"\nversion = "9.9"\n', encoding="utf-8")
    assert provenance._version_from_pyproject(other) is None
    assert provenance.package_version(other) == provenance.package_version(tmp_path / "missing.toml")


def test_version_from_pyproject_without_tomllib(tmp_path, monkeypatch):
    """The Python 3.10 fallback parser (no tomllib) reads the same version."""
    f = tmp_path / "p.toml"
    f.write_text('[project]\nname = "agentic-trader"\nversion = "1.2.3"\n\n[tool.x]\nversion = "0"\n', encoding="utf-8")
    real = builtins.__import__

    def no_tomllib(name, *a, **k):
        if name == "tomllib":
            raise ModuleNotFoundError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_tomllib)
    assert provenance._version_from_pyproject(f) == "1.2.3"
    f.write_text('[project]\nname = "other"\nversion = "1.2.3"\n', encoding="utf-8")
    assert provenance._version_from_pyproject(f) is None


def test_git_info_without_git_and_missing_dist(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    assert provenance.git_info() == (None, None)
    assert provenance._dist_version("surely-not-an-installed-dist-xyz") is None


# --------------------------------------------------------------------------- FRED
SPEC = FredSeries("TEST", lag_days=1, max_age_days=10)


def _table(values, start="2024-01-01"):
    return pd.DataFrame({"v": values}, index=pd.date_range(start, periods=len(values), freq="D"))


def test_fred_prepare_refusals():
    c = FredClient(fetch=lambda url: None)
    with pytest.raises(ValueError, match="not a series table"):
        c._prepare(pd.DataFrame(index=[1, 2]), SPEC)
    with pytest.raises(ValueError, match="no numeric observations"):
        c._prepare(pd.DataFrame({"v": ["."] * 3}), SPEC)
    with pytest.raises(ValueError, match="not dated"):
        c._prepare(pd.DataFrame({"v": [1.0]}, index=["not a date"]), SPEC)
    s = c._prepare(pd.DataFrame({"v": [1.0]}, index=["2024-01-01"]), SPEC)
    assert s.index[0] == pd.Timestamp("2024-01-02")  # dated by publication (lag 1)
    with pytest.raises(ValueError, match="vintage_step_days"):
        FredClient(vintage_step_days=0)


def test_fred_stale_cache_served_when_redownload_fails(tmp_path, monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) > 1:
            raise OSError("offline")
        return _table([1.0, 2.0, 3.0])

    c = FredClient(cache_dir=tmp_path, fetch=fetch, cache_max_age_days=1.0)
    assert c.value_asof(SPEC, date(2024, 1, 4)) == 3.0
    later = fred_mod.time.time() + 3 * 86400
    monkeypatch.setattr(fred_mod.time, "time", lambda: later)
    c2 = FredClient(cache_dir=tmp_path, fetch=fetch, cache_max_age_days=1.0)
    assert c2.value_asof(SPEC, date(2024, 1, 4)) == 3.0 and len(calls) == 2
    # without a cache the same outage leaves the series unavailable, not an exception
    assert FredClient(fetch=fetch).value_asof(SPEC, date(2024, 1, 4)) is None


def test_fred_corrupt_or_unusable_cache_is_replaced(tmp_path):
    (tmp_path / "TEST.csv").write_bytes(b"\xff\xfe\x00garbage")
    c = FredClient(cache_dir=tmp_path, fetch=lambda url: _table([5.0]))
    assert c.value_asof(SPEC, date(2024, 1, 2)) == 5.0 and c.requests == 1
    (tmp_path / "TEST.csv").write_text("date,v\n2024-01-01,.\n", encoding="utf-8")
    c = FredClient(cache_dir=tmp_path, fetch=lambda url: _table([6.0]))
    assert c.value_asof(SPEC, date(2024, 1, 2)) == 6.0 and c.requests == 1


def test_fred_cache_write_failure_is_logged_not_raised(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    c = FredClient(cache_dir=blocker / "sub", fetch=lambda url: _table([7.0]))
    assert c.value_asof(SPEC, date(2024, 1, 2)) == 7.0
    assert "cache write failed" in caplog.text


def test_fred_vintage_failure_and_staleness():
    spec = FredSeries("REV", 1, 10, revised=True)
    c = FredClient(vintages=True, fetch=lambda url: (_ for _ in ()).throw(OSError("down")))
    assert c.value_asof(spec, date(2024, 1, 2)) is None
    assert c.series_asof(spec, pd.DatetimeIndex(["2024-01-02"])).isna().all()
    ok = FredClient(fetch=lambda url: _table([1.0]))
    assert ok.value_asof(SPEC, date(2023, 12, 1)) is None  # before the first publication
    assert ok.value_asof(SPEC, date(2024, 3, 1)) is None  # older than max_age_days


# --------------------------------------------------------------------------- Yahoo parsing
class _FakeYF(types.ModuleType):
    def __init__(self, frame=None, news=None, info=None, raise_ticker=False):
        super().__init__("yfinance")
        self.frame, self._news, self._info, self.raise_ticker = frame, news, info, raise_ticker

    def download(self, sym, **kw):
        return self.frame

    def Ticker(self, sym):
        if self.raise_ticker:
            raise RuntimeError("schema changed")
        return types.SimpleNamespace(news=self._news, info=self._info)


TODAY = date(2026, 9, 23)


@pytest.fixture
def yahoo(monkeypatch):
    monkeypatch.setattr(yahoo_mod, "_now", lambda: datetime(2026, 9, 23, 19, 0, tzinfo=UTC))

    def make(**kw):
        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF(**kw))
        return YahooProvider(make_config(data_provider="yahoo", edgar=False))

    return make


def _actions_frame(multi=False, tz=False):
    idx = pd.date_range("2026-09-14", periods=8, freq="B", tz="America/New_York" if tz else None)
    df = pd.DataFrame(
        {"Close": [400.0, 404, 408, 100, 101, 102, 103, 999], "Stock Splits": [0, 0, 0, 4.0, 0, 0, 0, 0]}, index=idx
    )
    if multi:
        df.columns = pd.MultiIndex.from_product([df.columns, ["AAPL"]])
    return df


@pytest.mark.parametrize("multi,tz", [(False, False), (True, True)])
def test_yahoo_corporate_actions_parse_splits_and_as_traded_close(yahoo, multi, tz):
    p = yahoo(frame=_actions_frame(multi, tz))
    ins = Instrument.parse("AAPL")
    assert p.splits(ins) == {date(2026, 9, 17): 4.0}
    assert p.as_traded_close(ins, date(2026, 9, 16)) == pytest.approx(408.0 * 4.0)  # pre-split shares
    assert p.as_traded_close(ins, date(2026, 9, 22)) == 103.0  # today's partial bar is dropped
    assert p.as_traded_close(ins, date(2026, 9, 1)) is None
    got = p.as_traded_closes(ins, pd.DatetimeIndex(["2026-09-14", "2026-09-13"]))
    assert got[0] == 400.0 and math.isnan(got[1])
    assert p.as_traded_closes(Instrument.parse("EURUSD"), pd.DatetimeIndex(["2026-09-14"])) is None


def test_yahoo_corporate_action_outage_degrades_to_none(yahoo):
    p = yahoo(frame=pd.DataFrame())
    ins = Instrument.parse("AAPL")
    with pytest.raises(ValueError, match="no Yahoo corporate-action history"):
        p.splits(ins)
    assert p.as_traded_close(ins, TODAY) is None
    assert p.as_traded_closes(ins, pd.DatetimeIndex(["2026-09-14"])) is None


def test_yahoo_news_parsing_shapes_and_window(yahoo):
    ts = datetime(2026, 9, 21, 12, tzinfo=UTC).timestamp()
    news = [
        {
            "content": {
                "title": "Wrapped",
                "pubDate": "2026-09-22T10:00:00Z",
                "provider": {"displayName": "Wire"},
                "summary": None,
            }
        },
        {"title": "Flat", "providerPublishTime": ts, "publisher": "Pub", "provider": "not a dict"},
        {"content": {"title": "", "pubDate": "2026-09-22"}},  # no title: skipped
        {"content": {"title": "No date"}},  # no timestamp: skipped
        {"content": {"title": "Old", "pubDate": "2026-08-01"}},
    ]  # outside the window
    p = yahoo(news=news)
    out = p.news(Instrument.parse("AAPL"), TODAY, lookback_days=7)
    assert [(n.headline if hasattr(n, "headline") else n.title) for n in out] == ["Wrapped", "Flat"]
    assert out[0].source == "Wire" and out[0].summary == "" and out[1].source == "Pub"
    assert p.news(Instrument.parse("AAPL"), TODAY - timedelta(days=60), 7) == []  # beyond Yahoo's horizon


def test_yahoo_news_and_fundamentals_failures_are_empty(yahoo):
    p = yahoo(raise_ticker=True)
    assert p.news(Instrument.parse("AAPL"), TODAY, 7) == []
    assert p.fundamentals(Instrument.parse("AAPL"), TODAY) == {}


def test_yahoo_fundamentals_snapshot_units(yahoo):
    p = yahoo(info={"trailingPE": 30.0, "debtToEquity": 150.0, "freeCashflow": 5e9, "marketCap": 1e11})
    f = p.fundamentals(Instrument.parse("AAPL"), TODAY)
    assert f["debt_to_equity"] == 1.5 and f["fcf_yield"] == pytest.approx(0.05) and f["pe_ratio"] == 30.0
    p = yahoo(info={"marketCap": 0, "freeCashflow": 5e9})
    f = p.fundamentals(Instrument.parse("AAPL"), TODAY)
    assert f["fcf_yield"] is None and f["debt_to_equity"] is None
    assert p.fundamentals(Instrument.parse("AAPL"), TODAY - timedelta(days=30)) == {}  # stale snapshot
    assert p.fundamentals(Instrument.parse("EURUSD"), TODAY) == {}


# --------------------------------------------------------------------------- Almgren-Chriss
@pytest.mark.parametrize("kappa", [8.98846567431158e307, 1.7e308, 1e300])
@pytest.mark.parametrize("n", [1, 3])
def test_almgren_chriss_huge_kappa_is_finite(kappa, n):
    """Regression (found by test_fuzz): for kappa > DBL_MAX / 2, ``-2 * kappa`` overflowed to
    -inf and ``-inf * 0`` at the last slice gave NaN. Huge kappa means sell everything now."""
    from agentic_trader import quant
    from agentic_trader.quant import pycore

    for impl in (pycore.almgren_chriss, quant.almgren_chriss):
        out = impl(1000.0, n, kappa)
        assert np.all(np.isfinite(out)) and out[0] == pytest.approx(1000.0) and out.sum() == pytest.approx(1000.0)
