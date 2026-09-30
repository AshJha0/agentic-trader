"""v0.9: the TSMOM(12-1) and Carry return streams as fully costed baselines."""
import numpy as np
import pandas as pd
import pytest

from agentic_trader import make_config
from agentic_trader.backtest import (AGENT, TSMOM_LOOKBACK, TSMOM_SKIP, baseline_weights, carry_weights,
                                     run_agent_backtest, run_portfolio_backtest, tsmom_weights)

CFG = make_config(memory_path=None)


def test_tsmom_is_the_signed_12_1_return_at_the_vol_target_size():
    n = TSMOM_LOOKBACK + 60
    close = np.exp(np.linspace(0.0, 1.0, n))                     # a steady uptrend
    vt = np.full(n, 0.7)
    w = tsmom_weights(close, vt, allow_short=True)
    assert np.all(w[:TSMOM_LOOKBACK] == 0.0) and np.allclose(w[TSMOM_LOOKBACK:], 0.7)
    down = close[::-1].copy()                                     # a steady downtrend
    assert np.allclose(tsmom_weights(down, vt, allow_short=True)[TSMOM_LOOKBACK:], -0.7)
    assert np.all(tsmom_weights(down, vt, allow_short=False) == 0.0)   # long-only goes flat, never short
    # the signal skips the last month: a reversal inside the skip window does not flip it
    rev = close.copy(); rev[-TSMOM_SKIP:] = close[-TSMOM_SKIP] * 0.5
    assert tsmom_weights(rev, vt, True)[-1] == pytest.approx(0.7)


def test_carry_weights_follow_the_desks_strategic_rule_and_are_flat_on_equities():
    carry = np.array([0.02, -0.01, 0.10, np.nan, 0.0])          # annual fractions
    w = carry_weights(carry, 5, scale=2.0, cap=0.5)
    assert w.tolist() == pytest.approx([0.5, -0.5, 0.5, 0.0, 0.0])   # 2% / 2 = 1.0 -> capped at 0.5
    assert carry_weights(np.array([0.005]), 1, 2.0, 0.5)[0] == pytest.approx(0.25)
    assert np.all(carry_weights(None, 4, 2.0, 0.5) == 0.0)


def test_baseline_weights_carry_both_streams_and_keep_the_old_six():
    n = 400
    idx = pd.bdate_range("2020-01-01", periods=n)
    c = 100 * np.exp(np.cumsum(np.random.default_rng(0).normal(0.0005, 0.01, n)))
    full = pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)
    w = baseline_weights(full, allow_short=False, carry_annual=np.full(n, 0.03), carry_scale=2.0, carry_cap=0.5)
    assert set(w) == {"Buy&Hold", "B&H vol-target", "SMA(20/50)", "MACD", "KDJ+RSI", "ZMR", "TSMOM(12-1)", "Carry"}
    assert np.all(np.abs(w["TSMOM(12-1)"]) <= w["B&H vol-target"] + 1e-12)
    assert np.all(w["Carry"] == 0.5)
    assert np.all(w["TSMOM(12-1)"] >= 0.0)


def test_streams_run_fully_costed_in_every_sleeve_and_the_portfolio():
    rep = run_agent_backtest("EURUSD", "2024-01-02", "2024-06-28", CFG, rebalance_every=10)
    assert {"TSMOM(12-1)", "Carry"} <= set(rep.results)
    carry = rep.results["Carry"]
    assert carry.positions.shape == rep.results[AGENT].positions.shape
    # the target is capped at 0.5; the held weight drifts with the price between decisions (constant units)
    assert np.all(np.abs(carry.positions) <= 0.5 * 1.1) and np.abs(carry.positions).max() > 0.4
    eq = run_agent_backtest("AAPL", "2024-01-02", "2024-06-28", CFG, rebalance_every=10)
    assert np.all(eq.results["Carry"].positions == 0.0)              # flat on equities
    port = run_portfolio_backtest(["AAPL", "EURUSD"], "2024-01-02", "2024-06-28", CFG, rebalance_every=10,
                                  weighting="risk_parity")
    assert {"TSMOM(12-1)", "Carry"} <= set(port.metrics) and "Carry" in port.returns


def _combiner():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "combine_v09.py"
    spec = importlib.util.spec_from_file_location("combine_v09", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_combiner_shares_are_risk_parity_without_look_ahead_and_sum_to_one():
    mod = _combiner()
    rng = np.random.default_rng(3)
    ex = np.column_stack([rng.normal(0, 0.01, 600), rng.normal(0, 0.03, 600)])   # one stream 3x as volatile
    shares = mod.risk_parity_shares(ex, window=120, every=5)
    assert shares.shape == ex.shape and np.allclose(shares.sum(axis=1), 1.0)
    assert np.allclose(shares[:120], 0.5)                          # equal until a window exists
    assert shares[-1, 0] > 0.65 > shares[-1, 1]                    # the quiet stream gets more capital
    # no look-ahead: shares on day t only change on a rebalance day and depend on days < t
    ex2 = ex.copy(); ex2[300:] *= 10.0
    assert np.array_equal(mod.risk_parity_shares(ex2, 120, 5)[:301], shares[:301])


def test_drawdown_overlay_halves_after_a_loss_and_recovers():
    mod = _combiner()
    r = np.zeros(200); r[50] = -0.2; r[120:160] = 0.01
    sc = mod.drawdown_overlay(r, dd_window=60, dd_limit=0.10)
    assert sc[50] == 1.0 and np.all(sc[51:110] == 0.5)             # halved the day after the loss, not on it
    assert np.all(sc[170:] == 1.0)                                  # the loss left the window and the book recovered


def test_overlay_blend_is_the_control_at_zero_and_the_desk_at_one():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "overlay_v09.py"
    spec = importlib.util.spec_from_file_location("overlay_v09", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = np.random.default_rng(5)
    desk, ctl = rng.normal(0.0004, 0.01, 300), rng.normal(0.0005, 0.008, 300)
    assert np.array_equal(mod.blend(desk, ctl, 0.0), ctl) and np.allclose(mod.blend(desk, ctl, 1.0), desk)
    assert np.allclose(mod.blend(desk, ctl, 0.5), 0.5 * (desk + ctl))
    # excess pairs the bill credited over (t-1, t] with the return at t: bar 0 (flat) is dropped
    rf = np.linspace(0.01, 0.05, 300)
    assert mod.excess(ctl, rf).shape == (299,) and mod.excess(ctl, rf)[0] == pytest.approx(ctl[1] - rf[0] / mod.PPY)
    assert mod.mdd_pct(np.array([0.1, -0.2, 0.05])) == pytest.approx(20.0)
