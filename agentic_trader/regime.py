"""Regime labelling with a small Gaussian hidden Markov model (PLAN.md item 5.2).

Three daily features per bar, each using bars up to that bar only:

* ``log_vol``: log of the 20-day realised volatility (annualised);
* ``trend``: the 60-day return divided by the 60-day volatility;
* ``rate_change``: the 20-day change in the risk-free rate (percentage points), the
  provider's 3-month bill series.

A 2- or 3-state HMM with diagonal Gaussian emissions is fitted by Baum-Welch (EM) in
numpy, on bars from ``fit_start`` up to the *earlier* of the as-of date and ``fit_end``
(the design end), so the model never sees the holdout and never sees past the decision.
Labels are the forward-filtered state probabilities (``P(state_t | x_1..x_t)``, not the
smoothed ones, which would use later bars). States are ordered by their mean volatility,
so label 0 is the calmest regime and label ``K - 1`` the most stressed.

The label is exposed to the agents as a fact (``config["regime"]["enabled"]``) and, with
``config["regime"]["condition"]``, conditions the IC combination: ICs and the sizing
volatility come only from bars in the current regime (``combine.desk_forecast``).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

REGIME_NAMES = {2: ("calm", "stressed"), 3: ("calm", "normal", "stressed")}

# Fitted models keyed by a digest of the exact fitting rows and K: a walk-forward that
# refits on the same rows (the fit end truncated to a month start) reuses the fit.
_FIT_CACHE: dict[tuple[str, int], tuple["GaussianHMM", np.ndarray, np.ndarray]] = {}
_FIT_CACHE_MAX = 512


def regime_features(close: pd.Series, risk_free: np.ndarray | None = None, periods_per_year: float = 252.0) -> pd.DataFrame:
    """The three features, indexed like ``close``; rows with any NaN are left NaN."""
    r = close.astype(float).pct_change()
    vol20 = r.rolling(20).std() * math.sqrt(periods_per_year)
    vol60 = r.rolling(60).std() * math.sqrt(60)
    trend = (close / close.shift(60) - 1.0) / vol60.where(vol60 > 0)
    rf = pd.Series(np.zeros(len(close)) if risk_free is None else np.asarray(risk_free, float), index=close.index)
    return pd.DataFrame(
        {"log_vol": np.log(vol20.where(vol20 > 0)), "trend": trend, "rate_change": rf - rf.shift(20)}, index=close.index
    )


@dataclass
class GaussianHMM:
    """Diagonal-covariance Gaussian HMM. ``means`` and ``variances`` are ``K x D``,
    ``trans`` ``K x K`` (rows sum to one), ``start`` length ``K``. States are sorted by the
    mean of feature 0 (``log_vol``) after fitting."""

    means: np.ndarray
    variances: np.ndarray
    trans: np.ndarray
    start: np.ndarray

    @property
    def k(self) -> int:
        return self.means.shape[0]

    def _loglik(self, x: np.ndarray) -> np.ndarray:
        d = x[:, None, :] - self.means[None, :, :]
        return -0.5 * (np.log(2 * np.pi * self.variances)[None] + d * d / self.variances[None]).sum(axis=2)

    def filtered(self, x: np.ndarray) -> np.ndarray:
        """``P(state_t | x_1..x_t)`` for every row of ``x`` (``T x K``); forward pass only."""
        ll = self._loglik(np.asarray(x, float))
        out = np.empty_like(ll)
        a = self.start.copy()
        for t in range(ll.shape[0]):
            if t:
                a = out[t - 1] @ self.trans
            e = np.exp(ll[t] - ll[t].max())
            p = a * e
            out[t] = p / p.sum()
        return out

    def labels(self, x: np.ndarray) -> np.ndarray:
        return self.filtered(x).argmax(axis=1)


def fit_hmm(x: np.ndarray, k: int = 2, n_iter: int = 100, tol: float = 1e-6) -> GaussianHMM:
    """Baum-Welch on ``x`` (``T x D``, no NaN), initialised from quantiles of feature 0 so
    the fit is deterministic. Variances are floored at 1e-4 of each feature's variance."""
    x = np.asarray(x, float)
    if x.ndim != 2 or not np.isfinite(x).all():
        raise ValueError("x must be a finite T x D array")
    t, dim = x.shape
    if k not in (2, 3):
        raise ValueError("k must be 2 or 3")
    if t < 10 * k:
        raise ValueError(f"{t} rows are too few for a {k}-state fit")
    floor = 1e-4 * x.var(axis=0) + 1e-12
    order = np.argsort(x[:, 0], kind="stable")
    chunks = np.array_split(order, k)
    means = np.array([x[c].mean(axis=0) for c in chunks])
    variances = np.array([np.maximum(x[c].var(axis=0), floor) for c in chunks])
    trans = np.full((k, k), 0.05 / (k - 1))
    np.fill_diagonal(trans, 0.95)
    start = np.full(k, 1.0 / k)
    model = GaussianHMM(means, variances, trans, start)
    prev = -np.inf
    for _ in range(n_iter):
        ll = model._loglik(x)
        m = ll.max(axis=1, keepdims=True)
        e = np.exp(ll - m)
        alpha = np.empty((t, k))
        c = np.empty(t)
        a = model.start * e[0]
        c[0] = a.sum()
        alpha[0] = a / c[0]
        for i in range(1, t):
            a = (alpha[i - 1] @ model.trans) * e[i]
            c[i] = a.sum()
            alpha[i] = a / c[i]
        beta = np.ones((t, k))
        for i in range(t - 2, -1, -1):
            beta[i] = (model.trans @ (e[i + 1] * beta[i + 1])) / c[i + 1]
        gamma = alpha * beta
        gamma /= gamma.sum(axis=1, keepdims=True)
        xi = model.trans * (alpha[:-1].T @ (e[1:] * beta[1:] / c[1:, None]))
        total = float(np.log(c).sum() + m.sum())
        w = gamma.sum(axis=0) + 1e-12
        model = GaussianHMM(
            means=(gamma.T @ x) / w[:, None],
            variances=np.maximum((gamma.T @ (x * x)) / w[:, None] - ((gamma.T @ x) / w[:, None]) ** 2, floor),
            trans=xi / xi.sum(axis=1, keepdims=True),
            start=gamma[0] / gamma[0].sum(),
        )
        if total - prev < tol * abs(total):
            break
        prev = total
    srt = np.argsort(model.means[:, 0], kind="stable")
    return GaussianHMM(model.means[srt], model.variances[srt], model.trans[np.ix_(srt, srt)], model.start[srt])


class RegimeSeries:
    """Filtered regime labels for every prefix of one price series.

    The features and, per fitted model, the forward-filtered state probabilities are computed
    once for the whole series. Both are causal (row ``t`` uses rows ``<= t`` from the same
    first bar), so the labels of the prefix ending at bar ``end`` are a slice of them, equal
    to the labels computed on that prefix alone. A walk-forward that refits monthly therefore
    runs one forward pass per refit instead of one per decision.
    """

    def __init__(self, close: pd.Series, risk_free: np.ndarray | None = None, periods_per_year: float = 252.0):
        feats = regime_features(close, risk_free, periods_per_year)
        self.index = close.index
        self.x = feats.to_numpy(float)
        self.ok = feats.notna().all(axis=1).to_numpy()
        self._filtered: dict[tuple[str, int], np.ndarray] = {}

    def labels(
        self, end: int, k: int, fit_start: pd.Timestamp | None, fit_end: pd.Timestamp
    ) -> tuple[np.ndarray, np.ndarray | None, GaussianHMM | None]:
        """``regime_labels`` for the prefix of bars ``0..end``."""
        n = end + 1
        ok, idx, x = self.ok[:n], self.index[:n], self.x[:n]
        fit = ok & (idx <= min(fit_end, idx[-1]))
        if fit_start is not None:
            fit &= idx >= fit_start
        labels = np.full(n, -1)
        if fit.sum() < 10 * k:
            return labels, None, None
        key = (hashlib.sha256(np.ascontiguousarray(x[fit]).tobytes()).hexdigest(), k)
        hit = _FIT_CACHE.get(key)
        if hit is None:
            mu, sd = x[fit].mean(axis=0), x[fit].std(axis=0)
            sd = np.where(sd > 0, sd, 1.0)
            hit = (fit_hmm((x[fit] - mu) / sd, k), mu, sd)
            if len(_FIT_CACHE) >= _FIT_CACHE_MAX:
                _FIT_CACHE.pop(next(iter(_FIT_CACHE)))
            _FIT_CACHE[key] = hit
        model, mu, sd = hit
        full = self._filtered.get(key)
        if full is None:
            full = model.filtered(((self.x - mu) / sd)[self.ok])
            self._filtered[key] = full
        probs = full[: int(ok.sum())]
        labels[ok] = probs.argmax(axis=1)
        return labels, (probs[-1] if ok[-1] else None), model


def regime_labels(
    close: pd.Series,
    risk_free: np.ndarray | None,
    k: int,
    fit_start: pd.Timestamp | None,
    fit_end: pd.Timestamp,
    periods_per_year: float = 252.0,
) -> tuple[np.ndarray, np.ndarray | None, GaussianHMM | None]:
    """Filtered labels for every bar of ``close`` (``-1`` where the features are undefined),
    from an HMM fitted on bars in ``[fit_start, min(fit_end, last bar)]``.

    Features are standardised with the mean and standard deviation of the fitting rows.
    Returns ``(labels, probs, model)``: ``probs`` is the filtered state distribution at the
    last bar (``None`` when that bar has no label). ``model`` is ``None`` (all labels
    ``-1``) when too few rows are available to fit.
    """
    return RegimeSeries(close, risk_free, periods_per_year).labels(len(close) - 1, k, fit_start, fit_end)
