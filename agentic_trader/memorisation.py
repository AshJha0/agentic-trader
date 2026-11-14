"""Round 4 part B: the memorisation pair (registered 2026-11-14, before any row existed).

Plain idea. If a model has memorised price histories, telling it the real name and date helps
it before its training cutoff and cannot help after. So the same technical-analyst decision is
asked twice on the same state: ``named`` (real symbol, date and price level) and ``anon`` (the
desk's anonymised prompt). The gap in forecasting skill between the two arms is measured before
the cutoff and after it. A gap that exists before and vanishes after is memory.

Formally (``docs/evaluation/v19_round4_registration.md``, part B):

    IC_{t,a}  per-date cross-sectional Spearman IC of the model signal against the 5-trading-day
              forward return, inside each asset class with >= 5 usable names, weighted by names
    gap_t     IC_{t,named} - IC_{t,anon}       (same states, so paired by date)
    DiD       mean_t(gap_t | pre) - mean_t(gap_t | post)

with a 95 % moving-block bootstrap interval: each window's gap series is resampled on its own
in blocks of about four weeks (2,000 resamples). Memorisation is reported when the interval
lies wholly above zero. Windows: ``pre`` is the 20 first-pass design dates (weekdays spread over
2016-2021; the two that are NYSE closures score nothing, as in the first-pass report); ``post``
is the 70 weekly post-cutoff sessions of ``study_design.POSTCUTOFF``.

Worked example. Pre gaps averaging +0.06 and post gaps averaging +0.01 give DiD 0.05. If the
bootstrap interval is [0.01, 0.09] the pair reports memorisation; [-0.02, 0.12] reports no
evidence at this power, with the interval.

Evidence class: the arithmetic is unit-tested on synthetic rows; no part B row existed when this
module was written.
"""

from __future__ import annotations

import json
import math
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np

from .study_design import MAX_FALLBACK_SHARE, MIN_NAMES, POSTCUTOFF, _usable, decide, weekly_dates

ARMS = ("anon", "named")
WINDOWS = ("pre", "post")
HORIZON_DAYS = 5
BLOCK_DAYS = 28  # registered block length: four weeks
N_BOOT = 2000
BOOT_SEED = 20261114
FIRST_PASS_DATES = 20
DESIGN_START, DESIGN_END = date(2016, 1, 1), date(2021, 12, 31)
REGISTRATION = "docs/evaluation/v19_round4_registration.md"


class RegistrationNotSigned(RuntimeError):
    """Raised when part B is asked to run before the Round 4 registration is signed."""


def registration_gate(root: Path | str = ".") -> dict[str, str]:
    """The signed registration's path and SHA-256 for the run header; raises when it is absent
    or still a draft. Part B rows may exist only after the signature (registration, item 3)."""
    import hashlib

    p = Path(root) / REGISTRATION
    if not p.is_file():
        raise RegistrationNotSigned(f"{REGISTRATION} does not exist (the draft is not a registration)")
    first = p.read_text(encoding="utf-8").splitlines()[0]
    if "signed" not in first.lower() or "draft" in first.lower():
        raise RegistrationNotSigned(f"{REGISTRATION} is not marked signed in its title")
    return {"registration_path": REGISTRATION, "registration_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}


def first_pass_dates(n: int = FIRST_PASS_DATES) -> list[date]:
    """The first-pass grid: ``n`` weekdays spread evenly over the design period (the formula of
    ``scripts/llm_study.py design_dates``, repeated here so the package does not import a
    script; a test pins the two together)."""
    import pandas as pd

    days = pd.bdate_range(DESIGN_START, DESIGN_END)
    return [days[i].date() for i in np.linspace(0, len(days) - 1, n).round().astype(int)]


def grid(names: Sequence[str]) -> list[tuple[str, date, str, str]]:
    """Every registered decision as (window, date, name, arm). Both arms of a state sit next to
    each other, so a run stopped early leaves the arms balanced."""
    out = []
    for window, dates in (("pre", first_pass_dates()), ("post", weekly_dates(POSTCUTOFF))):
        for d in dates:
            for n in names:
                for arm in ARMS:
                    out.append((window, d, n, arm))
    return out


def run(
    names: Sequence[str],
    graph: Any,
    llm: Any,
    out: Path,
    *,
    header: dict[str, Any],
    limit: int = 0,
    echo: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    """Run part B into ``out`` (JSONL, one row per decision, resumable; rows already in the file
    are kept and skipped). ``header`` must already have passed ``study_lineage.check_resume``.
    A state that cannot be prepared (no bars) is recorded with ``error`` and scores nothing."""
    from .study_lineage import stamp

    out.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    done: set[tuple[str, str, str]] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            rows.append(r)
            done.add((r["symbol"], r["as_of"], r["arm"]))
    g = grid(names)
    if limit:
        g = g[:limit]
    t0 = time.time()
    with out.open("a", encoding="utf-8") as fh:
        for k, (window, d, n, arm) in enumerate(g, 1):
            if (n, d.isoformat(), arm) in done:
                continue
            try:
                row = decide(graph, llm, n, d, HORIZON_DAYS, named=arm == "named")
            except Exception as e:  # noqa: BLE001 - recorded per row; a closure has no bar
                row = {"symbol": n, "as_of": d.isoformat(), "signal_model": None, "signal_rule": None, "fwd_ret": None}
                row["error"] = f"{type(e).__name__}: {e}"[:300]
            row = {"cell": "memo_pair", "window": window, "arm": arm, **row, "horizon_days": HORIZON_DAYS}
            stamp(row, header)
            fh.write(json.dumps(row, default=str) + "\n")
            fh.flush()
            rows.append(row)
            echo(
                f"[{k}/{len(g)}] {window} {arm} {d} {n}: model={row['signal_model']} fwd={row['fwd_ret']} {time.time() - t0:.0f}s"
            )
    return rows


def _spearman(x: np.ndarray, y: np.ndarray) -> float | None:
    from .recall_audit import spearman

    v = spearman(list(x), list(y))
    return None if v is None or not math.isfinite(v) else v


def per_date_ic(rows: Sequence[dict[str, Any]], min_names: int = MIN_NAMES) -> dict[str, float]:
    """{as_of: IC_t} for one arm and window: Spearman(model, forward return) inside each asset
    class with at least ``min_names`` usable rows, weighted by rows. Unusable rows (fell back,
    no forward return, stale bar) are dropped by ``study_design._usable``."""
    by_d, _ = _usable(rows)
    out: dict[str, float] = {}
    for d, groups in by_d.items():
        acc = []
        for rs in groups.values():
            if len(rs) < min_names:
                continue
            v = _spearman(np.array([r["signal_model"] for r in rs], float), np.array([r["fwd_ret"] for r in rs], float))
            if v is not None:
                acc.append((v, len(rs)))
        w = sum(n for _, n in acc)
        if w:
            out[d] = sum(v * n for v, n in acc) / w
    return out


def block_length(dates: Sequence[str], block_days: int = BLOCK_DAYS) -> int:
    """Dates per bootstrap block: ``block_days`` over the median spacing of the window's dates,
    at least 1. Weekly dates give 4; the first-pass grid (about 115 days apart) gives 1."""
    ds = sorted(date.fromisoformat(d) for d in dates)
    if len(ds) < 2:
        return 1
    spacing = float(np.median([(b - a).days for a, b in zip(ds, ds[1:])]))
    return max(1, round(block_days / spacing)) if spacing > 0 else 1


def _block_means(x: np.ndarray, block: int, rng: np.random.Generator, n_boot: int) -> np.ndarray:
    """Moving-block bootstrap of the mean: blocks of ``block`` consecutive values (start drawn
    uniformly), concatenated and cut to the series length."""
    n = len(x)
    block = min(block, n)
    starts = n - block + 1
    k = math.ceil(n / block)
    idx = rng.integers(0, starts, size=(n_boot, k))[:, :, None] + np.arange(block)[None, None, :]
    return x[idx.reshape(n_boot, -1)[:, :n]].mean(axis=1)


def score(rows: Sequence[dict[str, Any]], *, n_boot: int = N_BOOT, seed: int = BOOT_SEED) -> dict[str, Any]:
    """The registered part B scoring (module docstring): per-window gaps, the DiD, its bootstrap
    interval, the verdict and the admissibility of each arm and window."""
    cells: dict[str, dict[str, Any]] = {}
    ics: dict[tuple[str, str], dict[str, float]] = {}
    for w in WINDOWS:
        for a in ARMS:
            rs = [r for r in rows if r.get("window") == w and r.get("arm") == a]
            fell = sum(r.get("signal_model") is None and not r.get("error") for r in rs)
            attempted = sum(not r.get("error") for r in rs)
            share = fell / attempted if attempted else None
            ics[(w, a)] = per_date_ic(rs)
            vals = list(ics[(w, a)].values())
            cells[f"{w}_{a}"] = {
                "rows": len(rs),
                "errors": sum(bool(r.get("error")) for r in rs),
                "fallback_share": share,
                "admissible": share is not None and share <= MAX_FALLBACK_SHARE,
                "dates_scored": len(vals),
                "mean_ic": float(np.mean(vals)) if vals else None,
            }
    rng = np.random.default_rng(seed)
    gaps: dict[str, dict[str, Any]] = {}
    boots = {}
    for w in WINDOWS:
        common = sorted(set(ics[(w, "named")]) & set(ics[(w, "anon")]))
        g = np.array([ics[(w, "named")][d] - ics[(w, "anon")][d] for d in common], float)
        b = block_length(common)
        gaps[w] = {"dates": len(common), "mean_gap": float(g.mean()) if len(g) else None, "block": b}
        boots[w] = _block_means(g, b, rng, n_boot) if len(g) else None
    admissible = all(c["admissible"] for c in cells.values())
    if boots["pre"] is None or boots["post"] is None:
        return {"cells": cells, "gaps": gaps, "did": None, "ci95": None, "verdict": "not scorable", "admissible": admissible}
    did = gaps["pre"]["mean_gap"] - gaps["post"]["mean_gap"]
    dist = boots["pre"] - boots["post"]
    lo, hi = (float(v) for v in np.percentile(dist, [2.5, 97.5]))
    if not admissible:
        verdict = "inadmissible: at least one arm/window above the 10 % fallback cap"
    elif lo > 0:
        verdict = "memorisation: the named-minus-anonymised gap is larger before the cutoff"
    else:
        verdict = "no evidence of memorisation at this power"
    return {
        "cells": cells,
        "gaps": gaps,
        "did": did,
        "ci95": [lo, hi],
        "n_boot": n_boot,
        "seed": seed,
        "verdict": verdict,
        "admissible": admissible,
        "registration": REGISTRATION,
    }


def dry_run(names: Sequence[str], seconds_per_call: tuple[float, float] = (30.0, 50.0)) -> dict[str, Any]:
    """Counts and wall-clock for the registered grid (no prices read, no model called)."""
    g = grid(names)
    by = {f"{w}_{a}": sum(1 for x in g if x[0] == w and x[3] == a) for w in WINDOWS for a in ARMS}
    lo, hi = (len(g) * s / 3600 for s in seconds_per_call)
    pre = first_pass_dates()
    post = weekly_dates(POSTCUTOFF)
    return {
        "decisions": len(g),
        "per_cell": by,
        "pre_dates": [pre[0].isoformat(), pre[-1].isoformat(), len(pre)],
        "post_dates": [post[0].isoformat(), post[-1].isoformat(), len(post)],
        "names": len(names),
        "hours": [round(lo, 1), round(hi, 1)],
        "blocks": {"pre": block_length([d.isoformat() for d in pre]), "post": block_length([d.isoformat() for d in post])},
        "last_post_scorable_after": (post[-1] + timedelta(days=10)).isoformat(),
    }
