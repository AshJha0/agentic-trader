"""Pure-numpy reference implementation of the C++ core (cpp/src/*.cpp).

Used automatically when the compiled ``_atcore`` extension is not available.
Numerical conventions must stay identical to the C++ code; tests/test_quant.py
cross-checks the two backends whenever the extension is built.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

NaN = float("nan")


def _arr(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _check(n: int) -> None:
    if n <= 0:
        raise ValueError("window must be positive")


def _first_valid(x: np.ndarray) -> int:
    idx = np.flatnonzero(~np.isnan(x))
    return int(idx[0]) if idx.size else len(x)


def _wilder(x: np.ndarray, n: int, start: int) -> np.ndarray:
    out = np.full(len(x), NaN)
    seed = start + n - 1
    if seed >= len(x):
        return out
    prev = x[start : seed + 1].sum() / n
    out[seed] = prev
    for i in range(seed + 1, len(x)):
        prev = (prev * (n - 1) + x[i]) / n
        out[i] = prev
    return out


# ---------------------------------------------------------------- indicators
def sma(x, n: int) -> np.ndarray:
    _check(n)
    x = _arr(x)
    out = np.full(len(x), NaN)
    if len(x) < n:
        return out
    # Cumulative sums over NaN-free stretches only: a NaN resets the window, so a
    # derived series' leading NaNs do not poison every later value (mirrors C++).
    nan = np.isnan(x)
    c = np.cumsum(np.insert(np.where(nan, 0.0, x), 0, 0.0))
    win = (c[n:] - c[:-n]) / n
    bad = np.cumsum(np.insert(nan.astype(int), 0, 0))
    has_nan = (bad[n:] - bad[:-n]) > 0
    out[n - 1:] = np.where(has_nan, NaN, win)
    return out


def ema(x, n: int) -> np.ndarray:
    _check(n)
    x = _arr(x)
    out = np.full(len(x), NaN)
    start = _first_valid(x)
    seed = start + n - 1
    if seed >= len(x):
        return out
    prev = x[start : seed + 1].sum() / n
    out[seed] = prev
    alpha = 2.0 / (n + 1.0)
    for i in range(seed + 1, len(x)):
        prev = alpha * x[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


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
    ag = _wilder(np.where(d > 0, d, 0.0), n, 1)
    al = _wilder(np.where(d < 0, -d, 0.0), n, 1)
    for i in range(n, len(c)):
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
    if not kappa >= 0:
        raise ValueError("almgren_chriss: kappa must be >= 0")
    if kappa < 1e-8:
        return np.full(n, total / n)
    t = np.arange(1, n + 1) / n
    remaining = total * np.sinh(kappa * (1.0 - t)) / np.sinh(kappa)
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
    out[ok] = np.where(f[ok] > s[ok], 1.0, -1.0 if allow_short else 0.0)
    return out


def strat_macd(close, fast: int = 12, slow: int = 26, signal: int = 9, allow_short: bool = False):
    _, _, hist = macd(close, fast, slow, signal)
    ok = ~np.isnan(hist)
    out = np.zeros(len(hist))
    out[ok] = np.where(hist[ok] > 0, 1.0, -1.0 if allow_short else 0.0)
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
    risk_free_annual: float = 0.0


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


@dataclass
class BacktestResult:
    equity: np.ndarray
    returns: np.ndarray
    positions: np.ndarray
    trades: list = field(default_factory=list)
    metrics: Metrics = field(default_factory=Metrics)
    stop_exits: int = 0
    impact_paid: float = 0.0  # cumulative market-impact cost as a fraction of equity


def max_drawdown(equity) -> float:
    e = _arr(equity)
    e = e[~np.isnan(e)]  # a missing point neither sets a peak nor counts as a drawdown (mirrors C++)
    if e.size == 0:
        return 0.0
    peak = np.maximum.accumulate(np.maximum(e, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        dd = np.where(peak > 0, 1.0 - e / peak, 0.0)
    return float(max(dd.max(), 0.0))


def compute_metrics(equity, positions, periods_per_year: float,
                    risk_free_annual: float = 0.0) -> Metrics:
    e, pos = _arr(equity), _arr(positions)
    m = Metrics()
    if e.size < 2:
        return m
    n = e.size - 1
    m.periods = n
    r = e[1:] / e[:-1] - 1.0
    m.cumulative_return = float(e[-1] / e[0] - 1.0)
    with np.errstate(over="ignore"):  # a huge one-bar gain annualises to inf, as in C++ (no exception)
        m.annualized_return = (
            float(np.power(np.float64(1.0 + m.cumulative_return), periods_per_year / n) - 1.0)
            if m.cumulative_return > -1.0 else -1.0
        )
    rf = risk_free_annual / periods_per_year
    mean = r.mean()
    sd = float(r.std(ddof=1)) if n > 1 else 0.0
    dd = float(np.sqrt(np.mean(np.minimum(r - rf, 0.0) ** 2)))
    ann = np.sqrt(periods_per_year)
    m.annualized_vol = sd * ann
    m.sharpe = float((mean - rf) / sd * ann) if sd > 0 else 0.0
    m.sharpe_tstat = float((mean - rf) / sd * np.sqrt(n)) if sd > 0 else 0.0
    m.sortino = float((mean - rf) / dd * ann) if dd > 0 else 0.0
    m.max_drawdown = max_drawdown(e)
    m.calmar = m.annualized_return / m.max_drawdown if m.max_drawdown > 0 else 0.0

    prev = np.concatenate([[0.0], pos[:-1]])
    changed = pos != prev
    m.num_trades = int(changed.sum())
    m.turnover = float(np.abs(pos - prev)[changed].sum())
    held_mask = pos[:n] != 0
    held = int(held_mask.sum())
    m.win_rate = float((r[held_mask] > 0).sum() / held) if held else 0.0
    m.avg_exposure = float(np.abs(pos[:n]).mean())
    return m


def _exit_fill(w, stop, take, o, h, l):
    """Fill price if a protective level trades inside the bar, else NaN (see backtest.hpp)."""
    if w > 0:
        if not np.isnan(stop) and o <= stop:
            return o
        if not np.isnan(stop) and l <= stop:
            return stop
        if not np.isnan(take) and o >= take:
            return o
        if not np.isnan(take) and h >= take:
            return take
    elif w < 0:
        if not np.isnan(stop) and o >= stop:
            return o
        if not np.isnan(stop) and h >= stop:
            return stop
        if not np.isnan(take) and o <= take:
            return o
        if not np.isnan(take) and l <= take:
            return take
    return NaN


def run_backtest(prices, target_weights, config: BacktestConfig) -> BacktestResult:
    return run_backtest_ex(prices, target_weights, config)


def run_backtest_ex(prices, target_weights, config: BacktestConfig, carry=None, open=None,
                    high=None, low=None, stop=None, take=None, rebalance=None,
                    impact=None) -> BacktestResult:
    p, w_in = _arr(prices), _arr(target_weights)
    if p.size != w_in.size:
        raise ValueError("run_backtest: prices and weights length mismatch")
    if config.periods_per_year <= 0:
        raise ValueError("periods_per_year must be > 0")
    T = p.size
    extras = {}
    for name, arr in (("carry", carry), ("open", open), ("high", high), ("low", low),
                      ("stop", stop), ("take", take), ("rebalance", rebalance),
                      ("impact", impact)):
        a = None if arr is None or len(arr) == 0 else _arr(arr)
        if a is not None and a.size != T:
            raise ValueError(f"run_backtest: {name} length does not match prices")
        extras[name] = a
    has_levels = extras["stop"] is not None or extras["take"] is not None
    has_ohlc = all(extras[k] is not None for k in ("open", "high", "low"))
    if has_levels and not has_ohlc:
        raise ValueError("run_backtest: stop/take levels need open, high and low")
    if T and not np.all((p > 0) & np.isfinite(p)):
        raise ValueError("run_backtest: prices must be positive and finite")

    equity = np.full(T, config.initial_capital)
    returns = np.zeros(T)
    positions = np.zeros(T)
    trades: list[Trade] = []
    if T == 0:
        return BacktestResult(equity, returns, positions, trades, Metrics())

    lo = -config.max_leverage if config.allow_short else 0.0
    hi = config.max_leverage
    unit_cost = (config.cost_bps + config.slippage_bps) / 1e4
    ppy = config.periods_per_year
    stop_a, take_a, reb = extras["stop"], extras["take"], extras["rebalance"]
    imp = extras["impact"]

    def impact_k(i: int) -> float:
        return 0.0 if imp is None or np.isnan(imp[i]) else float(imp[i])

    prev, prev_target, stopped, exits, impact_paid = 0.0, NaN, False, 0, 0.0
    for t in range(T - 1):
        target = 0.0 if np.isnan(w_in[t]) else float(min(max(w_in[t], lo), hi))
        rearm = (target != prev_target) if reb is None else (reb[t] != 0.0)
        if rearm:
            stopped = False
        prev_target = target
        w = 0.0 if stopped else target

        trade = w - prev
        if trade != 0.0:
            trades.append(Trade(t, prev, w, float(p[t])))

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

        impact_in = abs(trade) ** 1.5 * impact_k(t)
        ret = (w * (px_end / p[t] - 1.0) + w * rate / ppy
               - (-w * config.borrow_annual / ppy if w < 0 else 0.0) - abs(trade) * unit_cost
               - impact_in)
        impact_paid += impact_in
        if exited:
            impact_out = abs(w) ** 1.5 * impact_k(t + 1)
            ret -= abs(w) * unit_cost + impact_out
            impact_paid += impact_out
            trades.append(Trade(t + 1, w, 0.0, float(exit_px)))
            exits += 1
            stopped = True
        positions[t] = w
        returns[t + 1] = ret
        equity[t + 1] = equity[t] * (1.0 + ret)
        prev = 0.0 if exited else w
    positions[T - 1] = prev
    metrics = compute_metrics(equity, positions, ppy, config.risk_free_annual)
    return BacktestResult(equity, returns, positions, trades, metrics, exits, impact_paid)
