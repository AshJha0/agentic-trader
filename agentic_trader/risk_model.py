"""Risk model (v0.14, plan item 5.4): conditional VaR forecasts, factor exposures, stress and
capacity rows.

Why this exists. The desk's VaR rule -- a trailing 250-day historical quantile, the rule
``stats.rolling_var_forecast`` reproduces -- failed its own calibration checks on the design
period: Kupiec unconditional coverage passed for 2 of 15 names and Christoffersen
independence for 6 of 15 (PLAN.md section 2). The reason is well known: a long trailing window
reacts slowly to a change in volatility, so breaches arrive in runs after a vol spike and are
too rare in calm spells. The two forecasters here condition on *current* volatility:

* ``"ewma"``: RiskMetrics (J.P. Morgan, 1996). ``sigma2_t = lam * sigma2_{t-1} + (1 - lam) *
  r_{t-1}^2`` and ``VaR_t = -z_{1-alpha} * sigma_t`` under a zero-mean normal.
* ``"fhs"``: filtered historical simulation (Barone-Adesi, Giannopoulos and Vosper, 1999;
  Hull and White, 1998). Each past return is divided by its own ex-ante EWMA volatility; the
  empirical ``1 - alpha`` quantile of those standardised residuals over the trailing window
  is rescaled by today's volatility. It keeps the fat tails of the historical method and the
  responsiveness of EWMA.

Every forecast for day ``t`` uses returns strictly before ``t`` (no look-ahead), and the
series is aligned with the returns exactly as ``stats.rolling_var_forecast`` is, so
``stats.var_backtest`` (Kupiec + Christoffersen) remains the judge of all three methods.

Factor exposures, stress rows and the capacity row are plain functions over return series so
that table renderers can call them; none of them fetches data.
"""
from __future__ import annotations

import math
from statistics import NormalDist
from typing import Literal

import numpy as np
import pandas as pd

from . import quant
from .stats import rolling_var_forecast

VarMethod = Literal["historical", "ewma", "fhs"]
VAR_METHODS: tuple[str, ...] = ("historical", "ewma", "fhs")
EWMA_LAMBDA = 0.94      # RiskMetrics daily decay; not tuned on any period of this repository
MIN_RESIDUALS = 20      # standardised residuals below which an FHS quantile is not trusted


# ---------------------------------------------------------------- VaR forecasts
def ewma_vol(returns, lam: float = EWMA_LAMBDA, warmup: int = 20) -> np.ndarray:
    """Ex-ante EWMA volatility: element ``t`` uses returns strictly before ``t``; the output
    has ``len(returns) + 1`` elements, the last being the forecast for the day after the
    series ends.

    The recursion is seeded with the mean square of the first ``warmup`` finite returns (mean
    zero, as RiskMetrics assumes for daily data), so elements up to and including ``warmup``
    are NaN. A non-finite return leaves the variance unchanged rather than poisoning it.
    """
    if not 0.0 < lam < 1.0:
        raise ValueError(f"lam must be in (0, 1), got {lam}")
    r = np.asarray(returns, dtype=float)
    out = np.full(r.size + 1, np.nan)
    finite = np.flatnonzero(np.isfinite(r))
    if finite.size < warmup:
        return out
    start = int(finite[warmup - 1]) + 1
    s2 = float(np.mean(r[finite[:warmup]] ** 2))
    out[start] = math.sqrt(s2)
    for t in range(start, r.size):
        if np.isfinite(r[t]):
            s2 = lam * s2 + (1.0 - lam) * r[t] * r[t]
        out[t + 1] = math.sqrt(s2)
    return out


def _forecasts(r: np.ndarray, method: str, window: int, alpha: float, lam: float) -> np.ndarray:
    """VaR forecasts for days ``0 .. len(r)`` (one more than the returns: the last is for the
    day after the series ends). NaN where fewer than ``window`` returns precede the day."""
    if method not in VAR_METHODS:
        raise ValueError(f"unknown VaR method {method!r}; expected one of {VAR_METHODS}")
    if not 0.5 < alpha < 1.0:
        raise ValueError(f"alpha must be in (0.5, 1), got {alpha}")
    if method == "historical":
        return rolling_var_forecast(np.append(r, np.nan), window, alpha)
    sig = ewma_vol(r, lam)
    out = np.full(r.size + 1, np.nan)
    if method == "ewma":
        zq = -NormalDist().inv_cdf(1.0 - alpha)
        out[window:] = zq * sig[window:]
        return out
    with np.errstate(divide="ignore", invalid="ignore"):
        resid = np.where(sig[:-1] > 0, r / sig[:-1], np.nan)
    for t in range(window, r.size + 1):
        if not np.isfinite(sig[t]):
            continue
        z = resid[t - window:t]
        z = z[np.isfinite(z)]
        if z.size >= MIN_RESIDUALS:
            out[t] = max(0.0, -float(np.quantile(z, 1.0 - alpha))) * sig[t]
    return out


def var_forecast(returns, method: VarMethod = "fhs", window: int = 250, alpha: float = 0.95,
                 lam: float = EWMA_LAMBDA) -> np.ndarray:
    """1-day VaR (a non-negative loss fraction) forecast *for* each day ``t`` from returns
    strictly before it, aligned with ``returns``; a drop-in for ``stats.rolling_var_forecast``
    (``method="historical"`` reproduces it exactly) whose output ``stats.var_backtest`` judges.

    NaN for the first ``window`` days under every method, so the three are scored on the same
    days. ``window`` is the trailing sample for the historical quantile and for the FHS
    residual quantile; EWMA uses it only as the warm-up. ``lam`` is the EWMA decay used by
    ``"ewma"`` and as the FHS volatility filter.
    """
    r = np.asarray(returns, dtype=float)
    return _forecasts(r, method, window, alpha, lam)[:-1]


def var_next(returns, method: VarMethod = "fhs", window: int = 250, alpha: float = 0.95,
             lam: float = EWMA_LAMBDA) -> float | None:
    """VaR for the day after ``returns`` ends, by the same rule as ``var_forecast``; ``None``
    when it cannot be formed (too short a history). For a history shorter than ``window``
    the whole history is used as the window, so a short book is still checked when it has at
    least ``MIN_RESIDUALS`` usable returns plus the EWMA warm-up.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < MIN_RESIDUALS:
        return None
    v = float(_forecasts(r, method, min(window, r.size), alpha, lam)[-1])
    return v if math.isfinite(v) else None


# ---------------------------------------------------------------- factor exposures
FACTOR_PROXIES: dict[str, str] = {
    # Free daily proxies every provider here can supply (Yahoo live, synthetic in tests).
    "market": "SPY",     # US equity market
    "rates": "IEF",      # 7-10y Treasuries: long this = long duration
    "usd": "UUP",        # US dollar index fund: long this = long USD
    "momentum": "MTUM",  # US momentum factor fund
}


def factor_returns(provider, start, end, proxies: dict[str, str] | None = None) -> pd.DataFrame:
    """Daily close-to-close returns of the factor proxies from ``provider`` (any
    ``MarketDataProvider``), one column per factor name, on the union of their dates."""
    from .instruments import Instrument
    cols = {}
    for name, sym in (proxies or FACTOR_PROXIES).items():
        h = provider.history(Instrument.parse(sym), start, end)
        cols[name] = h["Close"].pct_change()
    return pd.DataFrame(cols).iloc[1:]


def factor_exposures(returns: pd.Series, factors: pd.DataFrame, window: int = 126) -> pd.DataFrame:
    """Rolling OLS betas (with intercept) of ``returns`` on each column of ``factors`` over
    the trailing ``window`` days ending at, and including, each date.

    The regression is joint (all factors at once), so a beta is the exposure to that factor
    holding the others fixed. Rows with any non-finite value are dropped inside each window;
    a window with fewer than ``2 * (k + 1)`` usable rows yields NaN. Output columns are the
    factor names plus ``alpha`` (daily intercept) and ``r2``.
    """
    df = pd.concat([returns.rename("_y"), factors], axis=1, join="inner")
    names = list(factors.columns)
    k = len(names)
    out = np.full((len(df), k + 2), np.nan)
    data = df.to_numpy(float)
    for i in range(window - 1, len(df)):
        w = data[i - window + 1:i + 1]
        w = w[np.isfinite(w).all(axis=1)]
        if len(w) < 2 * (k + 1):
            continue
        y, x = w[:, 0], np.column_stack([np.ones(len(w)), w[:, 1:]])
        coef, *_ = np.linalg.lstsq(x, y, rcond=None)
        ss_tot = float(((y - y.mean()) ** 2).sum())
        r2 = 1.0 - float(((y - x @ coef) ** 2).sum()) / ss_tot if ss_tot > 0 else float("nan")
        out[i, :k] = coef[1:]
        out[i, k], out[i, k + 1] = coef[0], r2
    return pd.DataFrame(out, index=df.index, columns=[*names, "alpha", "r2"])


# ---------------------------------------------------------------- stress rows
STRESS_WINDOWS: dict[str, tuple[str, str]] = {
    # Peak-to-trough episodes by the S&P 500, inclusive. 2022 lies inside the evaluation
    # holdout period: a 2022 row reports a series that has already been run there, it is not
    # a licence to choose anything on it.
    "2008": ("2008-09-01", "2009-03-09"),   # Lehman to the March 2009 low
    "2020": ("2020-02-19", "2020-03-23"),   # COVID crash
    "2022": ("2022-01-03", "2022-10-12"),   # rates shock
}


def stress_rows(returns: pd.Series, windows: dict[str, tuple[str, str]] | None = None) -> pd.DataFrame:
    """One row per stress window for a daily return series with a ``DatetimeIndex``: days
    covered, cumulative return, worst day, maximum drawdown and annualised volatility (all in
    percent, 252-day year). A window the series does not cover gives a row of NaN with
    ``days = 0``, so a table always shows every episode and says when one is missing.
    """
    rows = []
    for name, (a, b) in (windows or STRESS_WINDOWS).items():
        r = returns.loc[pd.Timestamp(a):pd.Timestamp(b)].dropna().to_numpy(float)
        if r.size == 0:
            rows.append({"window": name, "days": 0, "CR%": np.nan, "worst_day%": np.nan,
                         "MDD%": np.nan, "Vol%": np.nan})
            continue
        eq = np.cumprod(1.0 + r)
        rows.append({"window": name, "days": int(r.size), "CR%": 100 * (eq[-1] - 1.0),
                     "worst_day%": 100 * float(r.min()),
                     "MDD%": 100 * quant.max_drawdown(np.append(1.0, eq)),
                     "Vol%": 100 * float(r.std(ddof=1)) * math.sqrt(252) if r.size > 1 else np.nan})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- capacity row
def capacity_aum(impact_drag_annual: float, ann_vol: float, capital: float,
                 sharpe_cost: float = 0.1) -> float:
    """AUM at which modelled market impact costs ``sharpe_cost`` of annual Sharpe.

    Under the backtester's square-root impact model (``backtest.impact_coefficients``) a
    weight change ``dw`` costs ``|dw|^1.5 * K_t`` of equity with ``K_t`` proportional to
    ``sqrt(capital)``; for a fixed trading schedule the annual impact drag therefore scales
    as ``D(A) = D(capital) * sqrt(A / capital)``, and the Sharpe it costs is ``D(A) /
    ann_vol``. Solving ``D(A) / ann_vol = sharpe_cost`` gives ``A = capital * (sharpe_cost *
    ann_vol / D(capital))^2``. ``impact_drag_annual`` is the annualised impact paid in a run
    at ``capital`` (``BacktestResult.impact_paid`` divided by the years run). Infinite when
    the run paid no impact (impact off, or no volume data): no capacity limit was modelled,
    which is not the same as none existing. The schedule is held fixed, so this ignores any
    trading the strategy would cut at larger size.
    """
    if capital <= 0 or ann_vol <= 0 or sharpe_cost <= 0:
        raise ValueError("capital, ann_vol and sharpe_cost must be positive")
    if not impact_drag_annual > 0:
        return math.inf
    return capital * (sharpe_cost * ann_vol / impact_drag_annual) ** 2


def capacity_row(result, capital: float, periods_per_year: float = 252.0,
                 sharpe_cost: float = 0.1) -> dict[str, float]:
    """``capacity_aum`` from a ``quant.BacktestResult`` run at ``capital`` with impact on:
    returns the annual impact drag, the annual volatility and the capacity AUM."""
    r = np.asarray(result.returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        raise ValueError("need at least two finite returns to estimate volatility")
    years = r.size / periods_per_year
    drag = float(result.impact_paid) / years
    vol = float(r.std(ddof=1)) * math.sqrt(periods_per_year)
    return {"impact_drag%": 100 * drag, "Vol%": 100 * vol,
            "capacity_aum": capacity_aum(drag, vol, capital, sharpe_cost)}
