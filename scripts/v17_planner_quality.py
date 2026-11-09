"""Planner quality table (review B7), offline, no model.

    python scripts/v17_planner_quality.py [--fixtures tests/data/v15_local_model_plans.jsonl]
                                          [--out docs/results/v17_planner_quality]

Reads the recorded local-model plans for the 200 survival tasks, rebuilds the canonical plan
for each task and writes ``summary.json``, ``per_plan.csv`` and ``table.md``.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from agentic_trader import make_config  # noqa: E402
from agentic_trader.agentic.planner import canonical_plan, validate_plan  # noqa: E402
from agentic_trader.agentic.planner_quality import plan_quality, summarise  # noqa: E402
from agentic_trader.graph import DEFAULT_ANALYSTS  # noqa: E402

FIXTURES = ROOT / "tests" / "data" / "v15_local_model_plans.jsonl"
OUT = ROOT / "docs" / "results" / "v17_planner_quality"


def compute(fixtures: Path, budget: int = 200_000) -> tuple[list[dict], dict]:
    from agentic_trader.agentic.servers import DeskTools, build_registry
    from agentic_trader.data import SyntheticProvider
    from v15_governance import tasks
    cfg = make_config()
    cfg.setdefault("agentic", {})["max_plan_lookback_bars"] = budget
    registry = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
    plans = {}
    model = "model"
    for line in fixtures.read_text(encoding="utf-8").splitlines():
        if line.strip():
            obj = json.loads(line)
            plans[obj["task_id"]] = obj["steps"]
            model = obj.get("model", model)
    rows = []
    for task, inst in tasks():
        if task.id not in plans:
            continue
        analysts = list(DEFAULT_ANALYSTS[inst.asset_class])
        canon = canonical_plan(task, inst, analysts, cfg, registry)
        raw = plans[task.id]
        val = validate_plan(raw, task, inst, analysts, registry, config=cfg) if raw is not None else None
        q = plan_quality(raw, canon.steps, val)
        rows.append({"task_id": task.id, **q})
    summ = {"model": model, "fixtures": fixtures.relative_to(ROOT).as_posix() if fixtures.is_relative_to(ROOT)
            else str(fixtures), **summarise(rows)}
    return rows, summ


def render(s: dict) -> str:
    f = lambda x: "n/a" if x != x else f"{x:.3f}"  # noqa: E731 - nan check
    return "\n".join([
        f"# Planner quality vs canonical plan ({s['model']}, recorded plans, {s['plans']} tasks)",
        "",
        "| metric | value |", "|---|---|",
        f"| usable plans | {s['usable']} / {s['plans']} |",
        f"| step-set precision (usable) | {f(s['precision_mean'])} |",
        f"| step-set recall (usable) | {f(s['recall_mean'])} |",
        f"| step-set F1 (usable) | {f(s['f1_mean'])} |",
        f"| step-set F1 (all plans, unusable = 0) | {f(s['f1_mean_all_plans'])} |",
        f"| pairwise order agreement (usable) | {f(s['order_agreement_mean'])} |",
        f"| plans needing zero repair | {f(s['zero_repair_share'])} |",
        f"| plans equal to canonical (names, order) | {f(s['exact_canonical_share'])} |",
        "",
        "Evidence class: measured offline on recorded replies "
        f"({s['fixtures']}); governance steps excluded on both sides.", ""])


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--fixtures", default=str(FIXTURES))
    p.add_argument("--out", default=str(OUT))
    a = p.parse_args(argv)
    rows, summ = compute(Path(a.fixtures))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(summ, indent=2) + "\n", encoding="utf-8")
    with (out / "per_plan.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (out / "table.md").write_text(render(summ), encoding="utf-8")
    print(render(summ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
