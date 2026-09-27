"""Portfolio construction: covariance estimation, weighting schemes, constraints
and risk attribution. numpy only.

The desk produces one signed target weight per instrument. Portfolio
construction decides how much capital each sleeve gets, using the trailing
covariance of instrument returns estimated without look-ahead:

* ``equal``          1/N capital per sleeve;
* ``inverse_vol``    capital proportional to 1 / sigma_i;
* ``risk_parity``    equal contribution to portfolio variance;
* ``min_variance``   long-only minimum variance with a per-sleeve cap;
* ``mean_variance``  long-only maximum of mu'w - (lambda/2) w'Sigma w with the
                     desk's signals as expected returns.

Scheme weights are non-negative allocations of capital; they multiply the signed
desk targets, so a flat sleeve stays flat and a short sleeve stays short.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from . import quant

log = logging.getLogger(__name__)

Method = Literal["equal", "inverse_vol", "risk_parity", "min_variance", "mean_variance"]
METHODS: tuple[str, ...] = ("equal", "inverse_vol", "risk_parity", "min_variance", "mean_variance")


# -------------------------------------------------------------- covariance
def ewma_weights(t: int, halflife: float) -> np.ndarray:
    """Normalised exponential observation weights for ``t`` rows (most recent row last)."""
    if halflife <= 0:
        raise ValueError("halflife must be positive")
    lam = 0.5 ** (1.0 / halflife)
    w = lam ** np.arange(t - 1, -1, -1)
    return w / w.sum()


def ewma_cov(returns: np.ndarray, halflife: float = 60.0) -> np.ndarray:
    """Exponentially weighted covariance (most recent row last)."""
    r = np.asarray(returns, float)
    if r.ndim != 2 or r.shape[0] < 2:
        raise ValueError("returns must be a (T, N) array with T >= 2")
    w = ewma_weights(r.shape[0], halflife)
    mu = w @ r
    d = r - mu
    return (d * w[:, None]).T @ d


def sample_cov(returns: np.ndarray) -> np.ndarray:
    r = np.asarray(returns, float)
    if r.ndim != 2 or r.shape[0] < 2:
        raise ValueError("returns must be a (T, N) array with T >= 2")
    return np.cov(r, rowvar=False, ddof=1).reshape(r.shape[1], r.shape[1])


def ledoit_wolf_shrink(returns: np.ndarray, cov: np.ndarray | None = None,
                       weights: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Shrink a covariance toward the constant-correlation target (Ledoit & Wolf 2004).

    ``cov`` is the covariance being shrunk (default: the sample covariance of ``returns``)
    and ``weights`` the per-observation weights it was estimated with (default: equal, a
    plain sample covariance; pass ``ewma_weights(T, halflife)`` for an EWMA covariance).
    The intensity is the Ledoit-Wolf constant-correlation estimator kappa / n_eff computed
    with those same observation weights -- weighted mean for centring, weighted averages for
    pi, theta and rho -- and their effective sample size n_eff = 1 / sum(w^2), which is T
    for equal weights, where every formula reduces exactly to Ledoit & Wolf's. Computing the
    intensity with equal weights and T for an EWMA covariance measures the noise of a
    different estimator and shrinks less the more stale history precedes the window.

    A zero-variance column is uncorrelated with everything (its target entries are zero,
    as in the covariance) rather than a source of NaN. Returns the shrunk matrix and the
    intensity in [0, 1].
    """
    r = np.asarray(returns, float)
    t, n = r.shape
    if weights is None:
        w = np.full(t, 1.0 / t)
    else:
        if cov is None:
            raise ValueError("weights describe the estimator behind cov; pass the weighted covariance too")
        w = np.asarray(weights, float)
        if w.shape != (t,) or (w < 0).any() or w.sum() <= 0:
            raise ValueError("weights must be one non-negative value per row with a positive sum")
        w = w / w.sum()
    s = sample_cov(r) if cov is None else np.asarray(cov, float)
    if n == 1:
        return s.copy(), 0.0
    sd = np.sqrt(np.diag(s))
    pos = sd > 0
    sd_safe = np.where(pos, sd, 1.0)
    corr = s / np.outer(sd_safe, sd_safe)
    npos = int(pos.sum())
    rbar = (corr[np.ix_(pos, pos)].sum() - npos) / (npos * (npos - 1)) if npos > 1 else 0.0
    target = rbar * np.outer(sd, sd)
    np.fill_diagonal(target, np.diag(s))
    x = r - w @ r
    prod = x[:, :, None] * x[:, None, :]                     # (T, N, N): x_it x_jt
    # pi_ij: asymptotic variance of the covariance entries
    pi_mat = np.einsum("t,tij->ij", w, (prod - s) ** 2)
    pi = pi_mat.sum()
    # theta_ii,ij = weighted mean_t (x_it^2 - s_ii)(x_it x_jt - s_ij)
    theta = np.einsum("t,tij->ij", w, (x ** 2 - np.diag(s))[:, :, None] * (prod - s))
    # rho: covariance between the errors of S and of the constant-correlation target
    ratio = sd_safe[None, :] / sd_safe[:, None]              # sqrt(s_jj / s_ii)
    off = ~np.eye(n, dtype=bool)
    rho = np.trace(pi_mat) + rbar * (ratio * theta)[off].sum()
    gamma = ((target - s) ** 2).sum()
    kappa = (pi - rho) / gamma if gamma > 0 else 0.0
    n_eff = 1.0 / float(w @ w)
    delta = float(min(1.0, max(0.0, kappa / n_eff)))
    return delta * target + (1 - delta) * s, delta


def estimate_cov(returns: np.ndarray, halflife: float | None = 60.0, shrink: bool = True) -> np.ndarray:
    r = np.asarray(returns, float)
    if halflife:
        cov, w = ewma_cov(r, halflife), ewma_weights(r.shape[0], halflife)
    else:
        cov, w = sample_cov(r), None
    if shrink and r.shape[1] > 1:
        cov, _ = ledoit_wolf_shrink(r, cov, w)
    return cov


# ------------------------------------------------------------- weighting
def _simplex_box_projection(v: np.ndarray, cap: float) -> np.ndarray:
    """Project onto {w >= 0, w <= cap, sum w = 1} (bisection on the shift). A point already
    in the set is returned unchanged, so an uncapped allocation is not perturbed at the last bit."""
    if cap * v.size < 1.0 - 1e-12:
        raise ValueError("cap too small: N * cap must be >= 1")
    if (v >= 0).all() and (v <= cap).all() and abs(v.sum() - 1.0) <= 1e-12:
        return np.array(v, float, copy=True)
    lo, hi = v.min() - 1.0, v.max()
    for _ in range(100):
        mid = (lo + hi) / 2
        s = np.clip(v - mid, 0.0, cap).sum()
        if s > 1.0:
            lo = mid
        else:
            hi = mid
    return np.clip(v - hi, 0.0, cap)


def equal_weights(n: int) -> np.ndarray:
    return np.full(n, 1.0 / n)


def inverse_vol_weights(cov: np.ndarray) -> np.ndarray:
    sd = np.sqrt(np.diag(cov))
    inv = np.where(sd > 0, 1.0 / np.where(sd > 0, sd, 1.0), 0.0)
    return inv / inv.sum() if inv.sum() > 0 else equal_weights(len(sd))


def risk_parity_weights(cov: np.ndarray, budget: np.ndarray | None = None, iters: int = 500,
                        tol: float = 1e-10) -> np.ndarray:
    """Weights whose risk contributions match ``budget`` (equal by default).
    Cyclical coordinate descent on the convex reformulation (Spinu 2013)."""
    c = np.asarray(cov, float)
    if not np.isfinite(c).all():
        raise ValueError("covariance has non-finite entries")
    if not (np.diag(c) > 0).any():
        raise ValueError("covariance has no positive variance: risk parity is undefined")
    n = c.shape[0]
    b = np.full(n, 1.0 / n) if budget is None else np.asarray(budget, float) / np.sum(budget)
    x = inverse_vol_weights(c)
    for _ in range(iters):
        prev = x.copy()
        for i in range(n):
            a = c[i, i]
            bb = float(c[i] @ x - c[i, i] * x[i])
            x[i] = (-bb + math.sqrt(bb * bb + 4 * a * b[i])) / (2 * a) if a > 0 else 0.0
        if np.abs(x - prev).max() < tol:
            break
    return x / x.sum()


@dataclass(frozen=True)
class Convergence:
    """Whether a projected-gradient solver reached its stopping tolerance, and after how many
    iterations. An unconverged solve still returns its best iterate -- silently returning that
    iterate with no way to tell it apart from a converged one is how an ill-conditioned
    covariance (near-duplicate sleeves, a very tight cap) produces an allocation nobody checked."""
    converged: bool
    iterations: int


def min_variance_weights(cov: np.ndarray, cap: float = 1.0, iters: int = 2000,
                         return_info: bool = False):
    """Long-only minimum variance with a per-asset cap (projected gradient).

    Returns the weights array, or ``(weights, Convergence)`` when ``return_info=True``.
    """
    c = np.asarray(cov, float)
    n = c.shape[0]
    w = _simplex_box_projection(equal_weights(n), cap)
    lipschitz = 2 * max(np.linalg.eigvalsh(c).max(), 1e-12)
    for i in range(iters):
        g = 2 * c @ w
        w_new = _simplex_box_projection(w - g / lipschitz, cap)
        if np.abs(w_new - w).max() < 1e-10:
            return (w_new, Convergence(True, i + 1)) if return_info else w_new
        w = w_new
    return (w, Convergence(False, iters)) if return_info else w


def mean_variance_weights(mu: np.ndarray, cov: np.ndarray, risk_aversion: float = 5.0,
                          cap: float = 1.0, iters: int = 2000, return_info: bool = False):
    """Long-only max of mu'w - (lambda/2) w'Sigma w on the capped simplex.

    Returns the weights array, or ``(weights, Convergence)`` when ``return_info=True``.
    """
    c, m = np.asarray(cov, float), np.asarray(mu, float)
    if risk_aversion <= 0:
        raise ValueError("risk_aversion must be positive")
    n = c.shape[0]
    w = _simplex_box_projection(equal_weights(n), cap)
    lipschitz = risk_aversion * max(np.linalg.eigvalsh(c).max(), 1e-12)
    for i in range(iters):
        g = -m + risk_aversion * c @ w
        w_new = _simplex_box_projection(w - g / lipschitz, cap)
        if np.abs(w_new - w).max() < 1e-10:
            return (w_new, Convergence(True, i + 1)) if return_info else w_new
        w = w_new
    return (w, Convergence(False, iters)) if return_info else w


# ------------------------------------------------------------- attribution
def risk_contributions(w: np.ndarray, cov: np.ndarray) -> dict[str, np.ndarray | float]:
    w, c = np.asarray(w, float), np.asarray(cov, float)
    var = float(w @ c @ w)
    vol = math.sqrt(max(var, 0.0))
    marginal = c @ w / vol if vol > 0 else np.zeros_like(w)
    component = w * marginal
    sd = np.sqrt(np.diag(c))
    weighted_avg_vol = float(np.abs(w) @ sd)
    return {"vol": vol, "marginal": marginal, "component": component,
            "pct": component / vol if vol > 0 else np.zeros_like(w),
            "diversification_ratio": weighted_avg_vol / vol if vol > 0 else float("nan")}


# --------------------------------------------------------------- book risk
MIN_BOOK_OBS = 20   # aligned daily observations below which a book quantile is not trusted


def book_returns(weights: dict[str, float], returns: pd.DataFrame) -> np.ndarray | None:
    """Aligned daily returns of a weighted book, finite rows only.

    Symbols at zero weight are dropped *before* alignment: they cannot move the book, so a
    short-history symbol held at zero must not shorten everyone else's sample (0 * NaN is
    NaN). Held symbols missing from ``returns`` contribute nothing (their return is treated
    as exactly zero, which never manufactures diversification credit for missing data); a
    held symbol whose column is NaN on a row removes that row, so a held symbol with a short
    history shortens the sample and the caller sees that in the row count. Returns ``None``
    when no held symbol has any history at all.
    """
    held = [s for s, x in weights.items() if x != 0]
    if not held:
        return np.zeros(len(returns))
    cols = [s for s in held if s in returns.columns]
    if not cols:
        return None
    w = np.array([weights[s] for s in cols])
    r = returns[cols].to_numpy(float)
    port = r @ w
    return port[np.isfinite(port)]


def book_var_95(weights: dict[str, float], returns: pd.DataFrame, alpha: float = 0.95) -> float | None:
    """Historical VaR of a weighted book (the same convention as ``quant.historical_var`` for
    one instrument: a non-negative loss fraction). ``returns`` is an aligned (T, N) frame of
    daily returns; see ``book_returns`` for how zero-weight, missing and short-history symbols
    are treated. An empty book (every weight zero) has VaR 0. Returns ``None`` when fewer
    than ``MIN_BOOK_OBS`` aligned, finite observations are available -- too little to trust
    a quantile -- which ``book_var_scale`` treats as a failed check, never a passed one.
    """
    if not any(x != 0 for x in weights.values()):
        return 0.0
    port = book_returns(weights, returns)
    if port is None or port.size < MIN_BOOK_OBS:
        return None
    return quant.historical_var(port, alpha)


def book_var_scale(symbol: str, proposed_weight: float, other_positions: dict[str, float],
                   returns: pd.DataFrame, max_var_95: float | None, alpha: float = 0.95,
                   grid: int = 41) -> tuple[float, float | None, str | None]:
    """Scale ``proposed_weight`` in ``symbol`` down, if needed, so the book (``other_positions``
    unchanged, ``symbol`` at the scaled weight) stays within ``max_var_95`` of 1-day 95%
    historical VaR.

    Book VaR is *not* assumed monotonic in this instrument's own weight -- a new position can
    be a partial hedge against the rest of the book, in which case increasing it could lower
    book VaR -- so the largest feasible scale is found by a grid search over
    ``(0, proposed_weight]`` rather than a closed-form or bisected root. That search also
    runs when the rest of the book already breaches the limit: if some size of this position
    brings the book back within it, the largest such size is taken; only when no size does is
    the position flattened. Returns ``(scaled_weight, book_var_95_after, note)``; ``note`` is
    ``None`` when no scaling was needed (including when the check is off: ``max_var_95``
    falsy).

    The check fails closed: when the book's VaR cannot be evaluated (fewer than
    ``MIN_BOOK_OBS`` aligned observations, e.g. a held symbol with a short history) the
    position is flattened with a note saying so, never passed as if the check had run.
    """
    def var_at(c: float) -> float | None:
        w = dict(other_positions)
        w[symbol] = c * proposed_weight
        return book_var_95(w, returns, alpha)

    full = var_at(1.0)
    if proposed_weight == 0 or not max_var_95 or max_var_95 <= 0:
        return proposed_weight, full, None
    if symbol not in returns.columns:
        return 0.0, None, (f"book VaR could not be evaluated: no return history for {symbol}; "
                           f"flattened rather than sized")
    if full is None:
        port = book_returns({**other_positions, symbol: proposed_weight}, returns)
        n = 0 if port is None else int(port.size)
        return 0.0, None, (f"book VaR could not be evaluated: {n} aligned observations for the book "
                           f"with {symbol} (need {MIN_BOOK_OBS}); flattened rather than sized")
    if full <= max_var_95:
        return proposed_weight, full, None
    zero = var_at(0.0)
    rest_over = zero is None or zero > max_var_95
    zero_txt = "n/a" if zero is None else f"{zero:.2%}"
    cs = np.linspace(0.0, 1.0, grid)[1:]
    vs = [var_at(c) for c in cs]
    feasible = [c for c, v in zip(cs, vs) if v is not None and v <= max_var_95]
    if feasible:
        best = max(feasible)
        scaled = best * proposed_weight
        if rest_over:
            note = (f"book VaR {zero_txt} exceeds the {max_var_95:.2%} limit without this position; "
                    f"sized to the largest hedge that brings the book within it: "
                    f"{proposed_weight:+.2f} -> {scaled:+.2f}")
        else:
            note = f"book VaR limit {max_var_95:.2%}: {proposed_weight:+.2f} -> {scaled:+.2f}"
        return scaled, var_at(best), note
    if rest_over:
        return 0.0, zero, (f"book VaR {zero_txt} already exceeds the {max_var_95:.2%} limit without "
                          f"this position and no size of it brings the book within the limit; "
                          f"flattened rather than sized")
    return 0.0, zero, f"book VaR limit {max_var_95:.2%}: {proposed_weight:+.2f} -> +0.00"


# ----------------------------------------------------------- construction
@dataclass
class PortfolioWeights:
    symbols: list[str]
    allocation: np.ndarray        # the scheme's capital share per sleeve BEFORE vol-target scaling:
                                  # >= 0, each <= max_weight (raised to 1/k when max_weight < 1/k),
                                  # sums to gross_cap when any sleeve is active
    weights: np.ndarray           # signed final weights = allocation * desk target * scale,
                                  # |weights| <= the same per-sleeve cap and sum|weights| <= gross_cap
    method: str
    expected_vol: float           # annualised, of the signed weights
    contributions: pd.DataFrame   # per sleeve: allocation (pre-scale), weight, vol, marginal, component, pct
    diversification_ratio: float
    correlations: pd.DataFrame
    scale: float                  # vol-target scaling applied to the weights (1 = none)
    group_risk: pd.DataFrame | None = None   # per group: budget, allocation, share of risk
    converged: bool = True         # False if an iterative solver (min_variance, mean_variance)
                                   # hit its iteration cap before its tolerance: the allocation
                                   # is its best iterate, not a verified optimum (e.g. a covariance
                                   # near-singular from highly correlated sleeves)

    def to_dict(self) -> dict:
        d = {"method": self.method, "expected_vol": round(self.expected_vol, 4),
             "diversification_ratio": round(self.diversification_ratio, 3), "scale": round(self.scale, 4),
             "converged": self.converged,
             "weights": {s: round(float(w), 4) for s, w in zip(self.symbols, self.weights)}}
        if self.group_risk is not None:
            d["group_risk"] = self.group_risk.round(4).to_dict(orient="index")
        return d


def _allocate(method: str, sub: np.ndarray, cap: float, mu: np.ndarray | None,
              risk_aversion: float) -> tuple[np.ndarray, Convergence]:
    """Long-only allocation (sums to 1) of the active sleeves by one scheme, with whether it
    converged. The closed-form schemes (equal, inverse-vol, risk parity's fixed-point solve
    already tracks its own tolerance internally) are reported as converged; only the iterative
    optimisers can silently stop early."""
    k = sub.shape[0]
    if method == "equal":
        return equal_weights(k), Convergence(True, 0)
    if method == "inverse_vol":
        return inverse_vol_weights(sub), Convergence(True, 0)
    if method == "risk_parity":
        return risk_parity_weights(sub), Convergence(True, 0)
    if method == "min_variance":
        return min_variance_weights(sub, cap, return_info=True)
    return mean_variance_weights(mu, sub, risk_aversion, cap, return_info=True)


def construct(targets: dict[str, float], returns: pd.DataFrame, method: Method = "risk_parity",
              *, periods_per_year: float = 252.0, halflife: float | None = 60.0, shrink: bool = True,
              max_weight: float = 0.5, gross_cap: float = 1.0, target_vol: float | None = 0.15,
              risk_aversion: float = 5.0, expected_returns: dict[str, float] | None = None,
              groups: dict[str, str] | None = None,
              group_budgets: dict[str, float] | None = None) -> PortfolioWeights:
    """Allocate capital across the desk's signed targets.

    ``returns`` is a (T, N) frame of the instruments' daily returns up to the
    decision date (columns = symbols). Sleeves with a zero target get no capital.
    Every scheme's allocation is projected onto the capped simplex {a >= 0, a <= cap,
    sum a = 1} with cap = max(max_weight, 1/k) for k active sleeves (a cap below 1/k
    is infeasible), so no sleeve ever holds more than ``max_weight`` of capital; with
    group budgets the cap is enforced after the cross-group step too, overriding the
    budgets when they conflict (a hard limit beats a target). The weights are then
    scaled up to ``target_vol`` when their expected volatility is lower, with the
    scale capped so that neither ``gross_cap`` nor the per-sleeve cap is exceeded;
    ``allocation`` is the pre-scale split and ``scale`` the factor applied.

    Raises ``ValueError`` when the window cannot support an allocation (too few rows,
    a covariance with no positive variance, a non-finite solve), so a caller such as
    ``run_portfolio_backtest`` can keep its previous allocation rather than hold NaN.

    **Cross-asset risk budgets.** With ``groups`` (symbol -> group, e.g. the asset
    class) and ``group_budgets`` (group -> share of portfolio risk), allocation is
    hierarchical: ``method`` allocates *within* each group, each group's
    sub-portfolio is then treated as one asset, and risk parity with the given
    budgets allocates *across* groups using the full cross-group covariance. So an
    equity/FX book with budgets 0.6/0.4 has the equity sleeves contributing 60% of
    portfolio variance regardless of how many sleeves each side holds or how
    volatile they are. Groups with no active sleeve get nothing and the remaining
    budgets are renormalised.
    """
    if method not in METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {METHODS}")
    symbols = [s for s in targets if s in returns.columns]
    missing = [s for s in targets if s not in returns.columns]
    if missing:
        raise ValueError(f"no return history for {missing}")
    r = returns[symbols].to_numpy(float)
    r = r[np.isfinite(r).all(axis=1)]
    if r.shape[0] < 20:
        raise ValueError("need at least 20 rows of returns to estimate a covariance")
    n = len(symbols)
    cov = estimate_cov(r, halflife, shrink)
    tgt = np.array([float(targets[s]) for s in symbols])
    active = tgt != 0
    alloc = np.zeros(n)
    cap = 1.0
    group_risk = None
    converged = True
    if group_budgets is not None:
        if groups is None:
            raise ValueError("group_budgets needs groups (symbol -> group)")
        if any(b < 0 for b in group_budgets.values()) or sum(group_budgets.values()) <= 0:
            raise ValueError("group budgets must be non-negative and not all zero")
        unknown = sorted({groups.get(s, "?") for s in symbols} - set(group_budgets))
        if unknown:
            raise ValueError(f"no risk budget for group(s) {unknown}")
    if active.any():
        if not (np.diag(cov)[active] > 0).any():
            raise ValueError("no active sleeve has positive variance in this window: nothing to allocate on")
        k = int(active.sum())
        cap = min(1.0, max(max_weight, 1.0 / k))  # a cap below 1/k is infeasible on the simplex
        mu_all = np.array([(expected_returns or {}).get(s, targets[s]) for s in symbols])
        if group_budgets is None:
            sub = cov[np.ix_(active, active)]
            a, info = _allocate(method, sub, cap, mu_all[active], risk_aversion)
            converged = info.converged
            if not np.isfinite(a).all():
                raise ValueError(f"{method} allocation is not finite: degenerate covariance window")
            alloc[active] = _simplex_box_projection(a, cap)
        else:
            live = [g for g in group_budgets if any(active[i] and groups[s] == g for i, s in enumerate(symbols))]
            if not live:
                raise ValueError("no active sleeve in any budgeted group")
            # Within-group allocation, each as a column of a (n x G) portfolio matrix.
            P = np.zeros((n, len(live)))
            for j, g in enumerate(live):
                idx = [i for i, s in enumerate(symbols) if active[i] and groups[s] == g]
                subg = cov[np.ix_(idx, idx)]
                capg = min(1.0, max(max_weight, 1.0 / len(idx)))
                a, info = _allocate(method, subg, capg, mu_all[idx], risk_aversion)
                converged = converged and info.converged
                if not np.isfinite(a).all():
                    raise ValueError(f"{method} allocation for group {g!r} is not finite: "
                                     f"degenerate covariance window")
                P[idx, j] = _simplex_box_projection(a, capg)
            # Across groups: risk parity with the budgets on the group covariance.
            cov_g = P.T @ cov @ P
            budget = np.array([group_budgets[g] for g in live], float)
            b = risk_parity_weights(cov_g, budget / budget.sum())
            alloc = P @ b
            rc_g = risk_contributions(b, cov_g)
            group_risk = pd.DataFrame({"budget": budget / budget.sum(), "allocation": b,
                                       "risk_share": rc_g["pct"]}, index=live)
            if alloc.max() > cap + 1e-12:
                log.warning("per-sleeve cap %.3f overrides the group risk budgets (a budgeted group "
                            "concentrates in too few sleeves); the reported group risk shares are "
                            "those of the budgeted allocation before the cap", cap)
                alloc[active] = _simplex_box_projection(alloc[active], cap)
        if not np.isfinite(alloc).all() or alloc.sum() <= 0:
            raise ValueError(f"{method} allocation is not finite: degenerate covariance window")
        alloc *= gross_cap / alloc.sum()
    w = alloc * np.sign(tgt) * np.minimum(np.abs(tgt), 1.0)
    rc = risk_contributions(w, cov * periods_per_year)
    scale = 1.0
    if target_vol and rc["vol"] > 0 and rc["vol"] < target_vol:
        scale = max(1.0, min(target_vol / rc["vol"], gross_cap / np.abs(w).sum(),
                             cap * gross_cap / np.abs(w).max()))
        w = w * scale
        rc = risk_contributions(w, cov * periods_per_year)
    sd = np.sqrt(np.diag(cov) * periods_per_year)
    contrib = pd.DataFrame({"allocation": alloc, "weight": w, "vol": sd, "marginal": rc["marginal"],
                            "component": rc["component"], "pct_of_risk": rc["pct"]}, index=symbols).round(4)
    with np.errstate(invalid="ignore", divide="ignore"):   # a zero-variance pair has no correlation: NaN
        corr = pd.DataFrame(cov / np.outer(np.sqrt(np.diag(cov)), np.sqrt(np.diag(cov))),
                            index=symbols, columns=symbols).round(3)
    if not converged:
        log.warning("%s allocation did not converge within its iteration cap; the result is "
                    "the solver's best iterate, not a verified optimum (check for near-"
                    "duplicate or highly correlated sleeves)", method)
    return PortfolioWeights(symbols, alloc, w, method, rc["vol"], contrib, rc["diversification_ratio"],
                            corr, scale, group_risk, converged)
