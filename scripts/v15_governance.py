"""Plan items 4.1 and 4.2: outcome-aware governance report and planner survival table.

    python scripts/v15_governance.py outcomes --store PATH.db --memory PATH.jsonl [--provider yahoo]
    python scripts/v15_governance.py survival [--fixtures tests/data/v15_model_plans.jsonl] [--regen]

``outcomes`` joins recorded TaskRuns (a ``TaskStore`` SQLite file and/or JSON/JSONL records) to
``DecisionMemory`` realised P&L and prints per-role hit rates, critic-flag/outcome correlation,
false-positive rate per critic check and a weekly roll-up, every number with its sample size.

``survival`` runs 200 tasks through three planners -- the canonical plan, the rule planner
(``make_plan`` without a model: the canonical plan re-fed through ``validate_plan``) and
model-style plans read from a fixture file -- and prints step survival, additions and data-budget
hits. No model is called. The repository holds no recorded live-model plans ($0 rule), so the
fixture plans are synthetic: generated from a seed to carry the faults a planning model makes
(invented tools, other symbols and dates, oversized cross-sectional calls, state-changing tools,
missing or reordered stages, unparseable replies). They measure the validator, not a model.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader import make_config  # noqa: E402
from agentic_trader.agentic.domain import Role, Task  # noqa: E402
from agentic_trader.agentic.governance import (  # noqa: E402
    governance_report,
    join_outcomes,
    planner_survival,
    render_report,
    survival_table,
    weekly_rollup,
)
from agentic_trader.agentic.planner import canonical_plan, make_plan, validate_plan  # noqa: E402
from agentic_trader.graph import DEFAULT_ANALYSTS  # noqa: E402
from agentic_trader.instruments import Instrument  # noqa: E402
from agentic_trader.memory import DecisionMemory  # noqa: E402

FIXTURES = ROOT / "tests" / "data" / "v15_model_plans.jsonl"
SYMBOLS = ["AAPL", "MSFT", "NVDA", "JPM", "XOM", "SPY", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
CRITIC_CHECKS = (
    "evidence_resolves",
    "model_rule_divergence",
    "analyst_contradiction",
    "firm_limits",
    "protective_levels",
    "direction_vs_verdict",
    "llm_critique_wellformed",
)


# ----------------------------------------------------------------------------- outcomes
def load_records(paths: list[str]) -> list[dict]:
    out: list[dict] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            continue
        if path.suffix in {".db", ".sqlite", ".sqlite3"}:
            from agentic_trader.agentic.store import TaskStore

            st = TaskStore(path)
            out.extend(st.load_all())
            st.close()
        elif path.suffix == ".jsonl":
            out.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
            out.extend(data if isinstance(data, list) else [data])
    return out


def cmd_outcomes(a: argparse.Namespace) -> int:
    records = load_records(a.store)
    mem = DecisionMemory(a.memory) if a.memory and Path(a.memory).exists() else DecisionMemory(None)
    rows = join_outcomes(records, mem, provider=a.provider)
    rep = governance_report(rows, CRITIC_CHECKS)
    print(f"TaskRun records read: {len(records)}; memory entries: {len(mem.entries)}")
    print(render_report(rep, weekly_rollup(rows)))
    if a.json:
        Path(a.json).write_text(json.dumps({"report": rep, "weeks": weekly_rollup(rows)}, indent=1, default=str))
    return 0


# ----------------------------------------------------------------------------- survival
def tasks(n: int = 200, seed: int = 15) -> list[tuple[Task, Instrument]]:
    rng = random.Random(seed)
    out = []
    for i in range(n):
        sym = SYMBOLS[i % len(SYMBOLS)]
        day = date(2024, 1, 2) + timedelta(days=rng.randrange(0, 600))
        role = (Role.TRADER, Role.ANALYST, Role.RISK)[i % 3]
        out.append((Task(sym, day, role, id=f"TASK-v15-{i:03d}"), Instrument.parse(sym)))
    return out


def _model_plan(rng: random.Random, task: Task, inst: Instrument, analysts: list[str]) -> list | None:
    """One synthetic model-style plan with seeded faults (None: an unparseable reply)."""
    if rng.random() < 0.05:
        return None
    sym, day = inst.symbol, task.as_of.isoformat()
    steps: list = []
    if rng.random() < 0.8:
        steps.append({"type": "tool", "name": "knowledge.search", "arguments": {"query": "position limits", "k": 3}})
    if rng.random() < 0.7:
        steps.append({"type": "tool", "name": "quant.alpha", "arguments": {"symbol": sym, "as_of": day, "horizon": 10}})
    if rng.random() < 0.15:  # invented tool
        steps.append(
            {
                "type": "tool",
                "name": rng.choice(["market_data.options", "quant.ml_forecast", "web.search"]),
                "arguments": {"symbol": sym},
            }
        )
    if rng.random() < 0.15:  # another symbol / date
        steps.append(
            {"type": "tool", "name": "quant.technical", "arguments": {"symbol": rng.choice(SYMBOLS), "as_of": "2026-01-01"}}
        )
    if rng.random() < 0.2:  # oversized cross-section: data-budget pressure
        steps.append(
            {
                "type": "tool",
                "name": "quant.xalpha",
                "arguments": {"symbols": SYMBOLS * 4, "as_of": day, "lookback_days": rng.choice([900, 5000, 20000])},
            }
        )
    if rng.random() < 0.1:
        steps.append({"type": "tool", "name": "quant.baselines", "arguments": {"symbol": sym, "start": "1990-01-01", "end": day}})
    if rng.random() < 0.1:  # state-changing tool
        steps.append({"type": "tool", "name": "execution.submit_order", "arguments": {"symbol": sym, "side": "buy"}})
    if rng.random() < 0.1:  # unknown argument
        steps.append({"type": "tool", "name": "quant.risk", "arguments": {"symbol": sym, "as_of": day, "leverage": 5}})
    chosen = analysts if rng.random() < 0.7 else rng.sample(analysts, k=rng.randint(0, len(analysts)))
    steps += [{"type": "agent", "name": f"analyst:{a}"} for a in chosen]
    if rng.random() < 0.05:
        steps.append({"type": "agent", "name": "analyst:astrology"})
    stages = ["debate", "trader", "risk"]
    if rng.random() < 0.1:
        stages.remove(rng.choice(stages))
    if rng.random() < 0.1:
        rng.shuffle(stages)
    steps += [{"type": "agent", "name": s} for s in stages]
    if rng.random() < 0.1:
        steps.append({"type": "critic", "name": "critic"})
    if rng.random() < 0.03:
        steps.append("finish")
    return steps


def regen_fixtures(path: Path, cfg: dict, seed: int = 1515) -> None:
    rng = random.Random(seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for task, inst in tasks():
            analysts = list(DEFAULT_ANALYSTS[inst.asset_class])
            f.write(json.dumps({"task_id": task.id, "synthetic": True, "steps": _model_plan(rng, task, inst, analysts)}) + "\n")


def survival(cfg: dict, registry, fixtures: Path) -> list[dict]:
    plans, label = {}, "model plans (synthetic fixture)"
    if fixtures.exists():
        for line in fixtures.read_text(encoding="utf-8").splitlines():
            if line.strip():
                obj = json.loads(line)
                plans[obj["task_id"]] = obj["steps"]
                if obj.get("synthetic") is False:
                    label = f"model plans (local {obj.get('model', 'model')}, recorded)"
    res: dict[str, list[dict]] = {"canonical": [], "rule planner": [], label: []}
    for task, inst in tasks():
        analysts = list(DEFAULT_ANALYSTS[inst.asset_class])
        canon = canonical_plan(task, inst, analysts, cfg, registry)
        canon_raw = [
            {"type": s.type.value, "name": s.name, "arguments": dict(s.arguments)}
            for s in canon.steps
            if s.type.value in {"tool", "agent"}
        ]
        res["canonical"].append(planner_survival(canon_raw, canon))
        rule = make_plan(task, inst, analysts, cfg, registry, llm=None)
        rule_v = validate_plan(canon_raw, task, inst, analysts, registry, source="rules", config=cfg)
        assert [s.name for s in rule.steps] == [s.name for s in rule_v.steps]
        res["rule planner"].append(planner_survival(canon_raw, rule_v))
        if task.id in plans:
            raw = plans[task.id]
            plan = (
                validate_plan(raw, task, inst, analysts, registry, config=cfg)
                if raw is not None
                else canonical_plan(task, inst, analysts, cfg, registry)
            )
            res[label].append(planner_survival(raw, plan))
    return survival_table(res)


def render_survival(rows: list[dict]) -> str:
    lines = [
        "| Source | Tasks | Steps proposed | Survived | Survival | Added | Repaired | Unusable | Budget hits (plans) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = "n/a" if r["step_survival"] is None else f"{r['step_survival']:.1%}"
        lines.append(
            f"| {r['source']} | {r['tasks']} | {r['steps_proposed']} | {r['steps_survived']} | {s} | "
            f"{r['steps_added']} | {r['plans_repaired']} | {r['plans_unusable']} | "
            f"{r['budget_hits']} ({r['plans_with_budget_hit']}) |"
        )
    return "\n".join(lines)


def cmd_survival(a: argparse.Namespace) -> int:
    from agentic_trader.agentic.servers import DeskTools, build_registry
    from agentic_trader.data import SyntheticProvider

    cfg = make_config()
    cfg.setdefault("agentic", {})["max_plan_lookback_bars"] = a.budget
    registry = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
    fx = Path(a.fixtures)
    if a.regen or not fx.exists():
        regen_fixtures(fx, cfg)
    print(render_survival(survival(cfg, registry, fx)))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("outcomes")
    o.add_argument("--store", nargs="*", default=[], help="TaskStore .db or JSON/JSONL TaskRun records")
    o.add_argument("--memory", default=None, help="DecisionMemory JSONL")
    o.add_argument("--provider", default=None)
    o.add_argument("--json", default=None)
    o.set_defaults(fn=cmd_outcomes)
    s = sub.add_parser("survival")
    s.add_argument("--fixtures", default=str(FIXTURES))
    s.add_argument("--regen", action="store_true")
    s.add_argument("--budget", type=int, default=200_000, help="agentic.max_plan_lookback_bars")
    s.set_defaults(fn=cmd_survival)
    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
