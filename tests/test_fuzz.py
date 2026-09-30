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


def _positions_respect_cap_and_drift(r, prices, cfg):
    """v0.8 (constant units between decisions): the leverage cap and the short-sale flag bind on
    every bar where a trade was executed; on a hold bar the weight is the previous weight
    drifted by the bar's price move and total return, and it never changes sign."""
    p = np.asarray(prices, float)
    traded = r.traded != 0
    assert np.all(np.abs(r.positions[traded]) <= cfg.max_leverage + 1e-12)
    if not cfg.allow_short:
        assert np.all(r.positions >= 0)
    for t in range(2, len(p)):
        # two consecutive hold bars: returns[t] is then the gross return (no fee in it)
        if traded[t] or traded[t - 1] or r.exits[t] or r.positions[t - 1] == 0.0 or r.equity[t] <= 0:
            continue
        drift = r.positions[t - 1] * (p[t] / p[t - 1]) / (1.0 + r.returns[t])  # the engine's own ops
        assert r.positions[t] == pytest.approx(drift, rel=1e-9, abs=1e-12)


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
    assert np.all(np.isfinite(r.equity)) and np.all(r.equity >= 0)
    _positions_respect_cap_and_drift(r, prices, cfg)
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


# ------------------------------------------------------------------------------------
# Every optional per-bar input of run_backtest (finding 57). The contract in
# quant/__init__.py: same length as prices; stop/take need open/high/low; NaN means
# "none" for stop, take, impact and carry. Bar ranges must be usable prices (positive,
# finite) and rates/coefficients/levels must be finite or NaN -- anything else must be a
# ValueError, never inf/NaN equity or a NaN Sharpe.
OPTIONAL = ("carry", "open", "high", "low", "stop", "take", "rebalance", "impact")
ratio = st.floats(0.5, 2.0, allow_nan=False, allow_infinity=False)


def _optional_inputs(n, prices, data):
    """A full set of well-formed optional inputs, drawn around ``prices``."""
    r = lambda: data.draw(hnp.arrays(np.float64, n, elements=ratio))                        # noqa: E731
    mask = lambda: data.draw(hnp.arrays(np.bool_, n))                                       # noqa: E731
    open_ = prices * r()
    high = np.maximum.reduce([open_, prices, prices * r()])
    low = np.minimum.reduce([open_, prices, prices * r()])
    stop = np.where(mask(), prices * r(), np.nan)
    take = np.where(mask(), prices * r(), np.nan)
    rebalance = mask().astype(float)
    carry = np.where(mask(), data.draw(hnp.arrays(np.float64, n, elements=st.floats(-1.0, 1.0))), np.nan)
    impact = np.where(mask(), data.draw(hnp.arrays(np.float64, n, elements=st.floats(0, 0.05))), np.nan)
    return dict(carry=carry, open=open_, high=high, low=low, stop=stop, take=take,
                rebalance=rebalance, impact=impact)


def _metrics_finite(m) -> bool:
    # annualized_return (and so calmar) is +inf, not NaN, when a one-bar gain is too large to
    # annualise in float64 (e.g. 1 -> 17 over one of 252 periods is 17**252); documented in pycore.
    return all(np.isfinite(getattr(m, f)) for f in ("cumulative_return", "annualized_vol",
                                                   "sharpe", "sortino", "max_drawdown", "win_rate",
                                                   "turnover", "avg_exposure", "sharpe_tstat")) \
        and not any(np.isnan(getattr(m, f)) for f in ("annualized_return", "calmar"))


@given(n=st.integers(0, 80), data=st.data())
@FUZZ
def test_backtester_with_every_optional_input_is_finite_and_backends_agree(n, data):
    prices = data.draw(hnp.arrays(np.float64, n, elements=finite_pos))
    weights = data.draw(hnp.arrays(np.float64, n, elements=floats))
    extras = _optional_inputs(n, prices, data)
    # each optional input may also be left out; stop/take only together with the bar ranges
    for name in OPTIONAL:
        if data.draw(st.booleans(), label=f"drop {name}"):
            extras[name] = None
    if extras["stop"] is not None or extras["take"] is not None:
        for k in ("open", "high", "low"):
            if extras[k] is None:
                extras[k] = prices.copy()
    cfg = quant.BacktestConfig(cost_bps=data.draw(st.floats(0, 50)), slippage_bps=data.draw(st.floats(0, 50)),
                               max_leverage=data.draw(st.floats(0.1, 3.0)), allow_short=data.draw(st.booleans()),
                               borrow_annual=data.draw(st.floats(0, 0.2)), carry_annual=data.draw(st.floats(-0.2, 0.2)))
    r = quant.run_backtest(prices, weights, cfg, **extras)
    assert len(r.equity) == len(r.returns) == len(r.positions) == n
    assert np.all(np.isfinite(r.equity)) and np.all(np.isfinite(r.returns))
    assert _metrics_finite(r.metrics)
    _positions_respect_cap_and_drift(r, prices, cfg)
    assert r.impact_paid >= 0 and np.isfinite(r.impact_paid)
    levels = np.zeros(n, bool)                          # bars on which some protective level was armed
    for k in ("stop", "take"):
        if extras[k] is not None:
            levels |= ~np.isnan(extras[k])
    assert 0 <= r.stop_exits <= int(levels.sum())
    if quant.BACKEND == "cpp":
        ref = pycore.run_backtest_ex(prices, weights, cfg, **extras)
        _same(r.equity, ref.equity, _scale(r.equity))
        _same(r.returns, ref.returns, _scale(r.returns))
        _same(r.positions, ref.positions)
        assert r.stop_exits == ref.stop_exits
        assert r.impact_paid == pytest.approx(ref.impact_paid, rel=1e-9, abs=1e-15)
        for f in ("sharpe", "max_drawdown", "cumulative_return", "turnover"):
            assert getattr(r.metrics, f) == pytest.approx(getattr(ref.metrics, f), rel=1e-9, abs=1e-9)


def _ohlc(n):
    p = np.full(n, 100.0)
    return p, dict(open=p.copy(), high=p * 1.01, low=p * 0.99)


@pytest.mark.parametrize("name", OPTIONAL)
def test_backtester_rejects_length_mismatch_of_every_optional_input(name):
    p, ohlc = _ohlc(5)
    kw = dict(ohlc) if name in ("stop", "take") else {}
    kw[name] = np.ones(6)
    with pytest.raises(ValueError):
        quant.run_backtest(p, np.ones(5), **kw)
    with pytest.raises(ValueError):
        pycore.run_backtest_ex(p, np.ones(5), quant.BacktestConfig(), **kw)
    with pytest.raises(ValueError):                    # levels without bar ranges
        quant.run_backtest(p, np.ones(5), stop=np.full(5, 95.0))


_INF, _NINF, _NAN = float("inf"), float("-inf"), float("nan")
BAD_VALUES = [pytest.param(name, bad, id=f"{name}={bad}")
              for name, bads in (("open", (_NAN, _INF, _NINF, 0.0, -1.0)), ("high", (_NAN, _INF, _NINF, 0.0, -1.0)),
                                 ("low", (_NAN, _INF, _NINF, 0.0, -1.0)), ("stop", (_INF, _NINF)),
                                 ("take", (_INF, _NINF)), ("carry", (_INF, _NINF)), ("impact", (_INF, _NINF, -1.0)),
                                 ("rebalance", (_NAN, _INF)), ("cash_rate", (_INF, _NINF)))
              for bad in bads]


@pytest.mark.parametrize("name,bad", BAD_VALUES)
def test_backtester_rejects_non_finite_or_non_positive_optional_input(name, bad):
    """Before v0.8: open=-inf, carry=+-inf and impact=+-inf gave inf/NaN equity on both backends
    (C++ and numpy even disagreed on the drawdown for carry=+inf); the others were silently
    accepted. pycore.validate_backtest_inputs now rejects all of them on both backends."""
    n = 6
    p, ohlc = _ohlc(n)
    w = np.full(n, 0.5)
    kw = dict(ohlc)
    if name in ("open", "high", "low"):
        kw[name][2] = bad
        kw["stop"] = np.full(n, 90.0)
    elif name in ("stop", "take"):
        kw[name] = np.full(n, np.nan)
        kw[name][2] = bad
    else:
        kw = {name: np.where(np.arange(n) == 2, bad, 0.0)}
    with pytest.raises(ValueError):
        quant.run_backtest(p, w, quant.BacktestConfig(), **kw)
    with pytest.raises(ValueError):
        pycore.run_backtest_ex(p, w, quant.BacktestConfig(), **kw)


def test_backtester_rejects_multidimensional_optional_input():
    """A 2-D array is not a per-bar series and must be a ValueError on both backends. Before
    v0.8 the C++ path raised pybind11's TypeError (a non-ValueError crossing the boundary,
    against this module's first property) and the numpy path accepted a (T, 1) column for
    open/high/low silently; the shared validator now rejects every case, checked as one set."""
    p, ohlc = _ohlc(4)
    violations = []
    for name in OPTIONAL:
        for shape in ((4, 1), (2, 2)):
            kw = dict(ohlc) if name in ("stop", "take") else {}
            kw[name] = np.ones(shape)
            for label, fn in (("active", quant.run_backtest), ("numpy", pycore.run_backtest_ex)):
                try:
                    fn(p, np.ones(4), quant.BacktestConfig(), **kw)
                    violations.append(f"{label} {name}{shape}: accepted")
                except ValueError:
                    pass
                except Exception as e:                                  # noqa: BLE001
                    violations.append(f"{label} {name}{shape}: {type(e).__name__}")
    assert not violations, violations


@given(x=arrays, hs=st.lists(st.integers(-1, 40), max_size=4), skip=st.integers(-1, 5), short=st.booleans())
@FUZZ
def test_tsmom_survives_wild_input_and_backends_agree(x, hs, skip, short):
    out, err = _run(quant.strat_tsmom, x, hs, skip, short)
    ok = bool(hs) and min(hs) >= 1 and 0 <= skip < min(hs)
    assert (err is None) == ok                          # refused exactly when the arguments are bad
    if err is None:
        assert len(out) == len(x) and np.all(np.abs(out) <= 1.0)
        assert short or np.all(out >= 0.0)
        assert not np.any(out[:max(hs)])                # flat until the longest horizon exists
        _same(out, pycore.strat_tsmom(x, hs, skip, short))


CLOSE_STRATEGIES = {"strat_buy_hold": (), "strat_sma_cross": (3, 7, True), "strat_macd": (3, 6, 2, True),
                    "strat_zmr": (5, 1.0, 0.0, True)}


@pytest.mark.parametrize("name", sorted(CLOSE_STRATEGIES))
@given(x=arrays)
@FUZZ
def test_close_strategies_survive_wild_input(name, x):
    args = CLOSE_STRATEGIES[name]
    out, err = _run(getattr(quant, name), x, *args)
    ref, ref_err = _run(getattr(pycore, name), x, *args)
    assert (err is None) == (ref_err is None)
    if err is None:
        assert len(out) == len(x) == len(ref) and set(np.unique(out)) <= {-1.0, 0.0, 1.0}


@pytest.mark.parametrize("name", sorted(CLOSE_STRATEGIES))
@given(x=hnp.arrays(np.float64, st.integers(0, 60), elements=finite_pos))
@FUZZ
def test_close_strategies_backends_agree_on_prices(name, x):
    if quant.BACKEND != "cpp":
        pytest.skip("C++ extension not built")
    args = CLOSE_STRATEGIES[name]
    _same(getattr(quant, name)(x, *args), getattr(pycore, name)(x, *args))


@given(n=st.integers(0, 60), data=st.data())
@FUZZ
def test_kdj_rsi_strategy_survives_and_backends_agree(n, data):
    c = data.draw(hnp.arrays(np.float64, n, elements=finite_pos))
    spread = data.draw(hnp.arrays(np.float64, n, elements=st.floats(0.0, 0.05)))
    h, l = c * (1 + spread), c * (1 - spread)
    out = quant.strat_kdj_rsi(h, l, c, 5, 5, 30.0, 70.0, True)
    assert len(out) == n and set(np.unique(out)) <= {-1.0, 0.0, 1.0}
    _same(out, pycore.strat_kdj_rsi(h, l, c, 5, 5, 30.0, 70.0, True))


def _close(a, b, scale: float = 1.0) -> bool:
    return (np.isnan(a) and np.isnan(b)) or a == pytest.approx(b, rel=1e-9, abs=1e-9 * max(1.0, scale))


@given(x=hnp.arrays(np.float64, st.integers(0, 60), elements=finite_pos), n=windows)
@FUZZ
def test_realized_vol_survives_and_backends_agree(x, n):
    out, err = _run(quant.realized_vol, x, n, 252.0)
    ref, ref_err = _run(pycore.realized_vol, x, n, 252.0)
    assert (err is None) == (ref_err is None) == (n >= 1)
    if err is None:
        assert len(out) == len(x)
        _same(out, ref, _scale(ref))


@given(total=st.floats(-1e6, 1e6), n=st.integers(-2, 40), kappa=st.one_of(floats, st.floats(0, 800)))
@FUZZ
def test_almgren_chriss_survives_and_backends_agree(total, n, kappa):
    out, err = _run(quant.almgren_chriss, total, n, kappa)
    ok = n >= 1 and np.isfinite(kappa) and kappa >= 0
    assert (err is None) == ok
    if err is None:
        assert len(out) == n and np.all(np.isfinite(out))
        assert float(np.sum(out)) == pytest.approx(total, rel=1e-9, abs=1e-6)     # the slices add up to the order
        _same(out, pycore.almgren_chriss(total, n, kappa), abs(total))


fin = st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False)


@given(p=st.floats(0, 1), b=fin, sig=st.floats(-1, 1), vol=st.one_of(st.just(float("nan")), fin),
       tv=st.floats(0, 1), lev=st.floats(0, 10), eq=fin, rf=st.floats(0, 1), entry=fin, stop=fin)
@FUZZ
def test_sizing_functions_survive_and_backends_agree(p, b, sig, vol, tv, lev, eq, rf, entry, stop):
    for fn, args in ((quant.kelly_fraction, (p, b)), (quant.vol_target_weight, (sig, vol, tv, lev)),
                     (quant.position_units, (eq, rf, entry, stop))):
        out, ref = fn(*args), getattr(pycore, fn.__name__)(*args)
        assert isinstance(out, float) and _close(out, ref, abs(ref) if np.isfinite(ref) else 1.0)
    assert abs(quant.vol_target_weight(sig, vol, tv, lev)) <= lev


@given(n=st.integers(2, 60), data=st.data())
@FUZZ
def test_compute_metrics_survives_and_backends_agree(n, data):
    eq = data.draw(hnp.arrays(np.float64, n, elements=st.floats(1.0, 1e6)))
    pos = data.draw(hnp.arrays(np.float64, n, elements=st.floats(-1, 1)))
    traded = np.abs(np.diff(pos, prepend=0.0))
    a = quant.compute_metrics(eq, pos, 252.0, 0.02, traded)
    b = pycore.compute_metrics(eq, pos, 252.0, 0.02, traded)
    assert _metrics_finite(a)
    for field in ("cumulative_return", "max_drawdown", "sharpe", "annualized_vol"):
        assert _close(getattr(a, field), getattr(b, field), abs(getattr(b, field)))
    assert a.num_trades == b.num_trades
