"""Statistics for judging a backtest: is the Sharpe ratio real, and did selection
inflate it?

* ``sharpe_ci_bootstrap``  circular block bootstrap confidence interval.
* ``probabilistic_sharpe`` probability that the true Sharpe exceeds a benchmark,
  given sample length, skewness and kurtosis (Bailey & Lopez de Prado, 2012).
* ``deflated_sharpe``      the same probability after adjusting the benchmark for
  the number of strategy variants tried and the dispersion of their Sharpe
  ratios (Bailey & Lopez de Prado, 2014).
* ``min_track_record``     how many periods are needed before a Sharpe ratio is
  significant at a given confidence.

Sharpe ratios inside these formulas are per period (daily); the public helpers
convert from annualised figures where they take them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

_N = NormalDist()
EULER_GAMMA = 0.5772156649015329


@dataclass(frozen=True)
class SharpeStats:
    n: int
    mean: float          # per-period mean return
    std: float           # per-period std (ddof = 1)
    skew: float
    kurt: float          # non-excess (normal = 3)
    sharpe: float        # per period
    sharpe_annual: float
    t_stat: float        # sharpe * sqrt(n)


def sharpe_stats(returns, periods_per_year: float = 252.0) -> SharpeStats:
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = int(r.size)
    if n < 3:
        return SharpeStats(n, 0.0, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0)
    mean, std = float(r.mean()), float(r.std(ddof=1))
    if std <= 0:
        return SharpeStats(n, mean, 0.0, 0.0, 3.0, 0.0, 0.0, 0.0)
    z = (r - mean) / r.std(ddof=0)
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    sr = mean / std
    return SharpeStats(n, mean, std, skew, kurt, sr, sr * math.sqrt(periods_per_year), sr * math.sqrt(n))


def sharpe_ci_bootstrap(returns, periods_per_year: float = 252.0, n_boot: int = 2000,
                        block: int = 10, ci: float = 0.95, seed: int = 0) -> tuple[float, float]:
    """Annualised Sharpe confidence interval from a circular block bootstrap.

    Blocks preserve short-range autocorrelation; ``block`` of about 10 days is a
    reasonable default for daily returns.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n = r.size
    if n < 3 or block < 1 or n_boot < 10 or not 0 < ci < 1:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    starts = rng.integers(0, n, size=(n_boot, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n] % n
    samples = r[idx]
    mean = samples.mean(axis=1)
    std = samples.std(axis=1, ddof=1)
    sr = np.where(std > 0, mean / np.where(std > 0, std, 1.0), 0.0) * math.sqrt(periods_per_year)
    lo, hi = np.quantile(sr, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    return (float(lo), float(hi))


def probabilistic_sharpe(sr: float, n: int, skew: float = 0.0, kurt: float = 3.0,
                         sr_benchmark: float = 0.0) -> float:
    """P(true Sharpe > benchmark). ``sr`` and ``sr_benchmark`` are per period."""
    if n <= 1:
        return float("nan")
    var_term = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if var_term <= 0:
        return float("nan")
    z = (sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(var_term)
    return _N.cdf(z)


def expected_max_sharpe(n_trials: int, var_trials_sr: float) -> float:
    """Expected maximum per-period Sharpe among ``n_trials`` null strategies whose
    Sharpe ratios have variance ``var_trials_sr`` (the DSR benchmark, SR0)."""
    if n_trials <= 1 or var_trials_sr <= 0:
        return 0.0
    n = float(n_trials)
    return math.sqrt(var_trials_sr) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n)
                                       + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n * math.e)))


def deflated_sharpe(sr: float, n: int, n_trials: int, var_trials_sr: float,
                    skew: float = 0.0, kurt: float = 3.0) -> float:
    """PSR of ``sr`` against the expected maximum of ``n_trials`` null trials.

    All Sharpe ratios per period. ``var_trials_sr`` is the variance of the
    per-period Sharpe ratios across the variants that were tried.
    """
    return probabilistic_sharpe(sr, n, skew, kurt, expected_max_sharpe(n_trials, var_trials_sr))


def min_track_record(sr: float, sr_benchmark: float = 0.0, skew: float = 0.0, kurt: float = 3.0,
                     confidence: float = 0.95) -> float:
    """Periods needed for ``sr`` (per period) to beat the benchmark at ``confidence``.
    Infinite when the Sharpe ratio does not exceed the benchmark."""
    if sr <= sr_benchmark:
        return float("inf")
    z = _N.inv_cdf(confidence)
    var_term = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    return 1.0 + var_term * (z / (sr - sr_benchmark)) ** 2


def selection_report(chosen_returns, trial_sharpes_annual, periods_per_year: float = 252.0) -> dict:
    """Everything a reader needs to judge a chosen variant after a search.

    ``trial_sharpes_annual`` are the annualised Sharpe ratios of every variant tried
    (including the chosen one).
    """
    s = sharpe_stats(chosen_returns, periods_per_year)
    trials = np.asarray(trial_sharpes_annual, dtype=float) / math.sqrt(periods_per_year)
    n_trials = int(trials.size)
    var_trials = float(trials.var(ddof=1)) if n_trials > 1 else 0.0
    sr0 = expected_max_sharpe(n_trials, var_trials)
    lo, hi = sharpe_ci_bootstrap(chosen_returns, periods_per_year)
    return {
        "n": s.n, "sharpe_annual": round(s.sharpe_annual, 3), "t_stat": round(s.t_stat, 2),
        "skew": round(s.skew, 3), "kurtosis": round(s.kurt, 2),
        "bootstrap_ci_95": (round(lo, 3), round(hi, 3)),
        "psr_vs_zero": round(probabilistic_sharpe(s.sharpe, s.n, s.skew, s.kurt), 3),
        "trials": n_trials, "expected_max_sharpe_annual": round(sr0 * math.sqrt(periods_per_year), 3),
        "deflated_sharpe_prob": round(deflated_sharpe(s.sharpe, s.n, n_trials, var_trials, s.skew, s.kurt), 3),
        "min_track_record_periods": (None if not math.isfinite(m := min_track_record(s.sharpe, sr0, s.skew, s.kurt))
                                     else round(m)),
    }
