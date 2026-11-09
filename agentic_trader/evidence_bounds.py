"""Two honest bounds on what the evidence can say (v0.17, review items B6 and B8).

``decision_horizon`` (B6). The forward paper record is the only data no choice has seen, but
its pre-registered decision needs a sample long enough to detect the effect sizes at stake.
From the v0.9 pre-registration amendment: the holdout's paired block-bootstrap half-width was
0.35 Sharpe over 1,167 sessions; half-widths shrink as ``1 / sqrt(n)``, so a difference ``d``
is detectable at 95 % after ``n = 1167 * (0.35 / d) ** 2`` sessions. For ``d = 0.2`` that is
3,574 sessions, about 14.2 years of NYSE sessions from the 2026-09-29 freeze. Until then the
record is operational evidence (the pipeline runs, fills reconcile, nothing leaks), not
research evidence.

``selection_premium`` (B8). The equity universe is ten names chosen in 2025, nine large caps
plus SPY. A point-in-time top-N-by-market-cap universe needs historical shares outstanding
and delisted names, which no free source here supplies, so survivorship bias in the strict
sense cannot be measured. What can be measured is the premium of the hindsight-chosen names
over the index they sit in, over the same window: an upper bound on how much the choice of
names (survivorship plus hindsight plus luck) lifts an equal-weight buy-and-hold control.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

PREREG_HALFWIDTH = 0.35      # Sharpe, paired block bootstrap, holdout (v09_preregistration.md)
PREREG_SESSIONS = 1167       # holdout sessions behind that half-width
FREEZE_DATE = date(2026, 9, 29)


def sessions_needed(effect: float, halfwidth: float = PREREG_HALFWIDTH, n: int = PREREG_SESSIONS) -> float:
    """Sessions after which a 95 % half-width equals ``effect``, by ``1 / sqrt(n)`` scaling."""
    if effect <= 0 or halfwidth <= 0 or n <= 0:
        raise ValueError("effect, halfwidth and n must be positive")
    return n * (halfwidth / effect) ** 2


def nth_session(start: date, k: int) -> date:
    """The ``k``-th NYSE session on or after ``start`` (k=1 is the first), from the OMS calendar."""
    from .oms import nyse_holidays
    d, count = start, 0
    hol: dict[int, frozenset[date]] = {}
    while True:
        if d.weekday() < 5:
            if d.year not in hol:
                hol[d.year] = nyse_holidays(d.year)
            if d not in hol[d.year]:
                count += 1
                if count >= k:
                    return d
        d += timedelta(days=1)


def decision_horizon(effect: float = 0.2, start: date = FREEZE_DATE) -> dict[str, object]:
    """Sessions, years (252 a year) and the calendar date of the decision look for ``effect``."""
    n = sessions_needed(effect)
    k = math.ceil(n)
    return {"effect_sharpe": effect, "sessions": k, "years": n / 252.0,
            "decision_date": nth_session(start, k).isoformat()}


def selection_premium(name_cr_pct, index_cr_pct: float, years: float,
                      name_sharpe=None, index_sharpe: float | None = None) -> dict[str, float]:
    """Premium of hindsight-chosen names over their index on one window: mean and median
    cumulative return minus the index's (percentage points), the annualised premium of the
    equal-weight mean, and (when given) mean Sharpe minus the index Sharpe."""
    cr = np.asarray(name_cr_pct, dtype=float)
    mean_cr, med_cr = float(cr.mean()), float(np.median(cr))
    ann = ((1 + mean_cr / 100) / (1 + index_cr_pct / 100)) ** (1 / years) - 1
    out = {"mean_cr_pct": mean_cr, "median_cr_pct": med_cr, "index_cr_pct": float(index_cr_pct),
           "mean_premium_pp": mean_cr - index_cr_pct, "median_premium_pp": med_cr - index_cr_pct,
           "annualised_premium_pct": 100 * ann}
    if name_sharpe is not None and index_sharpe is not None:
        out["mean_sharpe_premium"] = float(np.mean(name_sharpe)) - float(index_sharpe)
    return out


# Holdout per instrument, core universe (docs/evaluation/evaluation.md, "Holdout per instrument";
# v0.7 engine, superseded for strategy numbers but buy-and-hold CR and Sharpe of a price series
# do not depend on the engine changes listed there except the cash leg). 2022-01-03 .. 2026-06-30.
HOLDOUT_BH_CR = {"AAPL": 62.58, "NVDA": 566.25, "MSFT": 15.66, "META": 67.82, "GOOGL": 148.61,
                 "AMZN": 39.84, "JPM": 126.97, "XOM": 151.32, "JNJ": 68.27}
HOLDOUT_BH_SHARPE = {"AAPL": 0.53, "NVDA": 1.07, "MSFT": 0.26, "META": 0.48, "GOOGL": 0.79,
                     "AMZN": 0.39, "JPM": 0.86, "XOM": 0.91, "JNJ": 0.75}
HOLDOUT_SPY = {"cr": 66.11, "sharpe": 0.73, "years": 4.5}


def holdout_selection_premium() -> dict[str, float]:
    """``selection_premium`` on the published holdout buy-and-hold rows (nine names vs SPY)."""
    return selection_premium(list(HOLDOUT_BH_CR.values()), HOLDOUT_SPY["cr"], HOLDOUT_SPY["years"],
                             list(HOLDOUT_BH_SHARPE.values()), HOLDOUT_SPY["sharpe"])
