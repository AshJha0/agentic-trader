"""Quant core facade.

Uses the compiled C++ extension (``_atcore``, built by CMake from ``cpp/``) when it
is importable and falls back to the pure-numpy reference implementation otherwise.
Every function returns numpy arrays / plain Python types regardless of backend.

Set the environment variable ``AGENTIC_TRADER_BACKEND=python`` to force the
fallback (useful for debugging or cross-checking).

Boundary contract: every entry point either returns a well-formed result or raises
``ValueError`` -- on both backends, for the same inputs. Window arguments are
validated here (an integer in ``[1, 2**31 - 1]``; ``bool`` is rejected) so the
compiled ``int`` parameters and the numpy twin see the same values.
"""
from __future__ import annotations

import operator
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
    if os.environ.get("AGENTIC_TRADER_BACKEND", "").lower() != "python":
        import warnings

        warnings.warn(
            "agentic_trader.quant: the compiled C++ core (_atcore) is not importable for this "
            "interpreter, so every number comes from the numpy backend (quant.BACKEND='python'). "
            "Build it with CMake (see README) or set AGENTIC_TRADER_BACKEND=python to choose the "
            "numpy backend explicitly.", RuntimeWarning, stacklevel=2)

__all__ = [
    "BACKEND", "BacktestConfig", "BacktestResult", "Metrics", "Trade",
    "sma", "ema", "rolling_std", "zscore", "rsi", "macd", "bollinger", "atr", "kdj",
    "pct_change", "realized_vol", "rolling_max", "rolling_min", "spearman", "almgren_chriss",
    "quantile", "historical_var", "historical_cvar",
    "kelly_fraction", "vol_target_weight", "position_units", "strat_buy_hold",
    "strat_sma_cross", "strat_macd", "strat_kdj_rsi", "strat_zmr", "run_backtest",
    "compute_metrics", "max_drawdown",
]

MAX_WINDOW = 2**31 - 1

# Window-length parameters per function: (positional index, keyword name).
_WINDOW_ARGS: dict[str, tuple[tuple[int, str], ...]] = {
    "sma": ((1, "n"),), "ema": ((1, "n"),), "rolling_std": ((1, "n"),), "zscore": ((1, "n"),),
    "rsi": ((1, "n"),), "rolling_max": ((1, "n"),), "rolling_min": ((1, "n"),),
    "realized_vol": ((1, "n"),), "atr": ((3, "n"),), "kdj": ((3, "n"),), "bollinger": ((1, "n"),),
    "macd": ((1, "fast"), (2, "slow"), (3, "signal")),
    "strat_sma_cross": ((1, "fast"), (2, "slow")),
    "strat_macd": ((1, "fast"), (2, "slow"), (3, "signal")),
    "strat_kdj_rsi": ((3, "kdj_n"), (4, "rsi_n")),
    "strat_zmr": ((1, "n"),),
}


def _window(v) -> int:
    if isinstance(v, (bool, np.bool_)):
        raise ValueError("window must be an integer, not a bool")
    try:
        n = operator.index(v)
    except TypeError:
        raise ValueError(f"window must be an integer, got {type(v).__name__}") from None
    if n <= 0:
        raise ValueError("window must be positive")
    if n > MAX_WINDOW:
        raise ValueError(f"window must be <= {MAX_WINDOW}")
    return n


def _validated(name: str, args: tuple, kw: dict) -> tuple[tuple, dict]:
    spec = _WINDOW_ARGS.get(name)
    if not spec:
        return args, kw
    args = list(args)
    for i, key in spec:
        if i < len(args):
            args[i] = _window(args[i])
        elif key in kw:
            kw[key] = _window(kw[key])
    return tuple(args), kw


def _l(x) -> list[float]:
    return np.asarray(x, dtype=float).tolist()


def _a(x) -> np.ndarray:
    return np.asarray(x, dtype=float)


def _dispatch_series(name: str):
    py_fn = getattr(pycore, name)

    def fn(*args, **kw):
        args, kw = _validated(name, args, kw)
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
    """Almgren-Chriss slice quantities (see cpp/include/at/indicators.hpp): finite for any finite
    kappa >= 0 (0 = TWAP); a negative or non-finite kappa raises ValueError."""
    n = _window(n)
    if _cpp is None:
        return pycore.almgren_chriss(total, n, kappa)
    return _a(_cpp.almgren_chriss(float(total), n, float(kappa)))
historical_var = _dispatch_scalar("historical_var", 1)
historical_cvar = _dispatch_scalar("historical_cvar", 1)
max_drawdown = _dispatch_scalar("max_drawdown", 1)
kelly_fraction = _dispatch_scalar("kelly_fraction", 0)
vol_target_weight = _dispatch_scalar("vol_target_weight", 0)
position_units = _dispatch_scalar("position_units", 0)


def _metrics_from_cpp(m) -> Metrics:
    return Metrics(**{f: getattr(m, f) for f in Metrics.__dataclass_fields__})


def compute_metrics(equity, positions, periods_per_year: float,
                    risk_free_annual=0.0, traded=None) -> Metrics:
    """Metrics of an equity curve (see ``pycore.compute_metrics``).

    ``risk_free_annual`` is a constant or a per-bar array of the same length as ``equity``
    (NaN -> 0); Sharpe, Sortino and the t-stat use excess returns ``r_t - rf_t / ppy``.
    ``traded`` (|dw| per bar) gives turnover and the trade count exactly; without it both
    are inferred from changes in ``positions``. ``positions`` must match ``equity`` in length.
    """
    if _cpp is None:
        return pycore.compute_metrics(equity, positions, periods_per_year, risk_free_annual, traded)
    tr = [] if traded is None else _l(traded)
    if np.ndim(risk_free_annual) > 0:
        m = _cpp.compute_metrics_rf(_l(equity), _l(positions), periods_per_year, _l(risk_free_annual), tr)
    else:
        m = _cpp.compute_metrics(_l(equity), _l(positions), periods_per_year, float(risk_free_annual), tr)
    return _metrics_from_cpp(m)


def run_backtest(prices, target_weights, config: BacktestConfig | None = None, *,
                 carry=None, open=None, high=None, low=None, stop=None, take=None,
                 rebalance=None, impact=None, cash_rate=None) -> BacktestResult:
    """Backtest a target-weight path (conventions in cpp/include/at/backtest.hpp).

    A target is executed on a decision bar (the target changes, or ``rebalance`` is set);
    between decisions the units are held and the weight drifts with the market, with no
    trade and no cost. The leverage cap applies to targets. Equity is floored at 0 (ruin:
    any one leg of a bar -- entry cost, move or exit cost -- consuming the whole account).

    Optional per-bar arrays (same length as ``prices``):
      carry      annual carry rate per bar (overrides ``config.carry_annual``)
      open/high/low  bar ranges, required when stop or take levels are given
      stop/take  absolute protective levels for the position held over (t, t+1]; NaN = none
      rebalance  non-zero where a new decision was made (re-arms after a stop exit)
      impact     square-root market-impact coefficient K_t for an account of
                 ``config.initial_capital``: a trade of |dw| at bar t costs
                 |dw|^1.5 * K_t * sqrt(equity_t / initial_capital) of equity
                 (see ``backtest.impact_coefficients``); NaN = none
      cash_rate  annual risk-free rate credited on idle cash: (1 - |w|) of the account when
                 ``config.funded`` (equities), the whole account otherwise (FX forwards);
                 NaN = nothing credited. The metrics then use it as the per-bar rf.

    The result carries ``positions`` (weight held over (t, t+1]), ``traded`` (|dw| per bar),
    ``exits`` (1 where a protective level filled) and ``ruined_at``.
    """
    config = config or BacktestConfig()
    prices, target_weights, extras = pycore.validate_backtest_inputs(
        prices, target_weights, config, carry=carry, open=open, high=high, low=low, stop=stop,
        take=take, rebalance=rebalance, impact=impact, cash_rate=cash_rate)
    if _cpp is None:
        return pycore.run_backtest_ex(prices, target_weights, config, **extras)
    c = _cpp.BacktestConfig()
    for f in BacktestConfig.__dataclass_fields__:
        setattr(c, f, getattr(config, f))
    kw = {k: _l(v) for k, v in extras.items() if v is not None}
    r = _cpp.run_backtest_ex(_l(prices), _l(target_weights), c, **kw)
    trades = [Trade(t.index, t.from_weight, t.to_weight, t.price) for t in r.trades]
    return BacktestResult(_a(r.equity), _a(r.returns), _a(r.positions), trades,
                          _metrics_from_cpp(r.metrics), int(r.stop_exits), float(r.impact_paid),
                          _a(r.traded), _a(r.exits), int(r.ruined_at))
