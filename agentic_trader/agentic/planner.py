"""Planning: the canonical plan, an optional model-proposed plan, and the
validator that makes any plan safe to execute.

A plan is restricted to the tool catalogue and the desk's agent stages. The
validator:

* drops steps with an unknown type, tool or stage (and records why);
* drops unknown arguments and pins ``symbol`` / ``as_of`` to the task's values,
  so a plan cannot look at another instrument or another date;
* enforces stage order dependencies (debate needs analysts, trader needs the
  debate, risk needs the trader), inserting canonical stages when missing;
* appends the governance steps (critic, validate, finalise) when a plan omits
  them, always in that order and always last;
* caps the number of steps.

If nothing usable remains, the canonical plan is used and the fact is recorded.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from ..instruments import Instrument
from ..llm import LLM, extract_json
from .domain import GOVERNANCE_STEPS, Plan, PlanStep, StepType, Task
from .tools import ToolRegistry

MAX_STEPS = 25

# Agent stages the harness knows how to run. Analysts are "analyst:<name>".
AGENT_STAGES = ("debate", "trader", "risk")
ANALYST_PREFIX = "analyst:"

# Stage prerequisites: stage -> stages that must appear earlier in the plan.
_PREREQ = {"debate": ("analysts",), "trader": ("debate",), "risk": ("trader",)}


def canonical_plan(task: Task, instrument: Instrument, analysts: list[str], config: dict[str, Any],
                   registry: ToolRegistry) -> Plan:
    steps: list[PlanStep] = []
    if "knowledge.search" in registry:
        query = ("position sizing risk limits stop loss " +
                 ("fx carry" if instrument.is_fx else "equity strategic weight"))
        steps.append(PlanStep.make(StepType.TOOL, "knowledge.search", {"query": query, "k": 3},
                                   rationale="firm policy passages for the trader and PM"))
    if config.get("agentic", {}).get("use_alpha_tool", True) and "quant.alpha" in registry:
        steps.append(PlanStep.make(StepType.TOOL, "quant.alpha",
                                   {"symbol": instrument.symbol, "as_of": task.as_of.isoformat(), "horizon": 10},
                                   rationale="alpha snapshot and information coefficients"))
    for name in analysts:
        steps.append(PlanStep.make(StepType.AGENT, f"{ANALYST_PREFIX}{name}", rationale=f"{name} report"))
    steps.append(PlanStep.make(StepType.AGENT, "debate", rationale="bull/bear debate and verdict"))
    steps.append(PlanStep.make(StepType.AGENT, "trader", rationale="sized proposal"))
    steps.append(PlanStep.make(StepType.AGENT, "risk", rationale="risk team and portfolio manager"))
    steps.extend(governance_steps())
    return Plan(tuple(steps), "canonical")


def governance_steps() -> list[PlanStep]:
    return [PlanStep.make(StepType.CRITIC, "critic", id_="STEP-critic"),
            PlanStep.make(StepType.VALIDATE, "validate_evidence", id_="STEP-validate"),
            PlanStep.make(StepType.FINALISE, "finalise", id_="STEP-finalise")]


def propose_plan(llm: LLM, task: Task, instrument: Instrument, analysts: list[str],
                 registry: ToolRegistry) -> tuple[list[dict[str, Any]] | None, str | None]:
    """Ask the model for a plan as JSON. Returns (raw steps, raw text)."""
    catalogue = [{"name": d.name, "description": d.description,
                  "arguments": list(d.input_schema.get("properties", {}))} for d in registry.descriptors()]
    prompt = (
        f"Plan a trading decision on {instrument.display} ({instrument.asset_class}) as of "
        f"{task.as_of.isoformat()} for a {task.role.value}."
        + (f" The requester asks: {task.question}" if task.question else "") + "\n\n"
        f"Available tools (call with exact names and only these arguments):\n{json.dumps(catalogue, indent=1)}\n\n"
        f"Available agent stages: {', '.join(ANALYST_PREFIX + a for a in analysts)}, debate, trader, risk. "
        "Stages must appear in the order analysts -> debate -> trader -> risk. Governance steps "
        "(critic, validate_evidence, finalise) are added automatically.\n\n"
        'Respond with a JSON object {"steps": [{"type": "tool"|"agent", "name": "...", '
        '"arguments": {...}, "rationale": "..."}]} and nothing else.'
    )
    text = llm.complete("You are the planning assistant of a trading desk. Use only the listed tools "
                        "and stages; never invent names.", prompt, deep=True)
    data = extract_json(text)
    if not data or not isinstance(data.get("steps"), list):
        return None, text
    return data["steps"], text


def validate_plan(raw_steps: list[Any], task: Task, instrument: Instrument, analysts: list[str],
                  registry: ToolRegistry, source: str = "llm") -> Plan:
    notes: list[str] = []
    steps: list[PlanStep] = []
    allowed_agents = {f"{ANALYST_PREFIX}{a}" for a in analysts} | set(AGENT_STAGES)
    for i, raw in enumerate(raw_steps[:MAX_STEPS * 2]):
        if not isinstance(raw, dict):
            notes.append(f"step {i}: not an object, dropped")
            continue
        kind, name = str(raw.get("type", "")).lower(), str(raw.get("name", "")).strip()
        args = raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {}
        rationale = str(raw.get("rationale", ""))[:200]
        if kind == "tool":
            if name not in registry:
                notes.append(f"step {i}: unknown tool {name!r}, dropped")
                continue
            schema = registry.get(name).descriptor.input_schema
            props = schema.get("properties", {})
            clean = {k: v for k, v in args.items() if k in props}
            dropped = sorted(set(args) - set(clean))
            if dropped:
                notes.append(f"step {i}: {name} arguments {dropped} dropped")
            if "symbol" in props:
                if clean.get("symbol", instrument.symbol) != instrument.symbol:
                    notes.append(f"step {i}: {name} symbol pinned to {instrument.symbol}")
                clean["symbol"] = instrument.symbol
            if "as_of" in props:
                if clean.get("as_of", task.as_of.isoformat()) != task.as_of.isoformat():
                    notes.append(f"step {i}: {name} as_of pinned to {task.as_of.isoformat()}")
                clean["as_of"] = task.as_of.isoformat()
            if not registry.get(name).descriptor.annotations.read_only:
                notes.append(f"step {i}: {name} changes state; a plan may not schedule it, dropped")
                continue
            steps.append(PlanStep.make(StepType.TOOL, name, clean, rationale=rationale))
        elif kind == "agent":
            if name not in allowed_agents:
                notes.append(f"step {i}: unknown stage {name!r}, dropped")
                continue
            if any(s.type is StepType.AGENT and s.name == name for s in steps):
                notes.append(f"step {i}: duplicate stage {name}, dropped")
                continue
            steps.append(PlanStep.make(StepType.AGENT, name, rationale=rationale))
        elif kind in {t.value for t in GOVERNANCE_STEPS} | {"critic", "validate", "finalise", "human_approval"}:
            notes.append(f"step {i}: governance step {name!r} is managed by the harness")
        else:
            notes.append(f"step {i}: unknown step type {kind!r}, dropped")

    # Stage ordering and prerequisites.
    stage_names = [s.name for s in steps if s.type is StepType.AGENT]
    if not any(n.startswith(ANALYST_PREFIX) for n in stage_names):
        for a in analysts:
            steps.append(PlanStep.make(StepType.AGENT, f"{ANALYST_PREFIX}{a}", rationale="canonical"))
        notes.append("no analysts in plan: canonical analysts added")
    ordered_tools = [s for s in steps if s.type is StepType.TOOL]
    ordered_analysts = [s for s in steps if s.type is StepType.AGENT and s.name.startswith(ANALYST_PREFIX)]
    rest = []
    for stage in AGENT_STAGES:
        found = next((s for s in steps if s.type is StepType.AGENT and s.name == stage), None)
        if found is None:
            found = PlanStep.make(StepType.AGENT, stage, rationale="canonical")
            notes.append(f"stage {stage} missing: added")
        rest.append(found)
    steps = ordered_tools + ordered_analysts + rest
    if len(steps) > MAX_STEPS:
        notes.append(f"plan truncated to {MAX_STEPS} steps")
        steps = steps[:MAX_STEPS]
    steps.extend(governance_steps())
    return Plan(tuple(steps), source if not notes else f"{source}+repaired", tuple(notes))


def make_plan(task: Task, instrument: Instrument, analysts: list[str], config: dict[str, Any],
              registry: ToolRegistry, llm: LLM | None) -> Plan:
    if llm is None or not config.get("agentic", {}).get("llm_planner", False):
        return canonical_plan(task, instrument, analysts, config, registry)
    raw, _ = propose_plan(llm, task, instrument, analysts, registry)
    if raw is None:
        plan = canonical_plan(task, instrument, analysts, config, registry)
        return Plan(plan.steps, "canonical", ("model plan unusable: canonical plan used",))
    return validate_plan(raw, task, instrument, analysts, registry)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {"source": plan.source, "notes": list(plan.notes),
            "steps": [{"id": s.id, "type": s.type.value, "name": s.name, "arguments": s.arguments,
                       "rationale": s.rationale} for s in plan.steps]}


def _iso(d: date) -> str:
    return d.isoformat()
