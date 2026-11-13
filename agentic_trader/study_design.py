"""Powered P2 design cells (review 2026-11-09, N3 and N9).

Plain idea. The v0.16 first pass (15 names x 20 dates, about 19 usable periods) cannot detect an
edge of realistic size: its minimum detectable effect (MDE) is about 0.9 annual Sharpe on the
portfolio metric and about 0.36 on decision-level IC. It is therefore pre-registered as
descriptive (contract rates, agreement with rules, fallback bias). The decisive question is
asked by a cell built for power:

* ``decisive_ta``: the technical analyst alone reasons with the model (one call per decision);
  15 core names x weekly design dates (2016-2021, about 313 weeks), 5-trading-day horizon,
  paired with the same analyst's rule signal on the same anonymised state.
* ``postcutoff_ta``: the same cell on weekly dates 2025-07-01 to 2026-10-30, after the model's
  training data (N9). An edge that exists in-training and vanishes after the cutoff is memory.

Formally (amended 2026-11-12, review C4/C5/C6/B2/B10, before any decisive row existed), the
primary metric is the residual information coefficient. It asks what the model's signal says
about the return that could not have been predicted from the rule signal alone.

    step 1   g_c = fit of s_model on s_rule, pooled over every usable row of asset class c
             (up to 20 quantile bins of s_rule, a straight line inside each bin; no return is used)
             e(i,t) = s_model(i,t) - g_c(s_rule(i,t)),    sd_c = pooled standard deviation of e
    step 2   IC_{t,c} = mean_i[ (e - mean_t e) (R(r) - mean_t R(r)) ] / ( sd_c * sd_t(R(r)) )
             with R(r) the average rank of the 5-day forward return inside the class at date t
    step 3   IC_t = sum_c n_c IC_{t,c} / sum_c n_c        (classes with >= 5 usable names)
             IC   = mean_t IC_t,   SE = Newey-West(lag L) standard error of the IC_t series

A model that is a function of the rule (a copy, a scaled, shrunk, flipped, clipped or rounded
copy) has e near zero everywhere; when sd_c is below 5 % of the model signal's own standard
deviation the class is declared a copy of the rule and scores exactly 0. The first version,
Spearman(s_model - s_rule, r), did not have this property (a model equal to half the rule
scored minus the rule's IC) and is still reported as ``legacy_model_minus_rule``, never as
evidence. A per-date rank residual was also tried and rejected on 2026-11-12: a model that
rounds the rule keeps the spacing between names that ranks discard, and passed at a rule IC
of 0.30 in about two runs in three. Ranking returns inside an asset class keeps
equity-against-FX timing out of the statistic.

Clustering by date is built in (one IC per date), and with weekly dates and a 5-day horizon
neighbouring dates do not overlap; L = 1 covers residual dependence. Dates are NYSE sessions:
a weekly anchor that falls on a closure rolls forward to the next session, so equities and FX
are read on the same bar. The planning MDE uses the null variance of the per-date statistic:
a common market move does not change ranks inside a date, so Var(IC_{t,c}) is about
1 / (n_c - 1), Var(IC_t) = sum_c w_c^2 / (n_c - 1) with w_c = n_c / N,
SE = sqrt(Var(IC_t) / T) and MDE = (z_{1-a/2} + z_{power}) * SE.

Futility (decided now): at every interim look of ``FUTILITY_EVERY`` decisions after the first
``FUTILITY_MIN_DATES`` dates, stop if the one-sided 90 % upper bound IC + 1.2816 * SE is below
``FUTILITY_IC`` (0.03). Stopping for futility cannot inflate false positives; no efficacy stop is
allowed, so the full design is the only route to a positive claim.

Worked example. T = 313, classes of 10 and 5 names: Var(IC_t) = (10/15)^2 / 9 + (5/15)^2 / 4
= 0.0772, SD 0.278, SE = 0.278 / sqrt(313) = 0.0157, MDE at 80 % power and 5 % two-sided =
2.80 x 0.0157 = 0.044. The earlier figure (0.093, from a design effect on pooled decisions)
overstated it about twofold. For the 70 post-cutoff dates SE = 0.033 and the one-sided 95 %
replication test detects 0.083 at 80 % power. At 50-100 s per call the decisive cell needs
65-130 CPU hours (2.7-5.4 days).

Replication (B2). A pass on the design dates counts only if the post-cutoff cell replicates
it: residual IC with a one-sided 95 % lower bound above zero. Anything else is "not
replicated" and the cell is not adopted; memory and no effect cannot then be told apart.

Evidence class: design arithmetic and unit tests with fake models; no decisive or post-cutoff
row had been run when the metric was amended.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

Z_975, Z_80, Z_90, Z_95 = 1.959964, 0.841621, 1.281552, 1.644854
FUTILITY_IC = 0.03
FUTILITY_EVERY = 1000
FUTILITY_MIN_DATES = 40
SECONDS_PER_CALL = (50.0, 100.0)      # the planning range on the owner's CPU (llm_study.py)
DEFAULT_RHO = 0.3                    # legacy planning value (pooled design effect); kept for comparison
MIN_NAMES = 5                        # usable names an asset class needs on a date to be scored
FIT_BINS = 20                        # most quantile bins of the rule signal in the pooled fit
FIT_ROWS_PER_BIN = 50                # fewer rows than this per bin: use fewer bins
COPY_SD_RATIO = 0.05                 # residual sd below this share of the model's sd: a copy of the rule
MAX_FALLBACK_SHARE = 0.10            # prereg: above this the cell is inadmissible
PREREG_SIGNED = "docs/evaluation/v16_preregistration.md"        # exists only once the owner has signed
PREREG_DRAFT = "docs/evaluation/v16_preregistration_DRAFT.md"


@dataclass(frozen=True)
class DesignCell:
    name: str
    description: str
    start: str
    end: str
    step_days: int = 7
    horizon_days: int = 5
    analysts: tuple[str, ...] = ("technical",)
    calls_per_decision: int = 1
    label: str = "decisive"
    # Why this cell may read dates inside PERIODS["holdout"] without the recall gate; None means
    # the gate applies. Recorded in the run header and the report (review B3).
    holdout_basis: str | None = None

    @property
    def trial_name(self) -> str:
        return f"P2 {self.name}: {self.description}"


DECISIVE = DesignCell(
    "decisive_ta", "technical-analyst-only local model, weekly design dates 2016-2021, 5-day horizon, "
    "incremental IC over the rule signal", "2016-01-04", "2021-12-31")
POSTCUTOFF = DesignCell(
    "postcutoff_ta", "technical-analyst-only local model, weekly dates 2025-07 to 2026-10 (post-training "
    "leakage control), 5-day horizon, incremental IC over the rule signal", "2025-07-01", "2026-10-30",
    label="leakage control",
    holdout_basis="dates after the model's release (qwen2.5, September 2024), so recall of them is "
                  "impossible and the recall gate does not apply; owner sign-off 2026-11-09 (prereg data "
                  "note); the Sharpe holdout look for LLM cells ends 2025-06-30 (amendment 2026-11-12)")
DESIGN_CELLS: tuple[DesignCell, ...] = (DECISIVE, POSTCUTOFF)


def weekly_dates(cell: DesignCell) -> list[date]:
    """One NYSE session per ``step_days``: the anchor steps from the first weekday on or after
    ``start``; an anchor on a closure rolls forward to the next session (a Monday holiday is
    read on Tuesday). An anchor whose roll passes ``end`` or reaches the next anchor is dropped.

    Worked example: 2016-01-18 (Martin Luther King Jr. Day) becomes 2016-01-19. Before the
    2026-11-12 amendment the holiday itself was used, so equities were read on Friday's bar
    and FX on Monday's in the same cross-section (review C6)."""
    from .nyse_calendar import is_session
    d, end = date.fromisoformat(cell.start), date.fromisoformat(cell.end)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    out: list[date] = []
    while d <= end:
        s = d
        while not is_session(s):
            s += timedelta(days=1)
        if s <= end and s < d + timedelta(days=cell.step_days):
            out.append(s)
        d += timedelta(days=cell.step_days)
    return out


def asset_class_of(symbol: str | None) -> str:
    """"equity" or "fx" for a symbol the instrument parser knows, else "all" (one group)."""
    if not symbol:
        return "all"
    try:
        from .instruments import Instrument
        return str(Instrument.parse(symbol).asset_class)
    except Exception:
        return "all"


def mde_ic_dates(n_dates: int, group_sizes: Sequence[int], power_z: float = Z_80,
                 alpha_z: float = Z_975) -> dict[str, Any]:
    """Planning MDE of the mean per-date residual IC (see the module docstring)."""
    gs = [int(g) for g in group_sizes if g >= MIN_NAMES]
    n = sum(gs)
    var_t = sum((g / n) ** 2 / (g - 1) for g in gs) if n else float("inf")
    se = math.sqrt(var_t / n_dates) if n_dates > 0 else float("inf")
    return {"n_dates": n_dates, "group_sizes": gs, "sd_per_date": math.sqrt(var_t), "se": se,
            "mde": (alpha_z + power_z) * se, "mde_one_sided_95": (Z_95 + power_z) * se}


def mde_ic(n_dates: int, n_names: int, rho: float = DEFAULT_RHO, power_z: float = Z_80,
           alpha_z: float = Z_975) -> dict[str, float]:
    deff = 1 + (n_names - 1) * rho
    n_eff = n_dates * n_names / deff
    se = 1 / math.sqrt(n_eff) if n_eff > 0 else float("inf")
    return {"n_dates": n_dates, "n_names": n_names, "rho": rho, "design_effect": deff, "n_eff": n_eff,
            "se": se, "mde": (alpha_z + power_z) * se}


def mde_sharpe_diff(years: float, corr: float, power_z: float = Z_80, alpha_z: float = Z_975) -> float:
    """MDE of an annual Sharpe difference between two streams (iid approximation)."""
    return (alpha_z + power_z) * math.sqrt(2 * (1 - corr) / years)


def first_pass_mde() -> dict[str, Any]:
    """Why the v0.16 first pass is descriptive: its MDEs at 80 % power, 5 % two-sided."""
    return {"label": "descriptive (cannot accept or reject an edge)",
            "sharpe_mde_corr0.7_6y": mde_sharpe_diff(6.0, 0.7),
            "ic_mde_neff60": (Z_975 + Z_80) / math.sqrt(60),
            "periods": 19, "note": "19 usable periods about 115 days apart; effective n about 60 decisions"}


def dry_run(cell: DesignCell, names: Sequence[str], seconds_per_call: tuple[float, float] = SECONDS_PER_CALL,
            rho: float = DEFAULT_RHO) -> dict[str, Any]:
    dates = weekly_dates(cell)
    sizes = Counter(asset_class_of(n) for n in names)
    decisions = len(dates) * len(names)
    calls = decisions * cell.calls_per_decision
    lo, hi = (calls * s / 3600 for s in seconds_per_call)
    return {"cell": cell.name, "label": cell.label, "trial_name": cell.trial_name, "dates": len(dates),
            "first_date": dates[0].isoformat() if dates else None,
            "last_date": dates[-1].isoformat() if dates else None, "names": len(names),
            "decisions": decisions, "calls": calls, "cpu_hours": [round(lo, 1), round(hi, 1)],
            "cpu_days": [round(lo / 24, 1), round(hi / 24, 1)], "horizon_days": cell.horizon_days,
            "mde": mde_ic_dates(len(dates), list(sizes.values())),
            "mde_legacy_pooled": mde_ic(len(dates), len(names), rho), "futility": futility_rule(),
            "holdout_basis": cell.holdout_basis}


def futility_rule() -> str:
    return (f"after {FUTILITY_MIN_DATES} dates, at every {FUTILITY_EVERY} decisions: stop if residual "
            f"IC + {Z_90:.4f} x SE < {FUTILITY_IC} (one-sided 90 % upper bound); no efficacy stop")


# ---- metrics ----------------------------------------------------------------------------------

def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    from .recall_audit import spearman
    v = spearman(list(x), list(y))
    return None if v is None or not math.isfinite(v) else v


def newey_west_se(x: Sequence[float], lag: int = 1) -> float:
    a = np.asarray(x, float)
    n = len(a)
    if n < 2:
        return float("nan")
    e = a - a.mean()
    s = float(e @ e) / n
    for k in range(1, min(lag, n - 1) + 1):
        w = 1 - k / (lag + 1)
        s += 2 * w * float(e[k:] @ e[:-k]) / n
    return math.sqrt(max(s, 0.0) / n)


def _ranks(x: np.ndarray) -> np.ndarray:
    """Average ranks (ties share the mean rank), as Spearman uses."""
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    r = np.empty(len(x), float)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return r


def _pearson(x: np.ndarray, y: np.ndarray) -> float | None:
    xc, yc = x - x.mean(), y - y.mean()
    den = math.sqrt(float(xc @ xc) * float(yc @ yc))
    return float(xc @ yc) / den if den > 0 else None


def rule_fit_residuals(model: np.ndarray, rule: np.ndarray) -> tuple[np.ndarray, dict[str, Any]]:
    """The part of the model signal that the rule signal does not predict (step 1).

    The rule values are cut into at most ``FIT_BINS`` quantile bins (at least
    ``FIT_ROWS_PER_BIN`` rows each; a rule with few distinct values gets one bin per value)
    and a least-squares line is fitted inside each bin. Only the two signals are used, never
    a return, so the fit cannot leak the outcome. Returns the residuals and
    ``{"bins", "sd_model", "sd_residual", "r2", "copy_of_rule"}``.

    Worked example: model = 0.5 x rule gives a perfect line in every bin, residual 0,
    ``copy_of_rule`` True. Model = round(rule) is flat inside almost every bin; only the few
    bins that straddle a rounding step leave a residual."""
    m, q = np.asarray(model, float), np.asarray(rule, float)
    n = len(m)
    fit = np.full(n, float(m.mean()) if n else 0.0)
    uniq = np.unique(q)
    k = max(1, min(FIT_BINS, n // FIT_ROWS_PER_BIN))
    if len(uniq) <= k:
        idx = np.searchsorted(uniq, q)
        k = len(uniq)
    else:
        edges = np.unique(np.quantile(q, np.linspace(0, 1, k + 1)[1:-1]))
        idx = np.searchsorted(edges, q, side="right")
        k = len(edges) + 1
    for j in range(k):
        sel = idx == j
        if not sel.any():
            continue
        qs, ms = q[sel], m[sel]
        qc = qs - qs.mean()
        den = float(qc @ qc)
        fit[sel] = ms.mean() + ((float(qc @ (ms - ms.mean())) / den) * qc if den > 0 else 0.0)
    e = m - fit
    sd_m, sd_e = (float(np.std(m)), float(np.std(e))) if n else (0.0, 0.0)
    copy = bool(sd_e <= COPY_SD_RATIO * sd_m)
    return e, {"bins": k, "sd_model": sd_m, "sd_residual": sd_e,
               "r2": 1.0 - (sd_e / sd_m) ** 2 if sd_m > 0 else None, "copy_of_rule": copy}


def residual_ic(resid: np.ndarray, fwd: np.ndarray, sd_resid: float) -> float | None:
    """Step 2 for one asset class on one date: the covariance of the residual with the return
    ranks, over the pooled residual sd and this date's sd of the ranks. ``None`` when the
    returns carry no order (all equal); 0.0 when ``sd_resid`` is 0."""
    rf = _ranks(np.asarray(fwd, float))
    fc = rf - rf.mean()
    sd_f = math.sqrt(float(fc @ fc) / len(fc))
    if sd_f == 0.0:
        return None
    if not sd_resid > 0:
        return 0.0
    e = np.asarray(resid, float)
    return float((e - e.mean()) @ fc) / len(fc) / (sd_resid * sd_f)


def _usable(rows: Sequence[dict[str, Any]]) -> tuple[dict[str, dict[str, list[dict]]], dict[str, int]]:
    """Rows grouped by date then asset class, and the exclusion counts.

    Excluded: a model call that fell back (``signal_model`` None), a missing rule signal or
    forward return, and a stale bar (``entry_bar_date`` differs from ``as_of``: the name did
    not trade that session, so its decision was made on an older close than its neighbours)."""
    by_d: dict[str, dict[str, list[dict]]] = {}
    counts = {"fallback": 0, "no_forward_return": 0, "stale_bar": 0}
    for r in rows:
        if r.get("signal_model") is None or r.get("signal_rule") is None:
            counts["fallback"] += 1
        elif r.get("fwd_ret") is None:
            counts["no_forward_return"] += 1
        elif r.get("entry_bar_date") not in (None, str(r["as_of"])):
            counts["stale_bar"] += 1
        else:
            g = r.get("asset_class") or asset_class_of(r.get("symbol"))
            by_d.setdefault(str(r["as_of"]), {}).setdefault(g, []).append(r)
    return by_d, counts


def incremental_ic(rows: Sequence[dict[str, Any]], *, lag: int = 1, min_names: int = MIN_NAMES) -> dict[str, Any]:
    """The pre-registered scoring of a design cell (amended 2026-11-12).

    ``primary`` is the mean per-date residual IC (module docstring, steps 1 to 3) with a
    Newey-West SE over dates. Beside it, on the same rows and grouping:
    ``paired_difference`` IC(model) - IC(rule), ``model`` and ``rule`` Spearman ICs, and
    ``legacy_model_minus_rule``, the first version of the metric (Spearman of model minus
    rule, all names pooled), kept so the change is visible and never used for a decision.
    ``rule_fit`` reports step 1 per asset class. Rows need ``as_of``, ``signal_model``,
    ``signal_rule`` and ``fwd_ret``; ``symbol`` (or ``asset_class``) sets the class, else all
    rows form one."""
    by_d, counts = _usable(rows)
    classes = sorted({g for gs in by_d.values() for g in gs})
    fits: dict[str, dict[str, Any]] = {}
    for g in classes:
        rs = [r for d in sorted(by_d) for r in by_d[d].get(g, [])]
        e, info = rule_fit_residuals(np.array([r["signal_model"] for r in rs], float),
                                     np.array([r["signal_rule"] for r in rs], float))
        fits[g] = info | {"rows": len(rs), "resid": {id(r): float(v) for r, v in zip(rs, e)}}
    series: dict[str, list[float]] = {k: [] for k in ("primary", "paired_difference", "model", "rule",
                                                       "legacy_model_minus_rule")}
    small = 0
    for d in sorted(by_d):
        acc: dict[str, list[tuple[float, int]]] = {k: [] for k in series if k != "legacy_model_minus_rule"}
        pooled = [r for rs in by_d[d].values() for r in rs]
        for g in sorted(by_d[d]):
            rs = by_d[d][g]
            if len(rs) < min_names:
                small += len(rs)
                continue
            f = np.array([r["fwd_ret"] for r in rs], float)
            m = np.array([r["signal_model"] for r in rs], float)
            q = np.array([r["signal_rule"] for r in rs], float)
            fit = fits[g]
            res = residual_ic(np.array([fit["resid"][id(r)] for r in rs]), f,
                              0.0 if fit["copy_of_rule"] else fit["sd_residual"])
            if res is not None:
                acc["primary"].append((res, len(rs)))
            im, iq = _spearman(m, f), _spearman(q, f)
            if im is not None:
                acc["model"].append((im, len(rs)))
            if iq is not None:
                acc["rule"].append((iq, len(rs)))
            if im is not None and iq is not None:
                acc["paired_difference"].append((im - iq, len(rs)))
        for k, vals in acc.items():
            w = sum(n for _, n in vals)
            if w:
                series[k].append(sum(v * n for v, n in vals) / w)
        if len(pooled) >= min_names:
            v = _spearman(np.array([r["signal_model"] - r["signal_rule"] for r in pooled], float),
                          np.array([r["fwd_ret"] for r in pooled], float))
            if v is not None:
                series["legacy_model_minus_rule"].append(v)

    def summ(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"ic": None, "se": None, "t": None, "dates": 0}
        se = newey_west_se(xs, lag)
        mu = float(np.mean(xs))
        return {"ic": mu, "se": se, "t": mu / se if se and se > 0 else None, "dates": len(xs),
                "ci95": [mu - Z_975 * se, mu + Z_975 * se], "upper90_one_sided": mu + Z_90 * se,
                "lower95_one_sided": mu - Z_95 * se}
    return {**{k: summ(v) for k, v in series.items()},
            "metric": "residual IC: model signal net of a pooled fit on the rule, within asset class (2026-11-12)",
            "rule_fit": {g: {k: v for k, v in f.items() if k != "resid"} for g, f in fits.items()},
            "excluded_rows": sum(counts.values()), "excluded": counts, "rows_in_small_classes": small,
            "rows": sum(len(rs) for gs in by_d.values() for rs in gs.values())}


def futility_stop(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Apply the pre-registered futility rule to the rows so far."""
    res = incremental_ic(rows)["primary"]
    if res["dates"] < FUTILITY_MIN_DATES or res["ic"] is None:
        return {"stop": False, "reason": f"fewer than {FUTILITY_MIN_DATES} dates", **res}
    ub = res["upper90_one_sided"]
    return {"stop": bool(ub < FUTILITY_IC), "reason": f"upper90 {ub:.4f} vs {FUTILITY_IC}", **res}


def replication_verdict(decisive: dict[str, Any], postcutoff: dict[str, Any] | None) -> dict[str, Any]:
    """The decision rule across the two cells; arguments are ``report()`` dicts.

    The design cell passes when it is admissible (fallback share at most 10 %) and the 95 %
    interval of its residual IC lies above zero. A pass is adopted only if the post-cutoff
    cell is admissible and its one-sided 95 % lower bound is above zero (review B2: the
    burden is on replication, so a low-powered control cannot wave a memory effect through)."""
    def ok(rep: dict[str, Any] | None) -> bool:
        return bool(rep) and rep.get("fallback_share") is not None and rep["fallback_share"] <= MAX_FALLBACK_SHARE
    d = decisive["metric"]["primary"]
    if not ok(decisive) or d["ic"] is None:
        return {"design_pass": False, "replicated": None, "adopt": False, "verdict": "design cell inadmissible or empty"}
    if not d["ci95"][0] > 0:
        return {"design_pass": False, "replicated": None, "adopt": False,
                "verdict": "no added information on the design dates (95 % interval includes zero)"}
    p = (postcutoff or {}).get("metric", {}).get("primary")
    if not ok(postcutoff) or not p or p["ic"] is None:
        return {"design_pass": True, "replicated": None, "adopt": False,
                "verdict": "design pass; post-cutoff cell missing or inadmissible, so not adopted"}
    rep_ok = bool(p["lower95_one_sided"] > 0)
    return {"design_pass": True, "replicated": rep_ok, "adopt": rep_ok,
            "verdict": "design pass replicated after the training cutoff" if rep_ok else
            "design pass not replicated after the training cutoff: not adopted "
            "(memory and no effect cannot be told apart)"}


def prereg_document(root: Path | str = ".") -> Path:
    """The pre-registration as it stands: the signed file when it exists, else the draft."""
    signed = Path(root) / PREREG_SIGNED
    return signed if signed.is_file() else Path(root) / PREREG_DRAFT


class PreregNotSigned(RuntimeError):
    """Raised when a registered cell is asked to run before the pre-registration is signed."""


def prereg_gate(root: Path | str = ".") -> dict[str, str]:
    """The signed pre-registration's path and SHA-256, for the run header. Raises
    ``PreregNotSigned`` while only the draft exists: a registered cell is scored only under
    a document that can no longer move (review B4)."""
    import hashlib
    p = Path(root) / PREREG_SIGNED
    if not p.is_file():
        raise PreregNotSigned(f"{PREREG_SIGNED} does not exist: the pre-registration is still a draft. "
                              "Sign it (python scripts/sign_prereg.py; see docs/evaluation/v16_prereg_amendment_2026-11-12.md) "
                              "before a registered cell runs.")
    text = p.read_text(encoding="utf-8")
    if "DRAFT" in text.splitlines()[0] or "not signed" in text[:600]:
        raise PreregNotSigned(f"{PREREG_SIGNED} still says it is a draft")
    return {"prereg_path": PREREG_SIGNED, "prereg_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def holdout_access(cell: DesignCell, recall_path: str | Path | None = None) -> dict[str, Any]:
    """Whether ``cell`` may read its dates. A window clear of ``PERIODS["holdout"]`` needs
    nothing. One that overlaps it needs either the cell's recorded ``holdout_basis`` or a
    passing v2 recall audit (``evaluation.require_recall_pass`` raises ``HoldoutLocked``)."""
    from .evaluation import DEFAULT_RECALL_AUDIT_PATH, require_recall_pass, touches_holdout
    if not touches_holdout({cell.name: (cell.start, cell.end)}):
        return {"touches_holdout": False}
    if cell.holdout_basis:
        return {"touches_holdout": True, "holdout_basis": cell.holdout_basis}
    require_recall_pass(recall_path or DEFAULT_RECALL_AUDIT_PATH)
    return {"touches_holdout": True, "holdout_basis": "v2 recall audit passed"}


# ---- runner -----------------------------------------------------------------------------------

def forward_return(provider: Any, instrument: Any, bar_date: date, horizon: int) -> tuple[float | None, str | None]:
    """Close-to-close return over ``horizon`` bars after ``bar_date`` (scoring only; never shown
    to the model). Returns (return, end bar date) or (None, None) when the bars do not exist."""
    import pandas as pd
    h = provider.history(instrument, bar_date - timedelta(days=5), bar_date + timedelta(days=3 * horizon + 10))
    c = h["Close"].astype(float)
    c = c[c.index >= pd.Timestamp(bar_date)]
    if len(c) <= horizon or c.index[0].date() != bar_date:
        return None, None
    return float(c.iloc[horizon] / c.iloc[0] - 1.0), str(c.index[horizon].date())


def run_cell(cell: DesignCell, names: Sequence[str], graph: Any, llm: Any, out: Path, *, header: dict[str, Any],
             limit: int = 0, shift_bars: int = 0, echo: Callable[[str], None] = print,
             futility_check: bool = True) -> list[dict[str, Any]]:
    """Run a design cell: per (date, name) one anonymised technical-analyst call, rule signal
    from the same analyst on the same state, forward return scored from the bars after the
    decision. Checkpointed JSONL with lineage (``study_lineage``); resume skips done keys.
    ``header`` must already have passed ``study_lineage.check_resume``."""
    from .agents.analysts import TechnicalAnalyst
    from .anonymize import Anonymizer
    from .study_lineage import market_lineage, prompt_sha256, stamp
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    rows: list[dict[str, Any]] = []
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(r)
            done.add((r["symbol"], r["as_of"]))
    grid = [(d, n) for d in weekly_dates(cell) for n in names]
    if limit:
        grid = grid[:limit]
    t0 = time.time()
    with out.open("a", encoding="utf-8") as fh:
        for k, (d, n) in enumerate(grid, 1):
            if (n, d.isoformat()) in done:
                continue
            state = graph.prepare(n, d)
            state.anon = Anonymizer(state.instrument, state.as_of, state.last_price)
            seen: list[tuple[str, str]] = []

            class _Rec:
                _seen = seen   # bound now, per grid cell

                def __init__(self, inner):
                    self.inner = inner

                def __getattr__(self, a):
                    return getattr(self.inner, a)

                def complete_json(self, system, prompt, *, deep, schema):
                    self._seen.append((system, prompt))
                    return self.inner.complete_json(system, prompt, deep=deep, schema=schema)

                def complete(self, system, prompt, *, deep):
                    self._seen.append((system, prompt))
                    return self.inner.complete(system, prompt, deep=deep)
            rep = TechnicalAnalyst(_Rec(llm) if llm is not None else None, graph.config).run(state, graph.provider)
            bar = state.history.index[-1].date()
            fwd, fwd_end = forward_return(graph.provider, state.instrument, bar, cell.horizon_days)
            ev = getattr(llm, "last_call", None) if llm is not None else None
            ev = ev if isinstance(ev, dict) else {}
            model_ok = rep.source == "llm"
            row = {"cell": cell.name, "symbol": n, "as_of": d.isoformat(),
                   "signal_model": float(rep.signal) if model_ok else None,
                   "signal_rule": float(rep.rule_signal if model_ok and rep.rule_signal is not None else rep.signal),
                   "source": rep.source, "abstained": bool(rep.abstained),
                   "fwd_ret": fwd, "fwd_end": fwd_end,
                   "prompt_sha256": prompt_sha256(*seen[-1]) if seen else None,
                   "prompt_eval_count": ev.get("prompt_eval_count"), "eval_count": ev.get("eval_count"),
                   "truncated": ev.get("truncated"), "stop_reason": ev.get("stop_reason"),
                   "model_served": ev.get("model_served"),
                   **market_lineage(state.history, None)}
            row["horizon_days"] = cell.horizon_days
            stamp(row, header)
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            rows.append(row)
            echo(f"[{k}/{len(grid)}] {cell.name} {d} {n}: model={row['signal_model']} rule={row['signal_rule']:+.2f} "
                 f"fwd={fwd} {time.time() - t0:.0f}s")
            if futility_check and len(rows) % FUTILITY_EVERY == 0:
                fs = futility_stop(rows)
                echo(f"futility look at {len(rows)} rows: {fs['reason']} stop={fs['stop']}")
                if fs["stop"]:
                    break
    return rows


def report(cell: DesignCell, rows: Sequence[dict[str, Any]], names: Sequence[str]) -> dict[str, Any]:
    from .study_lineage import row_vintage_status
    ic = incremental_ic(rows)
    n = len(rows)
    fell_back = sum(r.get("signal_model") is None for r in rows)
    trunc = sum(bool(r.get("truncated")) for r in rows)
    share = fell_back / n if n else None
    return {"cell": cell.name, "label": cell.label, "trial_name": cell.trial_name, "rows": n,
            "fallback_share": share, "admissible": share is not None and share <= MAX_FALLBACK_SHARE,
            "truncated_share": trunc / n if n else None, "holdout_basis": cell.holdout_basis,
            "headers": sorted({str(r.get("header_id")) for r in rows}),
            "legacy_rows": sum(row_vintage_status(r) == "legacy" for r in rows),
            "metric": ic, "futility": futility_stop(rows), "planned": dry_run(cell, names)}


def describe() -> list[dict[str, Any]]:
    return [asdict(c) | {"trial_name": c.trial_name} for c in DESIGN_CELLS]


def main(argv: list[str] | None = None) -> int:
    """``python -m agentic_trader.study_design --dry-run`` prints counts, runtime and MDEs."""
    import argparse
    from .evaluation import CORE_UNIVERSE, TRIALS
    ap = argparse.ArgumentParser(description="Powered P2 design cells (N3, N9): dry run")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rho", type=float, default=DEFAULT_RHO)
    a = ap.parse_args(argv)
    names = CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]
    registered = {t.name for t in TRIALS}
    out = {"first_pass": first_pass_mde(),
           "cells": [dry_run(c, names, rho=a.rho) | {"registered": c.trial_name in registered} for c in DESIGN_CELLS]}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
