"""Planning: the canonical plan, an optional model-proposed plan, and the
validator that makes any plan safe to execute.

A plan is restricted to the tool catalogue and the desk's agent stages. The
validator:

* drops steps with an unknown type, tool or stage (and records why);
* drops unknown arguments and pins ``symbol`` / ``as_of`` to the task's values,
  so a plan cannot look at another instrument or another date, and clips a
  ``symbols`` list to the configured universe (a step with nothing left is dropped,
  never a reason to fail the run);
* enforces stage order dependencies (debate needs analysts, trader needs the
  debate, risk needs the trader), inserting canonical stages when missing;
* appends the governance steps (critic, validate, finalise) when a plan omits
  them, always in that order and always last;
* caps the number of steps and the plan's data budget: the bars every tool step
  would load (symbols x lookback) must fit ``agentic.max_plan_lookback_bars``, so
  a model cannot schedule thousands of full-history evaluations in one plan.

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
DEFAULT_MAX_PLAN_LOOKBACK_BARS = 200_000
_ALPHA_TOOLS = {"quant.alpha", "quant.xalpha"}

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


def step_cost_bars(step: PlanStep, config: dict[str, Any] | None = None) -> int:
    """Calendar days of history a tool step loads, summed over its symbols (0 for steps
    that load none). The default window is the desk's ``lookback_days`` or, for the
    alpha tools, ``alpha_lookback_days``; an explicit ``lookback_days`` argument wins."""
    if step.type is not StepType.TOOL:
        return 0
    cfg = config or {}
    args = step.arguments
    symbols = args.get("symbols")
    n = len(symbols) if isinstance(symbols, (list, tuple)) else (1 if args.get("symbol") is not None else 0)
    if n == 0:
        return 0
    if isinstance(args.get("start"), str) and isinstance(args.get("end"), str):
        try:
            days = (date.fromisoformat(args["end"]) - date.fromisoformat(args["start"])).days
        except ValueError:
            days = 0
        return n * max(days, 0)
    lookback = args.get("lookback_days")
    if not isinstance(lookback, (int, float)) or isinstance(lookback, bool) or lookback <= 0:
        key = "alpha_lookback_days" if step.name in _ALPHA_TOOLS else "lookback_days"
        lookback = cfg.get(key, 900 if key == "alpha_lookback_days" else 400)
    return int(n * lookback)


def plan_cost_bars(steps: list[PlanStep] | tuple[PlanStep, ...], config: dict[str, Any] | None = None) -> int:
    return sum(step_cost_bars(s, config) for s in steps)


def max_plan_lookback_bars(config: dict[str, Any] | None) -> int:
    return int((config or {}).get("agentic", {}).get("max_plan_lookback_bars", DEFAULT_MAX_PLAN_LOOKBACK_BARS))


def clip_symbols(symbols: list[Any] | tuple[Any, ...], universe: list[str] | tuple[str, ...] | None
                 ) -> tuple[list[str], list[str], list[int]]:
    """(kept, dropped, indices): the entries of a ``symbols`` list that are in the configured
    universe (canonical spelling, duplicates removed) with their positions in the original
    list, and the entries that are not or do not parse. With no universe every parseable
    entry is kept."""
    allowed = {s.upper() for s in universe} if universe else None
    kept: list[str] = []
    dropped: list[str] = []
    indices: list[int] = []
    for i, s in enumerate(symbols):
        try:
            sym = Instrument.parse(str(s)).symbol
        except ValueError:
            dropped.append(str(s))
            continue
        if allowed is not None and sym not in allowed:
            dropped.append(sym)
        elif sym not in kept:
            kept.append(sym)
            indices.append(i)
    return kept, dropped, indices


def validate_plan(raw_steps: list[Any], task: Task, instrument: Instrument, analysts: list[str],
                  registry: ToolRegistry, source: str = "llm", config: dict[str, Any] | None = None) -> Plan:
    notes: list[str] = []
    steps: list[PlanStep] = []
    allowed_agents = {f"{ANALYST_PREFIX}{a}" for a in analysts} | set(AGENT_STAGES)
    universe = (config or {}).get("agentic", {}).get("symbol_universe")
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
            if "symbols" in props and isinstance(clean.get("symbols"), (list, tuple)):
                kept, dropped_syms, idx = clip_symbols(clean["symbols"], universe)
                if dropped_syms:
                    notes.append(f"step {i}: {name} symbols {dropped_syms} outside the configured universe dropped")
                if not kept:
                    notes.append(f"step {i}: {name} has no symbol in the configured universe, dropped")
                    continue
                targets = clean.get("targets")   # a parallel list (portfolio.construct) keeps its alignment
                if isinstance(targets, (list, tuple)) and len(targets) == len(clean["symbols"]):
                    clean["targets"] = [targets[j] for j in idx]
                clean["symbols"] = kept
            if "current_weight" in props and task.current_weight is not None:
                if clean.get("current_weight", task.current_weight) != task.current_weight:
                    notes.append(f"step {i}: {name} current_weight pinned to {task.current_weight:+.4f}")
                clean["current_weight"] = float(task.current_weight)
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
    # Identical tool steps are pointless repeats: they go before the step cap is applied, so
    # copies of one step cannot crowd a distinct later step out of the budget.
    seen: set[str] = set()
    unique_tools = []
    for s in ordered_tools:
        key = json.dumps({"name": s.name, "arguments": s.arguments}, sort_keys=True, default=str)
        if key in seen:
            notes.append(f"duplicate tool step {s.name} dropped")
            continue
        seen.add(key)
        unique_tools.append(s)
    # The cap only ever drops tool calls: the analysts and the debate / trader / risk
    # stages are what makes the plan a decision, so they are never truncated away.
    budget = max(0, MAX_STEPS - len(ordered_analysts) - len(rest))
    if len(unique_tools) > budget:
        notes.append(f"plan truncated to {MAX_STEPS} steps ({len(unique_tools) - budget} tool calls dropped)")
        unique_tools = unique_tools[:budget]
    # Data budget: the bars the remaining steps would load must fit the configured cap.
    cap, spent, kept_tools = max_plan_lookback_bars(config), 0, []
    for s in unique_tools:
        cost = step_cost_bars(s, config)
        if spent + cost > cap:
            notes.append(f"{s.name} dropped: plan would load {spent + cost} bars, over the "
                         f"max_plan_lookback_bars budget of {cap}")
            continue
        spent += cost
        kept_tools.append(s)
    steps = kept_tools + ordered_analysts + rest
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
    return validate_plan(raw, task, instrument, analysts, registry, config=config)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {"source": plan.source, "notes": list(plan.notes),
            "steps": [{"id": s.id, "type": s.type.value, "name": s.name, "arguments": s.arguments,
                       "rationale": s.rationale} for s in plan.steps]}


def _iso(d: date) -> str:
    return d.isoformat()
