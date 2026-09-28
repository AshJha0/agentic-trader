"""v0.8 engine fixes (tier-1 review findings 1, 14, 18, 19/33, 20, 21, 22, 23, 76, 77, 78, 79).

Every test fails on the v0.7 engine and passes now. Engine-level tests run on both the
active backend (``quant``) and the numpy twin (``pycore``) and, when the extension is
built, assert the two agree to 1e-12.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agentic_trader import TradingGraph, make_config, quant
from agentic_trader.algo import algo_cost_ratio
from agentic_trader.backtest import (AGENT, impact_coefficients, risk_free_series, run_agent_backtest,
                                     run_portfolio_backtest)
from agentic_trader.data import SyntheticProvider
from agentic_trader.instruments import Instrument
from agentic_trader.quant import pycore

NAN = float("nan")
CFG = make_config(memory_path=None)
CPP = quant.BACKEND == "cpp"
needs_cpp = pytest.mark.skipif(not CPP, reason="C++ extension not built")


def _engines():
    return [("active", quant.run_backtest), ("numpy", pycore.run_backtest_ex)]


ENGINES = pytest.mark.parametrize("engine", [e[1] for e in _engines()], ids=[e[0] for e in _engines()])


def _same_result(a, b, rtol=1e-12):
    np.testing.assert_allclose(a.equity, b.equity, rtol=rtol)
    np.testing.assert_allclose(a.positions, b.positions, rtol=rtol, atol=1e-15)
    np.testing.assert_allclose(a.returns, b.returns, rtol=rtol, atol=1e-15)
    np.testing.assert_array_equal(a.traded != 0, b.traded != 0)
    np.testing.assert_array_equal(a.exits, b.exits)
    assert a.ruined_at == b.ruined_at and a.stop_exits == b.stop_exits
    assert a.impact_paid == pytest.approx(b.impact_paid, rel=rtol, abs=1e-15)
    for f in ("sharpe", "sortino", "sharpe_tstat", "max_drawdown", "turnover", "avg_exposure",
              "cumulative_return", "win_rate"):
        assert getattr(a.metrics, f) == pytest.approx(getattr(b.metrics, f), rel=1e-11, abs=1e-14), f
    assert a.metrics.num_trades == b.metrics.num_trades and a.metrics.ruined == b.metrics.ruined


# ============================================================ 79: constant units between decisions
@ENGINES
def test_79_hold_bars_carry_units_not_weight(engine):
    p = [100, 110, 110, 121]
    cfg = quant.BacktestConfig(cost_bps=10.0)
    r = engine(p, np.full(4, 0.5), cfg)
    assert r.equity[1] == pytest.approx(100000 * (1 - 0.0005) * 1.05)   # fee out first, then 0.5 * 10%
    assert r.equity[2] == r.equity[1]                               # a hold bar costs nothing
    w1 = 0.5 * 1.1 / 1.05                                           # drifted weight
    assert r.positions[1] == pytest.approx(w1) and r.positions[2] == pytest.approx(w1)
    assert r.equity[3] == pytest.approx(r.equity[2] * (1 + w1 * 0.1))
    assert r.metrics.num_trades == 1 and r.metrics.turnover == pytest.approx(0.5)
    assert list(r.traded) == [0.5, 0.0, 0.0, 0.0]


@ENGINES
def test_79_rebalancing_to_the_same_target_is_a_charged_trade(engine):
    p = [100, 110, 110, 121]
    cfg = quant.BacktestConfig(cost_bps=10.0)
    r = engine(p, np.full(4, 0.5), cfg, rebalance=[1, 1, 0, 0])
    w1 = 0.5 * 1.1 / 1.05
    assert r.positions[1] == 0.5 and r.metrics.turnover == pytest.approx(0.5 + abs(0.5 - w1))
    assert r.equity[2] == pytest.approx(r.equity[1] * (1 - abs(0.5 - w1) * 1e-3))


@ENGINES
def test_79_carry_accrues_on_the_constant_notional(engine):
    cfg = quant.BacktestConfig(cost_bps=0, carry_annual=0.0252, periods_per_year=252)
    r = engine(np.ones(11), np.ones(11), cfg)
    assert r.equity[-1] == pytest.approx(100000 * 1.001, rel=1e-12)   # linear, not 1.0001**10
    assert r.positions[-1] == pytest.approx(1 / 1.001, rel=1e-12)     # cash grew, units did not


def test_79_desk_holds_units_between_decisions_and_pays_only_for_decisions():
    rep = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=5)
    res = rep.results[AGENT]
    p = rep.prices
    n = len(p)
    decision_bars = set(range(0, n - 1, 5))
    trade_bars = set(np.flatnonzero(res.traded))
    assert trade_bars <= decision_bars                                  # no hidden daily rebalancing
    # on a hold bar whose previous bar was also a hold bar, returns[t] is the gross return g
    hold = [t for t in range(2, n) if t not in decision_bars and t - 1 not in decision_bars and res.positions[t - 1] != 0]
    assert hold
    for t in hold:
        drift = res.positions[t - 1] * (p[t] / p[t - 1]) / (1 + res.returns[t])
        assert res.positions[t] == pytest.approx(drift, rel=1e-12)
    # a fully invested book stays exactly fully invested (costs do not leave it levered)
    assert (rep.results["Buy&Hold"].positions == 1.0).all()
    assert res.metrics.turnover == pytest.approx(res.traded.sum())
    assert res.metrics.num_trades == len(res.trades)


# ======================================================================= 18: ruin floor
@ENGINES
def test_18_ruin_floors_equity_and_flattens(engine):
    r = engine([10, 10, 24, 20, 15, 12], np.full(6, -1.0), quant.BacktestConfig(cost_bps=1.0))
    assert r.equity[1] == pytest.approx(99990.0)
    assert list(r.equity[2:]) == [0.0] * 4
    assert r.returns[2] == -1.0 and list(r.returns[3:]) == [0.0] * 3
    assert list(r.positions[2:]) == [0.0] * 4 and r.ruined_at == 2
    m = r.metrics
    assert m.ruined and m.max_drawdown == 1.0 and m.cumulative_return == -1.0 and m.annualized_return == -1.0
    assert m.win_rate == 0.0 and np.isfinite(m.sharpe) and m.sharpe < 0
    # a levered long through a crash
    r2 = engine([100, 40, 50, 60], np.full(4, 2.0), quant.BacktestConfig(cost_bps=0, max_leverage=2.0))
    assert r2.ruined_at == 1 and list(r2.equity[1:]) == [0.0] * 3 and (r2.positions[1:] == 0).all()
    ok = engine([100, 110, 121], np.ones(3), quant.BacktestConfig(cost_bps=0))
    assert not ok.metrics.ruined and ok.ruined_at == -1


@needs_cpp
def test_18_ruin_parity():
    for p, w, lev in (([10, 10, 24, 20, 15, 12], -1.0, 1.0), ([100, 40, 50, 60], 2.0, 2.0),
                      ([100, 50.0000001, 60], 2.0, 3.0)):
        cfg = quant.BacktestConfig(cost_bps=1.0, max_leverage=lev)
        _same_result(quant.run_backtest(p, np.full(len(p), w), cfg), pycore.run_backtest_ex(p, np.full(len(p), w), cfg))


# ============================================================ 21: gap through the take-profit
@ENGINES
def test_21_gap_through_take_fills_at_the_open(engine):
    cfg = quant.BacktestConfig(cost_bps=0)
    r = engine([100, 100], [1, 1], cfg, open=[100, 112], high=[100, 115], low=[100, 88], stop=[90, 90], take=[110, 110])
    assert r.stop_exits == 1 and r.trades[-1].price == 112 and r.equity[1] == pytest.approx(112_000)
    r = engine([100, 100], [-1, -1], cfg, open=[100, 88], high=[100, 112], low=[100, 85], stop=[110, 110], take=[90, 90])
    assert r.stop_exits == 1 and r.trades[-1].price == 88 and r.equity[1] == pytest.approx(112_000)
    # open inside both levels: intrabar ambiguity is still resolved stop-first
    r = engine([100, 100], [1, 1], cfg, open=[100, 100], high=[100, 115], low=[100, 88], stop=[90, 90], take=[110, 110])
    assert r.trades[-1].price == 90
    r = engine([100, 100], [-1, -1], cfg, open=[100, 100], high=[100, 112], low=[100, 85], stop=[110, 110], take=[90, 90])
    assert r.trades[-1].price == 110
    # a gap through the stop still fills at the open
    r = engine([100, 100], [1, 1], cfg, open=[100, 85], high=[100, 115], low=[100, 80], stop=[90, 90], take=[110, 110])
    assert r.trades[-1].price == 85


# ======================================= 22: the desk is told the position it actually holds
def test_22_desk_sees_flat_after_a_stop_and_the_drifted_weight_otherwise(monkeypatch):
    cfg = make_config(CFG, backtest={"use_stops": True}, risk={"stop_atr_mult": 0.5})
    told = []
    orig = TradingGraph.propagate

    def spy(self, symbol, as_of, asset_class=None, current_weight=None, book=None):
        told.append(current_weight)
        return orig(self, symbol, as_of, asset_class, current_weight, book)

    monkeypatch.setattr(TradingGraph, "propagate", spy)
    reb = 10
    rep = run_agent_backtest("NVDA", "2023-01-02", "2023-12-29", cfg, rebalance_every=reb)
    res = rep.results[AGENT]
    p = rep.prices
    bars = list(range(0, len(p) - 1, reb))
    assert len(told) == len(bars) and res.stop_exits > 0
    flat_after_stop = 0
    for k, i in enumerate(bars):
        if i == 0:
            assert told[k] == 0.0
            continue
        if res.exits[i] or res.positions[i - 1] == 0.0:
            expected = 0.0
        else:  # bar i-1 is a hold bar (rebalance every 10), so returns[i] is the gross return
            expected = res.positions[i - 1] * (p[i] / p[i - 1]) / (1 + res.returns[i])
        assert told[k] == pytest.approx(expected, abs=1e-12), (k, i)
        if expected == 0.0 and rep.decisions[k - 1].target_weight != 0.0:
            flat_after_stop += 1
    assert flat_after_stop > 0        # the finding's scenario occurred and the desk was told 0, not the old target
    # every adjustment that "keeps" the current position keeps a real one
    for k, dec in enumerate(rep.decisions):
        if any("no-trade band" in a for a in dec.adjustments):
            assert dec.target_weight == pytest.approx(told[k], abs=1e-9)


# ============================================== 23: impact scales with the equity actually traded
@ENGINES
def test_23_impact_coefficient_scales_with_sqrt_equity(engine):
    cfg = quant.BacktestConfig(cost_bps=0)
    r = engine([100, 200, 200, 200], [1, 1, 0, 0], cfg, impact=[0.0, 0.0, 0.01, 0.0])
    assert r.equity[1] == pytest.approx(200_000) and r.positions[1] == pytest.approx(1.0)
    assert r.impact_paid == pytest.approx(0.01 * np.sqrt(2))
    assert r.equity[3] == pytest.approx(200_000 * (1 - 0.01 * np.sqrt(2)))
    # a halved account trades half the notional: sqrt(0.5) of the coefficient
    r = engine([100, 50, 50, 50], [1, 1, 0, 0], cfg, impact=[0.0, 0.0, 0.01, 0.0])
    assert r.impact_paid == pytest.approx(0.01 * np.sqrt(0.5))
    # and the exit fill of a stop is charged at the same scale
    r = engine([100, 200, 200, 200], [1, 1, 1, 1], cfg, open=[100, 200, 200, 200], high=[100, 200, 200, 200],
               low=[100, 200, 150, 200], stop=[NAN, 180, 180, 180], impact=[0.0, 0.0, 0.01, 0.0])
    assert r.stop_exits == 1 and r.impact_paid == pytest.approx(0.01 * np.sqrt(2))


# ============================================ 1: portfolio sleeves pay impact for their share
def test_1_capital_share_equals_a_smaller_account():
    big = make_config(CFG, costs={"impact_coeff": 1.0}, initial_capital=1e9)
    quarter = make_config(big, initial_capital=0.25e9)
    full = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", big, rebalance_every=10)
    shared = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", big, rebalance_every=10,
                                capital_share=pd.Series(0.25, index=full.dates))
    small = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", quarter, rebalance_every=10)
    for name in full.results:
        assert shared.results[name].impact_paid == pytest.approx(small.results[name].impact_paid, rel=1e-9)
        if full.results[name].impact_paid > 0:
            assert shared.results[name].impact_paid < full.results[name].impact_paid
    assert small.results["Buy&Hold"].impact_paid > 0


def test_1_portfolio_of_n_sleeves_pays_the_impact_of_capital_over_n():
    big = make_config(CFG, costs={"impact_coeff": 1.0}, initial_capital=1e9)
    syms = ["AAPL", "NVDA"]
    port = run_portfolio_backtest(syms, "2024-01-02", "2024-03-28", big, rebalance_every=10)
    half = make_config(big, initial_capital=1e9 / len(syms))
    for s in syms:
        alone = run_agent_backtest(s, "2024-01-02", "2024-03-28", half, rebalance_every=10)
        for name, r in port.sleeves[s].results.items():
            assert r.impact_paid == pytest.approx(alone.results[name].impact_paid, rel=1e-9), (s, name)
        assert port.sleeves[s].results["Buy&Hold"].impact_paid > 0
    # class budgets: an equity sleeve given 30% of the book pays the impact of 30% of the capital
    port = run_portfolio_backtest(["AAPL", "EURUSD"], "2024-01-02", "2024-03-28", big, rebalance_every=10,
                                  class_budgets={"equity": 0.3, "fx": 0.7})
    alone = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", make_config(big, initial_capital=0.3e9),
                               rebalance_every=10)
    assert port.sleeves["AAPL"].results["Buy&Hold"].impact_paid == pytest.approx(
        alone.results["Buy&Hold"].impact_paid, rel=1e-9)


# ================================================================== 14: cash leg, excess Sharpe
@ENGINES
def test_14_engine_credits_idle_cash(engine):
    cfg = quant.BacktestConfig(cost_bps=0, periods_per_year=252)
    p = np.full(3, 100.0)
    r = engine(p, np.full(3, 0.5), cfg, cash_rate=[0.0252, NAN, 0.0252])
    assert r.equity[1] == pytest.approx(100000 * (1 + 0.5 * 1e-4)) and r.equity[2] == r.equity[1]
    fx = quant.BacktestConfig(cost_bps=0, periods_per_year=252, funded=False)
    r = engine(p, np.full(3, 0.5), fx, cash_rate=[0.0252, NAN, 0.0252])
    assert r.equity[1] == pytest.approx(100000 * (1 + 1e-4))
    flat = engine(p, np.zeros(3), cfg, cash_rate=[0.0252, 0.0252, 0.0252])
    assert flat.equity[-1] == pytest.approx(100000 * (1 + 1e-4) ** 2)
    with pytest.raises(ValueError):
        engine(p, np.zeros(3), cfg, cash_rate=[0.0252, 0.0252])


@ENGINES
def test_14_metrics_use_excess_returns_over_the_per_bar_rate(engine):
    e = np.array([100, 101, 100.5, 102, 103.0])
    rf = np.array([0.01, 0.02, 0.03, 0.04, 0.05])
    r = e[1:] / e[:-1] - 1
    ex = r - rf[:-1] / 252
    cm = pycore.compute_metrics if engine is pycore.run_backtest_ex else quant.compute_metrics
    m = cm(e, np.ones(5), 252, rf)
    assert m.sharpe == pytest.approx(ex.mean() / ex.std(ddof=1) * np.sqrt(252), rel=1e-12)
    assert m.sharpe_tstat == pytest.approx(ex.mean() / ex.std(ddof=1) * 2, rel=1e-12)
    assert m.sortino == pytest.approx(ex.mean() / np.sqrt(np.mean(np.minimum(ex, 0) ** 2)) * np.sqrt(252), rel=1e-12)
    assert m.annualized_vol == pytest.approx(ex.std(ddof=1) * np.sqrt(252), rel=1e-12)
    assert m.cumulative_return == pytest.approx(0.03)                    # total, not excess
    const = cm(e, np.ones(5), 252, 0.03)
    assert cm(e, np.ones(5), 252, np.full(5, 0.03)).sharpe == pytest.approx(const.sharpe, rel=1e-12)
    assert cm(e, np.ones(5), 252, np.array([0.03, NAN, 0.03, 0.03, 0.03])).sharpe != pytest.approx(const.sharpe)
    # the engine wires cash_rate through to the metrics
    p = np.array([100, 101, 100.5, 102, 103.0])
    res = engine(p, np.ones(5), quant.BacktestConfig(cost_bps=0), cash_rate=rf)
    assert res.metrics.sharpe == pytest.approx(m.sharpe, rel=1e-12)


class _Rate(SyntheticProvider):
    rate = 0.04

    def risk_free_series(self, dates):
        return np.full(len(dates), self.rate)


class _NoRate(SyntheticProvider):
    risk_free_series = None


def test_14_backtest_wiring_credits_cash_and_reports_excess_sharpe():
    base = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10, provider=_NoRate(CFG))
    assert base.rf is not None and (base.rf == 0.0).all()                 # config constant fallback
    rep = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10, provider=_Rate(CFG))
    assert rep.rf is not None and (rep.rf == 0.04).all() and rep.backtest_config.funded
    bh, bh0 = rep.results["Buy&Hold"], base.results["Buy&Hold"]
    np.testing.assert_allclose(bh.equity, bh0.equity, rtol=1e-12)         # fully invested: no idle cash
    assert (bh.positions == 1.0).all()                                     # and it stays exactly fully invested
    assert bh.metrics.sharpe < bh0.metrics.sharpe                          # Sharpe is now excess
    vt, vt0 = rep.results["B&H vol-target"], base.results["B&H vol-target"]
    assert vt.metrics.avg_exposure < 1 and vt.equity[-1] > vt0.equity[-1]  # idle cash earned 4%
    for name, r in rep.results.items():
        m = quant.compute_metrics(r.equity, r.positions, 252, rep.rf, traded=r.traded)
        assert r.metrics.sharpe == pytest.approx(m.sharpe, rel=1e-12), name
    # FX: unfunded forwards, the whole account earns the rate regardless of the weight
    fx = run_agent_backtest("EURUSD", "2024-01-02", "2024-02-29", CFG, rebalance_every=10, provider=_Rate(CFG))
    fx0 = run_agent_backtest("EURUSD", "2024-01-02", "2024-02-29", CFG, rebalance_every=10, provider=_NoRate(CFG))
    assert not fx.backtest_config.funded
    daily = np.cumprod(1 + np.r_[0.0, np.full(len(fx.dates) - 1, 0.04 / 252)])
    # every FX strategy's equity gains exactly the cash accrual on the constant notional path
    assert fx.results["Buy&Hold"].equity[-1] > fx0.results["Buy&Hold"].equity[-1] * daily[-1] * 0.999
    # an all-NaN series credits nothing and the metrics fall back to the constant
    nan_prov = _Rate(CFG)
    nan_prov.rate = NAN
    rep_nan = run_agent_backtest("AAPL", "2024-01-02", "2024-03-28", CFG, rebalance_every=10, provider=nan_prov)
    assert np.isnan(rep_nan.rf).all()
    for name in rep_nan.results:
        np.testing.assert_allclose(rep_nan.results[name].equity, base.results[name].equity, rtol=1e-12)
        assert rep_nan.results[name].metrics.sharpe == pytest.approx(base.results[name].metrics.sharpe, rel=1e-12)
    assert (risk_free_series(_NoRate(CFG), rep.dates, make_config(CFG, risk_free_annual=0.02)) == 0.02).all()


def test_14_portfolio_metrics_use_the_same_per_bar_rate():
    p0 = run_portfolio_backtest(["AAPL", "EURUSD"], "2024-01-02", "2024-03-28", CFG, rebalance_every=10,
                                provider=_NoRate(CFG))
    p1 = run_portfolio_backtest(["AAPL", "EURUSD"], "2024-01-02", "2024-03-28", CFG, rebalance_every=10,
                                provider=_Rate(CFG))
    assert p1.metrics["Buy&Hold"].sharpe < p0.metrics["Buy&Hold"].sharpe
    rf = np.full(len(p1.dates), 0.04)
    ppy = max(r.instrument.periods_per_year for r in p1.sleeves.values())
    eq = CFG["initial_capital"] * np.cumprod(1 + p1.returns["Buy&Hold"].to_numpy())
    pos = sum(pd.Series(np.abs(r.results["Buy&Hold"].positions), index=r.dates).reindex(p1.dates).fillna(0.0)
              for r in p1.sleeves.values()) / 2
    assert p1.metrics["Buy&Hold"].sharpe == pytest.approx(quant.compute_metrics(eq, pos.to_numpy(), ppy, rf).sharpe, rel=1e-9)
    assert p1.metrics["Buy&Hold"].sharpe != pytest.approx(quant.compute_metrics(eq, pos.to_numpy(), ppy, 0.0).sharpe)


# ========================================================= 19 / 33: Almgren-Chriss never overflows
@pytest.mark.parametrize("kappa", [1e-7, 1e-5, 1e-3, 0.5, 3.0, 50.0, 700.0, 720.0, 1e3, 1e4, 1e6])
def test_19_almgren_chriss_is_finite_and_sums_to_total(kappa):
    for fn in (quant.almgren_chriss, pycore.almgren_chriss):
        q = fn(1.0, 78, kappa)
        assert np.isfinite(q).all() and (q >= -1e-15).all() and q.sum() == pytest.approx(1.0, abs=1e-9)
        if kappa >= 1e4:
            assert q[0] == pytest.approx(1.0, abs=1e-12)                 # everything in the first slice
        elif kappa >= 700:
            assert q[0] > 0.999 and q[1] > q[2] > 0                        # front-loaded, still a schedule
    np.testing.assert_allclose(quant.almgren_chriss(1e6, 78, kappa), pycore.almgren_chriss(1e6, 78, kappa),
                               rtol=1e-12, atol=1e-6)
    if kappa <= 50:                                                     # where the textbook form is representable
        t = np.arange(1, 79) / 78
        rem = np.sinh(kappa * (1 - t)) / np.sinh(kappa)
        ref = np.concatenate([[1.0], rem[:-1]]) - rem
        np.testing.assert_allclose(quant.almgren_chriss(1.0, 78, kappa), ref, rtol=1e-9, atol=1e-13)


def test_33_large_kappa_charges_impact_instead_of_switching_it_off(monkeypatch):
    r700, r1e4 = algo_cost_ratio("ac", 78, "equity", 700.0), algo_cost_ratio("ac", 78, "equity", 1e4)
    assert np.isfinite(r1e4) and r1e4 >= r700 > algo_cost_ratio("ac", 78, "equity", 5.0)
    provider = SyntheticProvider(CFG)
    ins = Instrument.parse("AAPL")
    full = provider.history(ins, pd.Timestamp("2023-01-01").date(), pd.Timestamp("2024-01-01").date())
    base = make_config(CFG, costs={"impact_coeff": 1.0}, initial_capital=1e9)
    k_vwap = impact_coefficients(full, ins, base)
    k_ac = impact_coefficients(full, ins, make_config(base, costs={"execution_algo": "ac", "ac_kappa": 1e4}))
    finite = np.isfinite(k_vwap)
    assert finite.sum() > 100 and np.array_equal(np.isfinite(k_ac), finite)
    np.testing.assert_allclose(k_ac[finite], k_vwap[finite] * r1e4)
    rep = run_agent_backtest("AAPL", "2024-01-02", "2024-02-29", make_config(base, costs={"execution_algo": "ac", "ac_kappa": 1e4}),
                             rebalance_every=10)
    vwap = run_agent_backtest("AAPL", "2024-01-02", "2024-02-29", base, rebalance_every=10)
    for name in rep.results:
        if vwap.results[name].impact_paid > 0:
            assert rep.results[name].impact_paid > vwap.results[name].impact_paid
    # a non-finite schedule cost can never reach the engine as "no impact"
    import agentic_trader.backtest as bt_mod
    monkeypatch.setattr(bt_mod, "algo_cost_ratio", lambda *a, **k: NAN)
    with pytest.raises(ValueError, match="non-finite"):
        impact_coefficients(full, ins, make_config(base, costs={"execution_algo": "ac"}))


# ======================================================= 20: crossover dead band on flat windows
def test_20_flat_and_near_flat_series_give_no_position_on_either_backend():
    rng = np.random.default_rng(0)
    for level in np.r_[1.08, 7e5, 0.3333333, rng.uniform(0.5, 500, 100)]:
        flat = np.full(120, level)
        for fn, args in ((quant.strat_sma_cross, (20, 50, True)), (pycore.strat_sma_cross, (20, 50, True)),
                         (quant.strat_macd, (12, 26, 9, True)), (pycore.strat_macd, (12, 26, 9, True))):
            assert not fn(flat, *args).any(), (fn.__name__, level)
        near = level * (1 + 1e-15 * rng.standard_normal(120))           # rounding-level noise
        assert not quant.strat_sma_cross(near, 20, 50, True).any() and not pycore.strat_macd(near, 12, 26, 9, True).any()
    # prices then a halt at the last price: the halted stretch is flat once the windows have passed
    # (the SMAs after 50 bars; the EMAs behind MACD only converge exponentially, ~1e-27 after 800 bars)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 100)))
    halted = np.r_[c, np.full(800, c[-1])]
    for fn in (quant.strat_sma_cross, pycore.strat_sma_cross):
        assert not fn(halted, 20, 50, True)[150:].any()
    for fn in (quant.strat_macd, pycore.strat_macd):
        assert not fn(halted, 12, 26, 9, True)[-10:].any()
    np.testing.assert_array_equal(quant.strat_sma_cross(halted, 20, 50, True), pycore.strat_sma_cross(halted, 20, 50, True))
    np.testing.assert_array_equal(quant.strat_macd(halted, 12, 26, 9, True), pycore.strat_macd(halted, 12, 26, 9, True))
    # a real (if tiny) trend is still a signal, and the backends agree on it
    trend = 100 * (1 + 1e-9 * np.arange(120))
    assert quant.strat_sma_cross(trend, 20, 50, True)[-1] == 1.0 == pycore.strat_sma_cross(trend, 20, 50, True)[-1]
    wave = 100 * (1 + 1e-9 * np.sin(np.arange(120) / 5))                # MACD hist of a straight line is 0
    a, b = quant.strat_macd(wave, 12, 26, 9, True), pycore.strat_macd(wave, 12, 26, 9, True)
    assert np.abs(a[40:]).all() and np.array_equal(a, b)


@needs_cpp
def test_20_backends_agree_on_piecewise_constant_series():
    rng = np.random.default_rng(1)
    for _ in range(50):
        pieces = [np.full(int(rng.integers(5, 70)), rng.uniform(0.5, 500)) for _ in range(int(rng.integers(1, 5)))]
        x = np.concatenate(pieces)
        for allow_short in (False, True):
            np.testing.assert_array_equal(quant.strat_sma_cross(x, 20, 50, allow_short), pycore.strat_sma_cross(x, 20, 50, allow_short))
            np.testing.assert_array_equal(quant.strat_macd(x, 12, 26, 9, allow_short), pycore.strat_macd(x, 12, 26, 9, allow_short))


# ============================================================= 76: one NaN rule for every indicator
def _series(n=300, seed=3):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    return c * (1 + np.abs(rng.normal(0, 0.005, n))), c * (1 - np.abs(rng.normal(0, 0.005, n))), c


def _nan_span(v, start):
    idx = np.flatnonzero(np.isnan(v[start:])) + start
    return (int(idx[0]), int(idx[-1])) if idx.size else None


K = 150
CASES = [  # name, fn(h, l, c) -> series, first index to inspect, expected NaN span for a NaN bar at K
    ("sma", lambda h, l, c: quant.sma(c, 20), 40, (K, K + 19)),
    ("ema", lambda h, l, c: quant.ema(c, 20), 40, (K, K + 19)),
    ("rolling_std", lambda h, l, c: quant.rolling_std(c, 20), 40, (K, K + 19)),
    ("zscore", lambda h, l, c: quant.zscore(c, 20), 40, (K, K + 19)),
    ("rsi", lambda h, l, c: quant.rsi(c, 14), 40, (K, K + 14)),
    ("atr", lambda h, l, c: quant.atr(h, l, c, 14), 40, (K, K + 14)),
    ("macd_hist", lambda h, l, c: quant.macd(c)[2], 40, (K, K + 33)),
    ("kdj_j", lambda h, l, c: quant.kdj(h, l, c, 9)[2], 40, (K, K + 8)),
    ("bollinger_pb", lambda h, l, c: quant.bollinger(c, 20)[3], 40, (K, K + 19)),
    ("realized_vol", lambda h, l, c: quant.realized_vol(c, 20, 252), 40, (K, K + 20)),
    ("rolling_max", lambda h, l, c: quant.rolling_max(c, 20), 40, (K, K + 19)),
]


@pytest.mark.parametrize("name,fn,start,span", CASES, ids=[c[0] for c in CASES])
def test_76_a_missing_bar_is_nan_for_its_window_and_the_series_recovers(name, fn, start, span):
    h, l, c = _series()
    clean = fn(h, l, c)
    hn, ln, cn = h.copy(), l.copy(), c.copy()
    hn[K] = ln[n := K] = cn[K] = NAN
    out = fn(hn, ln, cn)
    assert _nan_span(out, start) == span, (name, _nan_span(out, start))
    assert np.isfinite(out[span[1] + 1:]).all()
    np.testing.assert_allclose(out[start:K], clean[start:K], rtol=1e-12)
    if CPP:
        pyfn = {"macd_hist": lambda: pycore.macd(cn)[2], "kdj_j": lambda: pycore.kdj(hn, ln, cn, 9)[2],
                "bollinger_pb": lambda: pycore.bollinger(cn, 20)[3], "realized_vol": lambda: pycore.realized_vol(cn, 20, 252),
                "atr": lambda: pycore.atr(hn, ln, cn, 14), "rsi": lambda: pycore.rsi(cn, 14),
                "sma": lambda: pycore.sma(cn, 20), "ema": lambda: pycore.ema(cn, 20),
                "rolling_std": lambda: pycore.rolling_std(cn, 20), "zscore": lambda: pycore.zscore(cn, 20),
                "rolling_max": lambda: pycore.rolling_max(cn, 20)}[name]()
        np.testing.assert_allclose(out, pyfn, rtol=1e-9, atol=1e-12, equal_nan=True)


def test_76_rsi_never_treats_a_missing_close_as_a_zero_change():
    _, _, c = _series()
    cn = c.copy()
    cn[K] = NAN
    for fn in (quant.rsi, pycore.rsi):
        out = fn(cn, 14)
        assert np.isnan(out[K:K + 15]).all() and np.isfinite(out[K + 15:]).all()
    e = quant.ema([NAN, NAN, 1.0, 2.0, 3.0], 3)                          # leading NaNs are still skipped
    assert np.isnan(e[:4]).all() and e[4] == pytest.approx(2.0)


# =================================================== 77: compute_metrics validates its lengths
def test_77_compute_metrics_rejects_length_mismatch_with_value_error_on_both_backends():
    e = [100, 101, 102, 103, 104.0]
    for cm in (quant.compute_metrics, pycore.compute_metrics):
        with pytest.raises(ValueError):
            cm(e, [1, 1, 1], 252)
        with pytest.raises(ValueError):
            cm(e, [1] * 8, 252)
        with pytest.raises(ValueError):
            cm(e, [], 252)
        with pytest.raises(ValueError):
            cm(e, [1] * 5, 252, [0.0] * 4)
        with pytest.raises(ValueError):
            cm(e, [1] * 5, 252, 0.0, traded=[0.0] * 4)
        m = cm(e, [1] * 5, 252)
        assert m.avg_exposure == 1.0 and m.win_rate == 1.0 and m.num_trades == 1
        t = cm(e, [1] * 5, 252, 0.0, traded=[1, 0, 0.5, 0, 0])
        assert t.num_trades == 2 and t.turnover == 1.5


# ======================================================== 78: window arguments at the boundary
def test_78_window_arguments_outside_int_range_raise_value_error_on_both_backends():
    x = np.arange(30.0)
    for bad in (2**40, 2**31, True, False, 3.0, "3", None, -1, 0):
        with pytest.raises(ValueError):
            quant.sma(x, bad)
    np.testing.assert_array_equal(quant.sma(x, np.int64(3)), quant.sma(x, 3))
    assert len(quant.sma(x, 2**31 - 1)) == 30 and np.isnan(quant.sma(x, 2**31 - 1)).all()
    with pytest.raises(ValueError):
        quant.macd(x, fast=True)
    with pytest.raises(ValueError):
        quant.strat_kdj_rsi(x, x, x, 9, 2**31)
    with pytest.raises(ValueError):
        quant.atr(x, x, x, n=2**40)
    with pytest.raises(ValueError):
        quant.almgren_chriss(1.0, 2**40, 1.0)
    assert quant.strat_sma_cross(x, 5, 10, True).shape == (30,)         # the bool flag is still a flag
    assert quant.rsi(x, n=14).shape == (30,)


# =================================================== parity of everything new, on random paths
@needs_cpp
@pytest.mark.parametrize("seed", range(6))
def test_v08_cpp_matches_numpy_with_cash_rate_drift_and_ruin(seed):
    rng = np.random.default_rng(seed)
    n = 250
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))
    o = c * np.exp(rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)))
    w = np.round(rng.uniform(-2.5, 2.5, n) * (rng.random(n) > 0.7), 2)
    w[rng.random(n) > 0.97] = NAN
    stop = np.where(w > 0, c * 0.97, c * 1.03)
    take = np.where(w > 0, c * 1.04, c * 0.96)
    stop[rng.random(n) > 0.6] = NAN
    reb = (rng.random(n) > 0.7).astype(float)
    carry = rng.normal(0.01, 0.02, n)
    impact = np.abs(rng.normal(0.003, 0.001, n))
    impact[rng.random(n) > 0.9] = NAN
    cash = np.where(rng.random(n) > 0.1, rng.uniform(0, 0.06, n), NAN)
    cfg = quant.BacktestConfig(cost_bps=1.5, slippage_bps=0.5, borrow_annual=0.02, allow_short=bool(seed % 2),
                               max_leverage=1.0 + seed * 0.5, funded=bool(seed % 3), initial_capital=1e6)
    kw = dict(carry=carry, open=o, high=h, low=l, stop=stop, take=take, rebalance=reb, impact=impact, cash_rate=cash)
    _same_result(quant.run_backtest(c, w, cfg, **kw), pycore.run_backtest_ex(c, w, cfg, **kw))
