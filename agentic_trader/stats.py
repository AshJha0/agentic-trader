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
* ``paired_bootstrap``     bootstrap over *instruments*: is the mean per-instrument
  difference between two strategies (Sharpe, drawdown, ...) distinguishable
  from zero across the universe, not just along time?

Sharpe ratios inside these formulas are per period (daily); the public helpers
convert from annualised figures where they take them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from . import quant

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


DEFLATED_SHARPE_CAVEAT = (
    "an upper bound on the true significance: the benchmark is built from the dispersion of "
    "trial_sharpes_annual, which is usually narrower than the dispersion of the full return "
    "series each trial would have produced, so the true search space is wider than this "
    "reports and the real probability is no higher than the number given."
)


def selection_report(chosen_returns, trial_sharpes_annual, periods_per_year: float = 252.0) -> dict:
    """Everything a reader needs to judge a chosen variant after a search.

    ``trial_sharpes_annual`` are the annualised Sharpe ratios of every variant tried
    (including the chosen one). The probabilities in the result are an upper bound
    (``DEFLATED_SHARPE_CAVEAT``, attached as ``"caveat"`` so it travels with the number
    wherever this dict is printed or logged, not only where the docs happen to repeat it).
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
        "caveat": DEFLATED_SHARPE_CAVEAT if n_trials > 1 else None,
    }


# ------------------------------------------------------ across instruments
@dataclass(frozen=True)
class PairedBootstrap:
    n: int                   # instruments with both values
    mean_diff: float         # mean(a - b) over instruments
    ci_low: float            # bootstrap percentile interval of the mean difference
    ci_high: float
    p_value: float           # two-sided: share of resamples on the other side of zero, doubled
    wins: int                # instruments where a > b

    @property
    def significant(self) -> bool:
        """Significant at the nominal (uncorrected) level. When several ``PairedBootstrap``
        results are reported together (one evaluation prints a paired test per period per
        baseline per universe), reading each one's ``significant`` flag on its own is a
        multiple-comparisons problem the same way trying many rule variants is -- correct
        with ``benjamini_hochberg`` over the whole set's ``p_value``s before trusting any
        one flag in a table of many."""
        return self.n >= 3 and (self.ci_low > 0 or self.ci_high < 0)


def benjamini_hochberg(p_values, q: float = 0.05) -> np.ndarray:
    """Which of several p-values are still significant after controlling the false discovery
    rate at ``q`` (Benjamini & Hochberg, 1995).

    Returns a boolean array the same length as ``p_values``. Reporting many paired-bootstrap
    or other significance tests side by side (as the evaluation's per-period, per-baseline,
    per-universe tables do) is exactly the repeated-testing problem the deflated Sharpe ratio
    corrects for when choosing among rule variants; this is the analogous correction for a
    table of significance flags read together rather than a single winner chosen from trials.
    NaN p-values (fewer than three instruments) are never significant.
    """
    p = np.asarray(p_values, dtype=float)
    m = p.size
    out = np.zeros(m, dtype=bool)
    finite = np.isfinite(p)
    if m == 0 or not finite.any():
        return out
    idx = np.argsort(np.where(finite, p, np.inf))
    ranked = p[idx]
    k = np.arange(1, m + 1)
    thresh = k / m * q
    ok = finite[idx] & (ranked <= thresh)
    if not ok.any():
        return out
    # BH: reject every hypothesis up to the largest k whose own p clears its threshold.
    largest = np.max(np.where(ok)[0])
    out[idx[:largest + 1]] = finite[idx[:largest + 1]]
    return out


def paired_bootstrap(a, b, n_boot: int = 10_000, ci: float = 0.95, seed: int = 0,
                     groups=None) -> PairedBootstrap:
    """Bootstrap the mean paired difference ``a - b`` across instruments.

    The time-series bootstrap (``sharpe_ci_bootstrap``) asks whether one instrument's
    Sharpe is real. This asks the other question the evaluation needs: given one number
    per instrument for two strategies on the same instruments and bars, is the *average*
    edge across the universe more than the luck of which instruments were picked? It
    resamples instruments with replacement (pairs kept together), so it makes no
    assumption about the distribution of per-instrument differences, only that the
    instruments are exchangeable draws from the universe of interest.

    That exchangeability assumption is false when the universe mixes clusters of highly
    correlated instruments -- e.g. nine rate/credit/commodity ETFs that mostly move
    together, next to unrelated equities -- because plain resampling can by chance draw an
    unusually large or small share of one cluster far more easily than it could if every
    instrument moved independently, which understates the true resampling variance and
    makes the interval too tight. Pass ``groups`` (one label per instrument, the same length
    as ``a``/``b``) to resample *within* each group instead, keeping every group's own count
    fixed across replicates: this is the standard stratified-bootstrap fix and needs no
    assumption about the correlation structure inside or between groups, only that groups are
    chosen so instruments within one are the ones plausibly correlated. ``groups=None``
    (the default) is the original unstratified behaviour, correct when the universe already
    is close to exchangeable (e.g. one asset class of broadly similar instruments).

    NaN pairs are dropped. Fewer than three pairs gives NaN bounds and ``p_value = 1``.
    """
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.shape != b.shape:
        raise ValueError("a and b must have the same length (one value per instrument)")
    if groups is not None:
        groups = np.asarray(groups)
        if groups.shape != a.shape:
            raise ValueError("groups must be the same length as a and b")
    d = a - b
    ok = np.isfinite(d)
    d = d[ok]
    if groups is not None:
        groups = groups[ok]
    n = int(d.size)
    if n == 0:
        return PairedBootstrap(0, float("nan"), float("nan"), float("nan"), 1.0, 0)
    mean = float(d.mean())
    wins = int((d > 0).sum())
    if n < 3 or n_boot < 10 or not 0 < ci < 1:
        return PairedBootstrap(n, mean, float("nan"), float("nan"), 1.0, wins)
    rng = np.random.default_rng(seed)
    if groups is None or np.unique(groups).size < 2:
        idx = rng.integers(0, n, size=(n_boot, n))
        means = d[idx].mean(axis=1)
    else:
        pieces = []
        for g in np.unique(groups):
            gi = np.flatnonzero(groups == g)
            samp = rng.integers(0, gi.size, size=(n_boot, gi.size))
            pieces.append(d[gi][samp])
        means = np.concatenate(pieces, axis=1).mean(axis=1)
    lo, hi = np.quantile(means, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    tail = float(min((means <= 0).mean(), (means >= 0).mean()))
    return PairedBootstrap(n, mean, float(lo), float(hi), min(1.0, 2.0 * tail), wins)


# --------------------------------------------------------------- VaR coverage
def rolling_var_forecast(returns, window: int = 250, alpha: float = 0.95) -> np.ndarray:
    """The historical VaR (a non-negative loss fraction) forecast *for* day ``t``, using only
    returns strictly before it (``returns[t-window:t]``): no look-ahead. NaN for the first
    ``window`` observations, where there is no trailing window yet.

    This is the same rule ``agents.risk.risk_facts`` applies live at each decision (a trailing
    historical quantile), reproduced here to check that rule's *calibration* against a whole
    return series after the fact: whether the desk's own claimed 1-day VaR is realistic.
    """
    r = np.asarray(returns, dtype=float)
    out = np.full(r.size, np.nan)
    for t in range(window, r.size):
        w = r[t - window:t]
        w = w[np.isfinite(w)]
        if w.size >= 20:
            out[t] = quant.historical_var(w, alpha)
    return out


@dataclass(frozen=True)
class VarBacktest:
    """Whether a VaR forecast series was well calibrated against what actually happened.

    ``breach_rate`` should sit near ``1 - alpha``; ``kupiec_p`` tests exactly that
    (unconditional coverage: are there the *right number* of breaches). ``christoffersen_p``
    tests whether breaches cluster in time rather than landing independently (a VaR model can
    have the right average breach rate and still fail badly if breaches come in runs, which is
    exactly when a risk desk needs the limit to have worked). ``conditional_coverage_p``
    combines both into a single test. A low p-value in any of the three is evidence the model
    is *not* calibrated on that dimension; this checks calibration, it does not by itself imply
    the position sizes built on top of an uncalibrated VaR were wrong in any particular
    direction.
    """
    n: int
    breaches: int
    breach_rate: float
    expected_rate: float
    kupiec_lr: float
    kupiec_p: float
    christoffersen_lr: float | None   # None when there are too few breaches to test independence
    christoffersen_p: float | None
    conditional_coverage_p: float | None


def _binom_loglik(x: int, n: int, p: float) -> float:
    """``x*log(p) + (n-x)*log(1-p)``, with the convention ``0 * log(0) = 0`` (so a rate of
    exactly 0 or 1 never raises, matching the boundary cases of the Kupiec/Christoffersen
    likelihood-ratio tests)."""
    t1 = 0.0 if x == 0 else x * math.log(p)
    t2 = 0.0 if x == n else (n - x) * math.log(1.0 - p)
    return t1 + t2


def _chi2_1df_p(lr: float) -> float:
    """P(chi-square_1 >= lr), via chi-square_1 = Z^2 for standard normal Z."""
    if not math.isfinite(lr) or lr < 0:
        return float("nan")
    return 2.0 * (1.0 - _N.cdf(math.sqrt(lr)))


def _chi2_2df_p(lr: float) -> float:
    """P(chi-square_2 >= lr): the chi-square_2 survival function has a closed form, exp(-lr/2)."""
    if not math.isfinite(lr) or lr < 0:
        return float("nan")
    return math.exp(-lr / 2.0)


def var_backtest(returns, var_forecasts, alpha: float = 0.95) -> VarBacktest:
    """Kupiec (1995) unconditional coverage and Christoffersen (1998) independence tests for a
    VaR forecast series against what actually happened.

    ``returns`` and ``var_forecasts`` are aligned, same-length series (``var_forecasts[t]`` is
    the VaR *magnitude* -- a non-negative number, ``historical_var``'s convention -- known
    before ``returns[t]`` was realized; ``rolling_var_forecast`` produces exactly this). A pair
    is a *breach* when the realized return is worse than the forecast loss: ``returns[t] <
    -var_forecasts[t]``. NaN pairs (including the warm-up window) are dropped.

    Both likelihood-ratio statistics are asymptotically chi-square under their null (1 degree
    of freedom each; their sum, the conditional-coverage test, is chi-square with 2). With
    fewer than two breaches, streaks cannot be assessed and the Christoffersen and combined
    p-values are ``None``.
    """
    r, v = np.asarray(returns, dtype=float), np.asarray(var_forecasts, dtype=float)
    if r.shape != v.shape:
        raise ValueError("returns and var_forecasts must have the same length")
    ok = np.isfinite(r) & np.isfinite(v)
    r, v = r[ok], v[ok]
    n = int(r.size)
    p = 1.0 - alpha
    if n == 0:
        return VarBacktest(0, 0, float("nan"), p, float("nan"), float("nan"), None, None, None)
    breach = r < -v
    x = int(breach.sum())
    rate = x / n
    lr_uc = 2.0 * (_binom_loglik(x, n, rate) - _binom_loglik(x, n, p))
    lr_uc = max(lr_uc, 0.0)
    kupiec_p = _chi2_1df_p(lr_uc)

    lr_ind = p_cc = None
    if x >= 2 and n > x:
        b = breach.astype(int)
        n00 = int(np.sum((b[:-1] == 0) & (b[1:] == 0)))
        n01 = int(np.sum((b[:-1] == 0) & (b[1:] == 1)))
        n10 = int(np.sum((b[:-1] == 1) & (b[1:] == 0)))
        n11 = int(np.sum((b[:-1] == 1) & (b[1:] == 1)))
        p01 = n01 / (n00 + n01) if (n00 + n01) else 0.0
        p11 = n11 / (n10 + n11) if (n10 + n11) else 0.0
        p_bar = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
        ll_restricted = _binom_loglik(n01 + n11, n00 + n01 + n10 + n11, p_bar)
        ll_unrestricted = _binom_loglik(n01, n00 + n01, p01) + _binom_loglik(n11, n10 + n11, p11)
        lr_ind = max(2.0 * (ll_unrestricted - ll_restricted), 0.0)
        p_ind = _chi2_1df_p(lr_ind)
        p_cc = _chi2_2df_p(lr_uc + lr_ind)
    else:
        p_ind = None
    return VarBacktest(n, x, rate, p, round(lr_uc, 4), round(kupiec_p, 4),
                       None if lr_ind is None else round(lr_ind, 4), p_ind,
                       None if p_cc is None else round(p_cc, 4))
