"""The agentic layer: domain, evidence, tools, policy, planner, harness state
machine, critic, audited reporter, knowledge retrieval and tracing. Offline."""
import json
import threading
import time
from datetime import date, timedelta

import numpy as np
import pytest

from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import (AgentHarness, AutoApprovalGateway, Capability, DenyApprovalGateway,
                                    DeskTools, EvidenceStore, EvidenceType, Finding, KnowledgeBase,
                                    Metrics, PolicyEngine, PolicyOutcome, QueuedApprovalGateway, Role,
                                    Task, TaskState, ToolExecutor, ToolRegistry, Tracer, build_registry,
                                    canonical_plan, evidence_audit, number_audit, schema_from_signature,
                                    validate_plan)
from agentic_trader.agentic.critic import Critic
from agentic_trader.agentic.domain import (RiskLevel, StepType, ToolAnnotations, ToolRequest, TRANSITIONS,
                                           canonical_json, digest)
from agentic_trader.agentic.harness import IllegalTransition
from agentic_trader.agentic.planner import ANALYST_PREFIX, make_plan
from agentic_trader.agentic.reporter import build_report, collect_facts
from agentic_trader.agentic.tools import coerce_arguments
from agentic_trader.data import SyntheticProvider
from agentic_trader.instruments import Instrument
from agentic_trader.memory import DecisionMemory

CFG = make_config(memory_path=None)
AS_OF = date(2024, 3, 1)


def graph(cfg=CFG, **kw):
    return TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None, **kw)


def harness(cfg=CFG, **kw):
    return AgentHarness(graph(cfg), **kw)


# ------------------------------------------------------------------ domain
def test_canonical_json_and_digest_are_stable():
    a = {"b": [1, 2.5, date(2024, 1, 2)], "a": np.array([1.0, 2.0]), "n": float("nan")}
    b = {"a": np.array([1.0, 2.0]), "n": float("nan"), "b": [1, 2.5, date(2024, 1, 2)]}
    assert canonical_json(a) == canonical_json(b)
    assert digest(a) == digest(b) and len(digest(a)) == 64
    assert digest({"x": 1}) != digest({"x": 2})


def test_transition_table_has_no_shortcut_to_completed():
    for s, allowed in TRANSITIONS.items():
        if s not in (TaskState.FINALISING,):
            assert TaskState.COMPLETED not in allowed, s


# ---------------------------------------------------------------- evidence
def test_evidence_store_resolves_and_detects_tampering():
    st = EvidenceStore()
    ev = st.record(EvidenceType.DATA, "market_data.news", "2 headlines", [{"h": "x"}], "CID-1")
    assert st.resolve(ev.id) and st.get(ev.id) is ev and len(st) == 1
    assert st.unresolved([ev.id, "DATA-deadbeef"]) == ["DATA-deadbeef"]
    ev.payload.append({"h": "injected"})            # payload mutated after the fact
    assert not st.resolve(ev.id)
    with pytest.raises(ValueError):
        st.add(ev)


# ------------------------------------------------------------------- tools
def test_schema_from_signature_and_coercion():
    def f(symbol: str, as_of: date, k: int = 3, weight: float | None = None, tags: list[str] = []) -> dict:
        """Doc."""
        return {}
    s = schema_from_signature(f)
    assert s["required"] == ["symbol", "as_of"] and s["properties"]["as_of"]["format"] == "date"
    assert s["properties"]["weight"]["nullable"] and s["properties"]["tags"]["type"] == "array"
    out = coerce_arguments(s, {"symbol": "AAPL", "as_of": "2024-03-01", "k": 2.0, "weight": None})
    assert out["as_of"] == date(2024, 3, 1) and out["k"] == 2 and out["weight"] is None
    for bad in ({"symbol": "AAPL"}, {"symbol": "AAPL", "as_of": "2024-03-01", "extra": 1},
                {"symbol": "AAPL", "as_of": "2024-03-01", "k": 2.5}, {"symbol": 1, "as_of": "2024-03-01"},
                {"symbol": "AAPL", "as_of": "2024-03-01", "k": True}, {"symbol": "x" * 3000, "as_of": "2024-03-01"}):
        with pytest.raises(ValueError):
            coerce_arguments(s, bad)


def test_registry_rejects_duplicates_and_lists_catalogue():
    reg = ToolRegistry()

    @reg.tool("demo", read_only=True, risk=RiskLevel.LOW, required={Capability.READ_MARKET_DATA})
    def echo(x: int) -> int:
        """Echo."""
        return x
    with pytest.raises(ValueError):
        reg.register("demo", echo)
    with pytest.raises(KeyError):
        reg.get("demo.nope")
    cat = reg.catalogue()
    assert cat[0]["name"] == "demo.echo" and cat[0]["read_only"] and "demo" in reg.servers()


def _executor(reg, role=Role.TRADER, gateway=None, timeout=5.0, policy_cfg=None):
    from agentic_trader.agentic.tools import ExecutorConfig
    return ToolExecutor(reg, PolicyEngine(policy_cfg or {"max_position": 1.0}), EvidenceStore(), role,
                        gateway or AutoApprovalGateway(), Tracer(), ExecutorConfig(timeout_s=timeout, max_attempts=2,
                                                                                   retry_backoff_s=0.0))


def test_executor_records_evidence_for_success_and_failure():
    reg = ToolRegistry()

    @reg.tool("demo")
    def ok(x: int) -> dict:
        """Ok."""
        return {"x": x}

    @reg.tool("demo")
    def boom(x: int) -> dict:
        """Boom."""
        raise RuntimeError("kaboom")
    ex = _executor(reg)
    r = ex.call("demo.ok", x=1)
    assert r.ok and r.payload == {"x": 1} and r.attempts == 1
    ev = ex.evidence_for(r)
    assert ev is not None and ev.type is EvidenceType.DATA and ex.evidence.resolve(ev.id)
    r2 = ex.call("demo.boom", x=1)
    assert not r2.ok and "kaboom" in r2.error and r2.attempts == 1        # a bug is not retried
    assert len(ex.evidence) == 2 and "FAILED" in list(ex.evidence)[-1].summary
    r3 = ex.call("demo.missing", x=1)
    assert not r3.ok and "unknown tool" in r3.error
    assert ex.tracer.metrics.counter("tool_calls_total", tool="demo.ok", outcome="ok") == 1


def test_executor_retries_transient_errors_and_times_out():
    reg = ToolRegistry()
    calls = {"n": 0}

    @reg.tool("demo")
    def flaky() -> int:
        """Flaky."""
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("blip")
        return 7

    @reg.tool("demo")
    def slow() -> int:
        """Slow."""
        time.sleep(0.5)
        return 1
    ex = _executor(reg, timeout=0.05)
    r = ex.call("demo.flaky")
    assert r.ok and r.payload == 7 and r.attempts == 2
    r2 = ex.call("demo.slow")
    assert not r2.ok and "timed out" in r2.error and r2.attempts == 2


# ------------------------------------------------------------------ policy
def _tool(read_only=True, risk=RiskLevel.LOW, required=frozenset({Capability.READ_MARKET_DATA})):
    from agentic_trader.agentic.domain import ToolDescriptor
    return ToolDescriptor("demo.t", "demo", "t", {"type": "object", "properties": {}},
                          ToolAnnotations(read_only, risk, required, EvidenceType.DATA))


def _req(**args):
    return ToolRequest("demo.t", args, "CID-1")


def test_policy_rules_in_order():
    pe = PolicyEngine({"symbol_universe": ["AAPL", "EURUSD"], "max_position": 0.5, "deny_tools": ["demo.t"]})
    d = pe.evaluate(_req(), _tool(), Role.ADMIN)
    assert d.outcome is PolicyOutcome.DENY and d.rule == "deny_list"
    pe = PolicyEngine({"symbol_universe": ["AAPL", "EURUSD"], "max_position": 0.5})
    assert pe.evaluate(_req(), _tool(required=frozenset({Capability.APPROVE_TRADES})), Role.TRADER).rule == "required_capabilities"
    d = pe.evaluate(_req(), _tool(read_only=False, required=frozenset()), Role.ANALYST)
    assert d.outcome is PolicyOutcome.DENY and d.rule == "read_only"
    d = pe.evaluate(_req(), _tool(read_only=False, required=frozenset()), Role.TRADER)
    assert d.outcome is PolicyOutcome.REQUIRE_APPROVAL and d.rule == "read_only"
    for args in ({"symbol": "MSFT"}, {"symbol": "EUR/XYZ"}, {"as_of": (date.today() + timedelta(days=1)).isoformat()},
                 {"as_of": "not-a-date"}, {"weight": 0.7}, {"weight": float("nan")}, {"weight": "x"},
                 {"lookback_days": 0}):
        d = pe.evaluate(_req(**args), _tool(), Role.ADMIN)
        assert d.outcome is PolicyOutcome.DENY and d.rule == "argument_guard", args
    d = pe.evaluate(_req(), _tool(risk=RiskLevel.HIGH), Role.ADMIN)
    assert d.outcome is PolicyOutcome.REQUIRE_APPROVAL and d.rule == "risk_level"
    d = pe.evaluate(_req(symbol="AAPL", weight=0.4), _tool(), Role.VIEWER)
    assert d.allowed and d.rule == "default_allow"
    assert len(pe.decisions) == 13


def test_policy_fails_closed_without_a_terminal_rule():
    pe = PolicyEngine(rules=(lambda ctx: None,))
    assert pe.evaluate(_req(), _tool(), Role.ADMIN).rule == "no_rule"


def test_queued_gateway_round_trip_and_deny_gateway():
    q = QueuedApprovalGateway()
    req = ToolRequest("execution.submit_order", {"symbol": "AAPL", "side": "buy", "quantity": 1}, "CID-1")
    assert q.decide("T1", req, "why") is None
    assert q.decide("T1", ToolRequest("execution.submit_order", req.arguments, "CID-2"), "why") is None
    assert len(q.pending()) == 1                       # same tool + arguments = same approval
    a = q.pending("T1")[0]
    q.resolve(a.id, True, "risk", "fine")
    assert q.decide("T1", req, "why") is True and not q.pending()
    with pytest.raises(ValueError):
        q.resolve(a.id, False)
    with pytest.raises(KeyError):
        q.resolve("APPROVAL-nope", True)
    assert DenyApprovalGateway().decide("T", req, "") is False


# ----------------------------------------------------------------- servers
def test_desk_tools_payloads_are_json_safe_and_point_in_time():
    tools = DeskTools(SyntheticProvider(CFG), CFG)
    reg = build_registry(tools)
    assert len(reg) == 15 and set(reg.servers()) == {"market_data", "quant", "knowledge", "portfolio", "execution"}
    hist = tools.history("AAPL", AS_OF, 60)
    assert max(hist["dates"]) <= AS_OF.isoformat() and len(hist["Close"]) == len(hist["dates"])
    json.dumps(hist); json.dumps(tools.technical("EURUSD", AS_OF)); json.dumps(tools.risk("AAPL", AS_OF, 0.5))
    news = tools.news("AAPL", AS_OF, 7)
    assert all(n["published"] <= AS_OF.isoformat() for n in news)
    assert tools.macro("USDJPY", AS_OF)["rate_diff"] == pytest.approx(3.75)
    assert tools.fundamentals("EURUSD", AS_OF) == {}
    assert tools.position("aapl") == {"symbol": "AAPL", "weight": 0.0, "capital": CFG["initial_capital"]}
    with pytest.raises(ValueError):
        tools.search("x", k=0)
    with pytest.raises(ValueError):
        tools.baselines("AAPL", "2024-03-01", "2024-01-01")
    alpha = tools.alpha("AAPL", AS_OF)
    assert "combined" in alpha["latest"] and alpha["horizon"] == 10
    plan = tools.plan("AAPL", AS_OF, 0.5, 0.1)
    assert plan["trade"] and plan["algo"] == "vwap" and 0 < plan["completion"] <= 1
    assert tools.plan("AAPL", AS_OF, 0.3, 0.3) == {"trade": False, "reason": "target equals current position"}
    pw = tools.construct(["AAPL", "JPM"], [1.0, 0.5], AS_OF, "inverse_vol")
    assert set(pw["weights"]) == {"AAPL", "JPM"} and pw["method"] == "inverse_vol"


# --------------------------------------------------------------- knowledge
def test_knowledge_base_retrieval():
    kb = KnowledgeBase.from_dir()
    assert len(kb.documents) == 11 and len(kb) > 30
    hits = kb.search("what is the value at risk cap", 3)
    assert hits and hits[0].chunk.doc_id == "risk_limits_policy"
    hits = kb.search("carry publication lag FRED", 2)
    assert hits[0].chunk.doc_id == "fx_carry_methodology"
    assert kb.search("", 3) == [] and kb.get(hits[0].chunk.id) is hits[0].chunk
    small = KnowledgeBase.from_texts({"a": "# A\n\n## One\nalpha beta\n\n## Two\ngamma"})
    assert [c.heading for c in small.chunks] == ["One", "Two"]


# ----------------------------------------------------------------- planner
def test_canonical_plan_ends_with_governance():
    ins = Instrument.parse("AAPL")
    reg = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
    plan = canonical_plan(Task("AAPL", AS_OF), ins, ["technical", "news"], CFG, reg)
    names = [s.name for s in plan.steps]
    assert names[-3:] == ["critic", "validate_evidence", "finalise"]
    assert names[:2] == ["knowledge.search", "quant.alpha"] and "analyst:technical" in names


def test_validate_plan_strips_repairs_pins_and_appends_governance():
    ins = Instrument.parse("AAPL")
    reg = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
    raw = [
        {"type": "tool", "name": "market_data.news", "arguments": {"symbol": "MSFT", "as_of": "2020-01-01",
                                                                   "lookback_days": 3, "evil": 1}},
        {"type": "tool", "name": "execution.submit_order", "arguments": {"symbol": "AAPL", "side": "buy", "quantity": 1}},
        {"type": "tool", "name": "nope.tool", "arguments": {}},
        {"type": "agent", "name": "risk"},
        {"type": "agent", "name": "analyst:technical"},
        {"type": "agent", "name": "analyst:technical"},
        {"type": "agent", "name": "rogue_stage"},
        {"type": "finalise", "name": "finalise"},
        "garbage", {"type": "??", "name": "x"},
    ]
    plan = validate_plan(raw, Task("AAPL", AS_OF), ins, ["technical", "news"], reg)
    names = [s.name for s in plan.steps]
    assert plan.source == "llm+repaired"
    tool = plan.steps[0]
    assert tool.name == "market_data.news" and tool.arguments == {"symbol": "AAPL", "as_of": AS_OF.isoformat(),
                                                                 "lookback_days": 3}
    assert "execution.submit_order" not in names and "nope.tool" not in names and "rogue_stage" not in names
    assert names.count("analyst:technical") == 1
    assert names[-6:] == ["debate", "trader", "risk", "critic", "validate_evidence", "finalise"]
    assert any("pinned" in n for n in plan.notes) and any("changes state" in n for n in plan.notes)


def test_make_plan_uses_canonical_when_model_output_is_unusable():
    class Bad:
        def complete(self, *a, **k):
            return "I have no plan for you."
    cfg = make_config(CFG, agentic={"llm_planner": True})
    reg = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
    plan = make_plan(Task("AAPL", AS_OF), Instrument.parse("AAPL"), ["technical"], cfg, reg, Bad())
    assert plan.source == "canonical" and "unusable" in plan.notes[0]

    class Good:
        def complete(self, *a, **k):
            return json.dumps({"steps": [{"type": "agent", "name": "analyst:technical"}]})
    plan = make_plan(Task("AAPL", AS_OF), Instrument.parse("AAPL"), ["technical"], cfg, reg, Good())
    assert plan.source.startswith("llm") and [s.name for s in plan.steps][-3:] == ["critic", "validate_evidence", "finalise"]


# ----------------------------------------------------------------- harness
@pytest.mark.parametrize("symbol", ["AAPL", "USDJPY"])
def test_harness_completes_with_evidence_findings_and_clean_audit(symbol):
    run = harness().run(Task(symbol, AS_OF, Role.TRADER, current_weight=0.1))
    assert run.state is TaskState.COMPLETED and not run.errors
    assert [h[0] for h in run.history] == ["PLANNING", "VALIDATING_PLAN", "EXECUTING", "CRITIQUING",
                                           "VALIDATING_EVIDENCE", "FINALISING", "COMPLETED"]
    assert len(run.evidence) >= 15 and run.findings and run.report is not None
    assert run.report.warnings == []                              # narrative audits clean
    assert all(run.evidence.resolve(i) for f in run.findings for i in f.evidence_ids)
    assert run.decision is not None and run.decision.evidence_ids
    assert run.trading_state.knowledge and run.trading_state.alpha
    kinds = {e.type for e in run.evidence}
    assert {EvidenceType.DATA, EvidenceType.CALCULATION, EvidenceType.DOCUMENT, EvidenceType.DECISION} <= kinds
    assert run.critic.passed and run.tracer.summary()["errors"] == 0
    assert run.to_dict()["state"] == "COMPLETED"


def test_harness_decision_matches_propagate():
    cfg = make_config(CFG, agentic={"use_alpha_tool": False})
    _, plain = graph(cfg).propagate("AAPL", AS_OF, current_weight=0.1)
    run = harness(cfg).run(Task("AAPL", AS_OF, current_weight=0.1))
    assert run.decision.target_weight == plain.target_weight and run.decision.action == plain.action


def test_harness_refuses_role_without_capability():
    run = harness().run(Task("AAPL", AS_OF, Role.VIEWER))
    assert run.state is TaskState.FAILED and "denied by policy" in run.errors[0]


def test_harness_fails_cleanly_on_bad_input():
    run = harness().run(Task("AAPL", date(2015, 1, 20)))
    assert run.state is TaskState.FAILED and "not enough history" in run.errors[0]
    run = harness(make_config(CFG, agentic={"symbol_universe": ["EURUSD"]})).run(Task("AAPL", AS_OF))
    assert run.state is TaskState.FAILED and "outside the configured universe" in run.errors[0]
    with pytest.raises(ValueError):
        harness(make_config(CFG, agentic={"approval": "bogus"}))


def test_harness_awaits_approval_then_resumes_or_cancels():
    h = harness(gateway=QueuedApprovalGateway())
    ins = Instrument.parse("AAPL")
    reg = h.registry
    # A plan that starts with a state-changing tool cannot come from the validator; build it by hand.
    from agentic_trader.agentic.domain import Plan, PlanStep
    run = h.submit(Task("AAPL", AS_OF, Role.TRADER))
    order = PlanStep.make(StepType.TOOL, "execution.submit_order", {"symbol": "AAPL", "side": "buy", "quantity": 5})
    base = canonical_plan(run.task, ins, h.graph.analyst_names(ins), CFG, reg)
    h._transition(run, TaskState.PLANNING)
    run.plan = Plan((order,) + base.steps, "test")
    h._transition(run, TaskState.VALIDATING_PLAN)
    h._transition(run, TaskState.EXECUTING)
    h.resume(run)
    assert run.state is TaskState.AWAITING_APPROVAL and run.pending_step == order.id
    pend = h.pending_approvals(run.id)
    assert len(pend) == 1 and pend[0].request.tool == "execution.submit_order"
    h.decide_approval(pend[0].id, True, "risk", "ok")
    assert run.state is TaskState.COMPLETED and order.id in run.completed_steps
    assert any(e.type is EvidenceType.APPROVAL for e in run.evidence)
    assert h.tools.orders and h.tools.orders[0]["status"] == "ticketed"

    run2 = h.submit(Task("AAPL", AS_OF, Role.TRADER))
    h._transition(run2, TaskState.PLANNING)
    run2.plan = Plan((PlanStep.make(StepType.TOOL, "execution.submit_order",
                                    {"symbol": "AAPL", "side": "sell", "quantity": 9}),) + base.steps, "test")
    h._transition(run2, TaskState.VALIDATING_PLAN)
    h._transition(run2, TaskState.EXECUTING)
    h.resume(run2)
    assert run2.state is TaskState.AWAITING_APPROVAL
    h.cancel(run2.id)
    assert run2.state is TaskState.CANCELLED and run2.finished_at is not None
    assert h.resume(run2).state is TaskState.CANCELLED           # terminal: resume is a no-op


def test_rejected_approval_fails_the_step_but_finishes_the_task():
    h = harness(gateway=DenyApprovalGateway())
    run = h.submit(Task("AAPL", AS_OF, Role.TRADER))
    from agentic_trader.agentic.domain import Plan, PlanStep
    ins = Instrument.parse("AAPL")
    base = canonical_plan(run.task, ins, h.graph.analyst_names(ins), CFG, h.registry)
    h._transition(run, TaskState.PLANNING)
    run.plan = Plan((PlanStep.make(StepType.TOOL, "execution.submit_order",
                                   {"symbol": "AAPL", "side": "buy", "quantity": 5}),) + base.steps, "test")
    h._transition(run, TaskState.VALIDATING_PLAN)
    h._transition(run, TaskState.EXECUTING)
    h.resume(run)
    assert run.state is TaskState.COMPLETED and any("approval rejected" in e for e in run.errors)
    assert not h.tools.orders


def test_illegal_transition_is_refused():
    h = harness()
    run = h.submit(Task("AAPL", AS_OF))
    with pytest.raises(IllegalTransition):
        h._transition(run, TaskState.COMPLETED)


def test_cancel_between_steps():
    h = harness()
    run = h.submit(Task("AAPL", AS_OF))
    run.cancel_requested = True
    h.resume(run)
    assert run.state is TaskState.CANCELLED and run.trading_state is not None


def test_harness_is_usable_from_threads():
    h = harness()
    runs = [h.submit(Task(s, AS_OF)) for s in ("AAPL", "MSFT", "EURUSD", "USDJPY")]
    threads = [threading.Thread(target=h.resume, args=(r,)) for r in runs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r.state is TaskState.COMPLETED for r in runs)
    assert len({r.correlation_id for r in runs}) == 4


# ------------------------------------------------------------------ critic
def test_critic_flags_divergence_wrong_side_levels_and_limits():
    st, _ = graph().propagate("AAPL", AS_OF)
    findings = [Finding.make("technical", "x", 0.9, ("DATA-00000001",))]
    store = EvidenceStore()
    rep = Critic(make_config(CFG, agentic={"llm_critic": False})).review(st, findings, store)
    assert not rep.passed and findings[0].confidence == 0.0          # unresolved evidence is an error
    # model view far from its rules
    st.reports["technical"].source, st.reports["technical"].rule_signal = "llm", -0.9
    st.decision.stop_loss = st.last_price * 1.5                       # wrong side for a long
    st.decision.target_weight = 1.5                                   # above the cap
    rep = Critic(make_config(CFG, agentic={"llm_critic": False})).review(st, [], store, {"var_95_1d": 0.05})
    names = {c.name: c for c in rep.checks}
    assert not names["model_rule_divergence"].passed and rep.multiplier <= 0.7
    assert not names["protective_levels"].passed and not names["firm_limits"].passed
    assert "VaR" in names["firm_limits"].detail


def test_llm_critique_can_only_lower_confidence():
    class Booster:
        def complete(self, system, prompt, *, deep):
            return json.dumps({"concerns": ["none"], "confidence_multiplier": 3.0})
    st, _ = graph().propagate("AAPL", AS_OF)
    rep = Critic(CFG, Booster()).review(st, [], EvidenceStore())
    assert rep.llm_multiplier == 1.0 and rep.multiplier == 1.0 and rep.llm_concerns == ["none"]

    class Doubter:
        def complete(self, system, prompt, *, deep):
            return json.dumps({"concerns": ["thin evidence"], "confidence_multiplier": 0.4})
    rep = Critic(CFG, Doubter()).review(st, [], EvidenceStore())
    assert rep.multiplier == pytest.approx(0.4)


# ---------------------------------------------------------------- reporter
def test_number_and_evidence_audits():
    facts = {"target_weight": 0.5354, "last_close": 223.219, "n_bullish": 4.0, "confidence": 0.51}
    ok = "BUY at +0.54 (confidence 0.51); last close 223.22; 4 analysts; that is 53.5% of capital."
    assert number_audit(ok, facts) == []
    assert number_audit("weight 0.99 and 17 analysts", facts) == ["0.99", "17"]
    assert number_audit("as of 2024-03-01 see DATA-0123abcd", facts) == []   # dates and ids are not figures
    store = EvidenceStore()
    ev = store.record(EvidenceType.DATA, "x", "y", {"a": 1}, "C")
    assert evidence_audit(f"see {ev.id}", [], store) == []
    assert evidence_audit("see DATA-deadbeef", [Finding.make("a", "b", 0.5, ("DEC-00000000",))], store) == \
        ["DATA-deadbeef", "DEC-00000000"]


def test_report_flags_fabricated_numbers_and_ids_from_a_model():
    class Fabricator:
        def complete(self, system, prompt, *, deep):
            return ("Buy with weight +0.5354 (confidence 0.51). Revenue grew 99.9% and the fill rate was 42%; "
                    "see EXEC-deadbeef and DATA-ffffffff.")
    st, _ = graph().propagate("AAPL", AS_OF)
    critic = Critic(make_config(CFG, agentic={"llm_critic": False})).review(st, [], EvidenceStore())
    rep = build_report(Task("AAPL", AS_OF), st, [], critic, EvidenceStore(), Fabricator())
    assert rep.narrative_source == "llm"
    joined = " ".join(rep.warnings)
    assert "99.9%" in joined and "42%" in joined and "DATA-ffffffff" in joined
    assert "EXEC-deadbeef" not in joined                              # not one of our id prefixes
    md = rep.to_markdown()
    assert "## Audit warnings" in md and "## Evidence" in md
    facts = collect_facts(st, critic)
    assert facts["n_analysts"] == 4 and facts["target_weight"] == st.decision.target_weight


# ----------------------------------------------------------------- tracing
def test_tracer_and_metrics_render():
    tr = Tracer()
    with tr.span("outer", a=1) as o:
        with tr.span("inner"):
            pass
        o.set(b=2)
    with pytest.raises(RuntimeError):
        with tr.span("bad"):
            raise RuntimeError("x")
    spans = tr.to_list()
    assert spans[1]["parent_id"] == spans[0]["id"] and spans[2]["status"] == "error"
    assert tr.summary()["errors"] == 1 and tr.summary()["spans"] == 3
    m = Metrics()
    m.inc("c", tool="a"); m.inc("c", tool="a"); m.observe("h", 12.0, tool="a")
    text = m.render()
    assert 'c{tool="a"} 2' in text and "# TYPE h histogram" in text and 'h_count{tool="a"} 1' in text
    assert 'h_bucket{tool="a",le="10.0"} 0' in text and 'h_bucket{tool="a",le="25.0"} 1' in text
