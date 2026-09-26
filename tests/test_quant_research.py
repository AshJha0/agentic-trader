"""Quant research layer: statistics, alpha library and evaluation, execution
algorithms and simulator, portfolio construction, plus C++ vs numpy cross-checks
of the new core functions."""
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import Instrument, make_config, quant, run_portfolio_backtest
from agentic_trader.alpha import (ALPHAS, alpha_report, alpha_snapshot, combine, compute_alphas,
                                  forward_returns, information_coefficient, significant_alpha_signal)
from agentic_trader.algo import (almgren_chriss_schedule, plan_execution, pov_schedule, simulate_execution,
                                 synthetic_intraday_bars, twap_schedule, volume_profile, vwap_schedule)
from agentic_trader.data import SyntheticProvider
from agentic_trader.portfolio import (METHODS, construct, ewma_cov, inverse_vol_weights,
                                      ledoit_wolf_shrink, mean_variance_weights, min_variance_weights,
                                      risk_contributions, risk_parity_weights, sample_cov)
from agentic_trader.quant import pycore
from agentic_trader.state import Action, FinalDecision
from agentic_trader.stats import (deflated_sharpe, expected_max_sharpe, min_track_record, probabilistic_sharpe,
                                  selection_report, sharpe_ci_bootstrap, sharpe_stats)

CFG = make_config(memory_path=None)
NAN = float("nan")


@pytest.fixture(scope="module")
def frames():
    p = SyntheticProvider(CFG)
    out = {}
    for s in ("AAPL", "USDJPY"):
        ins = Instrument.parse(s)
        df = p.history(ins, date(2020, 1, 1), date(2024, 3, 28))
        carry = p.carry_series(ins, df.index) if ins.is_fx else None
        out[s] = (ins, df, carry)
    return out


# ------------------------------------------------------------- C++ core
def test_sma_ignores_leading_nans_and_resets_on_nan():
    x = [NAN, NAN, 1, 2, 3, NAN, 4, 5, 6, 7.0]
    for fn in (quant.sma, pycore.sma):
        out = fn(x, 3)
        assert np.isnan(out[:4]).all() and out[4] == 2.0 and np.isnan(out[5:8]).all()
        assert out[8] == 5.0 and out[9] == 6.0


def test_rolling_extremes_and_spearman():
    x = [3, 1, 4, 1, 5, 9, 2, 6.0]
    assert list(quant.rolling_max(x, 3)[2:]) == [4, 4, 5, 9, 9, 9]
    assert list(quant.rolling_min(x, 3)[2:]) == [1, 1, 1, 1, 2, 2]
    rm = quant.rolling_max([1, NAN, 3, 4.0], 2)
    assert np.isnan(rm[:3]).all() and rm[3] == 4
    assert quant.spearman([1, 2, 3, 4], [10, 20, 30, 40]) == pytest.approx(1.0)
    assert quant.spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1.0)
    assert quant.spearman([1, 1, 2, 2, 3], [1, 2, 1, 2, 3]) == pytest.approx(pycore.spearman([1, 1, 2, 2, 3], [1, 2, 1, 2, 3]))
    assert np.isnan(quant.spearman([1, 2], [1, 2])) and np.isnan(quant.spearman([1, 1, 1], [1, 2, 3]))
    assert quant.spearman([1, NAN, 3, 4, 5], [2, 9, 4, 5, 7]) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        quant.spearman([1, 2, 3], [1, 2])


def test_almgren_chriss_schedule_properties():
    flat = quant.almgren_chriss(100.0, 5, 0.0)
    np.testing.assert_allclose(flat, 20.0)
    fl = quant.almgren_chriss(100.0, 5, 2.0)
    assert fl.sum() == pytest.approx(100.0) and (fl >= 0).all() and fl[0] > fl[1] > fl[-1]
    np.testing.assert_allclose(fl, pycore.almgren_chriss(100.0, 5, 2.0), rtol=1e-12)
    with pytest.raises(ValueError):
        quant.almgren_chriss(1.0, 0, 1.0)
    with pytest.raises(ValueError):
        quant.almgren_chriss(1.0, 3, -1.0)


@pytest.mark.skipif(quant.BACKEND != "cpp", reason="C++ extension not built")
def test_new_core_functions_match_numpy():
    rng = np.random.default_rng(3)
    x = rng.normal(size=400)
    x[rng.random(400) < 0.03] = NAN
    y = x + rng.normal(size=400)
    for n in (5, 20):
        np.testing.assert_allclose(quant.rolling_max(x, n), pycore.rolling_max(x, n), equal_nan=True)
        np.testing.assert_allclose(quant.rolling_min(x, n), pycore.rolling_min(x, n), equal_nan=True)
        np.testing.assert_allclose(quant.sma(x, n), pycore.sma(x, n), equal_nan=True, rtol=1e-12)
    assert quant.spearman(x, y) == pytest.approx(pycore.spearman(x, y), rel=1e-12)
    for k in (0.0, 0.3, 3.0):
        np.testing.assert_allclose(quant.almgren_chriss(1e6, 78, k), pycore.almgren_chriss(1e6, 78, k), rtol=1e-11)


# ----------------------------------------------------------------- stats
def test_sharpe_stats_and_bootstrap():
    rng = np.random.default_rng(0)
    r = rng.normal(0.001, 0.01, 1000)
    s = sharpe_stats(r)
    assert s.n == 1000 and s.sharpe_annual == pytest.approx(s.sharpe * math.sqrt(252))
    assert s.t_stat == pytest.approx(s.sharpe * math.sqrt(1000)) and 2.5 < s.kurt < 3.6
    lo, hi = sharpe_ci_bootstrap(r, n_boot=500)
    assert lo < s.sharpe_annual < hi and lo > -1 and hi < 4
    assert all(math.isnan(v) for v in sharpe_ci_bootstrap(r[:2]))
    assert sharpe_stats([0.0, 0.0, 0.0]).sharpe == 0.0


def test_probabilistic_and_deflated_sharpe():
    assert probabilistic_sharpe(0.1, 1000) > 0.99 and probabilistic_sharpe(0.0, 1000) == pytest.approx(0.5)
    assert probabilistic_sharpe(0.1, 1000, skew=-1.0) < probabilistic_sharpe(0.1, 1000, skew=0.0)
    assert math.isnan(probabilistic_sharpe(0.1, 1))
    sr0 = expected_max_sharpe(100, 0.01)
    assert sr0 > expected_max_sharpe(10, 0.01) > 0 and expected_max_sharpe(1, 0.01) == 0.0
    assert deflated_sharpe(0.1, 1000, 100, 0.01) < probabilistic_sharpe(0.1, 1000)
    assert min_track_record(0.1, 0.0) > 0 and math.isinf(min_track_record(0.0, 0.1))
    assert min_track_record(0.2, 0.0) < min_track_record(0.1, 0.0)
    rep = selection_report(np.random.default_rng(1).normal(0.001, 0.01, 800), [0.5, 1.0, 1.4, 0.3, 0.9])
    assert rep["trials"] == 5 and 0 <= rep["deflated_sharpe_prob"] <= 1 and rep["expected_max_sharpe_annual"] > 0


# ----------------------------------------------------------------- alpha
def test_alpha_signals_are_bounded_point_in_time_and_complete(frames):
    for sym, (ins, df, carry) in frames.items():
        sig = compute_alphas(df, ins, None, carry)
        assert set(sig.columns) == set(ALPHAS if ins.is_fx else [a for a in ALPHAS if a != "carry"])
        assert ((sig.dropna() >= -1) & (sig.dropna() <= 1)).all().all()
        assert sig.notna().mean().min() > 0.6                                   # every alpha computes
        short = compute_alphas(df.iloc[:-50], ins, None, None if carry is None else carry[:-50])
        pd.testing.assert_frame_equal(sig.iloc[:-50], short, check_exact=False, rtol=1e-12)
    with pytest.raises(ValueError):
        compute_alphas(frames["AAPL"][1], frames["AAPL"][0], ["nope"])


def test_alpha_semantics():
    ins = Instrument.parse("AAPL")
    idx = pd.bdate_range("2021-01-01", periods=400)
    up = pd.DataFrame({"Close": 100 * np.exp(np.linspace(0, 0.8, 400))}, index=idx)
    up["Open"], up["High"], up["Low"], up["Volume"] = up["Close"], up["Close"] * 1.001, up["Close"] * 0.999, 1e6
    sig = compute_alphas(up, ins)
    last = sig.iloc[-1]
    assert last["tsmom_12_1"] > 0.9 and last["high_52w"] == pytest.approx(1.0) and last["donchian_20"] > 0.9
    assert last["reversal_5"] < 0 and last["rsi_contrarian"] < 0            # fade a straight rally
    fx = Instrument.parse("USDJPY")
    sigfx = compute_alphas(up, fx, ["carry"], np.full(400, 0.03))
    assert sigfx["carry"].iloc[-1] == pytest.approx(math.tanh(1.0))
    assert np.isnan(compute_alphas(up, fx, ["carry"])["carry"]).all()       # no carry series -> no signal


def test_combine_and_information_coefficient():
    s = pd.DataFrame({"a": [1.0, NAN, -1.0], "b": [0.0, 0.5, NAN]})
    c = combine(s, {"a": 3.0, "b": 1.0})
    assert c.tolist() == pytest.approx([0.75, 0.5, -1.0])
    fwd = forward_returns([100, 101, 102, 103, 104.0], 2)
    assert np.isnan(fwd[-2:]).all() and fwd[0] == pytest.approx(0.02)
    ic, t, n = information_coefficient([1, 2, 3, 4, 5], [1, 3, 2, 5, 4])
    assert 0 < ic < 1 and t == pytest.approx(ic * math.sqrt(5)) and n == 5
    assert math.isnan(information_coefficient([1, NAN], [1, 2])[0])


def test_alpha_report_structure(frames):
    ins, df, carry = frames["USDJPY"]
    rep = alpha_report(df, ins, 10, carry_series=carry)
    assert "combined" in rep.table.index and set(rep.decay.columns) == {1, 5, 10, 21, 42}
    assert rep.correlations.shape == (9, 9) and set(rep.best(2)) <= set(rep.table.index)
    assert ((rep.table["hit%"].dropna() >= 0) & (rep.table["hit%"].dropna() <= 100)).all()
    snap = alpha_snapshot(df, ins, carry)
    assert "combined" in snap and all(v is None or -1 <= v <= 1 for v in snap.values())
    with pytest.raises(ValueError):
        alpha_report(df, ins, 0)


def test_significant_alpha_signal_gates_on_tstat_and_n():
    latest = {"a": 0.6, "b": -0.4, "c": 0.2}
    # "a" is significant and positive-IC; "b" is significant but fails the n floor;
    # "c" has a below-threshold t-stat. Only "a" should end up in the combination.
    ic = {"a": {"IC": 0.15, "t(IC)": 2.5, "n": 50},
         "b": {"IC": -0.20, "t(IC)": 2.1, "n": 10},
         "c": {"IC": 0.05, "t(IC)": 1.0, "n": 200},
         "combined": {"IC": 0.10, "t(IC)": 5.0, "n": 200}}  # must be ignored by name
    comb, names = significant_alpha_signal(latest, ic, min_tstat=2.0, min_n=30)
    assert names == ["a"]
    assert comb == pytest.approx(0.6)

    # No alpha clears the bar -> abstain (None, []), not zero.
    comb2, names2 = significant_alpha_signal(latest, {"a": {"IC": 0.15, "t(IC)": 1.0, "n": 50}})
    assert comb2 is None and names2 == []
    assert significant_alpha_signal({}, {}) == (None, [])


# ------------------------------------------------------------------ algo
def test_profiles_and_schedules():
    eq = volume_profile("equity", 78)
    assert eq.sum() == pytest.approx(1.0) and eq[0] > eq[39] and eq[-1] > eq[39]
    assert np.allclose(volume_profile("fx", 10), 0.1)
    assert twap_schedule(100, 4).tolist() == [25.0] * 4
    assert vwap_schedule(100, [1, 3]).tolist() == [25.0, 75.0]
    assert pov_schedule(100, [1000, 1000, 1000], 0.05).tolist() == [50.0, 50.0, 0.0]
    assert pov_schedule(10, [1000, 1000], 0.05).tolist() == [10.0, 0.0]
    ac = almgren_chriss_schedule(100, 5, sigma_session=1.0, eta=0.1, risk_aversion=1.0)
    assert ac.sum() == pytest.approx(100) and ac[0] > ac[-1]
    for bad in (lambda: twap_schedule(1, 0), lambda: vwap_schedule(1, [0, 0]), lambda: pov_schedule(1, [1], 0.5),
                lambda: almgren_chriss_schedule(1, 3, 1.0, 0.0, 1.0), lambda: volume_profile("fx", 0)):
        with pytest.raises(ValueError):
            bad()


def test_intraday_bars_respect_the_daily_bar():
    day = pd.Series({"Open": 100.0, "High": 104.0, "Low": 97.0, "Close": 102.0, "Volume": 1e6})
    for seed in range(5):
        bars = synthetic_intraday_bars(day, 78, "equity", seed)
        assert bars.iloc[0]["Open"] == 100.0 and bars.iloc[-1]["Close"] == 102.0
        assert bars["High"].max() <= 104.0 + 1e-9 and bars["Low"].min() >= 97.0 - 1e-9
        assert bars["Volume"].sum() == pytest.approx(1e6) and (bars["High"] >= bars["Low"]).all()
    with pytest.raises(ValueError):
        synthetic_intraday_bars(pd.Series({"Open": 100, "High": 99, "Low": 98, "Close": 100, "Volume": 1}), 5)


def test_simulator_costs_and_shortfall():
    day = pd.Series({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0, "Volume": 1e6})
    bars = synthetic_intraday_bars(day, 20, "equity", 1)
    sched = vwap_schedule(1000, bars["Volume"].to_numpy())
    buy = simulate_execution(sched, bars, "buy", "vwap", spread_bps=10.0, impact_coeff=0.0)
    sell = simulate_execution(sched, bars, "sell", "vwap", spread_bps=10.0, impact_coeff=0.0)
    assert buy.completion == pytest.approx(1.0) and buy.spread_cost_bps == pytest.approx(5.0)
    assert buy.impact_cost_bps == 0.0
    # A VWAP-shaped schedule tracks the session VWAP exactly, so both sides show the half-spread.
    assert buy.vs_vwap_bps == pytest.approx(5.0, abs=1e-6) and sell.vs_vwap_bps == pytest.approx(5.0, abs=1e-6)
    assert buy.avg_price > sell.avg_price
    twap = simulate_execution(twap_schedule(1000, 20), bars, "buy", "twap", 10.0, 0.0)
    assert twap.vs_vwap_bps != buy.vs_vwap_bps                        # timing risk shows up vs VWAP
    with_impact = simulate_execution(sched, bars, "buy", "twap", 10.0, 1.0, 0.02, adv=1e6)
    assert with_impact.impact_cost_bps > 0 and with_impact.avg_price > buy.avg_price
    capped = simulate_execution(np.full(20, 1e6), bars, "buy", "twap", 0.0, 0.0)
    assert capped.executed < capped.requested and capped.completion < 1   # cannot exceed bar volume
    empty = simulate_execution(np.zeros(20), bars, "buy")
    assert empty.executed == 0 and math.isnan(empty.avg_price)
    fx_bars = synthetic_intraday_bars(pd.Series({"Open": 1.1, "High": 1.11, "Low": 1.09, "Close": 1.1, "Volume": 0}), 10, "fx")
    fx = simulate_execution(twap_schedule(1e6, 10), fx_bars, "sell", "twap", 0.8, 0.0)
    assert fx.completion == 1.0 and math.isnan(fx.max_participation)
    with pytest.raises(ValueError):
        simulate_execution(twap_schedule(1, 3), bars, "buy")


def test_plan_execution_choices():
    ins = Instrument.parse("AAPL")
    d = FinalDecision("AAPL", date(2024, 3, 1), Action.BUY, 0.6, 0.5, None, None, "")
    small = plan_execution(d, ins, 0.1, 1e6, 100.0, adv=5e6)
    assert small.side == "buy" and small.quantity == pytest.approx(5000) and small.algo == "vwap" and small.slices == 78
    big = plan_execution(d, ins, 0.1, 1e9, 100.0, adv=5e6)
    assert big.algo == "pov" and "POV" in big.reason
    assert plan_execution(d, ins, 0.6, 1e6, 100.0) is None
    fx = plan_execution(FinalDecision("EURUSD", date(2024, 3, 1), Action.SELL, -0.5, 0.5, None, None, ""),
                        Instrument.parse("EURUSD"), 0.0, 1e6, 1.1)
    assert fx.side == "sell" and fx.algo == "twap" and fx.slices == 288
    forced = plan_execution(d, ins, 0.1, 1e6, 100.0, adv=5e6, algo="ac", slices=10)
    bars = synthetic_intraday_bars(pd.Series({"Open": 100, "High": 101, "Low": 99, "Close": 100, "Volume": 1e6}), 10)
    assert forced.schedule(bars).sum() == pytest.approx(forced.quantity)
    with pytest.raises(ValueError):
        plan_execution(d, ins, 0.1, 0.0, 100.0)


# -------------------------------------------------------------- portfolio
@pytest.fixture
def cov_and_returns():
    rng = np.random.default_rng(7)
    n = 4
    L = rng.normal(size=(n, n))
    cov = (L @ L.T) / 200 + np.diag([0.01, 0.04, 0.02, 0.09])
    rets = rng.multivariate_normal(np.zeros(n), cov / 252, 400)
    return cov, rets


def test_covariance_estimators(cov_and_returns):
    cov, rets = cov_and_returns
    s = sample_cov(rets) * 252
    assert np.allclose(s, s.T) and np.all(np.linalg.eigvalsh(s) > 0)
    e = ewma_cov(rets, 60)
    assert e.shape == (4, 4) and np.allclose(e, e.T)
    shrunk, delta = ledoit_wolf_shrink(rets)
    assert 0 <= delta <= 1 and np.allclose(shrunk, shrunk.T)
    assert np.allclose(np.diag(shrunk), np.diag(sample_cov(rets)))       # target keeps the variances
    _, d1 = ledoit_wolf_shrink(rets[:, :1])
    assert d1 == 0.0
    for bad in (lambda: ewma_cov(rets[:1]), lambda: ewma_cov(rets, 0), lambda: sample_cov(rets[0])):
        with pytest.raises(ValueError):
            bad()


def test_weighting_schemes(cov_and_returns):
    cov, _ = cov_and_returns
    iv = inverse_vol_weights(cov)
    assert iv.sum() == pytest.approx(1.0) and (iv > 0).all()
    rp = risk_parity_weights(cov)
    np.testing.assert_allclose(risk_contributions(rp, cov)["pct"], 0.25, atol=1e-6)
    b = np.array([0.4, 0.2, 0.2, 0.2])
    np.testing.assert_allclose(risk_contributions(risk_parity_weights(cov, b), cov)["pct"], b, atol=1e-6)
    mv = min_variance_weights(cov, cap=0.5)
    assert mv.sum() == pytest.approx(1.0) and mv.max() <= 0.5 + 1e-9 and (mv >= -1e-12).all()
    assert mv @ cov @ mv <= iv @ cov @ iv + 1e-12                          # lower variance than inverse vol
    mu = np.array([0.02, 0.10, 0.03, 0.01])
    mw = mean_variance_weights(mu, cov, risk_aversion=2.0, cap=0.6)
    assert mw.sum() == pytest.approx(1.0) and mw[1] == mw.max()             # tilts to the high-mu asset
    with pytest.raises(ValueError):
        min_variance_weights(cov, cap=0.1)                                  # 4 * 0.1 < 1 infeasible
    with pytest.raises(ValueError):
        mean_variance_weights(mu, cov, risk_aversion=0.0)
    rc = risk_contributions(np.zeros(4), cov)
    assert rc["vol"] == 0.0 and math.isnan(rc["diversification_ratio"])


def test_construct_end_to_end(cov_and_returns):
    cov, rets = cov_and_returns
    frame = pd.DataFrame(rets, columns=list("ABCD"))
    targets = {"A": 1.0, "B": -0.5, "C": 0.0, "D": 0.8}
    for m in METHODS:
        pw = construct(targets, frame, m, max_weight=0.6, target_vol=0.15)
        assert pw.method == m and pw.weights[2] == 0.0 and pw.allocation[2] == 0.0
        assert pw.weights[1] <= 0.0 and abs(pw.weights).sum() <= 1.0 + 1e-9   # a short sleeve never turns long
        assert (pw.allocation >= 0).all()
        assert pw.contributions.shape == (4, 6) and pw.correlations.shape == (4, 4)
        assert pw.expected_vol <= 0.15 + 1e-6 and pw.scale >= 1.0
    flat = construct({"A": 0.0, "B": 0.0}, frame, "equal")
    assert flat.expected_vol == 0.0 and (flat.weights == 0).all()
    for bad in (lambda: construct(targets, frame, "bogus"), lambda: construct({"Z": 1.0}, frame),
                lambda: construct(targets, frame.iloc[:10])):
        with pytest.raises(ValueError):
            bad()


def test_portfolio_backtest_weighting_schemes():
    eq = run_portfolio_backtest(["AAPL", "JPM", "EURUSD"], "2024-01-02", "2024-03-28", CFG, 10)
    assert eq.weighting == "equal" and eq.allocations is None
    rp = run_portfolio_backtest(["AAPL", "JPM", "EURUSD"], "2024-01-02", "2024-03-28", CFG, 10, weighting="risk_parity")
    assert rp.allocations is not None and rp.allocations.shape[1] == 3
    assert np.allclose(rp.allocations.sum(axis=1), 1.0, atol=1e-9)
    assert rp.table().loc["AgenticTrader", "Vol%"] != eq.table().loc["AgenticTrader", "Vol%"]
    with pytest.raises(ValueError):
        run_portfolio_backtest(["AAPL"], "2024-01-02", "2024-03-28", CFG, weighting="bogus")
