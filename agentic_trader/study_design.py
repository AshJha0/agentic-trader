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

Formally, the primary metric is the incremental information coefficient

    IC_t = Spearman_i( s_model(i,t) - s_rule(i,t),  r(i, t -> t+5) )    over names i at date t
    IC   = mean_t IC_t,   SE = Newey-West(lag L) standard error of the IC_t series

Clustering by date is built in (one IC per date), and with weekly dates and a 5-day horizon
neighbouring dates do not overlap; L = 1 covers residual dependence. The planning MDE uses a
design effect for cross-sectional correlation rho between names:
n_eff = T * N / (1 + (N - 1) * rho), SE ~ 1 / sqrt(n_eff), MDE = (z_{1-a/2} + z_{power}) * SE.

Futility (decided now): at every interim look of ``FUTILITY_EVERY`` decisions after the first
``FUTILITY_MIN_DATES`` dates, stop if the one-sided 90 % upper bound IC + 1.2816 * SE is below
``FUTILITY_IC`` (0.03). Stopping for futility cannot inflate false positives; no efficacy stop is
allowed, so the full design is the only route to a positive claim.

Worked example. T = 313, N = 15, rho = 0.3: design effect 5.2, n_eff = 903, SE = 0.033, MDE at
80 % power and 5 % two-sided = 2.80 x 0.033 = 0.093. A second, faster model on the same states
roughly doubles the decisions and brings the MDE near 0.066. At 50-100 s per call the cell
needs 65-130 CPU hours (2.7-5.4 days).

Evidence class: design arithmetic and unit tests with fake models; nothing has been run.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

Z_975, Z_80, Z_90 = 1.959964, 0.841621, 1.281552
FUTILITY_IC = 0.03
FUTILITY_EVERY = 1000
FUTILITY_MIN_DATES = 40
SECONDS_PER_CALL = (50.0, 100.0)      # the planning range on the owner's CPU (llm_study.py)
DEFAULT_RHO = 0.3                    # assumed mean cross-sectional correlation of signals x returns


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

    @property
    def trial_name(self) -> str:
        return f"P2 {self.name}: {self.description}"


DECISIVE = DesignCell(
    "decisive_ta", "technical-analyst-only local model, weekly design dates 2016-2021, 5-day horizon, "
    "incremental IC over the rule signal", "2016-01-04", "2021-12-31")
POSTCUTOFF = DesignCell(
    "postcutoff_ta", "technical-analyst-only local model, weekly dates 2025-07 to 2026-10 (post-training "
    "leakage control), 5-day horizon, incremental IC over the rule signal", "2025-07-01", "2026-10-30",
    label="leakage control")
DESIGN_CELLS: tuple[DesignCell, ...] = (DECISIVE, POSTCUTOFF)


def weekly_dates(cell: DesignCell) -> list[date]:
    """Every ``step_days`` from the first business day on or after ``start`` through ``end``."""
    d, end = date.fromisoformat(cell.start), date.fromisoformat(cell.end)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=cell.step_days)
    return out


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
    decisions = len(dates) * len(names)
    calls = decisions * cell.calls_per_decision
    lo, hi = (calls * s / 3600 for s in seconds_per_call)
    return {"cell": cell.name, "label": cell.label, "trial_name": cell.trial_name, "dates": len(dates),
            "first_date": dates[0].isoformat() if dates else None,
            "last_date": dates[-1].isoformat() if dates else None, "names": len(names),
            "decisions": decisions, "calls": calls, "cpu_hours": [round(lo, 1), round(hi, 1)],
            "cpu_days": [round(lo / 24, 1), round(hi / 24, 1)], "horizon_days": cell.horizon_days,
            "mde": mde_ic(len(dates), len(names), rho), "futility": futility_rule()}


def futility_rule() -> str:
    return (f"after {FUTILITY_MIN_DATES} dates, at every {FUTILITY_EVERY} decisions: stop if "
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


def incremental_ic(rows: Sequence[dict[str, Any]], *, lag: int = 1, min_names: int = 5) -> dict[str, Any]:
    """Mean per-date Spearman IC of (model - rule signal) on the forward return, NW SE by date.

    Rows need ``as_of``, ``signal_model``, ``signal_rule`` and ``fwd_ret``; rows whose model
    call fell back (``signal_model`` None) are excluded and counted. Also reports the model-only
    and rule-only ICs on the same rows."""
    by_d: dict[str, list[dict]] = {}
    excluded = 0
    for r in rows:
        if r.get("signal_model") is None or r.get("fwd_ret") is None or r.get("signal_rule") is None:
            excluded += 1
            continue
        by_d.setdefault(str(r["as_of"]), []).append(r)
    inc: list[float] = []
    mod: list[float] = []
    rul: list[float] = []
    for d in sorted(by_d):
        rs = by_d[d]
        if len(rs) < min_names:
            continue
        f = np.array([r["fwd_ret"] for r in rs], float)
        m = np.array([r["signal_model"] for r in rs], float)
        q = np.array([r["signal_rule"] for r in rs], float)
        for out, x in ((inc, m - q), (mod, m), (rul, q)):
            v = _spearman(x, f)
            if v is not None:
                out.append(v)

    def summ(xs: list[float]) -> dict[str, Any]:
        if not xs:
            return {"ic": None, "se": None, "t": None, "dates": 0}
        se = newey_west_se(xs, lag)
        mu = float(np.mean(xs))
        return {"ic": mu, "se": se, "t": mu / se if se and se > 0 else None, "dates": len(xs),
                "ci95": [mu - Z_975 * se, mu + Z_975 * se], "upper90_one_sided": mu + Z_90 * se}
    return {"incremental": summ(inc), "model": summ(mod), "rule": summ(rul), "excluded_rows": excluded,
            "rows": sum(len(v) for v in by_d.values())}


def futility_stop(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Apply the pre-registered futility rule to the rows so far."""
    res = incremental_ic(rows)["incremental"]
    if res["dates"] < FUTILITY_MIN_DATES or res["ic"] is None:
        return {"stop": False, "reason": f"fewer than {FUTILITY_MIN_DATES} dates", **res}
    ub = res["upper90_one_sided"]
    return {"stop": bool(ub < FUTILITY_IC), "reason": f"upper90 {ub:.4f} vs {FUTILITY_IC}", **res}


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
                def __init__(self, inner):
                    self.inner = inner

                def __getattr__(self, a):
                    return getattr(self.inner, a)

                def complete_json(self, system, prompt, *, deep, schema):
                    seen.append((system, prompt))
                    return self.inner.complete_json(system, prompt, deep=deep, schema=schema)

                def complete(self, system, prompt, *, deep):
                    seen.append((system, prompt))
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
    return {"cell": cell.name, "label": cell.label, "trial_name": cell.trial_name, "rows": n,
            "fallback_share": fell_back / n if n else None, "truncated_share": trunc / n if n else None,
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
