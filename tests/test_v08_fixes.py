"""Residual defects the v0.8 verification pass raised on the engine/data cluster (verify_v08_digest
findings 3, 10, 18, 19/32/33, 24, 27, 35, 36, 37, 57, 69, 75). Every test fails on the tree the
verifiers measured and passes now; engine tests run on both backends and, when the extension is
built, assert the two agree."""
from __future__ import annotations

import logging
import subprocess
import sys
import time
import types
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, TradingGraph, make_config, quant
from agentic_trader.agents.risk import RiskAnalyst, risk_facts
from agentic_trader.algo import algo_cost_ratio, plan_execution
from agentic_trader.backtest import impact_coefficients, run_portfolio_backtest
from agentic_trader.data import CSVProvider, SyntheticProvider
from agentic_trader.data import yahoo as yahoo_mod
from agentic_trader.data.base import clean_ohlcv
from agentic_trader.data.fred import FredClient
from agentic_trader.data.yahoo import YahooProvider
from agentic_trader.memory import DecisionMemory
from agentic_trader.portfolio import METHODS, construct
from agentic_trader.quant import pycore
from agentic_trader.sentiment import score_fx_headline
from agentic_trader.state import Action, FinalDecision, TradeProposal

ROOT = Path(__file__).resolve().parents[1]
NAN = float("nan")
INF = float("inf")
CFG = make_config(memory_path=None)
CPP = quant.BACKEND == "cpp"
needs_cpp = pytest.mark.skipif(not CPP, reason="C++ extension not built")
ENGINES = pytest.mark.parametrize("engine", [quant.run_backtest, pycore.run_backtest_ex], ids=["active", "numpy"])


def _same_result(a, b):
    np.testing.assert_allclose(a.equity, b.equity, rtol=1e-12)
    np.testing.assert_allclose(a.positions, b.positions, rtol=1e-12, atol=1e-15)
    np.testing.assert_allclose(a.returns, b.returns, rtol=1e-12, atol=1e-15)
    assert a.ruined_at == b.ruined_at and a.stop_exits == b.stop_exits
    assert a.metrics.ruined == b.metrics.ruined
    assert a.metrics.max_drawdown == pytest.approx(b.metrics.max_drawdown, abs=1e-14)


# ============================================ 18: ruin is decided per factor, not on the product
def _ruin_cases():
    lev3 = quant.BacktestConfig(cost_bps=5000.0, max_leverage=3.0, allow_short=False)
    lev2 = quant.BacktestConfig(max_leverage=2.0, allow_short=False)
    px = [100.0, 20.0, 25.0]
    return {
        "fee and move each exceed the account": (px, np.full(3, 3.0), lev3, {}),
        "entry impact >= 100% on a -80% bar": (px, np.full(3, 2.0), lev2, {"impact": np.full(3, 0.5)}),
        "exit impact >= 100% after a gap through the stop": (
            px, np.full(3, 2.0), lev2,
            {"open": px, "high": px, "low": px, "stop": [99.0, NAN, NAN], "impact": [0.0, 0.5, 0.0]}),
    }


@ENGINES
@pytest.mark.parametrize("case", list(_ruin_cases()))
def test_18_two_negative_factors_do_not_multiply_into_a_surviving_account(engine, case):
    prices, w, cfg, extras = _ruin_cases()[case]
    r = engine(prices, w, cfg, **extras)
    assert r.ruined_at == 1, case                                  # verifiers: -1 with equity 70000 / 24852.8
    assert r.equity[1] == 0.0 and r.equity[2] == 0.0 and r.returns[1] == -1.0 and r.returns[2] == 0.0
    assert r.positions[1] == 0.0 and r.positions[2] == 0.0 and r.metrics.ruined
    assert r.metrics.cumulative_return == -1.0 and r.metrics.max_drawdown == 1.0
    if "stop" in extras:
        assert r.stop_exits == 1 and r.exits[1] == 1.0


@ENGINES
def test_18_each_factor_alone_still_ruins_and_a_live_account_does_not(engine):
    lev3 = quant.BacktestConfig(cost_bps=5000.0, max_leverage=3.0, allow_short=False)
    assert engine([100.0, 100.0, 100.0], np.full(3, 3.0), lev3).ruined_at == 1           # fee alone
    assert engine([100.0, 20.0, 25.0], np.full(3, 3.0), replace(lev3, cost_bps=0.0)).ruined_at == 1  # move alone
    ok = engine([100.0, 110.0, 121.0], np.full(3, 1.0), quant.BacktestConfig(cost_bps=0.0, slippage_bps=0.0))
    assert ok.ruined_at == -1 and not ok.metrics.ruined
    # a survivable bar with a large but sub-100% fee is unchanged: (1 - 0.6) * (1 + 0.5) = 0.6
    r = engine([100.0, 125.0, 125.0], np.full(3, 2.0), quant.BacktestConfig(cost_bps=3000.0, max_leverage=2.0,
                                                                              allow_short=False))
    assert r.ruined_at == -1 and r.equity[1] == pytest.approx(100000.0 * 0.4 * 1.5)


@ENGINES
def test_18_equity_reaching_zero_sets_the_ruin_flag_on_that_bar(engine):
    w = np.full(3, np.nextafter(1.0, 0.0))
    r = engine([100.0, 50.0, 60.0], w, quant.BacktestConfig(cost_bps=1e4, allow_short=False))
    assert r.ruined_at == 1                                        # verifiers: 2, with a position carried on 0 equity
    assert list(r.equity) == [100000.0, 0.0, 0.0] and list(r.returns) == [0.0, -1.0, 0.0]
    assert r.positions[1] == 0.0 and r.positions[2] == 0.0


@needs_cpp
@pytest.mark.parametrize("case", list(_ruin_cases()))
def test_18_backends_agree_on_per_factor_ruin(case):
    prices, w, cfg, extras = _ruin_cases()[case]
    _same_result(quant.run_backtest(prices, w, cfg, **extras), pycore.run_backtest_ex(prices, w, cfg, **extras))
    w0 = np.full(3, np.nextafter(1.0, 0.0))
    c0 = quant.BacktestConfig(cost_bps=1e4, allow_short=False)
    _same_result(quant.run_backtest([100.0, 50.0, 60.0], w0, c0), pycore.run_backtest_ex([100.0, 50.0, 60.0], w0, c0))


@pytest.mark.parametrize("metrics", [quant.compute_metrics, pycore.compute_metrics], ids=["active", "numpy"])
def test_18_compute_metrics_statistics_stop_at_the_ruin_bar(metrics):
    # An externally supplied curve (the portfolio path) with a position carried through the dead
    # bars: the bars after ruin are not live, so they count neither as held nor as losing bars.
    dead = metrics([1.0, 1.1, 0.0, 0.0, 0.0], [1, 1, 1, 1, 1], 252.0)
    cut = metrics([1.0, 1.1, 0.0], [1, 1, 0], 252.0)
    assert dead.ruined and cut.ruined
    assert dead.win_rate == cut.win_rate == 0.5                    # 1 of 2 live bars, not 1 of 4
    assert dead.sharpe == pytest.approx(cut.sharpe) and dead.sharpe < 0
    assert dead.max_drawdown == 1.0 and dead.cumulative_return == -1.0


# ==================================== 27: a zero-variance sleeve is inactive under every scheme
def _mixed(rows: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    return pd.DataFrame({"A": rng.normal(0, 0.01, rows), "B": rng.normal(0, 0.012, rows), "C": 0.0},
                        index=pd.bdate_range("2024-01-01", periods=rows))


@pytest.mark.parametrize("method", METHODS)
def test_27_zero_variance_sleeve_gets_nothing_under_every_scheme(method, caplog):
    with caplog.at_level(logging.WARNING, logger="agentic_trader.portfolio"):
        pw = construct({"A": 1, "B": 1, "C": 1}, _mixed(), method, max_weight=1.0, target_vol=None)
    assert pw.allocation[2] == 0.0                                 # min_variance / mean_variance gave it 100%
    assert np.isfinite(pw.allocation).all() and pw.allocation.sum() == pytest.approx(1.0)
    assert pw.allocation[:2].min() > 0.0 and pw.weights[2] == 0.0 and np.isfinite(pw.expected_vol)
    assert pw.expected_vol > 0.0
    assert "zero variance" in caplog.text and "'C'" in caplog.text
    # the same book without the frozen sleeve is the same allocation
    two = construct({"A": 1, "B": 1}, _mixed()[["A", "B"]], method, max_weight=1.0, target_vol=None)
    np.testing.assert_allclose(pw.allocation[:2], two.allocation, atol=1e-9)


def test_27_group_budget_risk_parity_allocates_zero_to_a_group_without_variance():
    groups, budgets = {"A": "eq", "B": "eq", "C": "fx"}, {"eq": 0.6, "fx": 0.4}
    out = {}
    for method in METHODS:
        pw = construct({"A": 1, "B": 1, "C": 1}, _mixed(), method, max_weight=1.0, target_vol=None,
                       groups=groups, group_budgets=budgets)                      # risk_parity raised
        assert pw.allocation[2] == 0.0 and pw.allocation.sum() == pytest.approx(1.0)
        assert list(pw.group_risk.index) == ["eq"] and pw.group_risk["allocation"].iloc[0] == pytest.approx(1.0)
        out[method] = pw.allocation
    np.testing.assert_allclose(out["equal"], [0.5, 0.5, 0.0])
    # a window where no active sleeve has variance still raises, for every scheme
    for method in METHODS:
        with pytest.raises(ValueError, match="no active sleeve has positive variance"):
            construct({"C": 1}, _mixed(), method, max_weight=1.0, target_vol=None)
        with pytest.raises(ValueError):
            construct({"A": 1, "B": 1, "C": 1}, _mixed().assign(A=0.0, B=0.0), method)


class _FrozenAAPL(SyntheticProvider):
    """AAPL's prices are frozen over the block (a forward-filled feed); the others trade."""
    flat_start, flat_end = pd.Timestamp("2024-01-25"), pd.Timestamp("2024-03-08")

    def history(self, instrument, start, end):
        h = super().history(instrument, start, end).copy()
        m = (h.index >= self.flat_start) & (h.index <= self.flat_end)
        if instrument.symbol == "AAPL" and m.any():
            first = h.index[m][0]
            for c in ("Open", "High", "Low", "Close"):
                h.loc[m, c] = h.loc[first, "Close"]
        return h


@pytest.mark.parametrize("weighting", ["min_variance", "mean_variance"])
def test_27_portfolio_backtest_never_hands_the_book_to_a_frozen_sleeve(weighting):
    rp = run_portfolio_backtest(["AAPL", "JPM", "MSFT"], "2024-01-02", "2024-03-28", CFG, 5,
                                provider=_FrozenAAPL(CFG), weighting=weighting, cov_window=20)
    a = rp.allocations
    assert np.isfinite(a.to_numpy()).all()
    np.testing.assert_allclose(a.sum(axis=1), 1.0)
    inside = a[(a.index >= "2024-02-27") & (a.index <= "2024-03-08")]   # 20-row windows inside the block
    assert len(inside) >= 5
    assert inside["AAPL"].max() == 0.0                             # verifiers: 1.000 (JPM + MSFT 0.000)
    assert (inside[["JPM", "MSFT"]].min(axis=1) > 0.0).all()
    assert a["AAPL"].max() > 0.0                                   # live again outside the block


# ================================== 3: scan() keys held positions the way it keys book columns
@pytest.fixture
def book_graph():
    cfg = make_config(make_config(memory_path=None), risk={"max_book_var_95": 0.005})
    g = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None)
    seen = {}
    orig = g.propagate

    def spy(ins, as_of, **kw):
        seen[ins.symbol] = (kw.get("book"), kw.get("current_weight"))
        return orig(ins, as_of, **kw)
    g.propagate = spy
    return g, seen


@pytest.mark.parametrize("key", ["EUR/USD", "EURUSD=X", "eurusd ", "EURUSD"])
def test_3_scan_sees_a_held_position_however_its_key_is_spelled(book_graph, key):
    g, seen = book_graph
    df = g.scan(["QQQ"], "2024-03-01", positions={key: 3.0})
    book, _ = seen["QQQ"]
    assert book.positions == {"EURUSD": 3.0} and "EURUSD" in book.returns.columns
    row = df.iloc[0]
    assert row.error == "" and row.target_weight == 0.0             # verifiers: +0.1731, "book VaR n/a ..."
    assert "already exceeds" in row.adjustments and "n/a" not in row.adjustments


def test_3_scan_matches_the_symbol_under_decision_and_rejects_unparseable_keys(book_graph):
    g, seen = book_graph
    g.scan(["QQQ"], "2024-03-01", positions={"qqq": 0.25, "SPY": 0.1})
    book, current = seen["QQQ"]
    assert current == 0.25 and "QQQ" not in book.positions and book.positions == {"SPY": 0.1}
    with pytest.raises(ValueError, match="BAD TICKER"):
        g.scan(["QQQ"], "2024-03-01", positions={"BAD TICKER": 3.0})
    with pytest.raises(ValueError, match="different weights"):
        g.scan(["QQQ"], "2024-03-01", positions={"EUR/USD": 3.0, "EURUSD": 1.0})
    assert g.scan(["QQQ"], "2024-03-01", positions={"EUR/USD": 3.0, "EURUSD=X": 3.0}).iloc[0].error == ""


# ============================ 36: bar completeness is judged on the exchange's (New York) date
class _FakeYF:
    def __init__(self, today: date):
        self.today = today                                         # the exchange's in-progress day
        self.calls: list[tuple] = []
        self.partial_close = 137.0

    def download(self, sym, start=None, end=None, auto_adjust=True, progress=False, actions=False):
        self.calls.append((sym, start, end))
        s, e = pd.Timestamp(start), pd.Timestamp(end)
        last = min(e - pd.Timedelta(days=1), pd.Timestamp(self.today) - pd.Timedelta(days=1))
        idx = pd.bdate_range(s, last)
        if e > pd.Timestamp(self.today):
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


D = date(2026, 9, 23)                                              # a Wednesday, US session open
SESSION_OPEN_UTC = datetime(2026, 9, 23, 19, 0, tzinfo=timezone.utc)      # 15:00 New York
AFTER_NY_MIDNIGHT_UTC = datetime(2026, 9, 24, 4, 30, tzinfo=timezone.utc)  # 00:30 New York, D+1


@pytest.fixture
def yahoo_clock(monkeypatch):
    yf = _FakeYF(D)
    monkeypatch.setitem(sys.modules, "yfinance", yf)
    clock = {"now": SESSION_OPEN_UTC}
    monkeypatch.setattr(yahoo_mod, "_now", lambda: clock["now"])
    return YahooProvider(make_config(data_provider="yahoo", edgar=False)), yf, clock


@pytest.mark.parametrize("host_tz", ["Asia/Kolkata", "Asia/Tokyo", "Europe/London", "America/Los_Angeles"])
def test_36_completeness_is_the_new_york_date_whatever_the_host_clock_says(yahoo_clock, host_tz):
    p, yf, clock = yahoo_clock
    ins = Instrument.parse("AAPL")
    local = SESSION_OPEN_UTC.astimezone(ZoneInfo(host_tz))        # 00:30 IST on D+1; 12:00 in Los Angeles on D
    clock["now"] = local
    assert yahoo_mod._today() == D                                 # verifiers: local date D+1 east of UTC+4
    h = p.history(ins, D - timedelta(days=120), D + timedelta(days=1))
    assert h.index[-1].date() == D - timedelta(days=1)             # the in-progress bar is not served ...
    assert not (h.index >= pd.Timestamp(D)).any() and 137.0 not in h["Close"].to_numpy()
    assert p._covered[ins.yahoo_symbol][1] == D - timedelta(days=1)  # ... nor cached as complete
    assert len(yf.calls) == 1
    # once it is D+1 in New York the D bar is complete, whatever the host's own date
    clock["now"] = AFTER_NY_MIDNIGHT_UTC.astimezone(ZoneInfo(host_tz))
    yf.today = D + timedelta(days=1)
    assert yahoo_mod._today() == D + timedelta(days=1)
    h = p.history(ins, D - timedelta(days=120), D + timedelta(days=1))
    assert h.index[-1].date() == D and float(h["Close"].iloc[-1]) != 137.0 and len(yf.calls) == 2
    assert not (h.index > pd.Timestamp(D)).any()


def test_36_the_corporate_action_table_follows_the_exchange_date_too(yahoo_clock):
    p, yf, clock = yahoo_clock
    clock["now"] = SESSION_OPEN_UTC.astimezone(ZoneInfo("Asia/Kolkata"))
    a = p._corporate_actions("AAPL")
    assert a.index[-1].date() == D - timedelta(days=1) and p._actions_day["AAPL"] == D


def test_36_an_empty_download_raises_the_documented_value_error(yahoo_clock):
    p, yf, clock = yahoo_clock
    yf.download = lambda *a, **k: pd.DataFrame()
    with pytest.raises(ValueError, match="no Yahoo data for ZZZZ"):    # verifiers: TypeError from _complete_bars
        p.history(Instrument.parse("ZZZZ"), D - timedelta(days=30), D)
    empty = p.history(Instrument.parse("AAPL"), D, D)              # end < start once clipped to yesterday
    assert empty.empty and isinstance(empty.index, pd.DatetimeIndex)
    assert list(empty.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_36_a_reconfigured_provider_shares_the_downloads_under_its_own_settings(yahoo_clock, monkeypatch):
    """scripts/measure_v08.py hands one provider to every run; a run that overrides cash_leg or
    edgar needs the same bars under its own config (the first v0.8 measurement ran "EDGAR off"
    and "cash leg off" with both still on, because the shared provider kept its settings)."""
    from agentic_trader.data import edgar as edgar_mod
    p, yf, clock = yahoo_clock
    ins = Instrument.parse("AAPL")
    h = p.history(ins, D - timedelta(days=120), D)
    q = p.reconfigured(make_config(p.config, cash_leg="off"))
    assert q is not p and q.config["cash_leg"] == "off" and p.config["cash_leg"] == "auto"
    pd.testing.assert_frame_equal(q.history(ins, D - timedelta(days=120), D), h)
    assert len(yf.calls) == 1                                       # the bars were not downloaded again
    assert np.isnan(q.risk_free_series(h.index)).all()              # the engine credits nothing
    q.history(Instrument.parse("MSFT"), D - timedelta(days=30), D)
    assert "MSFT" in p._cache and len(yf.calls) == 2                # one cache, both ways
    assert q.macro_sources == {} and q.macro_sources is not p.macro_sources
    monkeypatch.setattr(edgar_mod.EdgarClient, "from_config", classmethod(lambda cls, c: ("edgar", c["edgar"])))
    assert p.reconfigured(make_config(p.config, edgar=True)).edgar == ("edgar", True)   # its own EDGAR client
    assert p.reconfigured(make_config(p.config, edgar=False)).edgar == ("edgar", False)


# ====================================== 69: the pair is a subject; both legs -> the first named
@pytest.mark.parametrize("headline, base, quote, sign", [
    ("USD/JPY falls as yen rallies", "USD", "JPY", -1),               # was 0.00
    ("Yen strengthens; USD/JPY slides", "USD", "JPY", -1),            # was 0.00
    ("BoJ hikes; USD/JPY tumbles", "USD", "JPY", -1),                 # was 0.00
    ("Loonie firms; USD/CAD slips", "USD", "CAD", -1),                # was 0.00
    ("Dollar strengthens; EUR/USD slides", "EUR", "USD", -1),         # was 0.00
    ("Yen jumps, USD/JPY drops below 150", "USD", "JPY", -1),         # -0.46 in v0.7, 0.00 in v0.8
    ("USD/JPY rallies as BoJ stays dovish", "USD", "JPY", +1),
    ("Yen gains against dollar", "USD", "JPY", -1),                   # was +0.46
    ("Dollar falls against the euro", "EUR", "USD", +1),              # was -0.46
    ("Euro climbs against the dollar", "EUR", "USD", +1),
    ("Dollar weakens; yen strengthens on hawkish BoJ", "USD", "JPY", -1),
    ("Yen weakens as BoJ stays dovish", "USD", "JPY", +1),
    ("Greenback gains; euro falls to two-week low", "EUR", "USD", -1),
    ("Sterling falls after BoE cuts", "GBP", "USD", -1),
    ("Audit finds strong growth at Cadence", "USD", "CAD", +1),
    ("Traders await USD inflation data", "EUR", "USD", 0),
])
def test_69_pair_clauses_are_not_flipped_and_two_leg_clauses_take_the_first_subject(headline, base, quote, sign):
    assert np.sign(score_fx_headline(headline, base, quote)) == sign, headline


def test_69_pair_only_clause_keeps_its_own_tone_alongside_a_quote_clause():
    # Both clauses are bad for USD/JPY: the yen clause is flipped, the pair clause is not.
    assert score_fx_headline("Yen strengthens; USD/JPY slides", "USD", "JPY") == pytest.approx(np.tanh(-1.0))
    # The synthetic template now scores on its documented semantics (-0.905, was -0.462).
    assert score_fx_headline("Hawkish JPY policymakers boost JPY, pressuring USD/JPY", "USD", "JPY") == \
        pytest.approx(np.tanh(-1.5))
    # "dollar-yen" names the pair and is not a yen clause
    assert score_fx_headline("Dollar-yen slides in thin trading", "USD", "JPY") < 0
    assert score_fx_headline("Yen slides in thin trading", "USD", "JPY") > 0


# ================================== 10: concurrent appends from separate processes lose nothing
_APPEND_WORKER = """
import sys, time
from datetime import date
import pandas as pd
from agentic_trader.memory import DecisionMemory
path, k, n, start = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
m = DecisionMemory(path)
idx = pd.bdate_range("2020-01-01", periods=n)
while time.time() < start:
    pass
for i in range(n):
    m.record(f"P{k}", idx[i].date(), "BUY", 0.2, 100.0 + i, "y" * 80, horizon_days=5, provider="csv")
"""


def test_10_concurrent_appends_from_separate_processes_lose_no_record(tmp_path):
    path = tmp_path / "memory.jsonl"
    n_proc, n_rec = 4, 150
    start = time.time() + 2.0
    procs = [subprocess.Popen([sys.executable, "-c", _APPEND_WORKER, str(path), str(k), str(n_rec), str(start)],
                              cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
             for k in range(n_proc)]
    outs = [p.communicate(timeout=180) for p in procs]
    assert all(p.returncode == 0 for p in procs), [o[1].decode(errors="replace")[-500:] for o in outs]
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == n_proc * n_rec                            # verifiers on Windows: 958 of 1200
    m = DecisionMemory(path)
    assert m.skipped_lines == 0 and len(m.entries) == n_proc * n_rec
    assert sorted({e.symbol for e in m.entries}) == [f"P{k}" for k in range(n_proc)]


def test_10_two_objects_in_one_process_still_share_the_file(tmp_path):
    path = tmp_path / "m.jsonl"
    a, b = DecisionMemory(path), DecisionMemory(path)
    for i in range(50):
        a.record("A", date(2024, 1, 2) + timedelta(days=i), "BUY", 0.5, 100.0, "a")
        b.record("B", date(2024, 1, 2) + timedelta(days=i), "SELL", -0.5, 50.0, "b")
    again = DecisionMemory(path)
    assert len(again.entries) == 100 and again.skipped_lines == 0
    assert path.read_text(encoding="utf-8").count("\n") == 100    # the lock never writes into the log


# ============================= 75: an entry whose exit bar never arrives still expires
def test_75_entry_whose_exit_bar_never_arrives_expires_after_twice_its_horizon():
    m = DecisionMemory(None)
    m.record("X", date(2024, 1, 2), "BUY", 0.5, 100.0, "s", horizon_days=10, provider="csv")
    idx = pd.bdate_range("2023-12-01", "2024-01-08")               # the feed stops 4 bars after entry
    dead = pd.DataFrame({"Close": np.linspace(100.0, 104.0, len(idx))}, index=idx)
    assert m.resolve("X", date(2024, 1, 8), dead, provider="csv") == 0        # not yet: 6 days old
    assert m.resolve("X", date(2024, 1, 30), dead, provider="csv") == 0       # 28 days: at the limit
    assert m.resolve("X", date(2024, 6, 3), dead, provider="csv") == 1        # verifiers: 0, open forever
    e = m.entries[0]
    assert e.expired and e.pnl is None and e.lesson is None and e.resolved_on == "2024-06-03"
    assert m.resolve("X", date(2024, 6, 4), dead, provider="csv") == 0
    # the same entry on a series that does reach the exit bar is settled, not expired
    m2 = DecisionMemory(None)
    m2.record("X", date(2024, 1, 2), "BUY", 0.5, 100.0, "s", horizon_days=10, provider="csv")
    full = pd.DataFrame({"Close": np.linspace(100.0, 110.0, 40)}, index=pd.bdate_range("2023-12-01", periods=40))
    assert m2.resolve("X", date(2024, 6, 3), full, provider="csv") == 1 and not m2.entries[0].expired
    assert m2.entries[0].pnl is not None


# ============================== 19/32/33: kappa 0 is TWAP; kappa must be finite and >= 0
@pytest.mark.parametrize("bad", [INF, -INF, NAN, -1.0], ids=["inf", "-inf", "nan", "negative"])
def test_19_non_finite_kappa_raises_everywhere_on_both_backends(bad):
    with pytest.raises(ValueError, match="kappa"):
        quant.almgren_chriss(223.0, 78, bad)                       # verifiers: a NaN last slice for inf
    with pytest.raises(ValueError, match="kappa"):
        pycore.almgren_chriss(223.0, 78, bad)
    with pytest.raises(ValueError, match="kappa"):
        algo_cost_ratio("ac", 78, "equity", bad)
    dec = FinalDecision("AAPL", date(2024, 3, 1), Action.BUY, 0.5, 0.0, None, None, "")
    with pytest.raises(ValueError, match="kappa"):
        plan_execution(dec, Instrument.parse("AAPL"), 0.0, 1e6, 100.0, adv=5e6, algo="ac", ac_kappa=bad)
    if np.isfinite(bad):
        return
    cfg = make_config(memory_path=None, costs={"impact_coeff": 1.0, "execution_algo": "ac", "ac_kappa": bad})
    full = SyntheticProvider(cfg).history(Instrument.parse("AAPL"), date(2023, 1, 1), date(2023, 12, 29))
    with pytest.raises(ValueError):
        impact_coefficients(full, Instrument.parse("AAPL"), cfg)


def test_19_finite_kappa_schedules_are_finite_and_sum_to_the_order():
    for kappa in (0.0, 1e-9, 3.0, 1e4, 1e300):
        for q in (quant.almgren_chriss(223.0, 78, kappa), pycore.almgren_chriss(223.0, 78, kappa)):
            assert np.isfinite(q).all() and q.sum() == pytest.approx(223.0, abs=1e-9) and (q >= -1e-12).all()
    np.testing.assert_allclose(quant.almgren_chriss(223.0, 78, 0.0), np.full(78, 223.0 / 78))


def _k(cfg_costs):
    cfg = make_config(memory_path=None, costs=cfg_costs)
    ins = Instrument.parse("AAPL")
    full = SyntheticProvider(cfg).history(ins, date(2023, 1, 1), date(2023, 12, 29))
    return impact_coefficients(full, ins, cfg)


def test_32_ac_kappa_zero_is_twap_in_the_backtester_not_the_default_urgency():
    twap = _k({"impact_coeff": 1.0, "execution_algo": "twap"})
    ac0 = _k({"impact_coeff": 1.0, "execution_algo": "ac", "ac_kappa": 0.0})
    ac3 = _k({"impact_coeff": 1.0, "execution_algo": "ac", "ac_kappa": 3.0})
    default = _k({"impact_coeff": 1.0, "execution_algo": "ac"})
    ok = np.isfinite(twap)
    assert ok.sum() > 200
    np.testing.assert_allclose(ac0[ok], twap[ok], rtol=1e-12)     # verifiers: ac0 == ac3 (ratio 1.151, not 1.061)
    np.testing.assert_allclose(ac3[ok] / twap[ok], algo_cost_ratio("ac", 78, "equity", 3.0) / algo_cost_ratio("twap", 78, "equity"), rtol=1e-12)
    assert not np.allclose(ac0[ok], ac3[ok])
    np.testing.assert_allclose(default[ok], ac3[ok], rtol=1e-12)  # unset still means the config default 3.0
    assert plan_execution(FinalDecision("AAPL", date(2024, 3, 1), Action.BUY, 0.5, 0.0, None, None, ""),
                          Instrument.parse("AAPL"), 0.0, 1e6, 100.0, adv=5e6, algo="ac", ac_kappa=0.0).ac_kappa == 0.0


# ===================================== 57: clean_ohlcv treats +inf like any other bad tick
def test_57_clean_ohlcv_repairs_plus_inf_like_minus_inf_and_never_widens_high_to_inf():
    idx = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"])
    raw = pd.DataFrame({"Open": [INF, -INF, 101.0, 100.0], "High": [102.0, 102.0, INF, 100.0],
                        "Low": [99.0, 99.0, -INF, 100.0], "Close": [100.0, 100.0, 100.0, INF],
                        "Volume": [1.0, 1.0, INF, 1.0]}, index=idx)
    out = clean_ohlcv(raw)
    assert np.isfinite(out[["Open", "High", "Low", "Close"]].to_numpy()).all()    # verifiers: Open=inf, High=inf
    assert list(out.index.date) == [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]  # +inf Close dropped
    assert out.loc["2024-01-02", "Open"] == 100.0 and out.loc["2024-01-02", "High"] == 102.0
    assert out.loc["2024-01-03", "Open"] == 100.0
    assert out.loc["2024-01-04", "High"] == 101.0 and out.loc["2024-01-04", "Low"] == 100.0
    assert (out["High"] >= out[["Open", "Close"]].max(axis=1)).all()
    assert (out["Low"] <= out[["Open", "Close"]].min(axis=1)).all()


# =============================== 35: a stale FRED file is served when the re-download fails
def _write_stale(cache: Path, sid: str, value: float, last: date, age_days: int) -> None:
    idx = pd.date_range(last - timedelta(days=400), last, freq="D")
    pd.DataFrame({sid: value}, index=pd.Index(idx, name="observation_date")).to_csv(cache / f"{sid}.csv")
    old = time.time() - age_days * 86400.0
    import os
    os.utime(cache / f"{sid}.csv", (old, old))


def test_35_stale_cache_is_served_with_a_warning_when_the_redownload_fails(tmp_path, caplog):
    today = date.today()
    last = today - timedelta(days=180)
    _write_stale(tmp_path, "DFF", 4.33, last, age_days=180)
    calls = []

    def dead(url):
        calls.append(url)
        raise ConnectionResetError("offline")
    c = FredClient(cache_dir=tmp_path, fetch=dead, cache_max_age_days=1.0)
    with caplog.at_level(logging.WARNING, logger="agentic_trader.data.fred"):
        assert c.rate("USD", last - timedelta(days=10)) == 4.33   # verifiers: None, and every FX view lost
    assert len(calls) == 1 and c.requests == 1
    assert "serving the cached" in caplog.text and "DFF" in caplog.text
    assert c.rate("USD", last - timedelta(days=100)) == 4.33 and len(calls) == 1   # loaded once
    assert c.rate("USD", today) is None                            # too old for a live date (max_age 10 days)
    assert (tmp_path / "DFF.csv").stat().st_mtime < time.time() - 100 * 86400  # the stale file is left alone
    # a working re-download still replaces the stale file
    def fresh(url):
        idx = pd.date_range(today - timedelta(days=400), today - timedelta(days=1), freq="D")
        return pd.DataFrame({"DFF": 3.9}, index=pd.Index(idx, name="observation_date"))
    c2 = FredClient(cache_dir=tmp_path, fetch=fresh, cache_max_age_days=1.0)
    assert c2.rate("USD", today) == 3.9 and c2.requests == 1
    assert (tmp_path / "DFF.csv").stat().st_mtime > time.time() - 60
    # no cache file and no network is still unavailable, quietly
    c3 = FredClient(cache_dir=tmp_path / "empty", fetch=dead, cache_max_age_days=1.0)
    assert c3.rate("EUR", today) is None


# ====================================== 37: a blank Adj Close cell is not a missing bar
def test_37_row_with_a_close_but_a_blank_adj_close_is_kept_on_the_adjusted_basis(tmp_path, caplog):
    rows = ["Date,Open,High,Low,Close,Adj Close,Volume",
            "2024-01-01,100,101,99,100,50,1000", "2024-01-02,101,102,100,101,50.5,1000",
            "2024-01-03,102,103,101,102,,1000", "2024-01-04,103,104,102,103,51.5,1000",
            "2024-01-05,104,105,103,104,52,1000"]
    (tmp_path / "EDG.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    with caplog.at_level(logging.WARNING, logger="agentic_trader.data.csv_provider"):
        h = p.history(Instrument.parse("EDG"), date(2024, 1, 1), date(2024, 1, 5))
    assert len(h) == 5                                             # verifiers: 4, the row silently dropped
    assert h.loc["2024-01-03", "Close"] == pytest.approx(51.0)     # nearest row's factor 0.5
    assert h.loc["2024-01-03", "Open"] == pytest.approx(51.0) and h.loc["2024-01-03", "High"] == pytest.approx(51.5)
    np.testing.assert_allclose(h["Close"].to_numpy(), [50.0, 50.5, 51.0, 51.5, 52.0])
    assert "Adj Close blank on 1 row" in caplog.text
    # rows with an Adj Close are untouched by the repair
    (tmp_path / "FULL.csv").write_text("\n".join(r for r in rows if not r.startswith("2024-01-03")) + "\n")
    full = p.history(Instrument.parse("FULL"), date(2024, 1, 1), date(2024, 1, 5))
    assert full["Close"].tolist() == [50.0, 50.5, 51.5, 52.0]


# ==================================== 24: the analyst reports the CVaR of the position's side
def test_24_risk_facts_carry_the_short_side_cvar_and_the_analyst_text_uses_it():
    r = np.array([-0.005] * 235 + [0.03] * 15)
    np.random.default_rng(1).shuffle(r)                            # right-skewed: a short's tail is the fat one
    g = TradingGraph(CFG, memory=DecisionMemory(None), on_event=lambda *_: None)
    state = g.prepare(Instrument.parse("EURUSD"), date(2024, 3, 1))
    close = 100.0 * np.cumprod(1.0 + np.r_[0.0, r])
    state.history = pd.DataFrame({"Open": close, "High": close * 1.001, "Low": close * 0.999, "Close": close,
                                  "Volume": 0.0}, index=pd.bdate_range(end="2024-03-01", periods=len(close)))
    state.proposal = TradeProposal(Action.SELL, -1.0, 0.6, float(close[-1]), None, None, 10, "test")
    f = risk_facts(state, CFG)
    assert f["cvar_95_1d_short"] == pytest.approx(quant.historical_cvar(-r, 0.95))
    assert f["cvar_95_1d"] == pytest.approx(0.005, abs=1e-9) and f["cvar_95_1d_short"] == pytest.approx(0.03, abs=1e-9)
    view = RiskAnalyst(None, CFG, "neutral").speak(state, f, 1, [])
    assert "CVaR95 3.00%" in view.argument and "CVaR95 0.50%" not in view.argument   # verifiers: 0.50% for the short
    assert "VaR95 (position side) 3.00%" in view.argument
    state.proposal = replace(state.proposal, action=Action.BUY, target_weight=1.0)
    long_view = RiskAnalyst(None, CFG, "neutral").speak(state, risk_facts(state, CFG), 1, [])
    assert "CVaR95 0.50%" in long_view.argument


# =========================================================================================
# v0.8 regression review (engine-2 cluster): items (a)-(k). Each test fails without its fix.
# =========================================================================================
import inspect
import os
import warnings

from agentic_trader.backtest import AGENT, run_agent_backtest

from agentic_trader.cli import common as cli_common
from agentic_trader.cli import evaluate as cli_evaluate
from agentic_trader.data.csv_provider import one_basis

METRICS = pytest.mark.parametrize("metrics", [quant.compute_metrics, pycore.compute_metrics], ids=["active", "numpy"])


def _flat_book_cases():
    T = 250
    flat = np.full(T, 100.0)
    fred = 0.03 + 0.002 * np.cumsum(np.random.default_rng(1).normal(size=T)) / 10   # a wandering DTB3-like path
    return {
        "flat book, constant rf, no cash leg": (flat, np.zeros(T), quant.BacktestConfig(risk_free_annual=0.03), {}),
        "flat book under a varying cash leg (earns exactly rf)": (flat, np.zeros(T), quant.BacktestConfig(),
                                                                {"cash_rate": fred}),
        "unfunded flat book under the cash leg": (flat, np.zeros(T), quant.BacktestConfig(funded=False),
                                                  {"cash_rate": fred}),
    }


@ENGINES
@pytest.mark.parametrize("case", list(_flat_book_cases()))
def test_a_constant_excess_return_has_zero_sharpe_sortino_and_tstat(engine, case):
    prices, w, cfg, extras = _flat_book_cases()[case]
    m = engine(prices, w, cfg, **extras).metrics
    assert (m.sharpe, m.sharpe_tstat, m.sortino, m.annualized_vol) == (0.0, 0.0, 0.0, 0.0)   # was -8e15 / +0.97


@needs_cpp
@pytest.mark.parametrize("case", list(_flat_book_cases()))
def test_a_backends_agree_on_the_flat_book(case):
    prices, w, cfg, extras = _flat_book_cases()[case]
    a, b = quant.run_backtest(prices, w, cfg, **extras).metrics, pycore.run_backtest_ex(prices, w, cfg, **extras).metrics
    for f in ("sharpe", "sharpe_tstat", "sortino", "annualized_vol", "cumulative_return"):
        assert getattr(a, f) == getattr(b, f), f


@METRICS
def test_a_a_curve_compounding_at_exactly_rf_is_zero_and_a_real_curve_is_untouched(metrics):
    T = 400
    rf = 0.02 + 0.03 * np.linspace(0, 1, T)
    e = 100_000.0 * np.cumprod(np.r_[1.0, 1.0 + rf[:-1] / 252.0])          # the portfolio path: equity at rf
    z = metrics(e, np.ones(T), 252.0, rf, np.zeros(T))
    assert (z.sharpe, z.sharpe_tstat, z.sortino, z.annualized_vol) == (0.0, 0.0, 0.0, 0.0)   # was 0.686
    c = metrics(np.full(T, 100_000.0), np.zeros(T), 252.0, 0.03, np.zeros(T))
    assert (c.sharpe, c.sharpe_tstat, c.sortino, c.annualized_vol) == (0.0, 0.0, 0.0, 0.0)
    # a series with genuine dispersion, however small, is reported exactly as before
    r = np.random.default_rng(3).normal(1e-4, 1e-6, T - 1)
    e2 = 100_000.0 * np.cumprod(np.r_[1.0, 1.0 + r])
    ex = e2[1:] / e2[:-1] - 1.0 - 0.03 / 252.0
    m = metrics(e2, np.ones(T), 252.0, 0.03, np.zeros(T))
    assert m.sharpe == pytest.approx(ex.mean() / ex.std(ddof=1) * np.sqrt(252), rel=1e-9)
    assert m.annualized_vol == pytest.approx(ex.std(ddof=1) * np.sqrt(252), rel=1e-9) and m.sortino != 0.0


@ENGINES
def test_b_equity_is_float64_for_an_integer_initial_capital(engine):
    px = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0, 0.01, 30))
    w = np.full(30, 0.7)
    ri = engine(px, w, quant.BacktestConfig(initial_capital=100_000))
    rf = engine(px, w, quant.BacktestConfig(initial_capital=100_000.0))
    assert ri.equity.dtype == np.float64                                    # numpy: int64, truncated per bar
    np.testing.assert_array_equal(ri.equity, rf.equity)
    assert ri.metrics.cumulative_return == rf.metrics.cumulative_return


@needs_cpp
def test_b_backends_agree_with_an_integer_initial_capital():
    px = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0, 0.01, 30))
    w = np.full(30, 0.7)
    cfg = quant.BacktestConfig(initial_capital=100_000, cost_bps=5)
    _same_result(quant.run_backtest(px, w, cfg, impact=np.full(30, 0.01)),
                 pycore.run_backtest_ex(px, w, cfg, impact=np.full(30, 0.01)))


@METRICS
def test_c_an_empty_rf_or_traded_array_means_absent_on_both_backends(metrics):
    e, pos, tr = np.array([1.0, 1.01, 1.0, 1.02, 1.03]), np.array([0.0, 1.0, 1.0, 0.5, 0.5]), np.array([1.0, 0, 0, .5, 0])
    fields = list(quant.Metrics.__dataclass_fields__)
    empty_rf, zero_rf = metrics(e, pos, 252.0, [], tr), metrics(e, pos, 252.0, 0.0, tr)   # numpy: ValueError
    assert [getattr(empty_rf, f) for f in fields] == [getattr(zero_rf, f) for f in fields]
    assert empty_rf.sharpe != metrics(e, pos, 252.0, 0.03, tr).sharpe
    with pytest.warns(RuntimeWarning, match="inferred from changes"):
        empty_tr = metrics(e, pos, 252.0, 0.0, [])
    with pytest.warns(RuntimeWarning, match="inferred from changes"):
        no_tr = metrics(e, pos, 252.0, 0.0, None)
    assert [getattr(empty_tr, f) for f in fields] == [getattr(no_tr, f) for f in fields]
    assert empty_tr.num_trades == 2 and empty_tr.turnover == pytest.approx(1.5)
    with pytest.raises(ValueError):
        metrics(e, pos, 252.0, [0.03, 0.03], tr)                                # a wrong length still raises
    with pytest.raises(ValueError):
        metrics(e, pos, 252.0, 0.0, [1.0, 0.0])


def _drifted_short(engine, T: int = 12):
    prices = np.full(T, 100.0)
    cfg = quant.BacktestConfig(borrow_annual=0.05, cost_bps=0.0, max_leverage=1.0)
    w = np.full(T, -1.0)
    reb = np.zeros(T)
    reb[0] = reb[5] = 1.0
    held = engine(prices[:6], w[:6], cfg, rebalance=reb[:6]).positions[5]     # the replay run_agent_backtest does
    return prices, cfg, w, reb, float(held)


@ENGINES
def test_e_a_keep_at_the_cap_is_no_trade_even_when_drift_sits_outside_it(engine):
    prices, cfg, w, reb, held = _drifted_short(engine)
    assert held < -1.0                                                         # borrow de-levers a short past the cap
    keep = w.copy()
    keep[5:] = held
    r = engine(prices, keep, cfg, rebalance=reb)
    assert len(r.trades) == 1 and r.traded[5] == 0.0 and r.metrics.num_trades == 1   # was 2: a +0.00099 trim
    assert r.positions[5] == held and r.positions[6] < held                  # still held, still drifting
    assert r.metrics.turnover == pytest.approx(1.0)
    # a genuinely new target outside the cap is still clamped (the cap binds on decisions)
    trim = w.copy()
    trim[5:] = -1.5
    t = engine(prices, trim, cfg, rebalance=reb)
    assert len(t.trades) == 2 and t.positions[5] == -1.0 and t.traded[5] == pytest.approx(abs(held) - 1.0)
    # and a new target equal to the cap while held is past it is a trim too (it is not the held weight)
    cap = w.copy()
    t2 = engine(prices, cap, cfg, rebalance=reb)
    assert len(t2.trades) == 2 and t2.positions[5] == -1.0
    # the unfunded FX long with negative carry: the mirror case
    fx = quant.BacktestConfig(carry_annual=-0.05, cost_bps=0.0, funded=False, max_leverage=1.0)
    held_fx = engine(prices[:6], -w[:6], fx, rebalance=reb[:6]).positions[5]
    assert held_fx > 1.0
    keep_fx = -w.copy()
    keep_fx[5:] = held_fx
    assert len(engine(prices, keep_fx, fx, rebalance=reb).trades) == 1


@needs_cpp
def test_e_backends_agree_on_the_keep_at_the_cap():
    prices, cfg, w, reb, held = _drifted_short(quant.run_backtest)
    assert held == _drifted_short(pycore.run_backtest_ex)[4]
    keep = w.copy()
    keep[5:] = held
    _same_result(quant.run_backtest(prices, keep, cfg, rebalance=reb),
                 pycore.run_backtest_ex(prices, keep, cfg, rebalance=reb))


def test_e_desk_deciding_the_cap_while_past_it_is_trimmed_and_a_keep_is_not(monkeypatch):
    # Final review (engine, high): the earlier version of this test enshrined "a decision equal to
    # the capped held weight is a keep", which never de-levered a short that drifted past the cap.
    # A keep is now only what the PM's no-trade band marks (FinalDecision.kept); a -1.0 decision
    # while the held weight sits past the cap is a trim back to it.
    cfg = make_config(CFG, risk={"allow_short_equity": True, "max_position": 1.0, "rebalance_band": 0.0},
                      costs={"equity_borrow_annual": 0.05, "equity_cost_bps": 0.0, "equity_slippage_bps": 0.0})
    told = []
    orig = TradingGraph.propagate

    def always_max_short(self, symbol, as_of, asset_class=None, current_weight=None, book=None):
        told.append(current_weight)
        st, dec = orig(self, symbol, as_of, asset_class, current_weight, book)
        return st, replace(dec, action=Action.SELL, target_weight=-1.0, stop_loss=None, take_profit=None)

    monkeypatch.setattr(TradingGraph, "propagate", always_max_short)
    reb = 5
    rep = run_agent_backtest("AAPL", "2024-01-02", "2024-06-28", cfg, rebalance_every=reb)
    res = rep.results[AGENT]
    bars = list(range(0, len(rep.prices) - 1, reb))
    assert len(told) == len(bars) and all(d.target_weight == -1.0 and not d.kept for d in rep.decisions)
    assert any(t < -1.0 for t in told)                    # borrow and price moves carried the short past the cap
    for k, i in enumerate(bars[1:], 1):
        assert res.positions[i] == -1.0, (k, i)           # was: kept at told[k] whenever told[k] <= -1.0
        assert res.traded[i] == pytest.approx(abs(-1.0 - told[k]), abs=1e-12)
    assert res.metrics.num_trades == sum(1 for t in told if t != -1.0)


@METRICS
def test_f_metrics_without_traded_warn_once_and_the_engine_paths_do_not(metrics):
    e, pos = np.array([1.0, 1.01, 1.0, 1.02, 1.03]), np.array([0.0, 1.0, 1.0, 0.5, 0.5])
    with pytest.warns(RuntimeWarning, match="drift every bar under constant units") as rec:
        m = metrics(e, pos, 252.0)
    assert len(rec) == 1 and m.num_trades == 2
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        assert metrics(e, pos, 252.0, 0.0, [1.0, 0.0, 0.0, 0.5, 0.0]).num_trades == 2
        px = 100 * np.cumprod(1 + np.random.default_rng(0).normal(0, 0.01, 40))
        for engine in (quant.run_backtest, pycore.run_backtest_ex):
            assert engine(px, np.r_[np.ones(20), np.zeros(20)], quant.BacktestConfig()).metrics.num_trades == 2
            engine(px, np.ones(40), quant.BacktestConfig(), cash_rate=np.full(40, 0.03))


def test_g_a_weight_change_below_one_lot_is_nothing_to_trade_not_an_error(caplog):
    dec = FinalDecision("AAPL", date(2024, 3, 1), Action.BUY, 0.25, 0.5, None, None, "")
    with caplog.at_level(logging.INFO, logger="agentic_trader.algo"):
        assert plan_execution(dec, Instrument.parse("AAPL"), 0.2499, 100_000.0, 180.0) is None   # was ValueError
    assert "below one lot" in caplog.text
    assert plan_execution(dec, Instrument.parse("AAPL"), 0.2400, 100_000.0, 180.0).quantity == 5.0
    fx = FinalDecision("EURUSD", date(2024, 3, 1), Action.BUY, 0.5, 0.5, None, None, "")
    assert plan_execution(fx, Instrument.parse("EURUSD"), 0.4995, 100_000.0, 1.08, lot_size=1000.0) is None
    assert plan_execution(fx, Instrument.parse("EURUSD"), 0.48, 100_000.0, 1.08, lot_size=1000.0).quantity == 1000.0
    for bad in ({"capital": 0.0}, {"last_price": 0.0}, {"lot_size": -1.0}):    # invalid inputs still raise
        kw = dict(capital=100_000.0, last_price=1.08)
        kw.update(bad)
        with pytest.raises(ValueError):
            plan_execution(fx, Instrument.parse("EURUSD"), 0.0, **kw)


def test_h_volume_is_rescaled_so_dollar_volume_stays_as_traded_across_a_split(tmp_path):
    rows = ["Date,Open,High,Low,Close,Adj Close,Volume"]
    for d in pd.bdate_range("2024-01-01", "2024-01-05"):
        rows.append(f"{d.date()},100,101,99,100,50,1000")                   # before the 2:1 split
    for d in pd.bdate_range("2024-01-08", "2024-01-12"):
        rows.append(f"{d.date()},50,51,49,50,50,2000")                      # after it
    (tmp_path / "SPL.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    h = p.history(Instrument.parse("SPL"), date(2024, 1, 1), date(2024, 1, 12))
    assert len(h) == 10 and (h["Close"] == 50.0).all()
    np.testing.assert_allclose(h["Volume"].to_numpy(), 2000.0)               # was 1000 before the split
    np.testing.assert_allclose((h["Close"] * h["Volume"]).to_numpy(), 100_000.0)   # dollar volume as traded
    # one_basis leaves a file without Volume, or without Adj Close, alone
    raw = pd.DataFrame({"Close": [100.0, 50.0], "Volume": [1000.0, 2000.0]}, index=pd.to_datetime(["2024-01-01", "2024-01-02"]))
    assert one_basis(raw.copy()).equals(raw)
    adj_only = one_basis(raw.assign(**{"Adj Close": [50.0, 50.0]}).drop(columns="Close"))
    assert adj_only["Volume"].tolist() == [1000.0, 2000.0]                    # no raw close: no factor, volume untouched


@pytest.mark.parametrize("host_tz", ["Asia/Kolkata", "Asia/Tokyo", "Europe/London", "America/Los_Angeles"])
def test_i_the_default_as_of_is_new_yorks_yesterday_whatever_the_host_clock_says(monkeypatch, host_tz):
    clock = {"now": datetime(2026, 9, 29, 3, 0, tzinfo=timezone.utc)}     # 23:00 Mon 28 in New York
    monkeypatch.setattr(cli_common, "_now", lambda: clock["now"].astimezone(ZoneInfo(host_tz)))
    args = types.SimpleNamespace(date=None)
    assert cli_common.exchange_today() == date(2026, 9, 28)
    assert cli_common.default_as_of() == cli_common._as_of(args) == date(2026, 9, 27)   # host yesterday: Mon 28 in IST
    clock["now"] = datetime(2026, 9, 29, 5, 0, tzinfo=timezone.utc)         # 01:00 Tue 29 in New York
    assert cli_common._as_of(args) == date(2026, 9, 28)
    assert cli_common._as_of(types.SimpleNamespace(date="2024-03-01")) == date(2024, 3, 1)
    assert cli_evaluate.default_as_of is cli_common.default_as_of
    for mod in (cli_common, cli_evaluate):
        assert "date.today" not in inspect.getsource(mod)


def test_k_the_environment_is_restored_between_tests_part_1():
    os.environ["AT_ENGINE2_PROBE"] = "leaked"


def test_k_the_environment_is_restored_between_tests_part_2():
    assert "AT_ENGINE2_PROBE" not in os.environ


# ======================================================= final code review (engine-3 cluster)
from agentic_trader.cli import main as cli_main
from agentic_trader.data.csv_provider import SPLIT_JUMP, split_factor
from agentic_trader.stats import paired_sharpe_block_bootstrap, sharpe_ci_bootstrap, sharpe_stats


def _winning_bars_under_a_cash_leg(T: int = 30):
    """Real dispersion (five +0.5% bars held long), flat and unpositioned for the rest of the
    window under a wandering cash leg: the only negative excess returns are the +-1e-16 rounding
    noise of the flat bars (r - rf/ppy), never a genuine loss."""
    prices = np.full(T, 100.0)
    prices[1:6] = 100.0 * 1.005 ** np.arange(1, 6)
    prices[6:] = prices[5]
    w = np.zeros(T)
    w[:5] = 1.0
    cash = 0.03 + 0.002 * np.cumsum(np.random.default_rng(1).normal(size=T)) / 10
    return prices, w, quant.BacktestConfig(cost_bps=0.0, slippage_bps=0.0), cash


@ENGINES
def test_fa_sortino_is_zero_when_only_the_downside_is_rounding_noise(engine):
    prices, w, cfg, cash = _winning_bars_under_a_cash_leg()
    r = engine(prices, w, cfg, cash_rate=cash)
    ex = r.returns[1:] - cash[:-1] / cfg.periods_per_year
    assert (ex < 0).sum() > 5 and ex.min() > -1e-14                        # losses are rounding noise only
    assert r.metrics.sharpe == pytest.approx(7.1197, abs=1e-3) and r.metrics.annualized_vol > 0.02
    assert r.metrics.sortino == 0.0                                          # was +2.76e14 on both backends
    # the direct entry with a constant rf and an equity curve compounding at exactly rf on flat bars
    e = np.empty(40)
    e[0] = 100_000.0
    for i in range(39):
        e[i + 1] = e[i] * (1.0 + (0.004 if 5 <= i < 10 else 0.03 / 252.0))
    metrics = quant.compute_metrics if engine is quant.run_backtest else pycore.compute_metrics
    m = metrics(e, np.ones(40), 252.0, 0.03, np.zeros(40))
    assert m.sharpe > 5.0 and m.sortino == 0.0                              # was +1.89e14
    # a genuine loss, however small next to the noise, still gives a finite Sortino
    e[20] *= 1 - 1e-6
    m2 = metrics(e, np.ones(40), 252.0, 0.03, np.zeros(40))
    assert 0.0 < m2.sortino < 1e6 and m2.sharpe > 5.0


@needs_cpp
def test_fa_backends_agree_on_the_downside_rule_and_its_boundary():
    prices, w, cfg, cash = _winning_bars_under_a_cash_leg()
    a = quant.run_backtest(prices, w, cfg, cash_rate=cash).metrics
    b = pycore.run_backtest_ex(prices, w, cfg, cash_rate=cash).metrics
    assert a.sortino == b.sortino == 0.0 and a.sharpe == pytest.approx(b.sharpe, rel=1e-12)
    # ZERO_VARIANCE_TOL is a per-bar floor of 1e-12: sd 1e-10 keeps its Sharpe, 1e-13 is zeroed (both)
    T = 300
    for sd, real in ((1e-10, True), (1e-13, False)):
        rr = 1e-4 + sd * np.random.default_rng(5).standard_normal(T - 1)
        e = 100_000.0 * np.cumprod(np.r_[1.0, 1.0 + rr])
        ma, mb = (f(e, np.ones(T), 252.0, 0.0, np.zeros(T)) for f in (quant.compute_metrics, pycore.compute_metrics))
        if real:
            ref = rr.mean() / rr.std(ddof=1) * np.sqrt(252)
            assert ma.sharpe == pytest.approx(ref, rel=1e-3) and mb.sharpe == pytest.approx(ref, rel=1e-3)
            assert ma.annualized_vol > 0 and mb.annualized_vol > 0
        else:
            assert (ma.sharpe, ma.sortino, ma.annualized_vol) == (0.0, 0.0, 0.0) == (mb.sharpe, mb.sortino, mb.annualized_vol)


def test_fb_the_stats_module_reports_zero_for_a_flat_book_like_the_table():
    T = 200
    r = np.random.default_rng(0).normal(0.0004, 0.01, T)
    flat = np.full(T, 0.05 / 252.0)                                           # exactly rf every day
    d = paired_sharpe_block_bootstrap(np.zeros(T), r, 252.0, rf=0.05, n_boot=200)
    assert d.sharpe_a == 0.0 and np.isfinite(d.diff) and abs(d.ci_low) < 1e3    # sharpe_a was -1.16e17
    assert d.sharpe_b == pytest.approx((r - 0.05 / 252).mean() / r.std(ddof=1) * np.sqrt(252))
    e = paired_sharpe_block_bootstrap(flat, r, 252.0, rf=np.full(T, 0.05), n_boot=200)
    assert e.sharpe_a == 0.0
    s = sharpe_stats(flat + 1e-17 * np.random.default_rng(1).standard_normal(T))
    assert s.sharpe == s.sharpe_annual == s.t_stat == 0.0 and s.std == 0.0     # was +-1e14
    assert sharpe_ci_bootstrap(flat, 252.0, n_boot=100) == (0.0, 0.0)
    # real dispersion, however small, keeps its Sharpe in every helper
    tiny = 1e-4 + 1e-10 * np.random.default_rng(2).standard_normal(T)
    ref = tiny.mean() / tiny.std(ddof=1) * np.sqrt(252)
    assert sharpe_stats(tiny).sharpe_annual == pytest.approx(ref, rel=1e-6)
    assert paired_sharpe_block_bootstrap(tiny, r, 252.0, n_boot=50).sharpe_a == pytest.approx(ref, rel=1e-6)
    lo, hi = sharpe_ci_bootstrap(tiny, 252.0, n_boot=100)
    assert np.isfinite(lo) and hi > lo


# ---- (c) a keep is a keep only when the desk actually kept
class _Rising(SyntheticProvider):
    """A price that rises 1% a session: constant units carry a short well past the cap between
    decision bars (a -1.0 short is -1.105 five bars later)."""

    def _frame(self, instrument):
        if instrument.symbol not in self._cache:
            dates = pd.bdate_range("2022-01-03", "2024-12-31")
            close = 100.0 * 1.01 ** np.arange(len(dates))
            df = pd.DataFrame({"Open": close, "High": close * 1.002, "Low": close * 0.998, "Close": close,
                               "Volume": np.full(len(dates), 1e6)}, index=dates)
            df["_z"] = 0.0
            self._cache[instrument.symbol] = df
        return self._cache[instrument.symbol]


_SHORT_CFG = make_config(CFG, risk={"allow_short_equity": True, "max_position": 1.0, "rebalance_band": 0.0},
                         costs={"equity_borrow_annual": 0.01, "equity_cost_bps": 0.0, "equity_slippage_bps": 0.0})


def _desk(monkeypatch, decide):
    """Patch the desk: ``decide(k, current_weight, dec)`` returns the k-th decision."""
    told = []
    orig = TradingGraph.propagate

    def patched(self, symbol, as_of, asset_class=None, current_weight=None, book=None):
        st, dec = orig(self, symbol, as_of, asset_class, current_weight, book)
        told.append(current_weight)
        return st, decide(len(told) - 1, current_weight, replace(dec, stop_loss=None, take_profit=None))

    monkeypatch.setattr(TradingGraph, "propagate", patched)
    return told


def _both_backends(run):
    """Run ``run()`` on the active backend and again with the numpy engine behind ``quant.run_backtest``."""
    active = run()
    if not CPP:
        return active, None
    saved = quant.run_backtest
    quant.run_backtest = pycore.run_backtest_ex
    try:
        numpy = run()
    finally:
        quant.run_backtest = saved
    return active, numpy


def test_fc_a_levered_short_past_the_cap_with_a_decision_at_the_cap_is_trimmed(monkeypatch):
    told = _desk(monkeypatch, lambda k, cw, dec: replace(dec, action=Action.SELL, target_weight=-1.0))

    def run():
        told.clear()
        return run_agent_backtest("AAPL", "2024-01-02", "2024-06-28", _SHORT_CFG, rebalance_every=5,
                                  provider=_Rising(_SHORT_CFG))

    rep, rep_np = _both_backends(run)
    res = rep.results[AGENT]
    bars = list(range(0, len(rep.prices) - 1, 5))
    assert all(d.target_weight == -1.0 and not d.kept for d in rep.decisions)
    assert min(told[1:]) < -1.09 and max(told[1:]) < -1.05        # every decision bar starts past the cap
    for k, i in enumerate(bars[1:], 1):
        assert res.positions[i] == -1.0 and res.traded[i] == pytest.approx(abs(told[k]) - 1.0, abs=1e-12)
    assert res.metrics.num_trades == len(bars) and np.abs(res.positions).max() < 1.12   # was 1 trade, |w| up to 15
    if rep_np is not None:
        _same_result(res, rep_np.results[AGENT])
        np.testing.assert_allclose(res.traded, rep_np.results[AGENT].traded, rtol=1e-12, atol=1e-15)


def test_fc_a_genuine_keep_past_the_cap_books_no_trade(monkeypatch):
    def decide(k, cw, dec):
        if k == 0:
            return replace(dec, action=Action.SELL, target_weight=-1.0)
        return replace(dec, action=Action.SELL, target_weight=round(cw, 4), kept=True,
                       adjustments=[f"within no-trade band: keep {cw:+.2f}"])

    told = _desk(monkeypatch, decide)

    def run():
        told.clear()
        return run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", _SHORT_CFG, rebalance_every=5,
                                  provider=_Rising(_SHORT_CFG))

    rep, rep_np = _both_backends(run)
    res = rep.results[AGENT]
    bars = list(range(0, len(rep.prices) - 1, 5))
    assert all(d.kept for d in rep.decisions[1:]) and not rep.decisions[0].kept
    assert res.ruined_at == -1 and told[-1] < -1.5                # the kept short keeps drifting past the cap
    for k, i in enumerate(bars[1:], 1):
        assert res.traded[i] == 0.0 and res.positions[i] == told[k]   # no trade to the rounded or capped weight
    assert res.metrics.num_trades == 1 and len(res.trades) == 1
    if rep_np is not None:
        _same_result(res, rep_np.results[AGENT])
        np.testing.assert_array_equal(res.traded != 0, rep_np.results[AGENT].traded != 0)


def test_fc_the_pm_marks_a_keep_only_when_the_band_holds_a_legal_position():
    free = TradingGraph(make_config(CFG, risk={"rebalance_band": 0.0}), provider=SyntheticProvider(CFG),
                        memory=DecisionMemory(None), on_event=lambda *_: None)
    _, d0 = free.propagate("AAPL", "2024-03-01")
    assert not d0.kept and "kept" in d0.to_dict() and d0.to_dict()["kept"] is False
    held = round(d0.target_weight - 0.04, 4)
    banded = TradingGraph(make_config(CFG, risk={"rebalance_band": 0.10}), provider=SyntheticProvider(CFG),
                          memory=DecisionMemory(None), on_event=lambda *_: None)
    _, d1 = banded.propagate("AAPL", "2024-03-01", current_weight=held)
    assert d1.kept and d1.target_weight == held and any("no-trade band" in a for a in d1.adjustments)
    _, d2 = banded.propagate("AAPL", "2024-03-01", current_weight=round(d0.target_weight - 0.3, 4))
    assert not d2.kept and d2.target_weight == d0.target_weight
    # a held weight past the cap is never kept, however close the new target: it is a target at the cap
    wide = TradingGraph(make_config(CFG, risk={"rebalance_band": 0.5, "allow_short_equity": True}),
                        provider=SyntheticProvider(CFG), memory=DecisionMemory(None), on_event=lambda *_: None)
    _, d3 = wide.propagate("AAPL", "2024-03-01", current_weight=1.3)
    assert not d3.kept and abs(d3.target_weight) <= 1.0
    assert not any("no-trade band" in a for a in d3.adjustments)


# ---- (d) Volume follows the split ratio only, never the dividend drift
def _csv(tmp_path, name, rows):
    (tmp_path / f"{name}.csv").write_text("Date,Open,High,Low,Close,Adj Close,Volume\n" + "\n".join(rows) + "\n",
                                          encoding="utf-8")
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    return p.history(Instrument.parse(name), date(2024, 1, 1), date(2024, 2, 29))


def test_fd_a_dividend_payer_without_a_split_keeps_its_volume_as_traded(tmp_path, caplog):
    days = pd.bdate_range("2024-01-01", "2024-01-12")
    rows = [f"{d.date()},100,101,99,100,{97 if i < 5 else 100},1000" for i, d in enumerate(days)]   # 3% ex-div row 5
    with caplog.at_level(logging.INFO, logger="agentic_trader.data.csv_provider"):
        h = _csv(tmp_path, "DIV", rows)
    assert h["Close"].tolist() == [97.0] * 5 + [100.0] * 5                   # prices on the total-return basis
    np.testing.assert_array_equal(h["Volume"].to_numpy(), 1000.0)            # was 1030.93 before the ex-date
    assert "split" not in caplog.text
    # a 3%-yield stock over a year (three ex-dates): the factor drifts by 3%, never in a jump
    days = pd.bdate_range("2024-01-01", "2024-12-31")
    adj = [100.0 * 0.99 ** (3 - sum(d.month > m for m in (3, 6, 9))) for d in days]
    rows = [f"{d.date()},100,101,99,100,{a:.6f},1000000" for d, a in zip(days, adj)]
    p = CSVProvider(make_config(csv_dir=str(tmp_path)))
    (tmp_path / "YLD.csv").write_text("Date,Open,High,Low,Close,Adj Close,Volume\n" + "\n".join(rows) + "\n", encoding="utf-8")
    y = p.history(Instrument.parse("YLD"), date(2024, 1, 1), date(2024, 12, 31))
    assert y["Close"].iloc[0] == pytest.approx(100 * 0.99 ** 3) and y["Close"].iloc[-1] == 100.0
    np.testing.assert_array_equal(y["Volume"].to_numpy(), 1e6)               # ADV in shares as traded, not 1.03e6


def test_fd_a_split_still_rescales_volume_and_a_dividend_beside_it_does_not(tmp_path, caplog):
    days = pd.bdate_range("2024-01-01", "2024-01-19")
    rows = []
    for i, d in enumerate(days):
        if i < 5:
            rows.append(f"{d.date()},100,101,99,100,48.5,1000")              # before the 2:1 split, before the dividend
        elif i < 10:
            rows.append(f"{d.date()},50,51,49,50,48.5,2000")                 # after the split, before the 3% dividend
        else:
            rows.append(f"{d.date()},50,51,49,50,50,2000")                   # after both
    with caplog.at_level(logging.INFO, logger="agentic_trader.data.csv_provider"):
        h = _csv(tmp_path, "SPD", rows)
    assert h["Close"].tolist() == [48.5] * 10 + [50.0] * 5
    np.testing.assert_allclose(h["Volume"].to_numpy(), 2000.0)               # pre-split x2 (was x2.06), rest untouched
    assert "1 split(s) detected" in caplog.text and str(days[5].date()) in caplog.text
    # split_factor itself: a 4:1 split, then a 1:10 reverse split, with a 3% dividend before each (the
    # factor is Adj Close / Close relative to the last row: 2.5 in old shares, 10 after the 4:1, 1 at the end)
    idx = pd.bdate_range("2024-01-01", periods=8)
    factor = pd.Series([2.5, 2.5, 2.5 * 1.03, 10.3, 10.3, 1.03, 1.0, 1.0], index=idx)
    comp, splits = split_factor(factor)
    np.testing.assert_allclose(comp.to_numpy(), [2.5, 2.5, 2.5, 10.0, 10.0, 1.0, 1.0, 1.0])   # 1000 old shares = 400 now
    assert list(splits) == [idx[3], idx[5]]
    comp1, none = split_factor(pd.Series([0.97, 0.97, 1.0, 1.0], index=idx[:4]))
    assert (comp1 == 1.0).all() and len(none) == 0 and 0 < SPLIT_JUMP < 0.1
    # unsorted, duplicated and blank rows: the split is found in date order and every row gets its factor
    shuffled = pd.Series([1.0, 0.5, NAN, 0.5, 1.0], index=pd.to_datetime(["2024-01-05", "2024-01-02", "2024-01-03",
                                                                          "2024-01-02", "2024-01-04"]))
    comp2, s2 = split_factor(shuffled)
    assert comp2.tolist() == [1.0, 0.5, 1.0, 0.5, 1.0] and list(s2) == [pd.Timestamp("2024-01-04")]


# ---- (e) the CLI's below-one-lot message sizes the effective change
def test_fe_cli_below_one_lot_message_uses_the_truncated_change_and_says_so(capsys):
    base = ["execute", "AAPL", "--date", "2024-03-01", "--capital", "100000"]
    assert cli_main(base + ["--target", "-0.3", "--current", "0.0001"]) == 0
    out = capsys.readouterr().out
    assert "nothing to trade" in out and "below one share" in out
    assert "+0.0001 -> +0.0000 (10 USD)" in out and "30,010" not in out        # was 'the change (30,010 USD)'
    assert "target -0.30 truncated to flat" in out
    assert cli_main(base + ["--target", "0.25", "--current", "0.2499"]) == 0
    out = capsys.readouterr().out
    assert "+0.2499 -> +0.2500 (10 USD) is below one share" in out and "truncated" not in out
    assert cli_main(base + ["--target", "-0.3", "--current", "0.0001", "--allow-short"]) == 0
    assert "SELL" in capsys.readouterr().out                                    # shorting allowed: a real order
