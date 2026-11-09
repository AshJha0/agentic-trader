"""Rebalance horizon from signal decay (v0.17, previous-review item Q4).

Plain idea. The desk rebalances every 5 bars by fiat. A signal whose predictive power fades
in two days is traded too slowly at 5; one that lasts two months is traded too often. The
decay of the information coefficient with the signal's age tells you which.

Formal statement. For a signal ``s`` and one-bar forward return ``r``, the lagged IC is
``IC(k) = Spearman(s_{t-k}, r_{t+1})`` for ``k = 0..K``. Fitting ``log IC(k) = a - k / tau``
over lags where IC keeps the sign of IC(0) gives a half-life ``h = tau * ln 2``. The suggested
rebalance interval is ``round(h)`` clipped to ``[min_every, max_every]``; when IC(0) is not
distinguishable from zero (|t| < ``min_t``) there is no decay to measure and the default is
returned with the reason.

Worked example. An AR(1) signal with ``phi = 0.9`` that predicts the next return has
``IC(k) ~ IC(0) * 0.9^k``, a half-life of ``ln 2 / -ln 0.9 = 6.6`` bars: rebalance every 7.

This is an option (``rebalance_from_decay``), rules only, applied offline to the design
period; it changes no default. ``scripts/horizon_table.py`` writes the design-period table.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

DEFAULT_REBALANCE_EVERY = 5


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 10:
        return float("nan")
    ra = pd.Series(a[m]).rank().to_numpy()
    rb = pd.Series(b[m]).rank().to_numpy()
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


def lagged_ic(signal, close, max_lag: int = 40) -> pd.Series:
    """``IC(k)`` for ``k = 0..max_lag``: Spearman of the signal ``k`` bars old against the next
    bar's simple return. ``signal[t]`` must use data up to ``t`` only."""
    s = np.asarray(signal, dtype=float)
    c = np.asarray(close, dtype=float)
    fwd = np.full(c.size, np.nan)
    fwd[:-1] = c[1:] / c[:-1] - 1.0
    out = {}
    for k in range(max_lag + 1):
        lagged = np.full(s.size, np.nan)
        lagged[k:] = s[:s.size - k] if k else s
        out[k] = _spearman(lagged, fwd)
    return pd.Series(out, name="IC")


@dataclass(frozen=True)
class DecayChoice:
    rebalance_every: int
    half_life: float          # bars; NaN when not measurable
    ic0: float
    t0: float
    reason: str


def half_life_from_ic(ic: pd.Series) -> float:
    """Half-life (bars) of an IC-by-lag series by a log-linear fit over the leading run of lags
    whose IC has the sign of IC(0) and at least 5 % of its size; NaN when it does not decay."""
    v = ic.to_numpy(float)
    if v.size < 3 or not np.isfinite(v[0]) or v[0] == 0:
        return float("nan")
    sgn = math.copysign(1.0, v[0])
    lags, logs = [], []
    for k, x in enumerate(v):
        if not np.isfinite(x) or sgn * x <= 0.05 * abs(v[0]):
            break
        lags.append(k)
        logs.append(math.log(sgn * x))
    if len(lags) < 3:
        return float(len(lags)) if lags else float("nan")   # dies within a couple of lags
    slope = float(np.polyfit(lags, logs, 1)[0])
    if slope >= 0:
        return float("inf")
    return math.log(2.0) / -slope


def rebalance_from_decay(signal, close, max_lag: int = 40, min_every: int = 1, max_every: int = 21,
                         min_t: float = 2.0, default: int = DEFAULT_REBALANCE_EVERY) -> DecayChoice:
    """The rebalance interval implied by the signal's IC half-life (see the module docstring)."""
    ic = lagged_ic(signal, close, max_lag)
    n = int(np.isfinite(np.asarray(signal, float)).sum())
    ic0 = float(ic.iloc[0])
    t0 = ic0 * math.sqrt(max(n - 2, 1)) / math.sqrt(max(1e-12, 1 - ic0 * ic0)) if np.isfinite(ic0) else float("nan")
    if not np.isfinite(t0) or abs(t0) < min_t:
        return DecayChoice(default, float("nan"), ic0, t0, f"|t(IC0)| < {min_t}: no measurable decay, default kept")
    h = half_life_from_ic(ic)
    if not np.isfinite(h):
        every = max_every if h == float("inf") else default
        return DecayChoice(every, h, ic0, t0, "IC does not decay within the lags" if h == float("inf")
                           else "half-life not measurable")
    every = int(min(max(round(h), min_every), max_every))
    return DecayChoice(every, h, ic0, t0, "half-life of lagged IC")
