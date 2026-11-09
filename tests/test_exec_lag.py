"""Execution lag and next-open fills (v0.17 lane L2, review finding Q1 / A1).

``BacktestConfig.exec_lag`` executes the target decided at bar t at bar t+k, and
``fill_next_open`` fills it at open[t+1]. Lag 0 with close fills must reproduce the old
engine exactly; lag k must equal shifting every decision-tied input by k; and a signal that
peeks one bar ahead must stop earning at lag 1.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from agentic_trader import quant
from agentic_trader.quant import pycore
from agentic_trader.quant.pycore import BacktestConfig

# sha256 of (equity, positions, traded, exits) for _case() produced by the engine at commit
# ae26242, before exec_lag existed. Lag 0 must stay bit-identical to it.
OLD_ENGINE_SHA = "c654ae934a484e68369eae22ea17df43669ea88a72e9d168a0a659260eb12d67"


def _inputs(T: int = 300, seed: int = 7):
    rng = np.random.default_rng(seed)
    p = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, T)))
    o = p * np.exp(rng.normal(0, 0.005, T))
    h = np.maximum(p, o) * 1.01
    lo = np.minimum(p, o) * 0.99
    w = np.clip(np.round(rng.normal(0, 0.8, T), 1), -1.5, 1.5)
    w[::7] = np.nan
    stop = np.where(w > 0, p * 0.97, p * 1.03)
    take = np.where(w > 0, p * 1.05, p * 0.95)
    reb = (rng.random(T) < 0.3).astype(float)
    return dict(p=p, o=o, h=h, l=lo, w=w, stop=stop, take=take, reb=reb,
                imp=np.full(T, 0.001), car=np.full(T, 0.01), cash=np.full(T, 0.02))


def _cfg(**kw) -> BacktestConfig:
    return BacktestConfig(cost_bps=2.0, slippage_bps=1.0, borrow_annual=0.01, max_leverage=1.2, **kw)


def _run(engine, d, cfg, *, levels=True, w=None, stop=None, take=None, reb=None):
    w = d["w"] if w is None else w
    kw = dict(carry=d["car"], open=d["o"], high=d["h"], low=d["l"], rebalance=d["reb"] if reb is None else reb,
              impact=d["imp"], cash_rate=d["cash"])
    if levels:
        kw.update(stop=d["stop"] if stop is None else stop, take=d["take"] if take is None else take)
    if engine is quant:
        return quant.run_backtest(d["p"], w, cfg, **kw)
    return pycore.run_backtest_ex(d["p"], w, cfg, **kw)


def _sha(r) -> str:
    return hashlib.sha256(np.concatenate([r.equity, r.positions, r.traded, r.exits]).tobytes()).hexdigest()


def _shift(a, k, fill):
    out = np.full_like(a, fill)
    out[k:] = a[:a.size - k]
    return out


GOLDEN = Path(__file__).parent / "data" / "exec_lag_old_engine.npz"


def test_lag0_is_bit_identical_to_old_engine():
    # The golden arrays are the pre-exec_lag engine's output (ae26242), saved on the machine where
    # their SHA-256 equalled OLD_ENGINE_SHA. The inputs come from np.exp/cumsum, whose last bit
    # differs across platforms and BLAS builds, so CI compares within 1e-12 instead of by hash;
    # the hash is still checked where it is reproducible.
    r = _run(pycore, _inputs(), _cfg())
    g = np.load(GOLDEN)
    for name in ("equity", "positions", "traded", "exits"):
        np.testing.assert_allclose(getattr(r, name), g[name], rtol=1e-12, atol=1e-12, err_msg=name)
    exact = all(np.array_equal(getattr(r, n), g[n]) for n in ("equity", "positions", "traded", "exits"))
    if exact:
        assert _sha(r) == OLD_ENGINE_SHA


@pytest.mark.parametrize("k", [1, 2, 5])
def test_lag_k_equals_shifting_decisions(k):
    d = _inputs()
    lagged = _run(pycore, d, _cfg(exec_lag=k))
    shifted = _run(pycore, d, _cfg(), w=_shift(d["w"], k, np.nan), stop=_shift(d["stop"], k, np.nan),
                   take=_shift(d["take"], k, np.nan), reb=_shift(d["reb"], k, 0.0))
    for a in ("equity", "positions", "traded", "exits", "returns"):
        np.testing.assert_array_equal(getattr(lagged, a), getattr(shifted, a))
    assert [(t.index, t.price) for t in lagged.trades] == [(t.index, t.price) for t in shifted.trades]


def test_peeking_signal_stops_earning_at_lag1():
    rng = np.random.default_rng(1)
    p = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 2000)))
    w = np.append(np.sign(np.diff(p)), 0.0)  # w[t] = sign(r[t+1]): pure look-ahead
    cfg0 = BacktestConfig(cost_bps=0.0)
    s0 = pycore.run_backtest_ex(p, w, cfg0).metrics.sharpe
    s1 = pycore.run_backtest_ex(p, w, BacktestConfig(cost_bps=0.0, exec_lag=1)).metrics.sharpe
    assert s0 > 10
    assert abs(s1) < 1.5


def test_next_open_hand_example():
    p = np.array([100.0, 110.0, 121.0])
    o = np.array([100.0, 105.0, 120.0])
    r = pycore.run_backtest_ex(p, np.ones(3), BacktestConfig(cost_bps=0.0, fill_next_open=True), open=o)
    np.testing.assert_allclose(r.equity, 100_000 * np.array([1.0, 110 / 105, 121 / 105]), rtol=1e-14)
    assert [(t.index, t.price) for t in r.trades] == [(1, 105.0)]
    assert r.traded.tolist() == [0.0, 1.0, 0.0]


def _levels_case():
    p = np.array([100.0, 110.0, 121.0, 121.0])
    o = np.array([100.0, 105.0, 100.0, 121.0])
    return p, o, np.maximum(p, o), np.minimum(p, o)


def test_next_open_with_stop_inside_the_entry_bar():
    # Enter at open[1]=105; bar 1 trades down to 99 through the stop at 100: exit at the stop.
    p, o, h, lo = _levels_case()
    lo[1] = 99.0
    stop = np.array([100.0, 100.0, 100.0, 100.0])
    r = pycore.run_backtest_ex(p, np.ones(4), BacktestConfig(cost_bps=0.0, fill_next_open=True),
                               open=o, high=h, low=lo, stop=stop)
    np.testing.assert_allclose(r.equity, 100_000 * np.array([1.0, 100 / 105, 100 / 105, 100 / 105]), rtol=1e-14)
    assert [(t.index, t.price) for t in r.trades] == [(1, 105.0), (1, 100.0)]
    assert r.exits.tolist() == [0.0, 1.0, 0.0, 0.0]
    assert r.positions.tolist() == [1.0, 0.0, 0.0, 0.0]


def test_next_open_stop_gapped_through_exits_at_the_open():
    # Held long carries the overnight 110 -> 100 gap, then the stop at 104 (already through the
    # open) exits at the open: no intrabar move is booked after the overnight leg.
    p, o, h, lo = _levels_case()
    stop = np.array([90.0, 104.0, 104.0, 104.0])
    r = pycore.run_backtest_ex(p, np.ones(4), BacktestConfig(cost_bps=0.0, fill_next_open=True),
                               open=o, high=h, low=lo, stop=stop)
    np.testing.assert_allclose(r.equity, 100_000 * np.array([1.0, 110 / 105, 100 / 105, 100 / 105]), rtol=1e-14)
    assert r.trades[-1].index == 2 and r.trades[-1].price == 100.0
    assert r.exits.tolist() == [0.0, 0.0, 1.0, 0.0]


def test_next_open_take_profit_and_stop_slippage():
    p, o, h, lo = _levels_case()
    take = np.full(4, 115.0)
    r = pycore.run_backtest_ex(p, np.ones(4), BacktestConfig(cost_bps=0.0, fill_next_open=True),
                               open=o, high=h, low=lo, take=take)
    np.testing.assert_allclose(r.equity[-1], 100_000 * 115 / 105, rtol=1e-14)
    # Slippage on a gapped stop: open less the half spread (floored at the low).
    stop = np.array([90.0, 104.0, 104.0, 104.0])
    lo[2] = 99.0
    r = pycore.run_backtest_ex(p, np.ones(4), BacktestConfig(cost_bps=0.0, fill_next_open=True,
                                                            stop_half_spread=0.005),
                               open=o, high=h, low=lo, stop=stop)
    np.testing.assert_allclose(r.equity[-1], 100_000 * 110 / 105 * (100 / 110) * 0.995, rtol=1e-14)


def test_next_open_without_levels_is_unchanged_by_the_new_path():
    d = _inputs()
    cfg = _cfg(fill_next_open=True)
    a = _run(pycore, d, cfg, levels=False)
    b = _run(pycore, d, cfg, levels=True, stop=np.full_like(d["p"], np.nan), take=np.full_like(d["p"], np.nan))
    for attr in ("equity", "positions", "traded", "exits", "returns"):
        np.testing.assert_array_equal(getattr(a, attr), getattr(b, attr))


def test_next_open_overnight_belongs_to_old_position():
    # Flip from long to flat: the long earns close -> open, nothing after the open fill.
    p = np.array([100.0, 100.0, 90.0, 90.0])
    o = np.array([100.0, 100.0, 95.0, 90.0])
    w = np.array([1.0, 0.0, 0.0, 0.0])
    r = pycore.run_backtest_ex(p, w, BacktestConfig(cost_bps=0.0, fill_next_open=True), open=o)
    # bar 0: enter at open[1]=100, earn to close[1]=100; bar 1: overnight 100->95, exit at open.
    np.testing.assert_allclose(r.equity, 100_000 * np.array([1.0, 1.0, 0.95, 0.95]), rtol=1e-14)


def test_validation():
    p = np.full(5, 100.0)
    with pytest.raises(ValueError, match="exec_lag"):
        pycore.run_backtest_ex(p, np.ones(5), BacktestConfig(exec_lag=-1))
    with pytest.raises(ValueError, match="exec_lag"):
        pycore.run_backtest_ex(p, np.ones(5), BacktestConfig(exec_lag=1.5))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="needs open"):
        pycore.run_backtest_ex(p, np.ones(5), BacktestConfig(fill_next_open=True))
    # Next-open fills combine with stop/take levels (v0.18 lane A, L2): no longer an error.
    r = pycore.run_backtest_ex(p, np.ones(5), BacktestConfig(fill_next_open=True), open=p, high=p, low=p,
                               stop=p * 0.9)
    assert r.exits.sum() == 0.0


@pytest.mark.skipif(quant.BACKEND != "cpp", reason="C++ extension not built")
@pytest.mark.parametrize("k,next_open,levels,slip", [
    (0, False, True, 0.0), (1, False, True, 0.0), (3, False, True, 0.0), (0, True, False, 0.0),
    (2, True, False, 0.0), (0, True, True, 0.0), (2, True, True, 0.0), (1, True, True, 5e-4)])
def test_cpp_matches_numpy(k, next_open, levels, slip):
    d = _inputs()
    cfg = _cfg(exec_lag=k, fill_next_open=next_open, stop_half_spread=slip, stop_range_frac=slip * 100)
    a = _run(pycore, d, cfg, levels=levels)
    b = _run(quant, d, cfg, levels=levels)
    for attr in ("equity", "positions", "traded", "exits", "returns"):
        np.testing.assert_allclose(getattr(a, attr), getattr(b, attr), rtol=1e-12, atol=1e-12)
    # indices must match exactly; prices only to the last bit (platform exp/log differ)
    assert [t.index for t in a.trades] == [t.index for t in b.trades]
    np.testing.assert_allclose([t.price for t in a.trades], [t.price for t in b.trades], rtol=1e-12, atol=1e-12)


def test_config_plumbing():
    from datetime import date

    from agentic_trader.backtest import backtest_config_for
    from agentic_trader.config import make_config
    from agentic_trader.instruments import Instrument

    ins = Instrument.parse("AAPL", "equity")
    px = np.full(3, 100.0)
    base = backtest_config_for(ins, make_config(), px, None, date(2020, 1, 2))  # type: ignore[arg-type]
    assert (base.exec_lag, base.fill_next_open) == (0, False)
    cfg = make_config(backtest={"exec_lag": 1, "fill": "next_open"})
    bt = backtest_config_for(ins, cfg, px, None, date(2020, 1, 2))  # type: ignore[arg-type]
    assert (bt.exec_lag, bt.fill_next_open) == (1, True)
    with pytest.raises(ValueError, match="backtest.fill"):
        backtest_config_for(ins, make_config(backtest={"fill": "vwap"}), px, None,  # type: ignore[arg-type]
                            date(2020, 1, 2))
