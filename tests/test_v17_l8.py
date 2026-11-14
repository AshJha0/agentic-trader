"""v0.17 lane L8: financing spread, VaR NaN policy, execution realism, corporate actions,
TCA, GJR-GARCH VaR/ES with ES and book-level coverage backtests, decay-derived rebalance,
evidence bounds."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from agentic_trader import quant
from agentic_trader import risk_model as rm
from agentic_trader.corporate_actions import apply_actions, cash_flow_rows
from agentic_trader.evidence_bounds import decision_horizon, holdout_selection_premium, sessions_needed
from agentic_trader.execution_realism import (
    abdi_ranaldo,
    cap_participation,
    corwin_schultz,
    participation_shortfall,
    simulate_ohlc,
    spread_consistent_y,
    spread_estimates,
    stop_fill_with_slippage,
    stop_slippage_frac,
)
from agentic_trader.financing import apply_financing, financing_drag, run_backtest_financed
from agentic_trader.garch import (
    GJRParams,
    acerbi_szekely_z2,
    es_backtest,
    fit_gjr,
    gjr_var_es_forecast,
    gjr_variance,
    simulate_gjr,
)
from agentic_trader.horizon import half_life_from_ic, rebalance_from_decay
from agentic_trader.quant import pycore
from agentic_trader.stats import var_backtest
from agentic_trader.tca import predicted_cost, tca_rows, tca_summary


# ---------------------------------------------------------------- A5 financing
def _prices(n=300, seed=1):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, n)))


def test_financing_drag_only_on_borrowed_notional():
    d = financing_drag([0.0, 0.5, 1.0, 1.5, -2.0, np.nan], 0.005, 0.0)
    assert d.tolist() == pytest.approx([0, 0, 0, 0.0025, 0.005, 0])
    d2 = financing_drag([0.25], 0.005, 0.001)
    assert d2[0] == pytest.approx(0.75 * 0.001)
    with pytest.raises(ValueError):
        financing_drag([1.0], -0.1)


def test_levered_run_pays_spread_exactly_without_costs():
    p = _prices()
    cfg = pycore.BacktestConfig(max_leverage=2.0, cost_bps=0.0, slippage_bps=0.0, risk_free_annual=0.03)
    w = np.full(p.size, 1.5)
    base = pycore.run_backtest(p, w, cfg)
    fin = run_backtest_financed(p, w, cfg, funding_spread_bps=50.0)
    drag = 0.5 * 0.005 / cfg.periods_per_year
    held = base.positions[:-1]
    # engine's held weight drifts; drag follows the held weight bar by bar
    exp = base.returns[1:] - (np.maximum(np.abs(held) - 1, 0) * 0.005 / cfg.periods_per_year)
    np.testing.assert_allclose(fin.returns[1:], exp, rtol=0, atol=1e-15)
    assert fin.equity[-1] < base.equity[-1]
    assert np.mean(base.returns[1:] - fin.returns[1:]) == pytest.approx(drag, rel=0.2)


def test_unlevered_run_is_unchanged_by_default():
    p = _prices()
    cfg = pycore.BacktestConfig(cost_bps=1.0)
    w = np.full(p.size, 0.8)
    base = pycore.run_backtest(p, w, cfg)
    fin = apply_financing(base, cfg.periods_per_year)
    np.testing.assert_array_equal(fin.returns, base.returns)


# ---------------------------------------------------------------- A6 var_next NaN policy
@pytest.mark.parametrize("method", ["historical", "ewma", "fhs"])
def test_var_next_agrees_with_var_forecast_across_nan_gaps(method):
    rng = np.random.default_rng(3)
    r = rng.standard_t(4, 600) * 0.01
    r[100:130] = np.nan  # a month of missing data
    r[400] = np.inf
    nxt = rm.var_next(r, method)
    ref = rm.var_forecast(np.append(np.where(np.isfinite(r), r, np.nan), 0.0), method)[-1]
    assert nxt == pytest.approx(ref, rel=1e-12)


def test_var_next_regression_old_code_dropped_nan_days():
    """The old code removed NaN days before forecasting, which moves the FHS window back in
    time: on this series the old answer differs from var_forecast; the new one agrees."""
    rng = np.random.default_rng(5)
    calm, wild = rng.normal(0, 0.01, 100), rng.standard_t(2, 400) * 0.01
    r = np.concatenate([wild, np.full(200, np.nan), calm])
    ref = rm.var_forecast(np.append(r, 0.0), "fhs")[-1]
    old = rm.var_next(r[np.isfinite(r)], "fhs")
    assert rm.var_next(r, "fhs") == pytest.approx(ref)
    assert abs(old - ref) > 1e-6
    assert rm.var_next(np.r_[np.full(50, np.nan), np.full(10, 0.01)]) is None


# ---------------------------------------------------------------- C1 execution realism
def test_stop_slippage_defaults_match_engine_and_worsen_with_parameters():
    for args in [
        (1.0, 95.0, 100, 101, 94),
        (1.0, 95.0, 93, 96, 92),
        (-1.0, 105.0, 100, 106, 99),
        (-1.0, 105.0, 107, 108, 104),
        (1.0, 95.0, 100, 101, 96),
    ]:
        w, s, o, h, low = args
        eng = pycore._exit_fill(w, s, np.nan, o, h, low)
        mine = stop_fill_with_slippage(w, s, o, h, low)
        assert (np.isnan(eng) and np.isnan(mine)) or eng == pytest.approx(mine)
    px = stop_fill_with_slippage(1.0, 95.0, 100, 101, 94, half_spread=5e-4, range_frac=0.5)
    assert 94 <= px < 95
    assert px == pytest.approx(95 * (1 - 5e-4) - 0.5)
    assert stop_slippage_frac(1.0, 95.0, 100, 101, 94, 5e-4, 0.5) > 0
    assert stop_fill_with_slippage(1.0, 95.0, 100, 101, 94.9, 0.0, 1.0) == pytest.approx(94.9)  # never below low
    assert stop_slippage_frac(1.0, 95.0, 100, 101, 96, 5e-4, 0.5) == 0.0


def test_participation_cap_limits_each_bar_and_converges():
    n = 10
    target = np.r_[0.0, np.full(n - 1, 1.0)]
    prices, adv = np.full(n, 100.0), np.full(n, 1000.0)
    # cap 10 % of 1000 shares x $100 = $10k per bar on $40k capital = 0.25 weight a bar
    out = cap_participation(target, prices, adv, capital=40_000, cap=0.10)
    assert np.all(np.abs(np.diff(np.r_[0.0, out])) <= 0.25 + 1e-12)
    assert out[4] == pytest.approx(1.0) and out[3] == pytest.approx(0.75)
    sf = participation_shortfall(target, out)
    assert sf["max_gap"] == pytest.approx(0.75)
    uncapped = cap_participation(target, prices, np.full(n, np.nan), capital=40_000)
    np.testing.assert_array_equal(uncapped, target)


def test_spread_estimators_rank_spreads_and_ar_is_near_truth_when_wide():
    wide = simulate_ohlc(3000, 0.004, 0.01, seed=1)
    narrow = simulate_ohlc(3000, 0.0005, 0.01, seed=1)
    ew, en = spread_estimates(wide), spread_estimates(narrow)
    assert ew["abdi_ranaldo"] > en["abdi_ranaldo"]
    assert ew["corwin_schultz"] > en["corwin_schultz"]
    assert abdi_ranaldo(wide["High"], wide["Low"], wide["Close"]) == pytest.approx(0.004, rel=0.35)
    cs = corwin_schultz(wide["High"], wide["Low"], wide["Close"])
    assert np.isnan(cs[0]) and np.nanmin(cs) >= 0


def test_spread_consistent_y_worked_example():
    assert spread_consistent_y(4e-4, 0.015) == pytest.approx(2e-4 / 0.0015)
    assert math.isnan(spread_consistent_y(4e-4, 0.0))


# ---------------------------------------------------------------- C3 corporate actions
def test_split_then_dividend_in_ex_date_order():
    acts = {
        "AAPL": pd.DataFrame({"Split": [4.0, 0.0], "Dividend": [0.0, 0.25]}, index=pd.to_datetime(["2024-06-10", "2024-06-12"]))
    }
    pos, cash, ev = apply_actions({"AAPL": 10.0, "MSFT": 5.0}, acts, through=date(2024, 6, 12))
    assert pos == {"AAPL": 40.0, "MSFT": 5.0}
    assert cash == pytest.approx(10.0)
    assert [e.kind for e in ev] == ["split", "dividend"]
    rows = cash_flow_rows(ev)
    assert len(rows) == 1 and rows[0]["amount"] == pytest.approx(10.0)


def test_actions_window_is_exclusive_after_inclusive_through_and_short_pays_dividend():
    acts = {"XOM": pd.DataFrame({"Dividend": [0.9, 0.95]}, index=pd.to_datetime(["2024-02-14", "2024-05-14"]))}
    pos, cash, _ = apply_actions({"XOM": -100.0}, acts, through=date(2024, 5, 14), after=date(2024, 2, 14))
    assert pos["XOM"] == -100.0 and cash == pytest.approx(-95.0)


def test_reverse_split_cash_in_lieu_or_refusal():
    acts = {"X": pd.DataFrame({"Split": [0.1]}, index=pd.to_datetime(["2024-01-10"]))}
    with pytest.raises(ValueError, match="fractional"):
        apply_actions({"X": 15.0}, acts, through=date(2024, 1, 31))
    pos, cash, ev = apply_actions({"X": 15.0}, acts, through=date(2024, 1, 31), prices={"X": 20.0})
    assert pos["X"] == 1.0 and cash == pytest.approx(10.0)
    assert {e.kind for e in ev} == {"split", "cash_in_lieu"}


# ---------------------------------------------------------------- C5 TCA
def _order(cid, side, qty, fills):
    return SimpleNamespace(
        client_order_id=cid, side=side, quantity=qty, fills=[SimpleNamespace(quantity=q, price=p, cost=c) for q, p, c in fills]
    )


def test_tca_worked_example_and_partial_fill():
    orders = [
        _order("a", "buy", 100, [(100, 50.02, 1.0)]),
        _order("b", "sell", 200, [(100, 30.0, 0.5)]),
        _order("c", "buy", 10, []),
    ]
    rows = tca_rows(orders, {"a": 50.0, "b": 30.0, "c": 10.0}, {"a": 1.5, "b": 2.0, "c": 0.1}).set_index("client_order_id")
    assert rows.loc["a", "realised_cost"] == pytest.approx(3.0)
    assert rows.loc["a", "slippage_bp"] == pytest.approx(3.0)
    assert rows.loc["b", "predicted_cost"] == pytest.approx(1.0)  # half filled -> half predicted
    assert rows.loc["b", "slippage_bp"] == pytest.approx(1e4 * (0.5 - 1.0) / 3000)
    assert rows.loc["c", "fill_ratio"] == 0 and math.isnan(rows.loc["c", "slippage_bp"])
    s = tca_summary(rows.reset_index())
    assert s["filled"] == 2 and s["worse_than_predicted"] == 0.5


def test_tca_on_real_oms_fill_matches_model_cost():
    from agentic_trader.config import DEFAULT_CONFIG
    from agentic_trader.oms import OMS, MarketSnapshot, OrderState

    oms = OMS(DEFAULT_CONFIG, capital=100_000.0)
    at = datetime(2024, 3, 5, 20, 59, tzinfo=timezone.utc)
    o = oms.submit("t1", "AAPL", "buy", 100, 170.0, 170.0, at)
    assert o.state is OrderState.ACKED
    oms.execute("t1", MarketSnapshot(170.0, None, None), at)
    bc_unit = o.fills[0].cost / (100 * 170.0)
    rows = tca_rows([o], {"t1": 170.0}, {"t1": predicted_cost(100 * 170.0, 100_000.0, bc_unit)})
    assert abs(rows["slippage_bp"].iloc[0]) < 1e-9  # fills at the reference: model error only


# ---------------------------------------------------------------- C4 GJR-GARCH
TRUE = GJRParams(omega=2e-6, alpha=0.04, gamma=0.08, beta=0.88)


def test_gjr_fit_recovers_parameters_on_long_path():
    r = simulate_gjr(3000, TRUE, seed=11)
    p = fit_gjr(r, use_scipy=False)
    assert p.persistence == pytest.approx(TRUE.persistence, abs=0.05)
    assert p.gamma > p.alpha * 0.5  # leverage term found
    assert math.sqrt(p.long_run_var) == pytest.approx(math.sqrt(TRUE.long_run_var), rel=0.3)


def test_gjr_variance_is_ex_ante():
    r = simulate_gjr(300, TRUE, seed=2)
    s = gjr_variance(r, TRUE)
    r2 = r.copy()
    r2[200] = -0.5
    s2 = gjr_variance(r2, TRUE)
    np.testing.assert_array_equal(s[:201], s2[:201])
    assert s2[201] > s[201]


def test_book_level_coverage_and_es_backtest_on_fixed_garch_path():
    """CI check: a 3-name book on fixed synthetic GJR paths; GJR VaR passes Kupiec and
    Christoffersen and its ES passes Z2, a half-size VaR/ES is rejected by both."""
    names = [simulate_gjr(2500, TRUE, seed=s) for s in (21, 22, 23)]
    book = 0.5 * names[0] + 0.3 * names[1] + 0.2 * names[2]
    var, es = gjr_var_es_forecast(book, 0.95, window=500, refit_every=500)
    ok = var_backtest(book, var, 0.95)
    # a weighted sum of GJR paths is only close to GJR, so the pass bar is the 1 % level
    assert ok.kupiec_p > 0.01 and ok.christoffersen_p is not None and ok.christoffersen_p > 0.01
    good = es_backtest(book, var, es, 0.95, n_sim=1000)
    assert good["p"] > 0.01
    bad = var_backtest(book, 0.5 * var, 0.95)
    assert bad.kupiec_p < 0.001
    assert es_backtest(book, 0.5 * var, 0.5 * es, 0.95, n_sim=1000)["p"] < 0.001


def test_z2_worked_example():
    n = 1000
    r = np.zeros(n)
    var, es = np.full(n, 0.0164), np.full(n, 0.0206)
    r[:50] = -0.0206
    assert acerbi_szekely_z2(r, var, es) == pytest.approx(0.0, abs=1e-12)
    r[:50] = -0.03
    assert acerbi_szekely_z2(r, var, es) == pytest.approx(1 - 0.03 / 0.0206)


# ---------------------------------------------------------------- Q4 horizon
def test_rebalance_from_ar1_signal_decay():
    rng = np.random.default_rng(0)
    n, phi = 6000, 0.9
    s = np.zeros(n)
    for t in range(1, n):
        s[t] = phi * s[t - 1] + rng.normal()
    r = np.r_[0.0, 0.002 * s[:-1] + rng.normal(0, 0.01, n - 1)]
    close = 100 * np.cumprod(1 + r)
    ch = rebalance_from_decay(s, close)
    assert ch.half_life == pytest.approx(math.log(2) / -math.log(phi), rel=0.35)
    assert 5 <= ch.rebalance_every <= 9


def test_rebalance_keeps_default_for_noise_and_half_life_edge_cases():
    rng = np.random.default_rng(1)
    s = rng.normal(size=2000)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, 2000))
    assert rebalance_from_decay(s, close).rebalance_every == 5
    assert half_life_from_ic(pd.Series([0.1, 0.05, 0.025, 0.0125])) == pytest.approx(1.0)
    assert math.isnan(half_life_from_ic(pd.Series([0.0, 0.1, 0.1])))


# ---------------------------------------------------------------- B6 / B8 bounds
def test_decision_horizon_from_prereg_numbers():
    # round 2 (C3): the published 3,574 sessions is the 50 % power figure
    assert sessions_needed(0.2, power=0.5) == pytest.approx(1167 * (0.35 / 0.2) ** 2)
    h = decision_horizon(0.2, power=0.5)
    assert h["sessions"] == 3574 and 14.0 < h["years"] < 14.4
    assert h["decision_date"].startswith("2040-")


def test_holdout_selection_premium_numbers():
    s = holdout_selection_premium()
    assert s["mean_premium_pp"] == pytest.approx(72.48, abs=0.01)
    assert s["median_premium_pp"] == pytest.approx(2.16, abs=0.01)
    assert s["mean_sharpe_premium"] == pytest.approx(-0.059, abs=0.001)


def test_quant_backend_facade_still_imports():
    assert quant.BACKEND in ("cpp", "python")
