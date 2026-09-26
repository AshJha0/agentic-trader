"""Edge cases of the quant core, run on whichever backend is active, plus a
randomised C++ vs numpy cross-check of the extended backtester."""
import numpy as np
import pytest

from agentic_trader import quant
from agentic_trader.quant import pycore

NAN = float("nan")


# ------------------------------------------------------------- indicators
@pytest.mark.parametrize("fn", [quant.sma, quant.ema, quant.rolling_std, quant.zscore])
def test_window_longer_than_series_is_all_nan(fn):
    assert np.isnan(fn([1.0, 2.0, 3.0], 5)).all()


@pytest.mark.parametrize("fn", [quant.sma, quant.ema, quant.rolling_std, quant.rsi])
def test_non_positive_window_rejected(fn):
    with pytest.raises(ValueError):
        fn([1.0, 2.0, 3.0], 0)


def test_window_of_one_is_identity_for_sma():
    x = [3.0, 1.0, 4.0]
    assert list(quant.sma(x, 1)) == x


def test_empty_series():
    assert len(quant.sma([], 3)) == 0
    assert len(quant.pct_change([])) == 0
    assert quant.max_drawdown([]) == 0.0


def test_ema_skips_leading_nans():
    e = quant.ema([NAN, NAN, 1.0, 2.0, 3.0], 3)
    assert np.isnan(e[:4]).all() and e[4] == pytest.approx(2.0)


def test_flat_prices():
    flat = np.full(40, 7.0)
    assert quant.zscore(flat, 20)[-1] == 0.0                # zero std -> 0, not NaN/inf
    assert quant.bollinger(flat, 20)[3][-1] == 0.5          # %B mid-band
    k, d, j = quant.kdj(flat, flat, flat, 9)
    assert k[-1] == pytest.approx(50.0)                     # no range -> neutral RSV
    assert quant.realized_vol(flat, 20, 252)[-1] == 0.0


def test_rsi_all_down_is_zero():
    assert quant.rsi(np.arange(30.0, 0.0, -1.0), 14)[-1] == pytest.approx(0.0)


def test_misaligned_ohlc_rejected():
    with pytest.raises(ValueError):
        quant.atr([1, 2], [1, 2, 3], [1, 2, 3])
    with pytest.raises(ValueError):
        quant.kdj([1, 2, 3], [1, 2], [1, 2, 3])


# ------------------------------------------------------------------- risk
def test_risk_degenerate_inputs():
    assert np.isnan(quant.quantile([], 0.5))
    assert quant.historical_var([], 0.95) == 0.0
    assert quant.historical_cvar([NAN, NAN], 0.95) == 0.0
    assert quant.kelly_fraction(0.9, 0.0) == 0.0
    assert quant.vol_target_weight(1.0, NAN, 0.15, 1.0) == 0.0
    assert quant.vol_target_weight(1.0, 0.0, 0.15, 1.0) == 0.0
    assert quant.vol_target_weight(-1.0, 0.05, 0.15, 1.0) == -1.0     # capped at leverage
    assert quant.position_units(1e5, 0.01, 50.0, 50.0) == 0.0         # stop at entry


def test_var_is_positive_loss_even_when_all_returns_positive():
    assert quant.historical_var([0.01, 0.02, 0.03]) == 0.0


# --------------------------------------------------------------- backtest
def test_nan_weights_are_flat_and_leverage_clipped():
    r = quant.run_backtest([100, 110, 121], [NAN, 3.0, 0], quant.BacktestConfig(cost_bps=0, max_leverage=1.5))
    assert list(r.positions[:2]) == [0.0, 1.5]


def test_single_bar_and_empty_backtest():
    r = quant.run_backtest([100.0], [1.0])
    assert r.metrics.periods == 0 and r.equity[0] == 100_000
    assert len(quant.run_backtest([], []).equity) == 0


@pytest.mark.parametrize("prices", [[100, 0, 101], [100, -1, 101], [100, NAN, 101]])
def test_non_positive_or_nan_prices_rejected(prices):
    with pytest.raises(ValueError):
        quant.run_backtest(prices, [1, 1, 1])


def test_extra_length_mismatch_rejected():
    with pytest.raises(ValueError):
        quant.run_backtest([100, 101, 102], [1, 1, 1], carry=[0.01, 0.01])


def test_stops_require_ohlc():
    with pytest.raises(ValueError):
        quant.run_backtest([100, 101], [1, 1], stop=[99, 99])


def test_stop_fill_gap_and_take():
    cfg = quant.BacktestConfig(cost_bps=0)
    c, o, h, l = [100, 97, 99], [100, 99, 97], [100, 100, 99], [100, 94, 96]
    r = quant.run_backtest(c, [1, 1, 1], cfg, open=o, high=h, low=l, stop=[95] * 3)
    assert r.stop_exits == 1 and r.equity[1] == pytest.approx(95_000)
    assert r.trades[-1].to_weight == 0.0 and r.trades[-1].price == 95
    r = quant.run_backtest(c, [1, 1, 1], cfg, open=[100, 90, 97], high=h, low=[100, 89, 96], stop=[95] * 3)
    assert r.equity[1] == pytest.approx(90_000)          # gapped through: filled at the open


def test_exit_costs_charged_once():
    cfg = quant.BacktestConfig(cost_bps=10)
    c = [100, 100, 100]
    r = quant.run_backtest(c, [1, 1, 1], cfg, open=c, high=c, low=[100, 90, 100], stop=[95] * 3)
    # entry 10 bps, stop loss 5 %, exit 10 bps
    assert r.equity[1] == pytest.approx(100_000 * (1 - 0.001 - 0.05 - 0.001))


def test_stop_stays_flat_without_rebalance_mask_until_target_changes():
    c = [100, 95, 95, 95, 100]
    lows = [100, 90, 95, 95, 95]
    w = [1, 1, 1, 0.5, 0.5]
    r = quant.run_backtest(c, w, quant.BacktestConfig(cost_bps=0), open=c, high=c, low=lows,
                           stop=[96, 96, 96, 80, 80])
    assert list(r.positions) == [1, 0, 0, 0.5, 0.5]


def test_carry_series_nan_is_zero():
    cfg = quant.BacktestConfig(cost_bps=0, periods_per_year=100)
    r = quant.run_backtest([1.0, 1.0, 1.0], [1, 1, 1], cfg, carry=[NAN, 0.1, 0.0])
    assert r.equity[-1] == pytest.approx(100_000 * 1.001)


def test_metrics_exposure_and_tstat():
    r = quant.run_backtest([100, 101, 100, 102, 101], [0.5, 0.5, 0, 0, 0], quant.BacktestConfig(cost_bps=0))
    m = r.metrics
    assert m.avg_exposure == pytest.approx(0.25)
    assert m.sharpe_tstat == pytest.approx(m.sharpe * np.sqrt(4 / 252))


def test_impact_is_square_root_and_charged_on_exits():
    flat = np.full(4, 100.0)
    cfg = quant.BacktestConfig(cost_bps=0.0)
    r = quant.run_backtest(flat, np.ones(4), cfg, impact=np.full(4, 0.01))
    assert r.equity[1] == pytest.approx(100000 * 0.99) and r.equity[-1] == pytest.approx(r.equity[1])
    assert r.impact_paid == pytest.approx(0.01)
    half = quant.run_backtest(flat, np.full(4, 0.5), cfg, impact=np.full(4, 0.01))
    assert half.equity[1] == pytest.approx(100000 * (1 - 0.5 ** 1.5 * 0.01))   # concave in size
    stopped = quant.run_backtest(flat, np.ones(4), cfg, open=flat, high=flat,
                                 low=np.array([100, 90, 100, 100.0]), stop=np.full(4, 95.0),
                                 impact=np.array([0.0, 0.02, 0.0, 0.0]))
    assert stopped.stop_exits == 1 and stopped.impact_paid == pytest.approx(0.02)
    none = quant.run_backtest(flat, np.ones(4), cfg, impact=np.full(4, NAN))
    assert none.impact_paid == 0.0 and none.equity[-1] == pytest.approx(100000.0)
    with pytest.raises(ValueError):
        quant.run_backtest(flat, np.ones(4), cfg, impact=np.full(3, 0.01))


# ------------------------------------------------ randomised cross-check
@pytest.mark.skipif(quant.BACKEND != "cpp", reason="C++ extension not built")
@pytest.mark.parametrize("seed", range(8))
def test_cpp_matches_python_extended_backtest(seed):
    rng = np.random.default_rng(seed)
    n = 300
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    o = c * np.exp(rng.normal(0, 0.004, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n)))
    w = np.round(rng.uniform(-1.2, 1.2, n) * (rng.random(n) > 0.8), 2)
    w = np.where(rng.random(n) > 0.95, NAN, w)
    stop = np.where(w > 0, c * 0.98, c * 1.02)
    take = np.where(w > 0, c * 1.03, c * 0.97)
    stop[rng.random(n) > 0.7] = NAN
    reb = (rng.random(n) > 0.8).astype(float)
    carry = rng.normal(0.01, 0.02, n)
    impact = np.abs(rng.normal(0.002, 0.001, n))
    impact[rng.random(n) > 0.9] = NAN
    cfg = quant.BacktestConfig(cost_bps=1.5, slippage_bps=0.5, borrow_annual=0.02,
                               allow_short=bool(seed % 2), max_leverage=1.0)
    kw = dict(carry=carry, open=o, high=h, low=l, stop=stop, take=take, rebalance=reb,
              impact=impact)
    rc = quant.run_backtest(c, w, cfg, **kw)
    rp = pycore.run_backtest_ex(c, w, cfg, **kw)
    np.testing.assert_allclose(rc.equity, rp.equity, rtol=1e-11)
    np.testing.assert_array_equal(rc.positions, rp.positions)
    assert rc.stop_exits == rp.stop_exits and len(rc.trades) == len(rp.trades)
    assert rc.impact_paid == pytest.approx(rp.impact_paid, rel=1e-11) and rc.impact_paid > 0
    for f in ("sharpe", "sharpe_tstat", "avg_exposure", "max_drawdown", "turnover"):
        assert getattr(rc.metrics, f) == pytest.approx(getattr(rp.metrics, f), rel=1e-9, abs=1e-12)
