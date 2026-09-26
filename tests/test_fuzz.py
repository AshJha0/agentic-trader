"""Property-based fuzzing of the Python <-> C++ boundary with hypothesis.

Two properties for every quant-core entry point, on arbitrary (NaN, inf, empty,
huge, tiny) inputs:

1. it either returns a well-formed result or raises ``ValueError`` -- never a
   crash, a hang, or any other exception type crossing the pybind11 boundary;
2. when the compiled extension is active, the C++ result equals the numpy twin's
   (NaN positions included).
"""
import numpy as np
import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # noqa: E402
from hypothesis.extra import numpy as hnp  # noqa: E402

from agentic_trader import quant  # noqa: E402
from agentic_trader.quant import pycore  # noqa: E402

FUZZ = settings(max_examples=60, deadline=None)
# "wild" inputs (NaN, +-inf, 1e300, subnormals) only have to be survived; "sane" inputs
# (finite, |x| <= 1e6, NaN allowed) must also give the same numbers on both backends.
# Beyond ~2^53 the running-window sum (C++) and the masked cumulative sum (numpy) lose
# precision differently, which is a property of float64, not a bug in either.
floats = st.floats(allow_nan=True, allow_infinity=True, width=64)
sane = st.one_of(st.just(float("nan")), st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False))
finite_pos = st.floats(min_value=1e-3, max_value=1e6, allow_nan=False, allow_infinity=False)
arrays = hnp.arrays(np.float64, st.integers(0, 60), elements=floats)
sane_arrays = hnp.arrays(np.float64, st.integers(0, 60), elements=sane)
windows = st.integers(min_value=-2, max_value=70)


def _same(a, b, scale: float = 1.0):
    a, b = np.asarray(a, float), np.asarray(b, float)
    assert a.shape == b.shape
    np.testing.assert_allclose(a, b, rtol=1e-9, atol=1e-9 * max(1.0, scale), equal_nan=True)


def _scale(*xs) -> float:
    vals = np.concatenate([np.asarray(x, float).ravel() for x in xs]) if xs else np.zeros(1)
    finite = vals[np.isfinite(vals)]
    return float(np.abs(finite).max()) if finite.size else 1.0


def _run(fn, *args):
    """Call and return (result, error) where error is None or a ValueError."""
    try:
        return fn(*args), None
    except ValueError as e:
        return None, e


WINDOWED = ["sma", "ema", "rolling_std", "zscore", "rsi", "rolling_max", "rolling_min"]


@pytest.mark.parametrize("name", WINDOWED)
@given(x=arrays, n=windows)
@FUZZ
def test_windowed_indicators_survive_wild_input(name, x, n):
    out, err = _run(getattr(quant, name), x, n)
    ref, ref_err = _run(getattr(pycore, name), x, n)
    assert (err is None) == (ref_err is None)          # both accept or both refuse
    if err is None:
        assert len(out) == len(x) == len(ref)


@pytest.mark.parametrize("name", WINDOWED)
@given(x=sane_arrays, n=st.integers(1, 70))
@FUZZ
def test_windowed_indicators_backends_agree(name, x, n):
    if quant.BACKEND != "cpp":
        pytest.skip("C++ extension not built")
    _same(getattr(quant, name)(x, n), getattr(pycore, name)(x, n), _scale(x))


@given(x=arrays)
@FUZZ
def test_pct_change_macd_bollinger_survive(x):
    out, err = _run(quant.pct_change, x)
    assert err is None and len(out) == len(x)
    for fn in (quant.macd, quant.bollinger):
        res, err = _run(fn, x)
        if err is None:
            assert all(len(r) == len(x) for r in res)


@given(x=sane_arrays)
@FUZZ
def test_pct_change_macd_backends_agree(x):
    if quant.BACKEND != "cpp":
        pytest.skip("C++ extension not built")
    s = _scale(x)
    _same(quant.pct_change(x), pycore.pct_change(x), s)
    for a, b in zip(quant.macd(x), pycore.macd(x)):
        _same(a, b, s)


@given(n=st.integers(0, 40), data=st.data())
@FUZZ
def test_ohlc_indicators(n, data):
    h = data.draw(hnp.arrays(np.float64, n, elements=sane))
    l = data.draw(hnp.arrays(np.float64, n, elements=sane))
    c = data.draw(hnp.arrays(np.float64, n, elements=sane))
    w = data.draw(st.integers(-1, 30))
    for fn in (quant.atr, quant.kdj):
        out, err = _run(fn, h, l, c, w)
        ref, ref_err = _run(getattr(pycore, fn.__name__), h, l, c, w)
        assert (err is None) == (ref_err is None)
        if err is None and quant.BACKEND == "cpp":
            s = _scale(h, l, c)
            if isinstance(out, tuple):
                for a, b in zip(out, ref):
                    _same(a, b, s)
            else:
                _same(out, ref, s)
    # mismatched lengths are always a ValueError
    with pytest.raises(ValueError):
        quant.atr(np.ones(3), np.ones(2), np.ones(3), 2)


@given(x=arrays, y=arrays, q=st.one_of(st.just(float("nan")), st.floats(-1, 2)))
@FUZZ
def test_scalar_functions_survive_wild_input(x, y, q):
    for fn, args in ((quant.quantile, (x, q)), (quant.historical_var, (x, 0.95)),
                     (quant.historical_cvar, (x, 0.95)), (quant.max_drawdown, (x,))):
        out, err = _run(fn, *args)
        ref, ref_err = _run(getattr(pycore, fn.__name__), *args)
        assert (err is None) == (ref_err is None)
        if err is None:
            assert isinstance(out, float)
    if len(x) == len(y):
        out, err = _run(quant.spearman, x, y)
        assert err is None and isinstance(out, float)
    else:
        with pytest.raises(ValueError):
            quant.spearman(x, y)


@given(x=sane_arrays, y=sane_arrays, q=st.floats(0, 1))
@FUZZ
def test_scalar_functions_backends_agree(x, y, q):
    if quant.BACKEND != "cpp":
        pytest.skip("C++ extension not built")
    s = _scale(x)
    for fn, args in ((quant.quantile, (x, q)), (quant.historical_var, (x, 0.95)),
                     (quant.historical_cvar, (x, 0.95)), (quant.max_drawdown, (x,))):
        out, ref = fn(*args), getattr(pycore, fn.__name__)(*args)
        assert (np.isnan(out) and np.isnan(ref)) or out == pytest.approx(ref, rel=1e-9, abs=1e-9 * max(1.0, s))
    if len(x) == len(y):
        out, ref = quant.spearman(x, y), pycore.spearman(x, y)
        assert (np.isnan(out) and np.isnan(ref)) or out == pytest.approx(ref, rel=1e-9, abs=1e-9)


@given(n=st.integers(0, 80), data=st.data())
@FUZZ
def test_backtester_never_crashes_and_stays_bounded(n, data):
    prices = data.draw(hnp.arrays(np.float64, n, elements=finite_pos))
    weights = data.draw(hnp.arrays(np.float64, n, elements=floats))
    impact = data.draw(hnp.arrays(np.float64, n, elements=st.one_of(st.just(float("nan")), st.floats(0, 0.05))))
    cfg = quant.BacktestConfig(cost_bps=data.draw(st.floats(0, 50)), slippage_bps=data.draw(st.floats(0, 50)),
                               max_leverage=data.draw(st.floats(0.1, 3.0)),
                               allow_short=data.draw(st.booleans()),
                               borrow_annual=data.draw(st.floats(0, 0.2)))
    r = quant.run_backtest(prices, weights, cfg, impact=impact)
    assert len(r.equity) == len(r.returns) == len(r.positions) == n
    assert np.all(np.isfinite(r.equity)) and np.all(np.abs(r.positions) <= cfg.max_leverage + 1e-12)
    if not cfg.allow_short:
        assert np.all(r.positions >= 0)
    assert r.impact_paid >= 0
    if quant.BACKEND == "cpp":
        ref = pycore.run_backtest_ex(prices, weights, cfg, impact=impact)
        _same(r.equity, ref.equity)
        _same(r.positions, ref.positions)
        assert r.impact_paid == pytest.approx(ref.impact_paid, rel=1e-9, abs=1e-15)


@given(n=st.integers(1, 30), data=st.data())
@FUZZ
def test_backtester_rejects_bad_prices_and_lengths(n, data):
    bad = data.draw(hnp.arrays(np.float64, n, elements=st.one_of(
        st.just(float("nan")), st.just(float("inf")), st.floats(max_value=0.0, allow_nan=False))))
    with pytest.raises(ValueError):
        quant.run_backtest(bad, np.ones(n))
    with pytest.raises(ValueError):
        quant.run_backtest(np.ones(n), np.ones(n + 1))
    with pytest.raises(ValueError):
        quant.run_backtest(np.ones(n), np.ones(n), carry=np.ones(n + 1))
