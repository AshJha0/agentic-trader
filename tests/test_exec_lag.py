"""Execution lag and next-open fills (v0.17 lane L2, review finding Q1 / A1).

``BacktestConfig.exec_lag`` executes the target decided at bar t at bar t+k, and
``fill_next_open`` fills it at open[t+1]. Lag 0 with close fills must reproduce the old
engine exactly; lag k must equal shifting every decision-tied input by k; and a signal that
peeks one bar ahead must stop earning at lag 1.
"""
from __future__ import annotations

import hashlib

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


def test_lag0_is_bit_identical_to_old_engine():
    assert _sha(_run(pycore, _inputs(), _cfg())) == OLD_ENGINE_SHA


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
    with pytest.raises(ValueError, match="stop/take"):
        pycore.run_backtest_ex(p, np.ones(5), BacktestConfig(fill_next_open=True), open=p, high=p, low=p,
                               stop=p * 0.9)


@pytest.mark.skipif(quant.BACKEND != "cpp", reason="C++ extension not built")
@pytest.mark.parametrize("k,next_open", [(0, False), (1, False), (3, False), (0, True), (2, True)])
def test_cpp_matches_numpy(k, next_open):
    d = _inputs()
    cfg = _cfg(exec_lag=k, fill_next_open=next_open)
    a = _run(pycore, d, cfg, levels=not next_open)
    b = _run(quant, d, cfg, levels=not next_open)
    for attr in ("equity", "positions", "traded", "exits", "returns"):
        np.testing.assert_allclose(getattr(a, attr), getattr(b, attr), rtol=1e-12, atol=1e-12)
    assert [(t.index, t.price) for t in a.trades] == [(t.index, t.price) for t in b.trades]


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
