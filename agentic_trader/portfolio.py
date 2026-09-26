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

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

Method = Literal["equal", "inverse_vol", "risk_parity", "min_variance", "mean_variance"]
METHODS: tuple[str, ...] = ("equal", "inverse_vol", "risk_parity", "min_variance", "mean_variance")


# -------------------------------------------------------------- covariance
def ewma_cov(returns: np.ndarray, halflife: float = 60.0) -> np.ndarray:
    """Exponentially weighted covariance (most recent row last)."""
    r = np.asarray(returns, float)
    if r.ndim != 2 or r.shape[0] < 2:
        raise ValueError("returns must be a (T, N) array with T >= 2")
    if halflife <= 0:
        raise ValueError("halflife must be positive")
    lam = 0.5 ** (1.0 / halflife)
    w = lam ** np.arange(r.shape[0] - 1, -1, -1)
    w /= w.sum()
    mu = w @ r
    d = r - mu
    return (d * w[:, None]).T @ d


def sample_cov(returns: np.ndarray) -> np.ndarray:
    r = np.asarray(returns, float)
    if r.ndim != 2 or r.shape[0] < 2:
        raise ValueError("returns must be a (T, N) array with T >= 2")
    return np.cov(r, rowvar=False, ddof=1).reshape(r.shape[1], r.shape[1])


def ledoit_wolf_shrink(returns: np.ndarray, cov: np.ndarray | None = None) -> tuple[np.ndarray, float]:
    """Shrink a covariance toward the constant-correlation target (Ledoit & Wolf 2004).

    Returns the shrunk matrix and the shrinkage intensity in [0, 1].
    """
    r = np.asarray(returns, float)
    t, n = r.shape
    s = sample_cov(r) if cov is None else np.asarray(cov, float)
    if n == 1:
        return s.copy(), 0.0
    sd = np.sqrt(np.diag(s))
    corr = s / np.outer(sd, sd)
    rbar = (corr.sum() - n) / (n * (n - 1))
    target = rbar * np.outer(sd, sd)
    np.fill_diagonal(target, np.diag(s))
    x = r - r.mean(axis=0)
    prod = x[:, :, None] * x[:, None, :]                     # (T, N, N): x_it x_jt
    # pi_ij: asymptotic variance of the sample covariance entries
    pi_mat = ((prod - s) ** 2).mean(axis=0)
    pi = pi_mat.sum()
    # theta_ii,ij = mean_t (x_it^2 - s_ii)(x_it x_jt - s_ij)
    theta = ((x ** 2 - np.diag(s))[:, :, None] * (prod - s)).mean(axis=0)
    # rho: covariance between the errors of S and of the constant-correlation target
    ratio = sd[None, :] / sd[:, None]                        # sqrt(s_jj / s_ii)
    off = ~np.eye(n, dtype=bool)
    rho = np.trace(pi_mat) + (rbar / 2.0) * ((ratio * theta)[off].sum() + (ratio.T * theta.T)[off].sum())
    gamma = ((target - s) ** 2).sum()
    kappa = (pi - rho) / gamma if gamma > 0 else 0.0
    delta = float(min(1.0, max(0.0, kappa / t)))
    return delta * target + (1 - delta) * s, delta


def estimate_cov(returns: np.ndarray, halflife: float | None = 60.0, shrink: bool = True) -> np.ndarray:
    cov = ewma_cov(returns, halflife) if halflife else sample_cov(returns)
    if shrink and np.asarray(returns).shape[1] > 1:
        cov, _ = ledoit_wolf_shrink(returns, cov)
    return cov


# ------------------------------------------------------------- weighting
def _simplex_box_projection(v: np.ndarray, cap: float) -> np.ndarray:
    """Project onto {w >= 0, w <= cap, sum w = 1} (bisection on the shift)."""
    if cap * v.size < 1.0 - 1e-12:
        raise ValueError("cap too small: N * cap must be >= 1")
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


def min_variance_weights(cov: np.ndarray, cap: float = 1.0, iters: int = 2000) -> np.ndarray:
    """Long-only minimum variance with a per-asset cap (projected gradient)."""
    c = np.asarray(cov, float)
    n = c.shape[0]
    w = _simplex_box_projection(equal_weights(n), cap)
    lipschitz = 2 * max(np.linalg.eigvalsh(c).max(), 1e-12)
    for _ in range(iters):
        g = 2 * c @ w
        w_new = _simplex_box_projection(w - g / lipschitz, cap)
        if np.abs(w_new - w).max() < 1e-10:
            return w_new
        w = w_new
    return w


def mean_variance_weights(mu: np.ndarray, cov: np.ndarray, risk_aversion: float = 5.0,
                          cap: float = 1.0, iters: int = 2000) -> np.ndarray:
    """Long-only max of mu'w - (lambda/2) w'Sigma w on the capped simplex."""
    c, m = np.asarray(cov, float), np.asarray(mu, float)
    if risk_aversion <= 0:
        raise ValueError("risk_aversion must be positive")
    n = c.shape[0]
    w = _simplex_box_projection(equal_weights(n), cap)
    lipschitz = risk_aversion * max(np.linalg.eigvalsh(c).max(), 1e-12)
    for _ in range(iters):
        g = -m + risk_aversion * c @ w
        w_new = _simplex_box_projection(w - g / lipschitz, cap)
        if np.abs(w_new - w).max() < 1e-10:
            return w_new
        w = w_new
    return w


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


# ----------------------------------------------------------- construction
@dataclass
class PortfolioWeights:
    symbols: list[str]
    allocation: np.ndarray        # capital share per sleeve (>= 0, sums to <= gross cap)
    weights: np.ndarray           # signed final weights = allocation * desk target
    method: str
    expected_vol: float           # annualised, of the signed weights
    contributions: pd.DataFrame   # per sleeve: allocation, weight, vol, marginal, component, pct
    diversification_ratio: float
    correlations: pd.DataFrame
    scale: float                  # vol-target scaling applied (1 = none)
    group_risk: pd.DataFrame | None = None   # per group: budget, allocation, share of risk

    def to_dict(self) -> dict:
        d = {"method": self.method, "expected_vol": round(self.expected_vol, 4),
             "diversification_ratio": round(self.diversification_ratio, 3), "scale": round(self.scale, 4),
             "weights": {s: round(float(w), 4) for s, w in zip(self.symbols, self.weights)}}
        if self.group_risk is not None:
            d["group_risk"] = self.group_risk.round(4).to_dict(orient="index")
        return d


def _allocate(method: str, sub: np.ndarray, cap: float, mu: np.ndarray | None,
              risk_aversion: float) -> np.ndarray:
    """Long-only allocation (sums to 1) of the active sleeves by one scheme."""
    k = sub.shape[0]
    if method == "equal":
        return equal_weights(k)
    if method == "inverse_vol":
        return inverse_vol_weights(sub)
    if method == "risk_parity":
        return risk_parity_weights(sub)
    if method == "min_variance":
        return min_variance_weights(sub, cap)
    return mean_variance_weights(mu, sub, risk_aversion, cap)


def construct(targets: dict[str, float], returns: pd.DataFrame, method: Method = "risk_parity",
              *, periods_per_year: float = 252.0, halflife: float | None = 60.0, shrink: bool = True,
              max_weight: float = 0.5, gross_cap: float = 1.0, target_vol: float | None = 0.15,
              risk_aversion: float = 5.0, expected_returns: dict[str, float] | None = None,
              groups: dict[str, str] | None = None,
              group_budgets: dict[str, float] | None = None) -> PortfolioWeights:
    """Allocate capital across the desk's signed targets.

    ``returns`` is a (T, N) frame of the instruments' daily returns up to the
    decision date (columns = symbols). Sleeves with a zero target get no capital.
    The result is scaled to ``target_vol`` when its expected volatility is lower
    (never levered above ``gross_cap``), and per-sleeve weights are capped.

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
    group_risk = None
    if group_budgets is not None:
        if groups is None:
            raise ValueError("group_budgets needs groups (symbol -> group)")
        if any(b < 0 for b in group_budgets.values()) or sum(group_budgets.values()) <= 0:
            raise ValueError("group budgets must be non-negative and not all zero")
        unknown = sorted({groups.get(s, "?") for s in symbols} - set(group_budgets))
        if unknown:
            raise ValueError(f"no risk budget for group(s) {unknown}")
    if active.any():
        k = int(active.sum())
        cap = min(1.0, max(max_weight, 1.0 / k))  # a cap below 1/k is infeasible on the simplex
        mu_all = np.array([(expected_returns or {}).get(s, targets[s]) for s in symbols])
        if group_budgets is None:
            sub = cov[np.ix_(active, active)]
            a = _allocate(method, sub, cap, mu_all[active], risk_aversion)
            alloc[active] = np.minimum(a, cap)
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
                a = _allocate(method, subg, capg, mu_all[idx], risk_aversion)
                P[idx, j] = np.minimum(a, capg) / max(np.minimum(a, capg).sum(), 1e-12)
            # Across groups: risk parity with the budgets on the group covariance.
            cov_g = P.T @ cov @ P
            budget = np.array([group_budgets[g] for g in live], float)
            b = risk_parity_weights(cov_g, budget / budget.sum())
            alloc = P @ b
            rc_g = risk_contributions(b, cov_g)
            group_risk = pd.DataFrame({"budget": budget / budget.sum(), "allocation": b,
                                       "risk_share": rc_g["pct"]}, index=live)
        alloc *= gross_cap / alloc.sum() if alloc.sum() > 0 else 1.0
    w = alloc * np.sign(tgt) * np.minimum(np.abs(tgt), 1.0)
    rc = risk_contributions(w, cov * periods_per_year)
    scale = 1.0
    if target_vol and rc["vol"] > 0 and rc["vol"] < target_vol:
        scale = min(target_vol / rc["vol"], gross_cap / max(np.abs(w).sum(), 1e-12))
        w = w * scale
        alloc = alloc * scale
        rc = risk_contributions(w, cov * periods_per_year)
    sd = np.sqrt(np.diag(cov) * periods_per_year)
    contrib = pd.DataFrame({"allocation": alloc, "weight": w, "vol": sd, "marginal": rc["marginal"],
                            "component": rc["component"], "pct_of_risk": rc["pct"]}, index=symbols).round(4)
    corr = pd.DataFrame(cov / np.outer(np.sqrt(np.diag(cov)), np.sqrt(np.diag(cov))),
                        index=symbols, columns=symbols).round(3)
    return PortfolioWeights(symbols, alloc, w, method, rc["vol"], contrib, rc["diversification_ratio"],
                            corr, scale, group_risk)
