"""Financing spread on leverage (v0.17, review item A5).

Plain idea. The engine's cash leg is ``(1 - |w|) * rf``: idle cash earns the risk-free rate
and, when ``|w| > 1``, the borrowed part is charged the same rate. No prime broker lends at
rf. A leveraged book pays rf plus a spread on the borrowed notional, and a broker usually
pays rf minus a spread on idle cash.

Formal statement. For a held weight ``w`` over one bar of length ``1 / ppy`` years, with a
risk-free rate ``rf`` and spreads ``s_b`` (borrow) and ``s_c`` (cash, optional):

    financing = (1 - |w|) * rf / ppy                      (what the engine already books)
    drag      = max(|w| - 1, 0) * s_b / ppy + max(1 - |w|, 0) * s_c / ppy

and the bar's arithmetic return falls by ``drag`` (times the entry and exit cost factors,
which are 1 when costs are zero). ``DEFAULT_FUNDING_SPREAD_BPS = 50`` is a round number of the
order a retail or small institutional margin account pays over the policy rate (evidence
class: convention, not measured here). The cash spread defaults to 0 so that unlevered
results are unchanged.

Worked example. ``w = 1.5``, ``s_b = 50`` bps, daily bars (252): the drag is
``0.5 * 0.005 / 252 = 9.9e-6`` per bar, about 0.25 % a year on the account, or 50 bps a year
on the borrowed half.

Where it hooks in. The engine loop is owned by another lane in v0.17, so this module applies
the drag after the run (``apply_financing``), which is exact when transaction costs are zero
and first-order otherwise (the error is ``drag * cost``, of order 1e-9 per bar). The exact
in-loop hook is one line in ``quant/pycore.py`` (and the C++ mirror), next to ``cash = ...``::

    cash -= financing_drag(w, funding_spread, cash_spread) / ppy

described in docs/review/v017_notes/L8_quant_rest.md.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

from . import quant

DEFAULT_FUNDING_SPREAD_BPS = 50.0   # over rf on borrowed notional (|w| > 1); convention
DEFAULT_CASH_SPREAD_BPS = 0.0       # under rf on idle cash; 0 keeps unlevered results unchanged


def financing_drag(w, funding_spread_annual: float = DEFAULT_FUNDING_SPREAD_BPS / 1e4,
                   cash_spread_annual: float = DEFAULT_CASH_SPREAD_BPS / 1e4) -> np.ndarray:
    """Annualised financing cost rate (a non-negative fraction of equity) for held weights ``w``:
    ``max(|w| - 1, 0) * funding_spread + max(1 - |w|, 0) * cash_spread``. Divide by periods
    per year for a per-bar figure. NaN weights count as flat."""
    if funding_spread_annual < 0 or cash_spread_annual < 0:
        raise ValueError("financing spreads must be non-negative")
    a = np.abs(np.nan_to_num(np.asarray(w, dtype=float), nan=0.0))
    return np.maximum(a - 1.0, 0.0) * funding_spread_annual + np.maximum(1.0 - a, 0.0) * cash_spread_annual


def apply_financing(result: quant.BacktestResult, periods_per_year: float,
                    funding_spread_bps: float = DEFAULT_FUNDING_SPREAD_BPS,
                    cash_spread_bps: float = DEFAULT_CASH_SPREAD_BPS,
                    risk_free_annual=0.0) -> quant.BacktestResult:
    """A copy of ``result`` with the financing drag taken out of each bar's return.

    ``result.positions[t]`` is the weight held over ``(t, t+1]`` and ``result.returns[t+1]``
    its return, so bar ``t+1`` loses ``financing_drag(positions[t]) / ppy``. Equity is
    recompounded from the adjusted returns and metrics recomputed with ``risk_free_annual``.
    A ruined run stays ruined from the same bar (returns after ruin are 0 already)."""
    r = np.asarray(result.returns, dtype=float).copy()
    if r.size < 2:
        return result
    pos = np.asarray(result.positions, dtype=float)
    drag = financing_drag(pos[:-1], funding_spread_bps / 1e4, cash_spread_bps / 1e4) / periods_per_year
    if result.ruined_at >= 0:
        drag[result.ruined_at:] = 0.0
    r[1:] = r[1:] - drag
    r = np.maximum(r, -1.0)
    e0 = float(result.equity[0])
    equity = e0 * np.cumprod(1.0 + r)
    metrics = quant.compute_metrics(equity, pos, periods_per_year, risk_free_annual, result.traded)
    return replace(result, equity=equity, returns=r, metrics=metrics)


def run_backtest_financed(prices, target_weights, config: quant.BacktestConfig,
                          funding_spread_bps: float = DEFAULT_FUNDING_SPREAD_BPS,
                          cash_spread_bps: float = DEFAULT_CASH_SPREAD_BPS, **extras) -> quant.BacktestResult:
    """``quant.run_backtest`` (with ``run_backtest_ex`` extras when given) followed by
    ``apply_financing``: the engine entry point with the financing parameter."""
    if extras:
        res = quant.pycore.run_backtest_ex(prices, target_weights, config, **extras)
    else:
        res = quant.run_backtest(prices, target_weights, config)
    rf = extras.get("cash_rate")
    rf = config.risk_free_annual if rf is None else rf
    return apply_financing(res, config.periods_per_year, funding_spread_bps, cash_spread_bps, rf)
