"""Null-centred bootstrap p-values (review B8).

Plain idea: a bootstrap resamples the data and recomputes the statistic, which gives the
spread of the estimate *around the observed value*. A p-value needs the spread *under the
null*. The share of resamples on the far side of zero (the percentile-tail p used in
``scripts/llm_study.py`` up to v0.16) mixes the two: it is roughly a one-sided test doubled,
and it is anti-conservative when the bootstrap distribution is skewed or biased.

Formal: with observed statistic ``t``, null value ``t0`` and bootstrap replicates ``t*_b``,
shift the replicates to the null, ``t*_b - t + t0`` (this keeps their spread and puts their
centre on ``t0``), and report the two-sided

    p = (1 + #{b : |t*_b - t| >= |t - t0|}) / (B + 1)

The ``+1`` keeps p strictly above zero (Davison and Hinkley 1997, section 4.4; Hall and
Wilson 1991 for the shift form). Evidence class: textbook method, checked against the normal
case in ``tests/test_v17_ai_rest.py``.

Worked example: replicates N(0.5, 0.2^2) for an observed 0.5 give |t - 0| / 0.2 = 2.5
standard errors, so p is close to 2 * (1 - Phi(2.5)) = 0.0124.
"""
from __future__ import annotations

import numpy as np


def null_centred_pvalue(boot: np.ndarray, observed: float, null: float = 0.0) -> float:
    """Two-sided bootstrap p-value with the replicates shifted onto ``null``."""
    b = np.asarray(boot, dtype=float)
    b = b[np.isfinite(b)]
    if b.size == 0 or not np.isfinite(observed):
        return float("nan")
    extreme = np.abs(b - observed) >= abs(observed - null) - 1e-12
    return float((1 + int(extreme.sum())) / (b.size + 1))


def percentile_tail_pvalue(boot: np.ndarray) -> float:
    """The pre-v0.17 rule, kept for comparison: twice the smaller share on either side of 0."""
    b = np.asarray(boot, dtype=float)
    return float(min(1.0, 2 * min(np.mean(b <= 0), np.mean(b >= 0))))
