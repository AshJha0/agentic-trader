"""Lane C coverage: the compiled-core dispatch glue in ``agentic_trader.quant`` (exercised
through a fake ``_cpp`` that records what it is handed and delegates to ``pycore``) and the
edge paths of ``agentic_trader.financing``."""

from __future__ import annotations

import warnings
from dataclasses import fields

import numpy as np
import pytest

from agentic_trader import financing, quant
from agentic_trader.quant import pycore


class _FakeCpp:
    """Stands in for the pybind11 module: records each call and checks the glue converted
    every array argument to ``list[float]`` before delegating to the numpy reference."""

    def __init__(self):
        self.calls: list[tuple[str, tuple, dict]] = []

    class BacktestConfig:  # mutable attribute bag, like the pybind11 struct
        pass

    def _record(self, name, args, kw):
        for a in args:
            assert not isinstance(a, np.ndarray), f"{name} got an ndarray, glue must pass lists"
        self.calls.append((name, args, kw))

    def __getattr__(self, name):
        py_fn = getattr(pycore, name)

        def fn(*args, **kw):
            self._record(name, args, kw)
            return py_fn(*args, **kw)

        return fn

    def compute_metrics(self, eq, pos, ppy, rf, tr):
        self._record("compute_metrics", (eq, pos, ppy, rf, tr), {})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return pycore.compute_metrics(eq, pos, ppy, rf, tr or None)

    def compute_metrics_rf(self, eq, pos, ppy, rf, tr):
        self._record("compute_metrics_rf", (eq, pos, ppy, rf, tr), {})
        return pycore.compute_metrics(eq, pos, ppy, rf, tr or None)

    def run_backtest_ex(self, prices, tw, c, **kw):
        self._record("run_backtest_ex", (prices, tw), kw)
        cfg = pycore.BacktestConfig(**{f.name: getattr(c, f.name) for f in fields(pycore.BacktestConfig)})
        return pycore.run_backtest_ex(prices, tw, cfg, **kw)


@pytest.fixture
def fake_cpp(monkeypatch):
    fake = _FakeCpp()
    monkeypatch.setattr(quant, "_cpp", fake)
    return fake


def _prices(n=120, seed=3):
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))


def test_series_dispatch_converts_arrays_and_returns_ndarrays(fake_cpp):
    p = _prices()
    out = quant.sma(p, 10)
    assert isinstance(out, np.ndarray)
    np.testing.assert_allclose(out, pycore.sma(p, 10), equal_nan=True)
    name, args, _ = fake_cpp.calls[-1]
    assert name == "sma" and isinstance(args[0], list) and args[1] == 10


def test_series_dispatch_tuple_outputs_are_each_ndarrays(fake_cpp):
    p = _prices()
    out = quant.macd(p)
    ref = pycore.macd(p)
    assert isinstance(out, tuple) and len(out) == len(ref)
    for o, r in zip(out, ref):
        assert isinstance(o, np.ndarray)
        np.testing.assert_allclose(o, r, equal_nan=True)


def test_series_dispatch_still_validates_window_before_the_backend(fake_cpp):
    with pytest.raises(ValueError):
        quant.sma(_prices(), 0)
    assert fake_cpp.calls == []


def test_scalar_dispatch_converts_only_the_series_arguments(fake_cpp):
    rng = np.random.default_rng(0)
    a, b = rng.normal(size=50), rng.normal(size=50)
    v = quant.spearman(a, b)
    assert isinstance(v, float)
    assert v == pytest.approx(pycore.spearman(a, b))
    q = quant.quantile(a, 0.25)
    _, args, _ = fake_cpp.calls[-1]
    assert isinstance(args[0], list) and args[1] == 0.25
    assert q == pytest.approx(pycore.quantile(a, 0.25))


def test_almgren_chriss_and_tsmom_go_through_the_backend(fake_cpp):
    np.testing.assert_allclose(quant.almgren_chriss(1000, 5, 0.3), pycore.almgren_chriss(1000, 5, 0.3))
    p = _prices()
    np.testing.assert_allclose(quant.strat_tsmom(p, [5, 20], 1, False), pycore.strat_tsmom(p, [5, 20], 1, False), equal_nan=True)
    assert [c[0] for c in fake_cpp.calls] == ["almgren_chriss", "strat_tsmom"]


@pytest.mark.parametrize("skip", [True, 1.5, -1, 5])
def test_strat_tsmom_rejects_bad_skip_before_the_backend(fake_cpp, skip):
    with pytest.raises(ValueError):
        quant.strat_tsmom(_prices(), [5, 20], skip)
    assert fake_cpp.calls == []


def test_strat_tsmom_rejects_empty_horizons():
    with pytest.raises(ValueError, match="empty"):
        quant.strat_tsmom(_prices(), [])


def test_compute_metrics_routes_rf_shapes_to_the_right_entry_point(fake_cpp):
    eq = 100.0 * np.cumprod(1 + np.r_[0.0, np.random.default_rng(1).normal(0, 0.01, 99)])
    pos = np.ones_like(eq)
    traded = np.zeros_like(eq)
    traded[0] = 1.0
    m_scalar = quant.compute_metrics(eq, pos, 252.0, 0.02, traded)
    assert fake_cpp.calls[-1][0] == "compute_metrics" and fake_cpp.calls[-1][1][3] == 0.02
    m_series = quant.compute_metrics(eq, pos, 252.0, np.full(eq.size, 0.02), traded)
    assert fake_cpp.calls[-1][0] == "compute_metrics_rf"
    assert m_series.sharpe == pytest.approx(m_scalar.sharpe)
    quant.compute_metrics(eq, pos, 252.0, np.array([]), traded)
    assert fake_cpp.calls[-1][0] == "compute_metrics" and fake_cpp.calls[-1][1][3] == 0.0
    with pytest.warns(RuntimeWarning):
        quant.compute_metrics(eq, pos, 252.0, 0.0, None)
    assert fake_cpp.calls[-1][1][4] == []


def test_run_backtest_through_backend_matches_numpy_reference(fake_cpp):
    p = _prices()
    w = np.where(np.arange(p.size) % 20 < 10, 1.0, 0.0)
    cfg = quant.BacktestConfig(cost_bps=2.0)
    got = quant.run_backtest(p, w, cfg)
    ref = pycore.run_backtest_ex(p, w, cfg)
    assert fake_cpp.calls[-1][0] == "run_backtest_ex"
    np.testing.assert_allclose(got.equity, ref.equity)
    np.testing.assert_allclose(got.traded, ref.traded)
    assert len(got.trades) == len(ref.trades) > 0
    assert got.trades[0].index == ref.trades[0].index
    assert got.ruined_at == ref.ruined_at
    assert got.metrics.sharpe == pytest.approx(ref.metrics.sharpe)


# ---- financing -------------------------------------------------------------------------------


def test_apply_financing_returns_short_results_unchanged():
    res = quant.run_backtest(np.array([100.0]), np.array([2.0]), quant.BacktestConfig(max_leverage=2.0))
    assert financing.apply_financing(res, 252.0) is res


def test_apply_financing_charges_leverage_but_not_unlevered_positions():
    p = _prices()
    cfg = quant.BacktestConfig(max_leverage=3.0, cost_bps=0.0)
    lev = quant.run_backtest(p, np.full(p.size, 2.0), cfg)
    unlev = quant.run_backtest(p, np.full(p.size, 1.0), cfg)
    f_lev = financing.apply_financing(lev, 252.0, funding_spread_bps=100.0)
    f_unlev = financing.apply_financing(unlev, 252.0, funding_spread_bps=100.0)
    np.testing.assert_allclose(f_unlev.returns, unlev.returns)
    assert f_lev.equity[-1] < lev.equity[-1]
    assert f_lev.returns[0] == lev.returns[0]  # bar 0 carries no drag


def test_apply_financing_leaves_bars_after_ruin_undrawn():
    p = _prices()
    cfg = quant.BacktestConfig(max_leverage=3.0)
    res = quant.run_backtest(p, np.full(p.size, 2.0), cfg)
    ruined = type(res)(**{**res.__dict__, "ruined_at": 50})
    out = financing.apply_financing(ruined, 252.0, funding_spread_bps=500.0)
    np.testing.assert_allclose(out.returns[51:], np.maximum(ruined.returns[51:], -1.0))
    assert not np.allclose(out.returns[1:50], ruined.returns[1:50])


def test_run_backtest_financed_with_extras_uses_cash_rate_as_rf():
    p = _prices()
    cfg = quant.BacktestConfig(max_leverage=2.0, risk_free_annual=0.05)
    cash = np.full(p.size, 0.01)
    w = np.full(p.size, 1.5)
    got = financing.run_backtest_financed(p, w, cfg, cash_rate=cash)
    base = pycore.run_backtest_ex(p, w, cfg, cash_rate=cash)
    expect = financing.apply_financing(base, cfg.periods_per_year, risk_free_annual=cash)
    np.testing.assert_allclose(got.equity, expect.equity)
    assert got.metrics.sharpe == pytest.approx(expect.metrics.sharpe)
