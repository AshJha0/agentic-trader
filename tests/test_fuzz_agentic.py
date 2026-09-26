"""Property-based fuzzing of the agentic layer's input boundaries with hypothesis.

Everything a model or a remote caller can hand the harness -- tool arguments, plan
steps, policy requests, JSON replies, third-party text -- is generated at random and
must be either accepted in a well-formed way or refused with ``ValueError``; nothing
else may escape, and the invariants the rest of the system relies on (plans end with
governance, every tool step is pinned to the task, a decision is always made) must
hold for every input.
"""
import json
import re
from datetime import date

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import example, given, settings, strategies as st  # noqa: E402

from agentic_trader import Instrument, make_config  # noqa: E402
from agentic_trader.agentic import DeskTools, build_registry  # noqa: E402
from agentic_trader.agentic.domain import (  # noqa: E402
    Capability, PolicyDecision, PolicyOutcome, RiskLevel, Role, StepType, Task, ToolAnnotations,
    ToolDescriptor, ToolRequest,
)
from agentic_trader.agentic.planner import MAX_STEPS, validate_plan  # noqa: E402
from agentic_trader.agentic.policy import PolicyEngine  # noqa: E402
from agentic_trader.agentic.tools import coerce_arguments  # noqa: E402
from agentic_trader.agents.base import _TAG, untrusted_block  # noqa: E402
from agentic_trader.data import SyntheticProvider  # noqa: E402
from agentic_trader.llm import extract_json  # noqa: E402

FUZZ = settings(max_examples=80, deadline=None)
CFG = make_config(memory_path=None)
REGISTRY = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
TOOL_NAMES = [d.name for d in REGISTRY.descriptors()]
TASK = Task("AAPL", date(2024, 3, 1))
INS = Instrument.parse("AAPL")

# JSON-ish values, including the shapes a model tends to produce by mistake.
scalars = st.one_of(st.none(), st.booleans(), st.integers(-10**6, 10**6), st.floats(allow_nan=True, allow_infinity=True),
                    st.text(max_size=40), st.dates().map(lambda d: d.isoformat()), st.just("2024-13-45"))
json_values = st.recursive(scalars, lambda c: st.one_of(st.lists(c, max_size=4), st.dictionaries(st.text(max_size=8), c, max_size=4)),
                           max_leaves=8)
prop_types = st.sampled_from(["integer", "number", "boolean", "string", "array", "object", "date", None])


@st.composite
def schemas(draw):
    names = draw(st.lists(st.text(min_size=1, max_size=6), min_size=0, max_size=5, unique=True))
    props = {}
    for n in names:
        t = draw(prop_types)
        spec = {"type": "string", "format": "date"} if t == "date" else ({"type": t} if t else {})
        if draw(st.booleans()):
            spec["nullable"] = True
        props[n] = spec
    required = draw(st.lists(st.sampled_from(names), unique=True)) if names else []
    return {"type": "object", "properties": props, "required": required}


# ------------------------------------------------------------ coerce_arguments
@given(schema=schemas(), args=st.dictionaries(st.text(max_size=6), json_values, max_size=6))
@FUZZ
def test_coerce_arguments_accepts_typed_values_or_refuses(schema, args):
    try:
        out = coerce_arguments(schema, args)
    except ValueError:
        return
    props = schema["properties"]
    assert set(out) == set(args) and set(out) <= set(props)
    assert all(r in out for r in schema["required"])
    for k, v in out.items():
        spec = props[k]
        if v is None:
            assert spec.get("nullable")
        elif spec.get("format") == "date":
            assert isinstance(v, date)
        elif spec.get("type") == "integer":
            assert isinstance(v, int) and not isinstance(v, bool)
        elif spec.get("type") == "number":
            assert isinstance(v, float)
        elif spec.get("type") == "boolean":
            assert isinstance(v, bool)
        elif spec.get("type") == "string":
            assert isinstance(v, str) and len(v) <= 2000
        elif spec.get("type") == "array":
            assert isinstance(v, list) and len(v) <= 1000


@given(name=st.sampled_from(TOOL_NAMES), args=st.dictionaries(st.text(max_size=12), json_values, max_size=6))
@FUZZ
def test_real_tool_schemas_never_crash_on_random_arguments(name, args):
    schema = REGISTRY.get(name).descriptor.input_schema
    try:
        coerce_arguments(schema, args)
    except ValueError:
        pass


# ------------------------------------------------------------------ validate_plan
step_dicts = st.fixed_dictionaries({}, optional={
    "type": st.one_of(st.sampled_from(["tool", "agent", "critic", "validate", "finalise", "human_approval", "order"]),
                      st.text(max_size=8), st.integers()),
    "name": st.one_of(st.sampled_from(TOOL_NAMES + ["analyst:technical", "analyst:alpha", "analyst:bogus", "debate",
                                                    "trader", "risk", "execution.submit_order"]), st.text(max_size=12), st.none()),
    "arguments": st.one_of(st.dictionaries(st.sampled_from(["symbol", "as_of", "lookback_days", "horizon", "query", "k", "junk"]),
                                           json_values, max_size=4), json_values),
    "rationale": st.one_of(st.text(max_size=300), st.integers()),
})
raw_plans = st.lists(st.one_of(step_dicts, json_values), max_size=40)


@given(raw=raw_plans, analysts=st.lists(st.sampled_from(["technical", "fundamentals", "news", "sentiment", "alpha"]),
                                        min_size=1, max_size=5, unique=True))
@FUZZ
def test_validate_plan_always_yields_a_safe_plan(raw, analysts):
    plan = validate_plan(raw, TASK, INS, analysts, REGISTRY)
    steps = plan.steps
    kinds = [s.type for s in steps]
    # governance closes every plan, exactly once, in order
    assert kinds[-3:] == [StepType.CRITIC, StepType.VALIDATE, StepType.FINALISE]
    assert sum(k in (StepType.CRITIC, StepType.VALIDATE, StepType.FINALISE) for k in kinds) == 3
    assert len(steps) <= MAX_STEPS + 3
    tools = [s for s in steps if s.type is StepType.TOOL]
    agents = [s.name for s in steps if s.type is StepType.AGENT]
    for s in tools:
        assert s.name in REGISTRY
        desc = REGISTRY.get(s.name).descriptor
        assert desc.annotations.read_only                              # a plan never schedules an order
        props = desc.input_schema["properties"]
        assert set(s.arguments) <= set(props)
        if "symbol" in props:
            assert s.arguments["symbol"] == "AAPL"
        if "as_of" in props:
            assert s.arguments["as_of"] == "2024-03-01"
        assert len(s.rationale) <= 200
    # tools first, then analysts, then the three desk stages once each in order
    order = [s.type for s in steps[:-3]]
    assert order == sorted(order, key=lambda t: {StepType.TOOL: 0, StepType.AGENT: 1}[t])
    assert [a for a in agents if not a.startswith("analyst:")] == ["debate", "trader", "risk"]
    assert any(a.startswith("analyst:") for a in agents)
    assert all(a.split(":", 1)[1] in analysts for a in agents if a.startswith("analyst:"))
    assert len(agents) == len(set(agents))
    assert plan.source in ("llm", "llm+repaired")


# ----------------------------------------------------------------- policy engine
tool_descriptors = st.builds(
    ToolDescriptor, name=st.sampled_from(TOOL_NAMES + ["x.y"]), server=st.just("x"), description=st.just("d"),
    input_schema=st.just({"type": "object", "properties": {}}),
    annotations=st.builds(ToolAnnotations, read_only=st.booleans(), risk=st.sampled_from(list(RiskLevel)),
                          required=st.frozensets(st.sampled_from(list(Capability)), max_size=3)))
arg_dicts = st.dictionaries(st.sampled_from(["symbol", "as_of", "start", "end", "weight", "target_weight", "current_weight",
                                             "proposed_weight", "lookback_days", "other"]), json_values, max_size=5)


@given(tool=tool_descriptors, args=arg_dicts, role=st.sampled_from(list(Role)),
       deny=st.lists(st.sampled_from(TOOL_NAMES), max_size=2), universe=st.one_of(st.none(), st.lists(st.sampled_from(["AAPL", "MSFT"]))))
@FUZZ
def test_policy_always_decides_and_never_allows_what_it_must_not(tool, args, role, deny, universe):
    engine = PolicyEngine({"deny_tools": deny, "symbol_universe": universe, "max_position": 1.0})
    d = engine.evaluate(ToolRequest(tool.name, args, "CORR"), tool, role)
    assert isinstance(d, PolicyDecision) and d.outcome in PolicyOutcome and d.rule
    caps = engine.capabilities(role)
    if tool.name in deny:
        assert d.outcome is PolicyOutcome.DENY and d.rule == "deny_list"
    elif tool.annotations.required - caps:
        assert d.outcome is PolicyOutcome.DENY
    elif not tool.annotations.read_only:
        assert d.outcome is not PolicyOutcome.ALLOW                  # state changes are never waved through
        if Capability.PROPOSE_TRADES not in caps:
            assert d.outcome is PolicyOutcome.DENY
    if d.outcome is PolicyOutcome.ALLOW:
        assert tool.annotations.read_only and tool.annotations.risk is not RiskLevel.HIGH
        w = {k: args[k] for k in ("weight", "target_weight", "current_weight", "proposed_weight") if k in args}
        for v in w.values():
            assert v is None or abs(float(v)) <= 1.0
        sym = args.get("symbol")
        if universe and sym is not None:
            assert Instrument.parse(str(sym)).symbol in universe


# ------------------------------------------------- model replies and third-party text
@given(text=st.one_of(st.text(max_size=400), st.builds(json.dumps, json_values),
                      st.builds(lambda v, pre, post: pre + json.dumps(v) + post, json_values, st.text(max_size=30), st.text(max_size=30))))
@FUZZ
def test_extract_json_returns_a_dict_or_none(text):
    out = extract_json(text)
    assert out is None or isinstance(out, dict)


fragments = st.sampled_from([f"<{_TAG}", f"</{_TAG}", f"</{_TAG}>", f"< / {_TAG} >", f"<{_TAG.upper()} x=1>", ">", "\n"])


@given(lines=st.lists(st.one_of(st.text(max_size=120), fragments, st.builds(lambda a, b: a + b, fragments, st.text(max_size=20))),
                      max_size=6), label=st.text(min_size=1, max_size=10))
@example(lines=[f"<{_TAG}"], label="x")
@example(lines=[f"</{_TAG}", ">"], label="x")
@FUZZ
def test_untrusted_block_cannot_be_closed_from_inside(lines, label):
    block = untrusted_block(label, lines)
    body = block.split("\n", 1)[1].rsplit("\n", 1)[0]
    assert re.search(rf"<\s*/?\s*{_TAG}", body, flags=re.I | re.S) is None   # the tag itself, not e.g. <untrusted_data0>
    assert block.startswith(f"<{_TAG} ") and block.endswith(f"</{_TAG}>")


@given(n_tools=st.integers(20, 40))
@FUZZ
def test_plan_cap_never_drops_the_desk_stages(n_tools):
    raw = [{"type": "tool", "name": "market_data.history", "arguments": {"symbol": "AAPL"}}] * n_tools
    raw += [{"type": "agent", "name": "analyst:technical"}, {"type": "agent", "name": "debate"},
            {"type": "agent", "name": "trader"}, {"type": "agent", "name": "risk"}]
    plan = validate_plan(raw, TASK, INS, ["technical"], REGISTRY)
    agents = [s.name for s in plan.steps if s.type is StepType.AGENT]
    assert agents == ["analyst:technical", "debate", "trader", "risk"]
    assert len(plan.steps) <= MAX_STEPS + 3
