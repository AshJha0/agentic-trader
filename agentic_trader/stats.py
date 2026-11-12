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
* ``paired_bootstrap``     bootstrap over *instruments* (or over clusters of correlated
  instruments): is the mean per-instrument difference between two strategies
  (Sharpe, drawdown, ...) distinguishable from zero across the universe, not
  just along time?

Sharpe ratios inside these formulas are per period (daily); the public helpers
convert from annualised figures where they take them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from . import quant
from .bootstrap import null_centred_pvalue

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
    if std <= quant.ZERO_VARIANCE_TOL * max(1.0, abs(mean)):
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
    sr = _sharpe_rows(r[idx], periods_per_year)
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
    Sharpe ratios have variance ``var_trials_sr`` (the DSR benchmark, SR0).

    WARNING (review 2026-11-12, C1). The benchmark assumes the trial Sharpes are null draws
    centred on zero: only their *dispersion* enters. Long-biased trials that share one equity
    beta all sit near a common mean (about 1.3 annualised in v0.11) with a small spread, so
    SR0 is small and any of them, including the no-desk vol-target control, "passes". Applied
    to absolute Sharpe ratios this is therefore not a test of selection skill; it is kept
    unchanged for the record (every published DSR used it). The selection statistic is
    ``deflated_sharpe_differential`` (chosen minus control, trials measured the same way)."""
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


ABSOLUTE_SELECTION_STATISTIC = (
    "absolute Sharpe against the dispersion of absolute trial Sharpes: NOT a selection test when "
    "the trials share a common mean (review C1); read deflated_sharpe_prob_differential")
DIFFERENTIAL_SELECTION_STATISTIC = "Sharpe of chosen-minus-control daily returns (differential DSR)"


def null_trial_sharpe_variance(n: int, sr: float = 0.0, skew: float = 0.0, kurt: float = 3.0) -> float:
    """Sampling variance of a per-period Sharpe estimate over ``n`` periods (Mertens/Lo form,
    the PSR denominator): ``(1 - skew*sr + (kurt - 1)/4 * sr^2) / (n - 1)``.

    Under the null that no trial beats the control, each trial's differential Sharpe is pure
    estimation noise around zero, so this is the dispersion ``expected_max_sharpe`` should use
    when the trials' own differential Sharpes were not stored. It treats the trials as
    independent; correlated trials make the resulting benchmark too strict, never too lenient.
    Worked example: n = 1564 daily periods, normal returns, sr = 0: 1 / 1563 = 6.398e-4
    (standard deviation 0.0253 per period, 0.408 annualised at 260)."""
    if n <= 1:
        return float("nan")
    return (1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr) / (n - 1)


def deflated_sharpe_differential(chosen_returns, control_returns, n_trials: int,
                                 periods_per_year: float = 252.0, trial_returns=None,
                                 trial_sharpes_vs_control_annual=None) -> dict:
    """Deflated Sharpe of the chosen variant's *excess over a control* (review C1).

    Plain idea: every trial here is a long-biased book on the same names, so their absolute
    Sharpe ratios share a common mean (the equity premium of the window). Selection skill is
    what the chosen variant adds over a control that took no decisions (the vol-target core),
    so the statistic is the Sharpe of ``d_t = chosen_t - control_t`` and the trials must be
    measured the same way, ``Sharpe(trial_t - control_t)``.

    Formal: ``SR_d`` (per period) is tested with ``probabilistic_sharpe`` against
    ``SR0 = expected_max_sharpe(n_trials, V)``. ``V`` is, in order of preference: the variance
    of the trials' differential Sharpes (``trial_returns``, a periods x trials matrix on the
    same days, or ``trial_sharpes_vs_control_annual``); otherwise
    ``null_trial_sharpe_variance(n)``, the sampling variance of a zero-skill differential
    Sharpe (``benchmark_variance_source`` says which).

    Worked example (``tests/test_round2_stats.py``): a control with annual Sharpe 1.3 and a
    "chosen" book equal to the control plus 0.1 % daily noise has absolute DSR close to 1 at
    81 trials under the old benchmark, but its differential DSR is below 0.5: it added nothing.
    """
    a = np.asarray(chosen_returns, dtype=float)
    c = np.asarray(control_returns, dtype=float)
    if a.shape != c.shape:
        raise ValueError("chosen_returns and control_returns must be aligned (same length)")
    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    d = a - c
    s = sharpe_stats(d, periods_per_year)
    source = "null sampling variance (trials independent, zero differential skill)"
    diff_trials: np.ndarray | None = None
    if trial_returns is not None:
        t = np.asarray(trial_returns, dtype=float)
        if t.ndim != 2 or t.shape[0] != c.size:
            raise ValueError("trial_returns must be (periods x trials) on the control's days")
        diff_trials = np.array([sharpe_stats(t[:, k] - c, periods_per_year).sharpe for k in range(t.shape[1])])
        source = "variance of the trials' differential Sharpes (from trial_returns)"
    elif trial_sharpes_vs_control_annual is not None:
        diff_trials = np.asarray(trial_sharpes_vs_control_annual, dtype=float) / math.sqrt(periods_per_year)
        source = "variance of the trials' differential Sharpes (given)"
    n_used = n_trials
    if diff_trials is not None and diff_trials[np.isfinite(diff_trials)].size > 1:
        var = float(np.var(diff_trials[np.isfinite(diff_trials)], ddof=1))
        n_used = max(n_trials, int(np.isfinite(diff_trials).sum()))
    else:
        var = null_trial_sharpe_variance(s.n)
        if diff_trials is not None:
            source = "null sampling variance (fewer than two trial differential Sharpes)"
    sr0 = expected_max_sharpe(n_used, var) if math.isfinite(var) else float("nan")
    dsr = probabilistic_sharpe(s.sharpe, s.n, s.skew, s.kurt, sr0) if math.isfinite(sr0) else float("nan")
    mtr = min_track_record(s.sharpe, sr0, s.skew, s.kurt) if math.isfinite(sr0) else float("inf")
    return {"selection_statistic": DIFFERENTIAL_SELECTION_STATISTIC, "n": s.n, "trials": n_used,
            "sharpe_annual": s.sharpe_annual, "skew": s.skew, "kurtosis": s.kurt,
            "benchmark_variance_source": source,
            "expected_max_sharpe_annual": sr0 * math.sqrt(periods_per_year),
            "deflated_sharpe_prob": dsr,
            "psr_vs_zero": probabilistic_sharpe(s.sharpe, s.n, s.skew, s.kurt),
            "min_track_record_periods": None if not math.isfinite(mtr) else mtr}


def selection_report(chosen_returns, trial_sharpes_annual, periods_per_year: float = 252.0,
                     n_trials: int | None = None, pre_registry_trials: int = 0,
                     trial_returns=None, control_returns=None,
                     trial_sharpes_vs_control_annual=None) -> dict:
    """Everything a reader needs to judge a chosen variant after a search.

    Which statistic (review 2026-11-12, C1): ``"selection_statistic"`` says it. Without
    ``control_returns`` the deflated Sharpe is the absolute one (``ABSOLUTE_SELECTION_STATISTIC``:
    kept for the record, not a selection test when the trials share a mean). With
    ``control_returns`` (the no-decision control on the same days) the report also carries
    ``deflated_sharpe_prob_differential`` and its inputs (``deflated_sharpe_differential``,
    trials from ``trial_returns`` or ``trial_sharpes_vs_control_annual`` when given), and that
    is the selection statistic. The pre-existing keys keep their values in both cases.

    ``trial_sharpes_annual`` are the annualised Sharpe ratios of every variant tried
    (including the chosen one) and must be the *same statistic on the same data* as the
    Sharpe of ``chosen_returns`` (v0.8 compared a portfolio Sharpe with per-instrument mean
    Sharpes, which understated the trials' dispersion; ``"statistic_warning"`` is set when the
    chosen Sharpe lies more than three trial standard deviations above the best trial, the
    signature of that mismatch). The probabilities in the result are an upper bound
    (``DEFLATED_SHARPE_CAVEAT``, attached as ``"caveat"`` so it travels with the number
    wherever this dict is printed or logged, not only where the docs happen to repeat it).

    ``n_trials`` (v0.16, PLAN 6.1) is the number of trials registered, when some have no
    Sharpe yet (pending LLM cells): the count used for the expected maximum is the larger of
    it and ``len(trial_sharpes_annual)``; the dispersion still comes from the measured ones.

    ``pre_registry_trials`` (v0.17, R1.3) is an estimate of the variants tried before the
    registry existed (rule constants, blends, lookbacks; ``evaluation.PRE_REGISTRY_TRIALS_ESTIMATE``).
    When positive the result also carries the deflated Sharpe at ``n_trials + pre_registry_trials``
    beside the registered-count figure; the registered count stays a floor, the sum a
    conservative ceiling of the search.

    ``trial_returns`` (v0.17 N8), a (periods x trials) matrix of the trials' return series,
    adds the DSR at the effective number of trials (``deflated_sharpe_effective``).
    """
    s = sharpe_stats(chosen_returns, periods_per_year)
    trials = np.asarray(trial_sharpes_annual, dtype=float) / math.sqrt(periods_per_year)
    n_measured = int(trials.size)
    if n_trials is not None and n_trials < 1:
        raise ValueError("n_trials must be >= 1")
    n_trials = max(n_measured, n_trials or 0)
    warning = None
    if n_measured > 1:
        sd_annual = float(np.std(trial_sharpes_annual, ddof=1))
        if s.sharpe_annual > float(np.max(trial_sharpes_annual)) + 3.0 * sd_annual:
            warning = ("chosen Sharpe exceeds the best trial by more than three trial standard deviations: "
                       "the trials are probably not the same statistic as the chosen series")
    var_trials = float(trials.var(ddof=1)) if n_measured > 1 else 0.0
    sr0 = expected_max_sharpe(n_trials, var_trials)
    lo, hi = sharpe_ci_bootstrap(chosen_returns, periods_per_year)
    return {
        "n": s.n, "sharpe_annual": round(s.sharpe_annual, 3), "t_stat": round(s.t_stat, 2),
        **({"statistic_warning": warning} if warning else {}),
        "skew": round(s.skew, 3), "kurtosis": round(s.kurt, 2),
        "bootstrap_ci_95": (round(lo, 3), round(hi, 3)),
        "psr_vs_zero": round(probabilistic_sharpe(s.sharpe, s.n, s.skew, s.kurt), 3),
        "trials": n_trials, "trials_measured": n_measured, "expected_max_sharpe_annual": round(sr0 * math.sqrt(periods_per_year), 3),
        "deflated_sharpe_prob": round(deflated_sharpe(s.sharpe, s.n, n_trials, var_trials, s.skew, s.kurt), 3),
        "min_track_record_periods": (None if not math.isfinite(m := min_track_record(s.sharpe, sr0, s.skew, s.kurt))
                                     else round(m)),
        "caveat": DEFLATED_SHARPE_CAVEAT if n_trials > 1 else None,
        **(_pre_registry_rows(s, n_trials, pre_registry_trials, var_trials, periods_per_year)
           if pre_registry_trials > 0 else {}),
        **(_effective_rows(s, trial_returns, var_trials) if trial_returns is not None else {}),
        "selection_statistic": ABSOLUTE_SELECTION_STATISTIC if control_returns is None
        else DIFFERENTIAL_SELECTION_STATISTIC,
        **(_differential_rows(chosen_returns, control_returns, n_trials, periods_per_year, trial_returns,
                              trial_sharpes_vs_control_annual) if control_returns is not None else {}),
    }


def _differential_rows(chosen_returns, control_returns, n_trials: int, periods_per_year: float,
                       trial_returns, trial_sharpes_vs_control_annual) -> dict:
    e = deflated_sharpe_differential(chosen_returns, control_returns, n_trials, periods_per_year,
                                     trial_returns=trial_returns,
                                     trial_sharpes_vs_control_annual=trial_sharpes_vs_control_annual)
    mtr = e["min_track_record_periods"]
    return {"differential_sharpe_annual": round(e["sharpe_annual"], 3),
            "differential_expected_max_sharpe_annual": round(e["expected_max_sharpe_annual"], 3),
            "differential_benchmark_variance_source": e["benchmark_variance_source"],
            "deflated_sharpe_prob_differential": round(e["deflated_sharpe_prob"], 3),
            "differential_min_track_record_periods": None if mtr is None else round(mtr)}


def _effective_rows(s: SharpeStats, trial_returns, var_trials: float) -> dict:
    e = deflated_sharpe_effective(s.sharpe, s.n, trial_returns, var_trials, s.skew, s.kurt)
    return {"trials_effective": round(e["n_eff"], 2), "trials_mean_corr": round(e["mean_corr"], 3),
            "deflated_sharpe_prob_effective": round(e["deflated_sharpe_prob"], 3),
            "effective_trials_method": "participation ratio of trial-return correlation eigenvalues; "
                                       "trial-Sharpe variance / (1 - mean correlation)"}


def _pre_registry_rows(s: SharpeStats, n_trials: int, pre: int, var_trials: float,
                       periods_per_year: float) -> dict:
    total = n_trials + int(pre)
    sr0 = expected_max_sharpe(total, var_trials)
    return {
        "trials_pre_registry_estimate": int(pre),
        "trials_incl_pre_registry": total,
        "expected_max_sharpe_annual_incl_pre_registry": round(sr0 * math.sqrt(periods_per_year), 3),
        "deflated_sharpe_prob_incl_pre_registry": round(
            deflated_sharpe(s.sharpe, s.n, total, var_trials, s.skew, s.kurt), 3),
    }


# ------------------------------------------------------ across instruments
@dataclass(frozen=True)
class PairedBootstrap:
    n: int                   # instruments with both values
    mean_diff: float         # mean(a - b) over instruments
    ci_low: float            # bootstrap percentile interval of the mean difference
    ci_high: float
    p_value: float           # two-sided, null-centred (bootstrap.null_centred_pvalue; round 2, C12)
    wins: int                # instruments where a > b
    scheme: str = "instruments"   # "instruments" (plain) or "clusters" (whole groups resampled)
    n_groups: int = 0        # distinct group labels among the finite pairs (0 when none were given)
    # the pre-round-2 p (share of resamples on the other side of zero, doubled), kept for comparison
    p_value_percentile: float = float("nan")
    # what the interval is conditional on (review C8): instruments are resampled, the time path is not
    conditioning: str = "conditional on the realised time path (instruments resampled, days fixed)"

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
    NaN p-values (rows that were never tested, e.g. fewer than three instruments) are never
    significant and do not count towards ``m``: only hypotheses that were actually tested share
    the false-discovery budget. Pass the p-values unrounded -- BH compares each one against a
    threshold ``k / m * q``, and rounding first can move a p across it in either direction.
    """
    p = np.asarray(p_values, dtype=float)
    out = np.zeros(p.size, dtype=bool)
    tested = np.flatnonzero(np.isfinite(p))
    m = tested.size
    if m == 0:
        return out
    order = tested[np.argsort(p[tested], kind="stable")]
    thresh = np.arange(1, m + 1) / m * q
    ok = p[order] <= thresh
    if not ok.any():
        return out
    # BH: reject every hypothesis up to the largest k whose own p clears its threshold.
    largest = int(np.max(np.flatnonzero(ok)))
    out[order[:largest + 1]] = True
    return out


MIN_CLUSTER_GROUPS = 5


def paired_bootstrap(a, b, n_boot: int = 10_000, ci: float = 0.95, seed: int = 0,
                     groups=None, min_groups: int = MIN_CLUSTER_GROUPS) -> PairedBootstrap:
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
    together, next to unrelated equities. A cluster's common shock is then one noisy draw
    shared by all its members, not nine independent ones, so the effective sample is closer
    to the number of clusters than to the number of instruments and plain resampling
    understates the sampling variance of the mean. Pass ``groups`` (one label per instrument,
    the same length as ``a``/``b``) to use a two-stage cluster bootstrap instead: each
    replicate draws whole groups with replacement, then instruments with replacement within
    each drawn group, and the replicate statistic is the pooled mean of the instruments drawn.
    Resampling whole groups is what carries the between-group (common-factor) variance into
    the interval; the within-group stage is deliberately kept because with a handful of
    groups the groups-only scheme is anti-conservative (its variance is biased by
    ``(G-1)/G`` and the percentile interval ignores the small-``G`` tail), and the extra
    within-group variance leans the other way -- Monte Carlo under a shared within-group
    factor puts this scheme's coverage of a true zero closest to nominal, and it errs
    conservative when the groups turn out to be independent (``tests/test_v08_stats.py``).

    The first stage draws clusters with equal probability whatever their size (each cluster
    is one draw: the standard cluster bootstrap), and the replicate statistic is the pooled
    mean over the instruments drawn, so a replicate that draws a large cluster several times
    is dominated by it and one that omits it is not. With markedly unequal cluster sizes
    (``--universe all``: 10/5/26/9/10) the replicate distribution is therefore not centred
    on ``mean_diff``: the percentile interval is not symmetric about it and the two-sided
    ``p_value`` inherits the same shift. This is the estimator's ratio-form bias, not an
    indexing artefact (a brute-force loop reproduces the vectorised numbers); read the
    interval's midpoint accordingly.

    Do NOT confuse this with the stratified bootstrap (resampling within each group with the
    group's count held fixed): that conditions on the group composition, so its variance is
    the pooled *within*-group variance only -- it can only narrow the interval relative to
    plain resampling and does nothing for within-cluster correlation.

    A cluster bootstrap needs enough clusters to resample: with fewer than ``min_groups``
    distinct labels among the finite pairs the plain instrument bootstrap is used instead and
    the result says so (``scheme="instruments"``, ``n_groups`` = the labels seen). Read a
    plain-scheme interval over a clustered universe as anti-conservative. ``groups=None``
    (the default) is the plain behaviour, appropriate when the universe is already close to
    exchangeable (one asset class of broadly similar instruments).

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
    n_groups = 0
    codes = None
    if groups is not None:
        _, codes = np.unique(groups[ok], return_inverse=True)
        n_groups = int(np.max(codes)) + 1 if codes.size else 0
    n = int(d.size)
    if n == 0:
        return PairedBootstrap(0, float("nan"), float("nan"), float("nan"), 1.0, 0, "instruments", n_groups)
    mean = float(d.mean())
    wins = int((d > 0).sum())
    clustered = n_groups >= max(2, min_groups)
    scheme = "clusters" if clustered else "instruments"
    if n < 3 or n_boot < 10 or not 0 < ci < 1:
        return PairedBootstrap(n, mean, float("nan"), float("nan"), 1.0, wins, scheme, n_groups)
    rng = np.random.default_rng(seed)
    if not clustered:
        idx = rng.integers(0, n, size=(n_boot, n))
        means = d[idx].mean(axis=1)
    else:
        assert codes is not None  # clustered implies groups were given
        means = _two_stage_cluster_means(d, codes, n_groups, n_boot, rng)
    lo, hi = np.quantile(means, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    tail = float(min((means <= 0).mean(), (means >= 0).mean()))
    return PairedBootstrap(n, mean, float(lo), float(hi), null_centred_pvalue(means, mean), wins, scheme,
                           n_groups, p_value_percentile=min(1.0, 2.0 * tail))


def _two_stage_cluster_means(d: np.ndarray, codes: np.ndarray, n_groups: int, n_boot: int,
                             rng: np.random.Generator) -> np.ndarray:
    """Replicate pooled means: ``n_groups`` groups drawn with replacement, then each drawn
    group's own size of instruments drawn with replacement from inside it."""
    sizes = np.bincount(codes, minlength=n_groups)
    widest = int(np.max(sizes))
    members = np.zeros((n_groups, widest), dtype=int)
    for g in range(n_groups):
        gi = np.flatnonzero(codes == g)
        members[g, :gi.size] = gi
    drawn = rng.integers(0, n_groups, size=(n_boot, n_groups))
    sz = sizes[drawn]
    # one uniform per padded slot, scaled to the drawn group's size; slots past it are masked
    within = np.minimum((rng.random(size=(n_boot, n_groups, widest)) * sz[:, :, None]).astype(int), widest - 1)
    picked = members[drawn[:, :, None], within]
    live = np.arange(widest)[None, None, :] < sz[:, :, None]
    return (d[picked] * live).sum(axis=(1, 2)) / sz.sum(axis=1)


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


# ------------------------------------------------------------- portfolio-level intervals
@dataclass(frozen=True)
class SharpeDifference:
    """Sharpe(a) - Sharpe(b) on the same days, with a paired circular block bootstrap over time."""
    n: int                    # days used (both series finite)
    sharpe_a: float
    sharpe_b: float
    diff: float
    ci_low: float
    ci_high: float
    p_value: float            # two-sided, null-centred (bootstrap.null_centred_pvalue; round 2, C12)
    block: int
    n_boot: int
    # the pre-round-2 p (share of resamples on the other side of zero, doubled), kept for comparison
    p_value_percentile: float = float("nan")


def _excess(r, rf, periods_per_year: float) -> np.ndarray:
    r = np.asarray(r, dtype=float)
    if rf is None:
        return r
    rf = np.asarray(rf, dtype=float)
    if rf.ndim == 0:
        return r - float(rf) / periods_per_year
    if rf.shape != r.shape:
        raise ValueError("rf must be a scalar or one annual rate per day")
    return r - np.where(np.isfinite(rf), rf, 0.0) / periods_per_year


def _sharpe_rows(x: np.ndarray, periods_per_year: float) -> np.ndarray:
    """Annualised Sharpe of every row, 0 where the row is constant to rounding (the
    ``quant.compute_metrics`` zero-variance rule, so a flat book reads 0 here as in the table)."""
    mean, sd = x.mean(axis=1), x.std(axis=1, ddof=1)
    real = sd > quant.ZERO_VARIANCE_TOL * np.maximum(1.0, np.abs(mean))
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(real, mean / np.where(real, sd, 1.0) * math.sqrt(periods_per_year), 0.0)


def paired_sharpe_block_bootstrap(a, b, periods_per_year: float = 252.0, rf=None, block: int = 10,
                                  n_boot: int = 5000, ci: float = 0.95, seed: int = 0) -> SharpeDifference:
    """Is one strategy's Sharpe higher than another's over the *same days*?

    The cross-instrument bootstrap (``paired_bootstrap``) treats instruments as the unit of
    independence, so it cannot speak to time-period luck that every instrument shared (one
    bear market, one rally). For a portfolio-level comparison the unit is the day: both daily
    return series are resampled with the same circular blocks (``block`` days, preserving
    short-range autocorrelation and the pairing), each resample's annualised Sharpe is taken on
    excess returns over ``rf`` (annual; a scalar or one rate per day, NaN = 0) and the
    percentile interval and two-sided p of the difference are reported. Days where either
    series is not finite are dropped; fewer than three days gives NaN bounds and ``p = 1``.
    """
    if block < 1 or n_boot < 1:
        raise ValueError("block and n_boot must be positive")
    ra, rb = _excess(a, rf, periods_per_year), _excess(b, rf, periods_per_year)
    if ra.shape != rb.shape:
        raise ValueError("a and b must have the same length (one return per day)")
    keep = np.isfinite(ra) & np.isfinite(rb)
    ra, rb = ra[keep], rb[keep]
    n = int(ra.size)
    nan = float("nan")
    if n < 3:
        return SharpeDifference(n, nan, nan, nan, nan, nan, 1.0, block, n_boot)
    sa = float(_sharpe_rows(ra[None, :], periods_per_year)[0])
    sb = float(_sharpe_rows(rb[None, :], periods_per_year)[0])
    rng = np.random.default_rng(seed)
    blk = min(block, n)
    starts = rng.integers(0, n, size=(n_boot, -(-n // blk)))
    idx = ((starts[:, :, None] + np.arange(blk)[None, None, :]) % n).reshape(n_boot, -1)[:, :n]
    diffs = _sharpe_rows(ra[idx], periods_per_year) - _sharpe_rows(rb[idx], periods_per_year)
    lo, hi = np.percentile(diffs, [100 * (1 - ci) / 2, 100 * (1 + ci) / 2])
    point = sa - sb
    if point == 0.0:
        p_pct = 1.0
    else:
        other = np.mean(diffs <= 0.0) if point > 0 else np.mean(diffs >= 0.0)
        p_pct = float(min(1.0, 2.0 * other))
    return SharpeDifference(n, sa, sb, point, float(lo), float(hi), null_centred_pvalue(diffs, point),
                            blk, n_boot, p_value_percentile=p_pct)


# ------------------------------------- time-block primary for paired tables (round 2, C8)
@dataclass(frozen=True)
class TimeBlockPaired:
    """Mean per-instrument Sharpe(a) - Sharpe(b), with the time-block interval as the primary.

    ``ci_low``/``ci_high``/``p_value`` resample *days* (circular blocks shared by every
    instrument, so a regime that moved every difference the same way is one draw, not N), and
    with ``two_way`` also instruments. ``secondary`` is the cross-instrument
    ``paired_bootstrap`` on the same per-instrument Sharpes: conditional on the realised path,
    reported beside the primary, never instead of it. p-values are null-centred (C12)."""
    n_days: int
    n_instruments: int
    mean_diff: float
    ci_low: float
    ci_high: float
    p_value: float
    scheme: str               # "time-block" or "two-way (instruments x time-block)"
    block: int
    n_boot: int
    secondary: PairedBootstrap

    @property
    def significant(self) -> bool:
        """Nominal-level flag on the primary interval (use ``paired_time_block_table`` for BH)."""
        return self.n_instruments >= 3 and (self.ci_low > 0 or self.ci_high < 0)


def _column_sharpes(x: np.ndarray, periods_per_year: float) -> np.ndarray:
    """Annualised Sharpe of every column over its finite rows (0 for constant, NaN for < 3 rows)."""
    ok = np.isfinite(x)
    cnt = ok.sum(axis=0)
    xz = np.where(ok, x, 0.0)
    mean = xz.sum(axis=0) / np.maximum(cnt, 1)
    dev = np.where(ok, x - mean, 0.0)
    sd = np.sqrt((dev ** 2).sum(axis=0) / np.maximum(cnt - 1, 1))
    real = sd > quant.ZERO_VARIANCE_TOL * np.maximum(1.0, np.abs(mean))
    with np.errstate(divide="ignore", invalid="ignore"):
        sr = np.where(real, mean / np.where(real, sd, 1.0) * math.sqrt(periods_per_year), 0.0)
    return np.where(cnt >= 3, sr, np.nan)


def paired_time_block(a, b, periods_per_year: float = 252.0, block: int = 10, n_boot: int = 2000,
                      ci: float = 0.95, seed: int = 0, two_way: bool = False, groups=None) -> TimeBlockPaired:
    """Time-block bootstrap of the mean per-instrument Sharpe difference (review C8).

    ``a`` and ``b`` are (days x instruments) daily return matrices for the two strategies on
    the same instruments and days (NaN where an instrument did not trade; a cell is used only
    where both are finite). The point estimate is the same quantity the cross-instrument
    tables report, ``mean_i [Sharpe(a_i) - Sharpe(b_i)]``; the interval resamples circular
    day blocks shared across instruments (``two_way`` also resamples instruments with
    replacement in each replicate). Worked example (``tests/test_round2_stats.py``): 20
    instruments whose differences all load on one common daily factor give a cross-instrument
    interval several times narrower than this one."""
    x, y = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if x.ndim != 2 or x.shape != y.shape:
        raise ValueError("a and b must be (days x instruments) matrices of the same shape")
    if block < 1 or n_boot < 10 or not 0 < ci < 1:
        raise ValueError("block >= 1, n_boot >= 10 and 0 < ci < 1 required")
    both = np.isfinite(x) & np.isfinite(y)
    x, y = np.where(both, x, np.nan), np.where(both, y, np.nan)
    d_inst = _column_sharpes(x, periods_per_year) - _column_sharpes(y, periods_per_year)
    secondary = paired_bootstrap(_column_sharpes(x, periods_per_year), _column_sharpes(y, periods_per_year),
                                 n_boot=max(n_boot, 10), ci=ci, seed=seed, groups=groups)
    live = np.isfinite(d_inst)
    n_t, k = x.shape[0], int(live.sum())
    scheme = "two-way (instruments x time-block)" if two_way else "time-block"
    nan = float("nan")
    if k == 0 or n_t < 3:
        return TimeBlockPaired(n_t, k, nan, nan, nan, 1.0, scheme, block, n_boot, secondary)
    x, y = x[:, live], y[:, live]
    point = float(np.mean(d_inst[live]))
    rng = np.random.default_rng(seed)
    blk = min(block, n_t)
    n_blocks = -(-n_t // blk)
    reps = np.empty(n_boot)
    for i in range(n_boot):
        idx = ((rng.integers(0, n_t, size=n_blocks)[:, None] + np.arange(blk)[None, :]) % n_t).ravel()[:n_t]
        cols = rng.integers(0, k, size=k) if two_way else slice(None)
        di = _column_sharpes(x[idx][:, cols], periods_per_year) - _column_sharpes(y[idx][:, cols], periods_per_year)
        reps[i] = np.nanmean(di) if np.isfinite(di).any() else np.nan
    reps = reps[np.isfinite(reps)]
    lo, hi = np.quantile(reps, [(1 - ci) / 2, 1 - (1 - ci) / 2])
    return TimeBlockPaired(n_t, k, point, float(lo), float(hi), null_centred_pvalue(reps, point), scheme,
                           blk, n_boot, secondary)


def paired_time_block_table(cases, periods_per_year: float = 252.0, fdr_q: float = 0.05, block: int = 10,
                            n_boot: int = 2000, seed: int = 0, two_way: bool = False) -> list[dict]:
    """The "BH-significant" paired table with the time-block interval as the primary (C8).

    ``cases``: iterable of dicts with ``label`` (e.g. ``"holdout / Buy&Hold"``), ``a`` and
    ``b`` (days x instruments return matrices) and optional ``groups``. Each row reports the
    primary (time-block) mean difference, interval and null-centred p; ``significant`` is
    Benjamini-Hochberg at ``fdr_q`` over the *primary* p-values of the rows in this table; the
    cross-instrument interval and p follow as ``secondary`` columns, labelled conditional on
    the realised path. This replaces reading ``evaluation.Evaluation.paired_table`` (which has
    only the per-instrument summary rows, not the daily series) as a significance headline."""
    rows, p = [], []
    for c in cases:
        r = paired_time_block(c["a"], c["b"], periods_per_year, block=block, n_boot=n_boot, seed=seed,
                              two_way=two_way, groups=c.get("groups"))
        pv = r.p_value if math.isfinite(r.ci_low) else float("nan")
        p.append(pv)
        s = r.secondary
        rows.append({"label": c["label"], "primary": r.scheme, "days": r.n_days, "n": r.n_instruments,
                     "mean Sharpe diff": r.mean_diff, "ci95 low": r.ci_low, "ci95 high": r.ci_high, "p": pv,
                     "secondary": "cross-instrument, " + s.conditioning,
                     "secondary ci95 low": s.ci_low, "secondary ci95 high": s.ci_high,
                     "secondary p": s.p_value})
    flags = benjamini_hochberg(np.asarray(p, dtype=float), fdr_q) if rows else np.zeros(0, dtype=bool)
    for row, f in zip(rows, flags):
        row["significant"] = bool(f)
    return rows


# ------------------------------------------------- HAC (Newey-West) inference, v0.17 R1.2
def newey_west_lag(n: int, horizon: int = 1) -> int:
    """Bartlett-kernel truncation lag: the Newey-West (1994) plug-in rule
    ``floor(4 * (n / 100) ** (2 / 9))``, raised to ``horizon`` when the series is built from
    overlapping ``horizon``-bar returns (neighbouring observations then share ``horizon - 1``
    bars, so the autocovariance is non-zero out to at least that lag). Worked example:
    n = 1000, horizon 1 -> floor(4 * 10 ** (2/9)) = 6; horizon 10 -> 10."""
    if n < 1:
        raise ValueError("n must be >= 1")
    auto = int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0)))
    return max(auto, int(horizon), 0) if n > 1 else 0


@dataclass(frozen=True)
class NeweyWest:
    mean: float
    se: float        # HAC standard error of the mean
    t: float         # mean / se
    lag: int         # Bartlett truncation lag used
    n: int           # finite observations
    n_eff: float     # n * gamma0 / long-run variance (<= n under positive autocorrelation)

    @property
    def p_value(self) -> float:
        """Two-sided normal p-value of ``t`` (HAC t is asymptotically normal)."""
        return 2.0 * (1.0 - _N.cdf(abs(self.t))) if math.isfinite(self.t) else float("nan")


def newey_west_t(x, lag: int | None = None, horizon: int = 1) -> NeweyWest:
    """t-statistic of the mean of ``x`` with a Newey-West (1987) HAC standard error.

    Plain idea: autocorrelated observations carry less information than their count, so the
    standard error of the mean must include the autocovariances. Formal: with
    ``g_j = (1/n) sum_{t>j} (x_t - m)(x_{t-j} - m)`` the long-run variance is
    ``S = g_0 + 2 sum_{j=1..L} (1 - j / (L + 1)) g_j`` and ``se = sqrt(S / n)``. ``L`` is
    ``newey_west_lag(n, horizon)`` unless given. NaNs are dropped (the series is read in
    order; gaps are closed, which slightly overstates dependence across them). Fewer than
    three finite values, or ``S <= 0``, gives NaN ``t``.
    """
    v = np.asarray(x, dtype=float)
    v = v[np.isfinite(v)]
    n = int(v.size)
    if n < 3:
        return NeweyWest(float(v.mean()) if n else float("nan"), float("nan"), float("nan"), 0, n, float("nan"))
    L = newey_west_lag(n, horizon) if lag is None else int(lag)
    L = min(max(L, 0), n - 1)
    m = float(v.mean())
    d = v - m
    g0 = float(d @ d) / n
    s = g0
    for j in range(1, L + 1):
        s += 2.0 * (1.0 - j / (L + 1.0)) * float(d[j:] @ d[:-j]) / n
    if s <= 0 or g0 <= 0:
        return NeweyWest(m, float("nan"), float("nan"), L, n, float("nan"))
    se = math.sqrt(s / n)
    return NeweyWest(m, se, m / se, L, n, min(float(n), n * g0 / s))


def _ranks(a: np.ndarray) -> np.ndarray:
    order = np.argsort(a, kind="mergesort")
    r = np.empty(a.size, dtype=float)
    r[order] = np.arange(a.size, dtype=float)
    # average ties
    sa = a[order]
    i = 0
    while i < sa.size:
        j = i
        while j + 1 < sa.size and sa[j + 1] == sa[i]:
            j += 1
        if j > i:
            r[order[i:j + 1]] = (i + j) / 2.0
        i = j + 1
    return r


def rank_ic_newey_west(signal, fwd_returns, horizon: int = 1, lag: int | None = None) -> NeweyWest:
    """HAC t for a time-series rank IC. Both series are ranked (ties averaged) and
    standardised over the finite pairs; the mean of the products ``z_s * z_f`` is the
    Spearman IC (up to the ``n / (n - 1)`` factor), so ``newey_west_t`` on the product series
    is a HAC test of IC = 0 that uses every pair while allowing for overlap."""
    s, f = np.asarray(signal, float), np.asarray(fwd_returns, float)
    ok = np.isfinite(s) & np.isfinite(f)
    s, f = s[ok], f[ok]
    if s.size < 3:
        return newey_west_t(np.array([]), lag, horizon)
    rs, rf = _ranks(s), _ranks(f)
    if rs.std() == 0 or rf.std() == 0:
        return NeweyWest(float("nan"), float("nan"), float("nan"), 0, int(s.size), float("nan"))
    zs = (rs - rs.mean()) / rs.std()
    zf = (rf - rf.mean()) / rf.std()
    return newey_west_t(zs * zf, lag, horizon)


def min_detectable_ic(n: float, alpha: float = 0.05, power: float = 0.8, se: float | None = None) -> float:
    """Smallest |IC| a two-sided test at ``alpha`` detects with probability ``power``.

    With a standard error (``se``, e.g. ``NeweyWest.se``) it is ``(z_{1-alpha/2} + z_power) * se``.
    Without one it assumes independent pairs and uses Fisher's z:
    ``tanh((z_{1-alpha/2} + z_power) / sqrt(n - 3))``. Worked example: n = 1000 independent
    pairs, 5%, 80% power -> tanh(2.8016 / 31.56) = 0.0886. A null result in a table with this
    line reads "cannot detect |IC| below x", not "no edge"."""
    if not (0 < alpha < 1 and 0 < power < 1):
        raise ValueError("alpha and power must lie in (0, 1)")
    k = _N.inv_cdf(1 - alpha / 2) + _N.inv_cdf(power)
    if se is not None:
        return k * se if math.isfinite(se) else float("nan")
    if not math.isfinite(n) or n <= 3:
        return float("nan")
    return math.tanh(k / math.sqrt(n - 3))


# ------------------------------------------- effective number of trials (v0.17 N8)
def effective_trials(trial_returns) -> tuple[float, float]:
    """Effective number of independent trials from a (periods x trials) return matrix.

    Method: eigenvalues ``l_i`` of the trials' correlation matrix; ``N_eff`` is the
    participation ratio ``(sum l_i)^2 / sum l_i^2`` (N for uncorrelated trials, 1 when all
    are the same series). Also returned: the mean off-diagonal correlation ``rho``. One-rule
    ablations are highly correlated, so the dispersion of their Sharpe ratios understates the
    dispersion of independent strategies by about a factor ``1 - rho``;
    ``deflated_sharpe_effective`` therefore uses ``N_eff`` trials with the trial-Sharpe
    variance divided by ``1 - rho``. Rows with any NaN and constant columns are dropped."""
    x = np.asarray(trial_returns, dtype=float)
    if x.ndim != 2:
        raise ValueError("trial_returns must be 2-D (periods x trials)")
    x = x[np.all(np.isfinite(x), axis=1)]
    if x.shape[0] >= 2:
        x = x[:, x.std(axis=0) > 0]
    k = x.shape[1]
    if k < 2 or x.shape[0] < 3:
        return float(k), 0.0
    c = np.corrcoef(x, rowvar=False)
    ev = np.clip(np.linalg.eigvalsh(c), 0.0, None)
    n_eff = float(ev.sum() ** 2 / (ev ** 2).sum())
    rho = float((c.sum() - k) / (k * (k - 1)))
    return n_eff, rho


def deflated_sharpe_effective(sr: float, n: int, trial_returns, var_trials_sr: float,
                              skew: float = 0.0, kurt: float = 3.0) -> dict:
    """DSR at the effective number of trials with the correlation-corrected trial-Sharpe
    variance (``effective_trials``). Sharpe ratios per period. Returns ``n_eff``,
    ``mean_corr``, ``var_trials_corrected`` and ``deflated_sharpe_prob``."""
    n_eff, rho = effective_trials(trial_returns)
    var_c = var_trials_sr / max(1.0 - rho, 1e-6) if rho > 0 else var_trials_sr
    m = max(1, int(round(n_eff)))
    return {"n_eff": n_eff, "mean_corr": rho, "var_trials_corrected": var_c,
            "deflated_sharpe_prob": deflated_sharpe(sr, n, m, var_c, skew, kurt)}
