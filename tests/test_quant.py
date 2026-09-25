import numpy as np
import pytest

from agentic_trader import quant
from agentic_trader.quant import pycore


def _prices(n=300, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    h = c * (1 + np.abs(rng.normal(0, 0.005, n)))
    l = c * (1 - np.abs(rng.normal(0, 0.005, n)))
    return h, l, c


def test_sma_ema_known_values():
    x = [1, 2, 3, 4, 5]
    assert np.isnan(quant.sma(x, 3)[1])
    assert quant.sma(x, 3)[4] == pytest.approx(4.0)
    assert list(quant.ema(x, 3)[2:]) == pytest.approx([2.0, 3.0, 4.0])


def test_rsi_extremes():
    up = np.arange(100.0, 130.0)
    assert quant.rsi(up, 14)[14] == pytest.approx(100.0)
    assert quant.rsi(np.full(30, 5.0), 14)[20] == pytest.approx(50.0)


def test_buy_hold_backtest():
    p = [100, 110, 121]
    r = quant.run_backtest(p, quant.strat_buy_hold(p), quant.BacktestConfig(cost_bps=0))
    assert r.metrics.cumulative_return == pytest.approx(0.21)
    assert r.metrics.max_drawdown == pytest.approx(0.0)
    assert r.metrics.num_trades == 1


def test_no_lookahead_timing():
    # A weight set on the last bar must not earn anything.
    p = [100, 100, 200]
    w = [0, 0, 1]
    r = quant.run_backtest(p, w, quant.BacktestConfig(cost_bps=0))
    assert r.metrics.cumulative_return == pytest.approx(0.0)


def test_fx_carry_and_short_clip():
    flat = np.ones(11)
    cfg = quant.BacktestConfig(cost_bps=0, carry_annual=0.0252, periods_per_year=252)
    r = quant.run_backtest(flat, np.ones(11), cfg)
    assert r.equity[-1] == pytest.approx(cfg.initial_capital * 1.0001**10)
    r = quant.run_backtest([100, 90], [-1, -1], quant.BacktestConfig(cost_bps=0, allow_short=False))
    assert r.metrics.cumulative_return == pytest.approx(0.0)


def test_risk_functions():
    r = [-0.05, -0.02, 0.0, 0.01, 0.03]
    assert quant.quantile(r, 0.25) == pytest.approx(-0.02)
    assert quant.historical_cvar(r) >= quant.historical_var(r)
    assert quant.kelly_fraction(0.6, 1.0) == pytest.approx(0.2)
    assert quant.vol_target_weight(1.0, 0.2, 0.1, 1.0) == pytest.approx(0.5)


@pytest.mark.skipif(quant.BACKEND != "cpp", reason="C++ extension not built")
def test_cpp_matches_python_reference():
    h, l, c = _prices()
    pairs = [
        (quant.rsi(c, 14), pycore.rsi(c, 14)),
        (quant.atr(h, l, c, 14), pycore.atr(h, l, c, 14)),
        (quant.zscore(c, 20), pycore.zscore(c, 20)),
        (quant.realized_vol(c, 20, 252), pycore.realized_vol(c, 20, 252)),
        (quant.strat_kdj_rsi(h, l, c), pycore.strat_kdj_rsi(h, l, c)),
        (quant.strat_zmr(c, allow_short=True), pycore.strat_zmr(c, allow_short=True)),
    ]
    pairs += list(zip(quant.macd(c), pycore.macd(c)))
    pairs += list(zip(quant.kdj(h, l, c), pycore.kdj(h, l, c)))
    pairs += list(zip(quant.bollinger(c), pycore.bollinger(c)))
    for a, b in pairs:
        np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-12, equal_nan=True)
    w = quant.strat_macd(c, allow_short=True)
    cfg = quant.BacktestConfig(cost_bps=2, carry_annual=0.01, borrow_annual=0.02)
    rc, rp = quant.run_backtest(c, w, cfg), pycore.run_backtest(c, w, cfg)
    np.testing.assert_allclose(rc.equity, rp.equity, rtol=1e-10)
    assert rc.metrics.sharpe == pytest.approx(rp.metrics.sharpe, rel=1e-9)
    assert rc.metrics.num_trades == rp.metrics.num_trades
