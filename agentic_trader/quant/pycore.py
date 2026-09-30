"""Pure-numpy reference implementation of the C++ core (cpp/src/*.cpp).

Used automatically when the compiled ``_atcore`` extension is not available.
Numerical conventions must stay identical to the C++ code; tests/test_quant.py
cross-checks the two backends whenever the extension is built. The conventions
themselves (timing, constant units between decisions, cash leg, stop fills, ruin
floor, NaN rule) are documented in cpp/include/at/backtest.hpp and indicators.hpp.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

NaN = float("nan")


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _check(n: int) -> None:
    if n <= 0:
        raise ValueError("window must be positive")


def _window_mean(x: np.ndarray, i: int, n: int) -> float:
    acc = 0.0
    for j in range(i - n + 1, i + 1):  # index order, as the C++ loop sums
        acc += float(x[j])
    return acc / n


def _recursive_mean(x: np.ndarray, n: int, start: int, alpha: float) -> np.ndarray:
    """Wilder / EMA recursion with the shared NaN rule: a NaN input resets the state, the
    output is NaN until n consecutive valid inputs re-seed it with their mean."""
    out = np.full(len(x), NaN)
    prev = NaN
    run = 0
    for i in range(start, len(x)):
        v = x[i]
        if np.isnan(v):
            run = 0
            continue
        run += 1
        if run < n:
            continue
        prev = _window_mean(x, i, n) if run == n else alpha * v + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _wilder(x: np.ndarray, n: int, start: int) -> np.ndarray:
    return _recursive_mean(x, n, start, 1.0 / n)


# ---------------------------------------------------------------- indicators
def sma(x, n: int) -> np.ndarray:
    _check(n)
    x = _arr(x)
    out = np.full(len(x), NaN)
    if len(x) < n:
        return out
    # Each window is summed directly (mirrors C++): a cumulative sum drifts by cancellation
    # noise, which a later window of tiny values sees as its mean. A window containing a
    # NaN is NaN, so a derived series' leading NaNs do not poison every later value.
    nan = np.isnan(x)
    windows = np.lib.stride_tricks.sliding_window_view(np.where(nan, 0.0, x), n)
    has_nan = np.lib.stride_tricks.sliding_window_view(nan, n).any(axis=1)
    out[n - 1:] = np.where(has_nan, NaN, windows.sum(axis=1) / n)
    return out


def ema(x, n: int) -> np.ndarray:
    _check(n)
    return _recursive_mean(_arr(x), n, 0, 2.0 / (n + 1.0))


def rolling_std(x, n: int) -> np.ndarray:
    _check(n)
    x = _arr(x)
    out = np.full(len(x), NaN)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1 : i + 1].std()  # ddof=0
    return out


def zscore(x, n: int) -> np.ndarray:
    x = _arr(x)
    m, s = sma(x, n), rolling_std(x, n)
    out = np.full(len(x), NaN)
    ok = ~np.isnan(m) & ~np.isnan(s)
    # A window whose spread is at rounding level relative to its mean is flat: z = 0,
    # not the +-1 that cancellation noise in (x - mean) / std would give (mirrors C++).
    floor = 1e-12 * np.maximum(np.abs(m[ok]), 1e-300)
    live = s[ok] > floor
    out[ok] = np.where(live, (x[ok] - m[ok]) / np.where(live, s[ok], 1.0), 0.0)
    return out


def rsi(close, n: int = 14) -> np.ndarray:
    _check(n)
    c = _arr(close)
    out = np.full(len(c), NaN)
    if len(c) <= n:
        return out
    d = np.diff(c, prepend=c[0])
    d[0] = 0.0
    missing = np.isnan(d)  # a missing close removes two changes; neither is a zero change
    ag = _wilder(np.where(missing, NaN, np.where(d > 0, d, 0.0)), n, 1)
    al = _wilder(np.where(missing, NaN, np.where(d < 0, -d, 0.0)), n, 1)
    for i in range(n, len(c)):
        if np.isnan(ag[i]) or np.isnan(al[i]):
            continue
        if al[i] == 0.0:
            out[i] = 50.0 if ag[i] == 0.0 else 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + ag[i] / al[i])
    return out


def macd(close, fast: int = 12, slow: int = 26, signal: int = 9):
    c = _arr(close)
    line = ema(c, fast) - ema(c, slow)
    sig = ema(line, signal)
    return line, sig, line - sig


def bollinger(close, n: int = 20, k: float = 2.0):
    c = _arr(close)
    mid = sma(c, n)
    s = rolling_std(c, n)
    upper, lower = mid + k * s, mid - k * s
    width = upper - lower
    pb = np.where(width > 0, (c - lower) / np.where(width > 0, width, 1.0), 0.5)
    pb[np.isnan(mid)] = NaN
    return mid, upper, lower, pb


def atr(high, low, close, n: int = 14) -> np.ndarray:
    _check(n)
    h, l, c = _arr(high), _arr(low), _arr(close)
    if not (len(h) == len(l) == len(c)):
        raise ValueError("atr: high/low/close length mismatch")
    tr = h - l
    if len(c) > 1:
        pc = c[:-1]
        tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - pc), np.abs(l[1:] - pc)])
    return _wilder(tr, n, 0)


def kdj(high, low, close, n: int = 9):
    _check(n)
    h, l, c = _arr(high), _arr(low), _arr(close)
    if not (len(h) == len(l) == len(c)):
        raise ValueError("kdj: high/low/close length mismatch")
    K, D, J = (np.full(len(c), NaN) for _ in range(3))
    k = d = 50.0
    for i in range(n - 1, len(c)):
        hw, lw = h[i - n + 1 : i + 1], l[i - n + 1 : i + 1]
        if np.isnan(c[i]) or np.isnan(hw).any() or np.isnan(lw).any():
            continue  # a window with a missing bar has no range; the smoothed state does not advance
        hh, ll = hw.max(), lw.min()
        rsv = (c[i] - ll) / (hh - ll) * 100.0 if hh > ll else 50.0
        k = 2.0 / 3.0 * k + rsv / 3.0
        d = 2.0 / 3.0 * d + k / 3.0
        K[i], D[i], J[i] = k, d, 3.0 * k - 2.0 * d
    return K, D, J


def pct_change(x) -> np.ndarray:
    x = _arr(x)
    out = np.full(len(x), NaN)
    if len(x) > 1:
        prev = x[:-1]
        out[1:] = np.where(prev != 0, x[1:] / np.where(prev != 0, prev, 1.0) - 1.0, NaN)
    return out


def rolling_max(x, n: int) -> np.ndarray:
    _check(n)
    x = _arr(x)
    out = np.full(len(x), NaN)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1 : i + 1]
        if not np.isnan(w).any():
            out[i] = w.max()
    return out


def rolling_min(x, n: int) -> np.ndarray:
    _check(n)
    x = _arr(x)
    out = np.full(len(x), NaN)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1 : i + 1]
        if not np.isnan(w).any():
            out[i] = w.min()
    return out


def _average_ranks(v: np.ndarray) -> np.ndarray:
    order = np.argsort(v, kind="stable")
    ranks = np.empty(len(v))
    i = 0
    while i < len(v):
        j = i
        while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


def spearman(x, y) -> float:
    x, y = _arr(x), _arr(y)
    if x.size != y.size:
        raise ValueError("spearman: length mismatch")
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 3:
        return NaN
    ra, rb = _average_ranks(x[ok]), _average_ranks(y[ok])
    ra, rb = ra - ra.mean(), rb - rb.mean()
    saa, sbb = float(ra @ ra), float(rb @ rb)
    if saa <= 0 or sbb <= 0:
        return NaN
    return float((ra @ rb) / np.sqrt(saa * sbb))


def almgren_chriss(total: float, n: int, kappa: float) -> np.ndarray:
    if n <= 0:
        raise ValueError("almgren_chriss: n must be positive")
    if not kappa >= 0 or not np.isfinite(kappa):
        raise ValueError("almgren_chriss: kappa must be finite and >= 0")
    if kappa < 1e-8:
        return np.full(n, total / n)
    # x(t) = X sinh(kappa (1 - t)) / sinh(kappa) = X exp(-kappa t) expm1(-2 kappa (1 - t)) / expm1(-2 kappa):
    # overflow-free for any kappa (sinh(710) is inf) and cancellation-free for small kappa.
    t = np.arange(1, n + 1) / n
    remaining = total * np.exp(-kappa * t) * np.expm1(-2.0 * kappa * (1.0 - t)) / np.expm1(-2.0 * kappa)
    prev = np.concatenate([[total], remaining[:-1]])
    return prev - remaining


def realized_vol(close, n: int, periods_per_year: float) -> np.ndarray:
    _check(n)
    r = pct_change(close)
    out = np.full(len(r), NaN)
    for i in range(n, len(r)):
        out[i] = r[i - n + 1 : i + 1].std() * np.sqrt(periods_per_year)
    return out


# ---------------------------------------------------------------------- risk
def quantile(x, q: float) -> float:
    if np.isnan(q):
        return NaN
    v = _arr(x)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return NaN
    return float(np.quantile(v, min(max(q, 0.0), 1.0)))


def historical_var(returns, alpha: float = 0.95) -> float:
    q = quantile(returns, 1.0 - alpha)
    return 0.0 if np.isnan(q) else max(0.0, -q)


def historical_cvar(returns, alpha: float = 0.95) -> float:
    r = _arr(returns)
    q = quantile(r, 1.0 - alpha)
    if np.isnan(q):
        return 0.0
    tail = r[~np.isnan(r) & (r <= q)]
    return max(0.0, -float(tail.mean())) if tail.size else 0.0


def kelly_fraction(p: float, b: float) -> float:
    return 0.0 if b <= 0 else p - (1.0 - p) / b


def vol_target_weight(signal: float, realized_vol_annual: float, target_vol: float,
                      max_leverage: float) -> float:
    if realized_vol_annual is None or np.isnan(realized_vol_annual) or realized_vol_annual <= 0:
        return 0.0
    return float(np.clip(signal * target_vol / realized_vol_annual, -max_leverage, max_leverage))


def position_units(equity: float, risk_fraction: float, entry: float, stop: float) -> float:
    per_unit = abs(entry - stop)
    return 0.0 if per_unit <= 0 else equity * risk_fraction / per_unit


# ---------------------------------------------------------------- strategies
def strat_buy_hold(close) -> np.ndarray:
    return np.ones(len(close))


def strat_sma_cross(close, fast: int = 20, slow: int = 50, allow_short: bool = False):
    f, s = sma(close, fast), sma(close, slow)
    ok = ~np.isnan(f) & ~np.isnan(s)
    out = np.zeros(len(f))
    # Two averages of identical prices differ only by summation-order noise: a gap at or
    # below 1e-12 of the level is no cross and the position is flat (mirrors C++).
    band = 1e-12 * np.maximum(np.abs(f[ok]), np.abs(s[ok]))
    live = np.abs(f[ok] - s[ok]) > band
    out[ok] = np.where(live, np.where(f[ok] > s[ok], 1.0, -1.0 if allow_short else 0.0), 0.0)
    return out


def strat_macd(close, fast: int = 12, slow: int = 26, signal: int = 9, allow_short: bool = False):
    c = _arr(close)
    _, _, hist = macd(c, fast, slow, signal)
    ok = ~np.isnan(hist)
    out = np.zeros(len(hist))
    live = np.abs(hist[ok]) > 1e-12 * np.abs(c[ok])
    out[ok] = np.where(live, np.where(hist[ok] > 0, 1.0, -1.0 if allow_short else 0.0), 0.0)
    return out


def strat_kdj_rsi(high, low, close, kdj_n: int = 9, rsi_n: int = 14, rsi_low: float = 30.0,
                  rsi_high: float = 70.0, allow_short: bool = False):
    _, _, j = kdj(high, low, close, kdj_n)
    r = rsi(close, rsi_n)
    out = np.zeros(len(r))
    pos = 0.0
    for i in range(len(r)):
        if not (np.isnan(j[i]) or np.isnan(r[i])):
            if r[i] < rsi_low or j[i] < 0.0:
                pos = 1.0
            elif r[i] > rsi_high or j[i] > 100.0:
                pos = -1.0 if allow_short else 0.0
        out[i] = pos
    return out


def strat_zmr(close, n: int = 20, entry: float = 1.0, exit: float = 0.0,
              allow_short: bool = False):
    z = zscore(close, n)
    out = np.zeros(len(z))
    pos = 0.0
    for i in range(len(z)):
        if not np.isnan(z[i]):
            if pos > 0 and z[i] >= -exit:
                pos = 0.0
            if pos < 0 and z[i] <= exit:
                pos = 0.0
            if z[i] < -entry:
                pos = 1.0
            elif z[i] > entry and allow_short:
                pos = -1.0
        out[i] = pos
    return out


def strat_tsmom(close, horizons, skip: int = 0, allow_short: bool = True):
    """Time-series momentum: the average over ``horizons`` of sign(close[i-skip]/close[i-h]-1),
    0 until the longest horizon exists; a non-finite ratio votes 0 (mirrors C++)."""
    c = _arr(close)
    hs = [int(h) for h in horizons]
    if not hs:
        raise ValueError("horizons must not be empty")
    if min(hs) < 1:
        raise ValueError("horizon must be positive")
    if skip < 0 or skip >= min(hs):
        raise ValueError("skip must be in [0, min horizon)")
    out = np.zeros(len(c))
    longest = max(hs)
    if len(c) > longest:
        for h in hs:
            with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                r = c[longest - skip:len(c) - skip] / c[longest - h:len(c) - h] - 1.0
            out[longest:] += np.where(np.isfinite(r), np.sign(r), 0.0)
        out /= len(hs)
        if not allow_short:
            out = np.maximum(out, 0.0)
    return out


# ------------------------------------------------------------------ backtest
@dataclass
class BacktestConfig:
    initial_capital: float = 100_000.0
    cost_bps: float = 1.0
    slippage_bps: float = 0.0
    periods_per_year: float = 252.0
    carry_annual: float = 0.0
    borrow_annual: float = 0.0
    max_leverage: float = 1.0
    allow_short: bool = True
    risk_free_annual: float = 0.0  # constant rf for the metrics when no cash_rate series is given
    funded: bool = True  # idle cash 1-|w| earns cash_rate; False (FX forwards): the whole account


@dataclass
class Trade:
    index: int
    from_weight: float
    to_weight: float
    price: float


@dataclass
class Metrics:
    cumulative_return: float = 0.0
    annualized_return: float = 0.0
    annualized_vol: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    max_drawdown: float = 0.0
    calmar: float = 0.0
    win_rate: float = 0.0
    num_trades: int = 0
    turnover: float = 0.0
    periods: int = 0
    avg_exposure: float = 0.0
    sharpe_tstat: float = 0.0
    ruined: bool = False  # equity reached 0; statistics stop at the ruin bar


@dataclass
class BacktestResult:
    equity: np.ndarray
    returns: np.ndarray
    positions: np.ndarray  # weight actually held over (t, t+1] (drifts between decisions)
    trades: list = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    stop_exits: int = 0
    impact_paid: float = 0.0  # cumulative market-impact cost as a fraction of equity
    traded: np.ndarray = field(default_factory=lambda: np.zeros(0))  # |dw| executed per bar
    exits: np.ndarray = field(default_factory=lambda: np.zeros(0))   # 1 where a level filled
    ruined_at: int = -1  # bar at which equity reached 0, or -1


def max_drawdown(equity) -> float:
    e = _arr(equity)
    e = e[~np.isnan(e)]  # a missing point neither sets a peak nor counts as a drawdown (mirrors C++)
    if e.size == 0:
        return 0.0
    peak = np.maximum.accumulate(np.maximum(e, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, 1.0 - e / peak, 0.0)
    return float(max(dd.max(), 0.0))


ZERO_VARIANCE_TOL = 1e-12  # sd <= tol * max(1, |mean|) is rounding noise, not dispersion (both backends)


def _warn_inferred_trades() -> None:
    warnings.warn(
        "compute_metrics: without `traded`, trades are inferred from changes in `positions`, which "
        "drift every bar under constant units; pass the engine's `traded` array for exact counts",
        RuntimeWarning, stacklevel=3)


def compute_metrics(equity, positions, periods_per_year: float,
                    risk_free_annual=0.0, traded=None) -> Metrics:
    """Metrics of an equity curve (see cpp/include/at/backtest.hpp).

    ``risk_free_annual`` is a constant or a per-bar series (NaN -> 0; an empty array means
    absent, i.e. rf = 0); Sharpe, Sortino and the t-stat are computed on the excess return
    ``r_t - rf_t / ppy``. An excess-return series that is constant to rounding (its sample
    standard deviation is at most ``ZERO_VARIANCE_TOL * max(1, |mean|)``) has no dispersion
    to divide by: Sharpe, Sortino, the t-stat and ``annualized_vol`` are 0, on both backends,
    rather than noise over noise (a flat book, or one earning exactly rf). The same tolerance
    applies to the downside deviation on its own: a series with real dispersion whose only
    losses are rounding noise (flat bars under a cash leg) has no downside to divide by, so
    its Sortino is 0 while its Sharpe stands. ``traded`` (|dw|
    per bar) gives turnover and the trade count; without it (``None`` or empty) both are
    inferred from changes in ``positions``, which drift every bar under constant units, and
    a ``RuntimeWarning`` says so once. Statistics stop at the ruin bar (the first equity <= 0).
    """
    e, pos = _arr(equity), _arr(positions)
    if pos.shape != e.shape:
        raise ValueError("compute_metrics: positions and equity length mismatch")
    rf_series = None
    if np.ndim(risk_free_annual) > 0 and np.size(risk_free_annual) > 0:
        rf_series = _arr(risk_free_annual)
        if rf_series.shape != e.shape:
            raise ValueError("compute_metrics: risk_free_annual length does not match equity")
    if traded is not None and np.size(traded) == 0:
        traded = None
    if traded is not None:
        traded = _arr(traded)
        if traded.shape != e.shape:
            raise ValueError("compute_metrics: traded length does not match equity")
    else:
        _warn_inferred_trades()
    m = Metrics()
    if e.size < 2:
        return m
    n = e.size - 1
    m.periods = n
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.where(e[:-1] > 0, e[1:] / np.where(e[:-1] > 0, e[:-1], 1.0) - 1.0, 0.0)
    live = n
    if not e[0] > 0:
        live, m.ruined = 0, True
    else:
        dead = np.flatnonzero(e[1:] <= 0)
        if dead.size:
            live, m.ruined = int(dead[0]) + 1, True
    m.cumulative_return = float(e[-1] / e[0] - 1.0) if e[0] > 0 else NaN
    with np.errstate(over="ignore"):  # a huge one-bar gain annualises to inf, as in C++ (no exception)
        m.annualized_return = (
            float(np.power(np.float64(1.0 + m.cumulative_return), periods_per_year / n) - 1.0)
            if m.cumulative_return > -1.0 else -1.0
        )
    if rf_series is None:
        rf0 = float(risk_free_annual) if np.ndim(risk_free_annual) == 0 else 0.0
        rf = np.full(n, 0.0 if np.isnan(rf0) else rf0)   # NaN = unknown = 0, as the C++ core reads it
    else:
        rf = np.where(np.isnan(rf_series[:n]), 0.0, rf_series[:n])
    ex = r[:live] - rf[:live] / periods_per_year
    mean = float(ex.mean()) if live else 0.0
    sd = float(ex.std(ddof=1)) if live > 1 else 0.0
    dd = float(np.sqrt(np.mean(np.minimum(ex, 0.0) ** 2))) if live else 0.0
    tol = ZERO_VARIANCE_TOL * max(1.0, abs(mean))
    if sd <= tol:
        sd, dd = 0.0, 0.0
    elif dd <= tol:
        dd = 0.0
    ann = np.sqrt(periods_per_year)
    m.annualized_vol = sd * ann
    m.sharpe = float(mean / sd * ann) if sd > 0 else 0.0
    m.sharpe_tstat = float(mean / sd * np.sqrt(live)) if sd > 0 else 0.0
    m.sortino = float(mean / dd * ann) if dd > 0 else 0.0
    m.max_drawdown = max_drawdown(e)
    m.calmar = m.annualized_return / m.max_drawdown if m.max_drawdown > 0 else 0.0

    if traded is None:
        prev = np.concatenate([[0.0], pos[:-1]])
        changed = pos != prev
        m.num_trades = int(changed.sum())
        m.turnover = float(np.abs(pos - prev)[changed].sum())
    else:
        m.num_trades = int((traded != 0).sum())
        m.turnover = float(traded.sum())
    held_mask = pos[:live] != 0
    held = int(held_mask.sum())
    m.win_rate = float((r[:live][held_mask] > 0).sum() / held) if held else 0.0
    m.avg_exposure = float(np.abs(pos[:n]).mean())
    return m


def _exit_fill(w, stop, take, o, h, l):
    """Fill price if a protective level trades inside the bar, else NaN (see backtest.hpp):
    the open is resolved first against both levels, then the range, stop before target."""
    if w > 0:
        if not np.isnan(stop) and o <= stop:
            return o
        if not np.isnan(take) and o >= take:
            return o
        if not np.isnan(stop) and l <= stop:
            return stop
        if not np.isnan(take) and h >= take:
            return take
    elif w < 0:
        if not np.isnan(stop) and o >= stop:
            return o
        if not np.isnan(take) and o <= take:
            return o
        if not np.isnan(stop) and h >= stop:
            return stop
        if not np.isnan(take) and l <= take:
            return take
    return NaN


_EXTRA_RULES = {"carry": "finite_or_nan", "open": "positive", "high": "positive", "low": "positive",
                "stop": "finite_or_nan", "take": "finite_or_nan", "rebalance": "finite",
                "impact": "nonneg_or_nan", "cash_rate": "finite_or_nan"}
_RULE_TEXT = {"positive": "positive and finite", "finite": "finite",
              "nonneg_or_nan": "NaN or a finite non-negative number", "finite_or_nan": "NaN or finite"}


def validate_backtest_inputs(prices, target_weights, config: BacktestConfig, **extras):
    """Coerce and check every ``run_backtest`` input; both backends call this before the engine.

    Returns ``(prices, weights, extras)`` as 1-D float arrays (an absent extra is ``None``).
    Prices and bar ranges must be positive and finite; ``rebalance`` finite; ``impact`` NaN or a
    finite non-negative number; carry, protective levels and cash_rate NaN or finite.
    """
    p, w_in = _arr(prices), _arr(target_weights)
    if p.ndim != 1 or w_in.ndim != 1:
        raise ValueError("run_backtest: prices and weights must be one-dimensional")
    if p.size != w_in.size:
        raise ValueError("run_backtest: prices and weights length mismatch")
    if config.periods_per_year <= 0:
        raise ValueError("periods_per_year must be > 0")
    if not (config.initial_capital > 0) or np.isinf(config.initial_capital):
        raise ValueError("initial_capital must be positive and finite")
    for name in ("cost_bps", "slippage_bps", "borrow_annual"):
        v = float(getattr(config, name))
        if not np.isfinite(v) or v < 0:
            raise ValueError(f"{name} must be a finite non-negative number, got {v}")
    if not np.isfinite(config.max_leverage) or config.max_leverage < 0:
        raise ValueError(f"max_leverage must be finite and >= 0, got {config.max_leverage}")
    if not np.isfinite(config.carry_annual):
        raise ValueError(f"carry_annual must be finite, got {config.carry_annual}")
    if np.isinf(config.risk_free_annual):
        raise ValueError("risk_free_annual must be finite or NaN (unknown = 0)")
    for name in ("cost_bps", "slippage_bps", "borrow_annual"):
        v = float(getattr(config, name))
        if not np.isfinite(v) or v < 0:
            raise ValueError(f"{name} must be a finite non-negative number, got {v}")
    if not np.isfinite(config.max_leverage) or config.max_leverage < 0:
        raise ValueError(f"max_leverage must be finite and >= 0, got {config.max_leverage}")
    if not np.isfinite(config.carry_annual):
        raise ValueError(f"carry_annual must be finite, got {config.carry_annual}")
    if np.isinf(config.risk_free_annual):
        raise ValueError("risk_free_annual must be finite or NaN (unknown = 0)")
    unknown = set(extras) - set(_EXTRA_RULES)
    if unknown:
        raise TypeError(f"run_backtest: unknown inputs {sorted(unknown)}")
    T = p.size
    if T and not np.all((p > 0) & np.isfinite(p)):
        raise ValueError("run_backtest: prices must be positive and finite")
    out = {}
    for name, rule in _EXTRA_RULES.items():
        arr = extras.get(name)
        a = None if arr is None or np.size(arr) == 0 else _arr(arr)
        if a is not None:
            if a.ndim != 1:
                raise ValueError(f"run_backtest: {name} must be a one-dimensional per-bar series")
            if a.size != T:
                raise ValueError(f"run_backtest: {name} length does not match prices")
            finite = np.isfinite(a)
            if rule == "positive":
                ok = finite & (a > 0)
            elif rule == "finite":
                ok = finite
            elif rule == "nonneg_or_nan":
                ok = np.isnan(a) | (finite & (a >= 0))
            else:
                ok = np.isnan(a) | finite
            if not np.all(ok):
                raise ValueError(f"run_backtest: {name} must be {_RULE_TEXT[rule]}")
        out[name] = a
    has_levels = out["stop"] is not None or out["take"] is not None
    if has_levels and not all(out[k] is not None for k in ("open", "high", "low")):
        raise ValueError("run_backtest: stop/take levels need open, high and low")
    return p, w_in, out


def run_backtest(prices, target_weights, config: BacktestConfig) -> BacktestResult:
    return run_backtest_ex(prices, target_weights, config)


def run_backtest_ex(prices, target_weights, config: BacktestConfig, carry=None, open=None,
                    high=None, low=None, stop=None, take=None, rebalance=None,
                    impact=None, cash_rate=None) -> BacktestResult:
    p, w_in, extras = validate_backtest_inputs(prices, target_weights, config, carry=carry, open=open,
                                               high=high, low=low, stop=stop, take=take,
                                               rebalance=rebalance, impact=impact, cash_rate=cash_rate)
    T = p.size
    has_levels = extras["stop"] is not None or extras["take"] is not None

    equity = np.full(T, float(config.initial_capital), dtype=float)
    returns = np.zeros(T)
    positions = np.zeros(T)
    traded = np.zeros(T)
    exit_flags = np.zeros(T)
    trades: list[Trade] = []
    if T == 0:
        return BacktestResult(equity, returns, positions, trades, Metrics(), traded=traded, exits=exit_flags)

    lo = -config.max_leverage if config.allow_short else 0.0
    hi = config.max_leverage
    unit_cost = (config.cost_bps + config.slippage_bps) / 1e4
    ppy = config.periods_per_year
    stop_a, take_a, reb = extras["stop"], extras["take"], extras["rebalance"]
    imp, cash_a = extras["impact"], extras["cash_rate"]
    E0 = float(config.initial_capital)

    def impact_k(i: int) -> float:
        return 0.0 if imp is None or np.isnan(imp[i]) else float(imp[i])

    prev, prev_target, stopped, ruined = 0.0, NaN, False, False
    exits, impact_paid, ruined_at = 0, 0.0, -1
    for t in range(T - 1):
        raw = 0.0 if np.isnan(w_in[t]) else float(w_in[t])
        clamped = float(min(max(raw, lo), hi))
        target = raw if raw == prev else clamped
        rearm = (clamped != prev_target) if reb is None else (reb[t] != 0.0)
        decide = rearm or clamped != prev_target
        if rearm:
            stopped = False
        prev_target = clamped
        w = 0.0 if (ruined or stopped) else (target if decide else prev)

        trade = w - prev
        if trade != 0.0:
            trades.append(Trade(t, prev, w, float(p[t])))
            traded[t] += abs(trade)

        exit_px = NaN
        if w != 0.0 and has_levels:
            s = NaN if stop_a is None else stop_a[t]
            k = NaN if take_a is None else take_a[t]
            exit_px = _exit_fill(w, s, k, extras["open"][t + 1], extras["high"][t + 1],
                                 extras["low"][t + 1])
        exited = not np.isnan(exit_px)
        px_end = exit_px if exited else p[t + 1]

        rate = config.carry_annual
        if extras["carry"] is not None:
            rate = 0.0 if np.isnan(extras["carry"][t]) else extras["carry"][t]
        cash_rate_t = 0.0
        if cash_a is not None and not np.isnan(cash_a[t]):
            cash_rate_t = float(cash_a[t])

        # Costs come out of equity before the position is put on (w is a fraction of post-cost
        # equity): E_{t+1} = E_t (1 - k_in) (1 + g) (1 - k_out). Mirrors C++ operation for operation.
        gross = px_end / p[t]  # kept as a ratio: 1 + (gross - 1) loses digits on a huge move
        price_ret = gross - 1.0
        carry = w * rate / ppy
        cash = (1.0 - abs(w) if config.funded else 1.0) * cash_rate_t / ppy
        borrow = -w * config.borrow_annual / ppy if w < 0 else 0.0
        scale = np.sqrt(equity[t] / E0)
        impact_in = abs(trade) ** 1.5 * impact_k(t) * scale if trade != 0.0 else 0.0
        k_in = abs(trade) * unit_cost + impact_in
        g = w * price_ret + carry + cash - borrow
        f_in, f_g, f_out = 1.0 - k_in, 1.0 + g, 1.0
        growth = f_in * f_g
        impact_paid += impact_in
        if exited:
            impact_out = abs(w) ** 1.5 * impact_k(t + 1) * scale
            f_out = 1.0 - (abs(w) * unit_cost + impact_out)
            growth *= f_out
            impact_paid += impact_out
            trades.append(Trade(t + 1, w, 0.0, float(exit_px)))
            traded[t + 1] += abs(w)
            exit_flags[t + 1] = 1.0
            exits += 1
            stopped = True

        # Each factor is a fraction of the account left after one leg of the bar (entry cost,
        # the move, the exit cost); any one of them reaching zero is ruin, whatever the product.
        ret = growth - 1.0
        nxt = equity[t] * (1.0 + ret)
        if ruined:
            ret, nxt = 0.0, equity[t]
        elif f_in <= 0.0 or f_g <= 0.0 or f_out <= 0.0 or nxt <= 0.0:
            ret, nxt = -1.0, 0.0
            ruined, ruined_at = True, t + 1
        positions[t] = w
        returns[t + 1] = ret
        equity[t + 1] = nxt
        prev = 0.0 if (exited or ruined or w == 0.0) else w * gross / (1.0 + g)
    positions[T - 1] = prev
    metrics = compute_metrics(equity, positions, ppy,
                              config.risk_free_annual if cash_a is None else cash_a, traded)
    metrics.num_trades = len(trades)
    return BacktestResult(equity, returns, positions, trades, metrics, exits, impact_paid,
                          traded, exit_flags, ruined_at)
