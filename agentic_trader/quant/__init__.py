"""Quant core facade.

Uses the compiled C++ extension (``_atcore``, built by CMake from ``cpp/``) when it
is importable and falls back to the pure-numpy reference implementation otherwise.
Every function returns numpy arrays / plain Python types regardless of backend.

Set the environment variable ``AGENTIC_TRADER_BACKEND=python`` to force the
fallback (useful for debugging or cross-checking).
"""
from __future__ import annotations

import os

import numpy as np

from . import pycore
from .pycore import BacktestConfig, BacktestResult, Metrics, Trade

try:  # pragma: no cover - depends on the local build
    if os.environ.get("AGENTIC_TRADER_BACKEND", "").lower() == "python":
        raise ImportError("forced python backend")
    from . import _atcore as _cpp  # type: ignore[attr-defined]

    BACKEND = "cpp"
except ImportError:  # pragma: no cover
    _cpp = None
    BACKEND = "python"

__all__ = [
    "BACKEND", "BacktestConfig", "BacktestResult", "Metrics", "Trade",
    "sma", "ema", "rolling_std", "zscore", "rsi", "macd", "bollinger", "atr", "kdj",
    "pct_change", "realized_vol", "rolling_max", "rolling_min", "spearman", "almgren_chriss",
    "quantile", "historical_var", "historical_cvar",
    "kelly_fraction", "vol_target_weight", "position_units", "strat_buy_hold",
    "strat_sma_cross", "strat_macd", "strat_kdj_rsi", "strat_zmr", "run_backtest",
    "compute_metrics", "max_drawdown",
]


def _l(x) -> list[float]:
    return np.asarray(x, dtype=float).tolist()


def _a(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _dispatch_series(name: str):
    py_fn = getattr(pycore, name)

    def fn(*args, **kw):
        if _cpp is None:
            return py_fn(*args, **kw)
        # Arrays -> list[float]; scalars (window lengths, flags) pass through untouched.
        out = getattr(_cpp, name)(*(_l(a) if np.ndim(a) > 0 else a for a in args), **kw)
        if isinstance(out, tuple):
            return tuple(_a(o) for o in out)
        return _a(out)

    fn.__name__ = name
    fn.__doc__ = py_fn.__doc__
    return fn


def _dispatch_scalar(name: str, n_series: int):
    py_fn = getattr(pycore, name)

    def fn(*args, **kw):
        if _cpp is None:
            return py_fn(*args, **kw)
        args = tuple(_l(a) if i < n_series else a for i, a in enumerate(args))
        return float(getattr(_cpp, name)(*args, **kw))

    fn.__name__ = name
    return fn


sma = _dispatch_series("sma")
ema = _dispatch_series("ema")
rolling_std = _dispatch_series("rolling_std")
zscore = _dispatch_series("zscore")
rsi = _dispatch_series("rsi")
macd = _dispatch_series("macd")
bollinger = _dispatch_series("bollinger")
atr = _dispatch_series("atr")
kdj = _dispatch_series("kdj")
pct_change = _dispatch_series("pct_change")
realized_vol = _dispatch_series("realized_vol")
rolling_max = _dispatch_series("rolling_max")
rolling_min = _dispatch_series("rolling_min")
strat_buy_hold = _dispatch_series("strat_buy_hold")
strat_sma_cross = _dispatch_series("strat_sma_cross")
strat_macd = _dispatch_series("strat_macd")
strat_kdj_rsi = _dispatch_series("strat_kdj_rsi")
strat_zmr = _dispatch_series("strat_zmr")

spearman = _dispatch_scalar("spearman", 2)
quantile = _dispatch_scalar("quantile", 1)


def almgren_chriss(total: float, n: int, kappa: float) -> np.ndarray:
    """Almgren-Chriss slice quantities (see cpp/include/at/indicators.hpp)."""
    if _cpp is None:
        return pycore.almgren_chriss(total, n, kappa)
    return _a(_cpp.almgren_chriss(float(total), int(n), float(kappa)))
historical_var = _dispatch_scalar("historical_var", 1)
historical_cvar = _dispatch_scalar("historical_cvar", 1)
max_drawdown = _dispatch_scalar("max_drawdown", 1)
kelly_fraction = _dispatch_scalar("kelly_fraction", 0)
vol_target_weight = _dispatch_scalar("vol_target_weight", 0)
position_units = _dispatch_scalar("position_units", 0)


def _metrics_from_cpp(m) -> Metrics:
    return Metrics(**{f: getattr(m, f) for f in Metrics.__dataclass_fields__})


def compute_metrics(equity, positions, periods_per_year: float,
                    risk_free_annual: float = 0.0) -> Metrics:
    if _cpp is None:
        return pycore.compute_metrics(equity, positions, periods_per_year, risk_free_annual)
    return _metrics_from_cpp(
        _cpp.compute_metrics(_l(equity), _l(positions), periods_per_year, risk_free_annual))


def run_backtest(prices, target_weights, config: BacktestConfig | None = None, *,
                 carry=None, open=None, high=None, low=None, stop=None, take=None,
                 rebalance=None, impact=None) -> BacktestResult:
    """Backtest a target-weight path.

    Optional per-bar arrays (same length as ``prices``):
      carry      annual carry rate per bar (overrides ``config.carry_annual``)
      open/high/low  bar ranges, required when stop or take levels are given
      stop/take  absolute protective levels for the position held over (t, t+1]; NaN = none
      rebalance  non-zero where a new decision was made (re-arms after a stop exit)
      impact     square-root market-impact coefficient K_t: a trade of |dw| at bar t costs
                 |dw|^1.5 * K_t of equity (see ``backtest.impact_coefficients``); NaN = none
    """
    config = config or BacktestConfig()
    extras = dict(carry=carry, open=open, high=high, low=low, stop=stop, take=take,
                  rebalance=rebalance, impact=impact)
    if _cpp is None:
        return pycore.run_backtest_ex(prices, target_weights, config, **extras)
    c = _cpp.BacktestConfig()
    for f in BacktestConfig.__dataclass_fields__:
        setattr(c, f, getattr(config, f))
    kw = {k: _l(v) for k, v in extras.items() if v is not None and len(v)}
    r = _cpp.run_backtest_ex(_l(prices), _l(target_weights), c, **kw)
    trades = [Trade(t.index, t.from_weight, t.to_weight, t.price) for t in r.trades]
    return BacktestResult(_a(r.equity), _a(r.returns), _a(r.positions), trades,
                          _metrics_from_cpp(r.metrics), int(r.stop_exits), float(r.impact_paid))
