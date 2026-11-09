"""GJR-GARCH(1,1) VaR/ES and the Acerbi-Szekely ES backtest (v0.17, review item C4).

Plain idea. EWMA (``risk_model``) is a GARCH with a fixed decay and no mean reversion: after a
shock its variance never returns to a long-run level, and it treats a 3 % fall like a 3 % rise.
GJR-GARCH estimates the decay, the long-run level and a leverage term (falls raise volatility
more than rises) from the data.

Formal statement (Glosten, Jagannathan and Runkle, 1993). With zero-mean daily returns ``r``:

    sigma2_t = omega + (alpha + gamma * 1[r_{t-1} < 0]) * r_{t-1}^2 + beta * sigma2_{t-1}

fitted by Gaussian quasi-maximum likelihood under ``omega > 0``, ``alpha, gamma, beta >= 0``
and ``alpha + gamma / 2 + beta < 1``. ``VaR_t = z * sigma_t`` and
``ES_t = sigma_t * phi(z) / (1 - level)`` with ``z = Phi^{-1}(level)``.

The optimiser is SciPy's Nelder-Mead when SciPy is importable and a Nelder-Mead written here
otherwise (infeasible points get a huge penalty) (SciPy is not a dependency of this package; the two agree to the tolerance the
tests pin). No new dependency is added.

ES backtest (Acerbi and Szekely, 2014, test 2). With ``I_t`` the VaR breach indicator,

    Z2 = 1 - sum_t (-r_t) * I_t / (T * (1 - level) * ES_t)

has mean 0 when the ES forecasts are right and is negative when they understate the tail.
The p-value is the share of ``n_sim`` simulated paths (drawn from the forecast distribution,
normal with ``sigma_t = VaR_t / z``) whose Z2 is at or below the observed one.

Worked example. A 95 % forecast with ``sigma = 1 %`` gives VaR 1.64 % and ES 2.06 %. If, over
1000 days, 50 breaches average a 2.06 % loss, the sum is ``50 * 2.06 / (1000 * 0.05 * 2.06) = 1``
and Z2 = 0. Losses averaging 3 % give Z2 = ``1 - 3 / 2.06 = -0.46``: the tail is understated.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

_N = NormalDist()


@dataclass(frozen=True)
class GJRParams:
    omega: float
    alpha: float
    gamma: float
    beta: float

    @property
    def persistence(self) -> float:
        return self.alpha + 0.5 * self.gamma + self.beta

    @property
    def long_run_var(self) -> float:
        p = self.persistence
        return self.omega / (1.0 - p) if p < 1 else float("inf")


def gjr_variance(r: np.ndarray, p: GJRParams, s2_0: float | None = None) -> np.ndarray:
    """Conditional variances ``sigma2_t`` for ``t = 0..len(r)`` (the last one is the forecast for
    the day after the series): element ``t`` uses ``r[:t]`` only. A non-finite return is
    replaced by its expectation (``E[r^2] = sigma2``, half the days negative), so the variance
    follows its expected path ``omega + persistence * sigma2`` across the gap."""
    n = r.size
    out = np.empty(n + 1)
    # seed: the caller's trailing estimate, else the model's own long-run variance (no data,
    # so no look-ahead); a non-stationary fit falls back to omega / (1 - beta)
    if s2_0 is not None:
        s2 = float(s2_0)
    elif p.persistence < 1:
        s2 = p.long_run_var
    else:
        s2 = p.omega / max(1e-12, 1.0 - p.beta)
    out[0] = s2
    for t in range(n):
        x = r[t]
        if math.isfinite(x):
            s2 = p.omega + (p.alpha + (p.gamma if x < 0 else 0.0)) * x * x + p.beta * s2
        else:
            s2 = p.omega + p.persistence * s2
        out[t + 1] = s2
    return out


def _neg_loglik(theta: np.ndarray, r: np.ndarray, s2_0: float) -> float:
    omega, alpha, gamma, beta = theta
    if omega <= 0 or alpha < 0 or gamma < 0 or beta < 0 or alpha + 0.5 * gamma + beta >= 0.9999:
        return 1e100
    s2 = s2_0
    nll = 0.0
    for x in r:
        if not math.isfinite(x):
            continue
        if s2 <= 0:
            return 1e100
        nll += math.log(s2) + x * x / s2
        s2 = omega + (alpha + (gamma if x < 0 else 0.0)) * x * x + beta * s2
    return 0.5 * nll


def _nelder_mead(f, x0: np.ndarray, step: np.ndarray, iters: int = 2000, tol: float = 1e-10) -> np.ndarray:
    n = x0.size
    simplex = [x0] + [x0 + np.eye(n)[i] * step[i] for i in range(n)]
    vals = [f(x) for x in simplex]
    for _ in range(iters):
        order = np.argsort(vals)
        simplex = [simplex[i] for i in order]
        vals = [vals[i] for i in order]
        if abs(vals[-1] - vals[0]) <= tol * (abs(vals[0]) + 1e-12):
            break
        c = np.mean(simplex[:-1], axis=0)
        xr = c + (c - simplex[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = c + 2.0 * (c - simplex[-1])
            fe = f(xe)
            simplex[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            simplex[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (simplex[-1] - c)
            fc = f(xc)
            if fc < vals[-1]:
                simplex[-1], vals[-1] = xc, fc
            else:
                simplex = [simplex[0]] + [simplex[0] + 0.5 * (s - simplex[0]) for s in simplex[1:]]
                vals = [vals[0]] + [f(s) for s in simplex[1:]]
    return simplex[int(np.argmin(vals))]


def fit_gjr(returns, use_scipy: bool | None = None) -> GJRParams:
    """Gaussian QMLE of GJR-GARCH(1,1) on zero-mean returns (non-finite values skipped).
    ``use_scipy`` None = SciPy when importable."""
    r = np.asarray(returns, dtype=float)
    fin = r[np.isfinite(r)]
    if fin.size < 100:
        raise ValueError(f"GJR-GARCH needs at least 100 finite returns, got {fin.size}")
    v = float(np.var(fin))
    s2_0 = float(np.mean(fin[: min(50, fin.size)] ** 2))
    x0 = np.array([0.05 * v, 0.05, 0.05, 0.85])
    f = lambda th: _neg_loglik(th, r, s2_0)  # noqa: E731
    best = None
    if use_scipy is not False:
        try:
            from scipy.optimize import minimize  # type: ignore[import-untyped]
            res = minimize(f, x0, method="Nelder-Mead", options={"maxiter": 4000, "xatol": 1e-10, "fatol": 1e-10})
            best = np.asarray(res.x)
        except ImportError:
            if use_scipy:
                raise
    if best is None:
        best = _nelder_mead(f, x0, np.array([0.04 * v, 0.03, 0.03, 0.05]))
        best = _nelder_mead(f, best, np.array([0.02 * v, 0.01, 0.01, 0.02]))   # restart: NM can stall
    return GJRParams(*(float(max(b, 0.0)) for b in best))


def gjr_var_es_forecast(returns, level: float = 0.95, window: int = 500, refit_every: int = 250,
                        params: GJRParams | None = None) -> tuple[np.ndarray, np.ndarray]:
    """1-day VaR and ES (non-negative loss fractions) forecast *for* each day ``t`` from returns
    strictly before it, aligned with ``returns`` like ``risk_model.var_forecast``. NaN for the
    first ``window`` days. Parameters are refitted every ``refit_every`` days on the trailing
    ``window`` returns (or held at ``params`` when given)."""
    if not 0.5 < level < 1.0:
        raise ValueError(f"level must be in (0.5, 1), got {level}")
    r = np.asarray(returns, dtype=float)
    n = r.size
    var = np.full(n, np.nan)
    es = np.full(n, np.nan)
    z = _N.inv_cdf(level)
    es_mult = _N.pdf(z) / (1.0 - level)
    t = window
    while t < n:
        p = params or fit_gjr(r[t - window:t])
        end = min(n, t + refit_every)
        s2 = gjr_variance(r[:end], p, s2_0=float(np.nanmean(r[max(0, t - window):t] ** 2)))
        sig = np.sqrt(s2[t:end])
        var[t:end] = z * sig
        es[t:end] = es_mult * sig
        t = end
    return var, es


def simulate_gjr(n: int, p: GJRParams, seed: int = 0, burn: int = 500) -> np.ndarray:
    """A zero-mean Gaussian GJR-GARCH return path of length ``n`` (after ``burn`` discarded)."""
    rng = np.random.default_rng(seed)
    e = rng.standard_normal(n + burn)
    s2 = p.long_run_var if p.persistence < 1 else p.omega
    out = np.empty(n + burn)
    for t in range(n + burn):
        out[t] = math.sqrt(s2) * e[t]
        s2 = p.omega + (p.alpha + (p.gamma if out[t] < 0 else 0.0)) * out[t] ** 2 + p.beta * s2
    return out[burn:]


def acerbi_szekely_z2(returns, var, es, level: float = 0.95) -> float:
    """Acerbi-Szekely Z2 on aligned series (``var``, ``es`` positive loss fractions; pairs with
    any NaN dropped)."""
    r, v, e = (np.asarray(x, dtype=float) for x in (returns, var, es))
    m = np.isfinite(r) & np.isfinite(v) & np.isfinite(e) & (e > 0)
    r, v, e = r[m], v[m], e[m]
    if r.size == 0:
        return float("nan")
    hit = r < -v
    return float(1.0 - np.sum(-r[hit] / e[hit]) / (r.size * (1.0 - level)))


def es_backtest(returns, var, es, level: float = 0.95, n_sim: int = 2000, seed: int = 0) -> dict[str, float]:
    """Z2 and its one-sided simulated p-value (small = ES understates the tail) under the
    normal forecast distribution implied by ``var`` (``sigma_t = VaR_t / z``)."""
    r, v, e = (np.asarray(x, dtype=float) for x in (returns, var, es))
    m = np.isfinite(r) & np.isfinite(v) & np.isfinite(e) & (e > 0)
    r, v, e = r[m], v[m], e[m]
    z2 = acerbi_szekely_z2(r, v, e, level)
    if r.size == 0:
        return {"z2": z2, "p": float("nan"), "n": 0.0}
    sig = v / _N.inv_cdf(level)
    rng = np.random.default_rng(seed)
    sims = rng.standard_normal((n_sim, r.size)) * sig
    hit = sims < -v
    z2s = 1.0 - np.sum(np.where(hit, -sims / e, 0.0), axis=1) / (r.size * (1.0 - level))
    return {"z2": z2, "p": float((np.sum(z2s <= z2) + 1) / (n_sim + 1)), "n": float(r.size)}
