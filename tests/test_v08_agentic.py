"""v0.8 agentic-services fixes (review findings 11, 12, 43-49, 51-53, 58, 59): argument guards
before approval, list-typed symbols and the plan data budget, at-most-once state-changing
tool calls, one driver per run, terminal-only record caching, bounded retention, one
Prometheus exposition, create_app honouring the approval mode, lease-gated sweeps, and a
governed MCP surface that fails closed on unannotated remote tools. All offline.

This module doubles as a hostile MCP stdio server when run with ``--serve`` (a tool with
no annotations and no meta), so the remote-tool classification is tested end to end.
"""
import asyncio
import json
import re
import sys
import threading
import time
from collections import Counter
from datetime import date

if "--serve" in sys.argv:   # hostile MCP server for test_remote_tools_without_annotations_fail_closed
    from mcp.server.mcpserver import MCPServer
    srv = MCPServer("hostile-broker")

    @srv.tool(name="broker__submit_order", description="Submit a live order")   # no annotations, no meta
    def submit_order(symbol: str, side: str, quantity: int) -> dict:
        return {"status": "filled", "symbol": symbol, "side": side, "quantity": quantity}

    srv.run(transport="stdio")
    sys.exit(0)

import pytest

from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import (AgentHarness, AutoApprovalGateway, Capability, DenyApprovalGateway,
                                    EvidenceStore, EvidenceType, Metrics, PolicyEngine, PolicyOutcome,
                                    QueuedApprovalGateway, Role, Task, TaskState, ToolExecutor, ToolRegistry,
                                    Tracer, validate_plan)
from agentic_trader.agentic.critic import Critic
from agentic_trader.agentic.domain import Plan, PlanStep, RiskLevel, StepType, ToolRequest
from agentic_trader.agentic.harness import wait_until_done
from agentic_trader.agentic.planner import canonical_plan, plan_cost_bars
from agentic_trader.agentic.servers import DeskTools, build_registry, ticket_from_plan
from agentic_trader.agentic.store import TaskStore
from agentic_trader.agentic.tools import ExecutorConfig
from agentic_trader.data import SyntheticProvider
from agentic_trader.instruments import Instrument
from agentic_trader.memory import DecisionMemory

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)
AS_OF = date(2024, 3, 1)
KEY = {"viewer": {"X-API-Key": "dev-viewer-key"}, "trader": {"X-API-Key": "dev-trader-key"},
       "risk": {"X-API-Key": "dev-risk-key"}}


def harness(cfg=CFG, **kw):
    return AgentHarness(TradingGraph(cfg, **QUIET), **kw)


def _ticket(h, symbol, target):
    return ticket_from_plan(h.tools.plan(symbol, AS_OF, target))


def _parked_run(h, tickets):
    """A run paused in AWAITING_APPROVAL on a hand-built plan whose first steps are orders."""
    ins = Instrument.parse("AAPL")
    run = h.submit(Task("AAPL", AS_OF, Role.TRADER))
    orders = tuple(PlanStep.make(StepType.TOOL, "execution.submit_order", t) for t in tickets)
    base = canonical_plan(run.task, ins, h.graph.analyst_names(ins), h.config, h.registry)
    h._transition(run, TaskState.PLANNING)
    run.plan = Plan(orders + base.steps, "test")
    h._transition(run, TaskState.VALIDATING_PLAN)
    h._transition(run, TaskState.EXECUTING)
    h.resume(run)
    assert run.state is TaskState.AWAITING_APPROVAL
    assert len(h.pending_approvals(run.id)) == len(tickets)
    return run


def _assert_single_execution(h, run, n_orders):
    assert run.state is TaskState.COMPLETED, (run.state, run.errors)
    assert not run.errors
    assert len(h.tools.orders) == n_orders and len({o["plan_id"] for o in h.tools.orders}) == n_orders
    agents = [f.agent for f in run.findings]
    assert len(agents) == len(set(agents)), agents          # every stage ran once
    assert run.history.count(("COMPLETED",)) == 0 and sum(s == "COMPLETED" for s, _ in run.history) == 1


# ------------------------------------------------- 43 / 59: guards before approval
def test_argument_guards_run_before_the_approval_decision_for_state_changing_tools():
    reg = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
    desc = reg.get("execution.submit_order").descriptor
    pe = PolicyEngine({"symbol_universe": ["AAPL"], "max_position": 1.0, "max_order_notional": 50_000})
    good = {"symbol": "AAPL", "side": "buy", "quantity": 10, "quantity_unit": "shares", "notional": 1000.0,
            "notional_currency": "USD", "price": 100.0, "plan_id": "PLAN-x"}
    d = pe.evaluate(ToolRequest("execution.submit_order", {**good, "symbol": "ZZZQ"}, "C"), desc, Role.TRADER)
    assert d.outcome is PolicyOutcome.DENY and d.rule == "argument_guard" and "outside the configured universe" in d.reason
    for bad in ({"quantity": float("nan")}, {"quantity": -1}, {"quantity": "ten"}, {"quantity": 0},
                {"notional": 60_000.0}, {"symbol": "EUR/XYZ"}):
        d = pe.evaluate(ToolRequest("execution.submit_order", {**good, **bad}, "C"), desc, Role.TRADER)
        assert d.outcome is PolicyOutcome.DENY and d.rule == "argument_guard", (bad, d)
    # a clean request still needs approval (read-only rule), never ALLOW
    d = pe.evaluate(ToolRequest("execution.submit_order", good, "C"), desc, Role.TRADER)
    assert d.outcome is PolicyOutcome.REQUIRE_APPROVAL and d.rule == "read_only"
    # and a role without the capability is refused by the capability rule before any guard
    d = pe.evaluate(ToolRequest("execution.submit_order", {**good, "symbol": "ZZZQ"}, "C"), desc, Role.VIEWER)
    assert d.outcome is PolicyOutcome.DENY and d.rule == "required_capabilities"

    # End to end under the default auto gateway: the out-of-universe order is not ticketed.
    h = harness(make_config(CFG, agentic={"symbol_universe": ["AAPL"]}), gateway=AutoApprovalGateway())
    ex = h._executor(h.submit(Task("AAPL", AS_OF, Role.TRADER)))
    res = ex.call("execution.submit_order", **_ticket(h, "MSFT", 0.1))
    assert not res.ok and "denied by policy (argument_guard)" in res.error and "MSFT" in res.error
    assert h.tools.orders == []
    assert ex.call("execution.submit_order", **_ticket(h, "AAPL", 0.1)).ok and len(h.tools.orders) == 1
    assert any(e.type is EvidenceType.APPROVAL for e in ex.evidence)


# ------------------------------------------------- 46: symbols lists and the plan budget
def test_symbol_lists_are_checked_element_wise_and_capped():
    pe = PolicyEngine({"symbol_universe": ["AAPL", "MSFT"], "max_position": 1.0, "max_symbols_per_call": 5})
    reg = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
    xd = reg.get("quant.xalpha").descriptor
    ok = pe.evaluate(ToolRequest("quant.xalpha", {"symbols": ["AAPL", "MSFT"], "as_of": "2024-03-01"}, "C"), xd,
                     Role.TRADER)
    assert ok.outcome is PolicyOutcome.ALLOW
    for syms, why in ((["AAPL", "MSFT", "ZZZQ"], "ZZZQ is outside"), (["AAPL", "EUR/XYZ"], "currency"),
                      ([f"S{i}" for i in range(6)], "at most 5 per call"), ("AAPL", "must be a list")):
        d = pe.evaluate(ToolRequest("quant.xalpha", {"symbols": syms, "as_of": "2024-03-01"}, "C"), xd, Role.TRADER)
        assert d.outcome is PolicyOutcome.DENY and d.rule == "argument_guard" and why in d.reason, (syms, d)
    cd = reg.get("portfolio.construct").descriptor
    d = pe.evaluate(ToolRequest("portfolio.construct", {"symbols": ["S1", "S2"], "targets": [1, 1],
                                                          "as_of": "2024-03-01"}, "C"), cd, Role.TRADER)
    assert d.outcome is PolicyOutcome.DENY and d.rule == "argument_guard"


def test_a_36k_evaluation_plan_is_rejected():
    cfg = make_config(CFG, agentic={"symbol_universe": ["AAPL", "MSFT"], "llm_planner": True})
    h = harness(cfg)
    ins, task = Instrument.parse("AAPL"), Task("AAPL", AS_OF)
    analysts = h.graph.analyst_names(ins)
    raw = [{"type": "tool", "name": "quant.xalpha",
            "arguments": {"symbols": [f"S{k:02d}{i:04d}" for i in range(1000)], "as_of": AS_OF.isoformat()}}
           for k in range(20)]
    # The validator keeps nothing of it: each step alone (1000 x 900 bars) is over the budget.
    plan = validate_plan(raw, task, ins, analysts, h.registry, config=cfg)
    assert not [s for s in plan.steps if s.type is StepType.TOOL]
    assert sum("max_plan_lookback_bars" in n for n in plan.notes) == 18     # 2 fell to the step cap first
    assert any("truncated" in n for n in plan.notes)
    assert plan_cost_bars(plan.steps, cfg) == 0
    # A hand-built plan that bypasses the validator is refused by the harness pre-check:
    # the symbols cap and the universe first ...
    run = h.submit(task)
    big = PlanStep.make(StepType.TOOL, "quant.xalpha", raw[0]["arguments"])
    base = canonical_plan(task, ins, analysts, cfg, h.registry)
    h._transition(run, TaskState.PLANNING)
    run.plan = Plan((big,) + base.steps, "test")
    d = h.policy.evaluate(ToolRequest("quant.xalpha", big.arguments, "C"), h.registry.get("quant.xalpha").descriptor,
                          Role.TRADER)
    assert d.outcome is PolicyOutcome.DENY and "at most 60 per call" in d.reason
    # ... and the aggregate budget even when every step passes policy on its own.
    cfg2 = make_config(CFG, agentic={"max_plan_lookback_bars": 100_000})
    h2 = harness(cfg2)
    from agentic_trader.agentic import planner as planner_mod
    real_make_plan = planner_mod.make_plan

    def oversized(task_, ins_, analysts_, config_, registry_, llm_):
        base_ = real_make_plan(task_, ins_, analysts_, config_, registry_, llm_)
        steps = tuple(PlanStep.make(StepType.TOOL, "quant.xalpha", {"symbols": ["AAPL", "MSFT", "GOOG"] * 20,
                                                                   "as_of": AS_OF.isoformat(), "horizon": k})
                      for k in (5, 10, 20)) + base_.steps
        return Plan(steps, "test")
    import agentic_trader.agentic.harness as harness_mod
    harness_mod.make_plan, planner_mod.make_plan = oversized, oversized
    try:
        run2 = h2.run(Task("AAPL", AS_OF))
    finally:
        harness_mod.make_plan, planner_mod.make_plan = real_make_plan, real_make_plan
    assert run2.state is TaskState.FAILED and "over max_plan_lookback_bars=100000" in run2.errors[0]
    assert plan_cost_bars(run2.plan.steps, cfg2) == 3 * 60 * 900 + 900


def test_validate_plan_drops_duplicate_tool_steps_and_keeps_the_budget():
    reg = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
    ins = Instrument.parse("AAPL")
    raw = [{"type": "tool", "name": "market_data.history", "arguments": {"symbol": "AAPL"}}] * 5
    raw += [{"type": "tool", "name": "market_data.history", "arguments": {"symbol": "AAPL", "lookback_days": 30}}]
    plan = validate_plan(raw, Task("AAPL", AS_OF), ins, ["technical"], reg, config=CFG)
    tools = [s for s in plan.steps if s.type is StepType.TOOL]
    assert len(tools) == 2 and sum("duplicate" in n for n in plan.notes) == 4
    assert plan_cost_bars(tools, CFG) == CFG["lookback_days"] + 30


# ------------------------------------------------- 44: at most one side effect per approval
def test_state_changing_tools_are_never_retried_and_timeouts_are_isolated():
    reg = ToolRegistry()
    invocations, commits = Counter(), []

    @reg.tool("oms", read_only=False, risk=RiskLevel.HIGH, required={Capability.PROPOSE_TRADES},
              evidence_type=EvidenceType.DECISION)
    def slow_order(symbol: str) -> dict:
        """Commits after a delay longer than the timeout."""
        invocations["slow"] += 1
        time.sleep(0.5)
        commits.append(("slow", symbol))
        return {"ok": True}

    @reg.tool("oms", read_only=False, risk=RiskLevel.HIGH, required={Capability.PROPOSE_TRADES},
              evidence_type=EvidenceType.DECISION)
    def flaky_order(symbol: str) -> dict:
        """Commits, then the connection drops on the reply."""
        invocations["flaky"] += 1
        commits.append(("flaky", symbol))
        raise ConnectionError("reset after commit")

    @reg.tool("demo")
    def slow_read() -> int:
        """Read-only and slow."""
        invocations["read"] += 1
        time.sleep(0.5)
        return 1

    @reg.tool("demo")
    def hang() -> int:
        """Never returns in time."""
        time.sleep(3.0)
        return 0

    @reg.tool("demo")
    def fast() -> int:
        """Fast."""
        return 1

    ex = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.TRADER, AutoApprovalGateway(),
                      Tracer(), ExecutorConfig(timeout_s=0.15, max_attempts=2, retry_backoff_s=0.01))
    r = ex.call("oms.slow_order", symbol="AAPL")
    assert not r.ok and "timed out" in r.error and "outcome unknown" in r.error and r.attempts == 1
    r2 = ex.call("oms.flaky_order", symbol="MSFT")
    assert not r2.ok and "transient" in r2.error and "not retried" in r2.error and r2.attempts == 1
    time.sleep(0.8)                                       # let the abandoned worker land its side effect
    assert invocations["slow"] == 1 and commits.count(("slow", "AAPL")) == 1      # exactly one, not two
    assert invocations["flaky"] == 1 and commits.count(("flaky", "MSFT")) == 1
    assert sum(1 for e in ex.evidence if "FAILED oms." in e.summary) == 2
    # read-only tools keep their retry
    r3 = ex.call("demo.slow_read")
    assert not r3.ok and r3.attempts == 2
    # a timed-out worker is abandoned, not left holding a shared pool: four hung calls in a row do
    # not delay the fifth, and the abandonments are counted
    t0 = time.perf_counter()
    for _ in range(4):
        assert not ex.call("demo.hang").ok
    assert ex.call("demo.fast").ok and time.perf_counter() - t0 < 2.5
    assert ex.tracer.metrics.counter("tool_calls_abandoned_total", tool="demo.hang") == 8
    assert ex.tracer.metrics.counter("tool_calls_abandoned_total", tool="oms.slow_order") == 1


# ------------------------------------------------- 11 / 45: one driver per run
@pytest.mark.parametrize("trial", range(3))
def test_two_approvals_decided_back_to_back_execute_each_step_once(trial):
    h = harness(gateway=QueuedApprovalGateway())
    run = _parked_run(h, [_ticket(h, "AAPL", 0.1), _ticket(h, "AAPL", 0.2)])
    for a in h.pending_approvals(run.id):
        h.decide_approval(a.id, True, "risk", "ok", resume=False)
    barrier, errors = threading.Barrier(2), []

    def drive():
        try:
            barrier.wait()
            h.resume(run)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)
    threads = [threading.Thread(target=drive) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert errors == []
    _assert_single_execution(h, run, 2)


def test_sequential_and_racing_decisions_never_drive_a_run_twice():
    # CLI path: each decision resumes on the calling thread; the second waits for its own approval.
    h = harness(gateway=QueuedApprovalGateway())
    run = _parked_run(h, [_ticket(h, "AAPL", 0.1), _ticket(h, "AAPL", 0.2)])
    a1, a2 = h.pending_approvals(run.id)
    h.decide_approval(a1.id, True)
    assert run.state is TaskState.AWAITING_APPROVAL and len(h.tools.orders) == 1
    assert [a.id for a in h.pending_approvals(run.id)] == [a2.id]
    h.decide_approval(a2.id, True)
    _assert_single_execution(h, run, 2)
    # A decision that lands while another thread drives the run is picked up by that driver
    # (or drives itself when the run is parked) -- never by a second concurrent driver.
    for _ in range(4):
        h = harness(gateway=QueuedApprovalGateway())
        run = _parked_run(h, [_ticket(h, "AAPL", 0.1), _ticket(h, "AAPL", 0.2)])
        a1, a2 = h.pending_approvals(run.id)
        t = threading.Thread(target=h.decide_approval, args=(a1.id, True))
        t.start()
        h.decide_approval(a2.id, True)
        t.join(120)
        wait_until_done(run, 120)
        if run.state is TaskState.AWAITING_APPROVAL:   # both decisions recorded, nobody driving: illegal
            pytest.fail("run left parked with every approval decided")
        _assert_single_execution(h, run, 2)


def test_approve_and_cancel_race_is_safe():
    outcomes = Counter()
    for _ in range(5):
        h = harness(gateway=QueuedApprovalGateway())
        run = _parked_run(h, [_ticket(h, "AAPL", 0.1)])
        a = h.pending_approvals(run.id)[0]
        barrier = threading.Barrier(2)

        def approve():
            barrier.wait()
            h.decide_approval(a.id, True)

        def cancel():
            barrier.wait()
            h.cancel(run.id)
        ts = [threading.Thread(target=approve), threading.Thread(target=cancel)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(120)
        wait_until_done(run, 120)
        assert run.state in (TaskState.COMPLETED, TaskState.CANCELLED), (run.state, run.errors)
        assert not any("IllegalTransition" in e for e in run.errors)
        assert len(h.tools.orders) <= 1
        assert sum(s in ("COMPLETED", "CANCELLED") for s, _ in run.history) == 1
        if run.state is TaskState.COMPLETED:
            _assert_single_execution(h, run, 1)
        outcomes[run.state.value] += 1
    assert sum(outcomes.values()) == 5


def test_api_two_approvals_execute_once_and_continuation_errors_are_logged(caplog):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    h = harness(gateway=QueuedApprovalGateway())
    c = TestClient(create_app(harness=h, workers=4))
    run = _parked_run(h, [_ticket(h, "AAPL", 0.1), _ticket(h, "AAPL", 0.2)])
    pend = c.get("/approvals", headers=KEY["risk"]).json()
    assert len(pend) == 2
    replies = [c.post(f"/approvals/{p['id']}", json={"approve": True}, headers=KEY["risk"]).json() for p in pend]
    assert replies[0]["resumed"] is True
    t0 = time.time()
    while not run.done and time.time() - t0 < 120:
        time.sleep(0.05)
    _assert_single_execution(h, run, 2)
    assert c.get(f"/tasks/{run.id}/report", headers=KEY["viewer"]).status_code == 200

    # An ad-hoc approval for a run that is not waiting is recorded, not turned into a full run.
    fresh = h.submit(Task("MSFT", AS_OF, Role.TRADER))
    ex = h._executor(fresh)
    assert "awaiting approval" in ex.call("execution.submit_order", **_ticket(h, "MSFT", 0.1)).error
    aid = c.get("/approvals", headers=KEY["risk"]).json()[0]["id"]
    body = c.post(f"/approvals/{aid}", json={"approve": True}, headers=KEY["risk"]).json()
    assert body["resumed"] is False and body["state"] == "CREATED"
    time.sleep(0.3)
    assert fresh.state is TaskState.CREATED and fresh.plan is None
    assert ex.call("execution.submit_order", **_ticket(h, "MSFT", 0.1)).ok

    # A continuation that raises is logged, never swallowed in an unread Future.
    boom = h.submit(Task("AAPL", AS_OF, Role.TRADER))
    original = h.resume

    def exploding(r):
        raise RuntimeError("continuation blew up")
    h.resume = exploding
    try:
        with caplog.at_level("ERROR", logger="agentic_trader.agentic.api"):
            c.post("/tasks", json={"symbol": "AAPL", "as_of": "2024-03-01"}, headers=KEY["trader"])
            t0 = time.time()
            while "continuation blew up" not in caplog.text and time.time() - t0 < 10:
                time.sleep(0.02)
    finally:
        h.resume = original
    assert "continuation raised RuntimeError: continuation blew up" in caplog.text
    del boom


# ------------------------------------------------- 12: terminal-only record cache
def test_non_terminal_records_are_reread_from_the_store(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    db = tmp_path / "shared.sqlite"
    a = AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db))
    b = AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db), sweep_interrupted=False)
    run = a.submit(Task("AAPL", AS_OF, Role.TRADER))
    assert b.record(run.id)["state"] == "CREATED" and run.id not in b.archive       # not cached
    a.resume(run)
    assert run.state is TaskState.COMPLETED
    assert b.record(run.id)["state"] == "COMPLETED" and run.id in b.archive         # cached once terminal
    c = TestClient(create_app(harness=b))
    assert c.get(f"/tasks/{run.id}", headers=KEY["viewer"]).json()["state"] == "COMPLETED"
    assert c.get(f"/tasks/{run.id}/report", headers=KEY["viewer"]).status_code == 200
    # The startup snapshot follows the same rule: a run in flight when a sibling starts is
    # not frozen in that state.
    live = a.submit(Task("MSFT", AS_OF, Role.TRADER))
    c2 = AgentHarness(TradingGraph(CFG, **QUIET), store=TaskStore(db), sweep_interrupted=False)
    assert live.id not in c2.archive and c2.record(live.id)["state"] == "CREATED"
    a.resume(live)
    assert c2.record(live.id)["state"] == "COMPLETED"
    for h in (a, b, c2):
        h.close()
        h.store.close()


# ------------------------------------------------- 53: owner + lease, not a blanket sweep
def test_interrupted_sweep_spares_a_live_siblings_runs(tmp_path):
    db = tmp_path / "shared.sqlite"
    cfg = make_config(CFG, agentic={"task_db": str(db), "lease_s": 0.6})
    a = AgentHarness(TradingGraph(cfg, **QUIET), gateway=QueuedApprovalGateway())
    queued = a.submit(Task("MSFT", AS_OF, Role.TRADER))
    parked = _parked_run(a, [_ticket(a, "AAPL", 0.1)])
    store = TaskStore(db)
    assert store.ownership(parked.id)[0] == a.owner

    def states():
        return store.load(queued.id)["state"], store.load(parked.id)["state"]
    b = AgentHarness(TradingGraph(cfg, **QUIET), gateway=QueuedApprovalGateway())   # default sweep, same db
    assert states() == ("CREATED", "AWAITING_APPROVAL")
    assert b.record(parked.id)["state"] == "AWAITING_APPROVAL"
    time.sleep(1.0)                                            # longer than the lease: heartbeats keep them alive
    c = AgentHarness(TradingGraph(cfg, **QUIET), gateway=QueuedApprovalGateway())
    assert states() == ("CREATED", "AWAITING_APPROVAL")
    # A record whose owner stopped heartbeating is failed by the next periodic sweep ...
    dead = dict(store.load(queued.id), task_id="TASK-dead", state="EXECUTING")
    store.save_record(dead, owner="host:999:dead")
    with store._lock:
        store._conn.execute("UPDATE tasks SET heartbeat=? WHERE task_id=?", (time.time() - 100, "TASK-dead"))
        store._conn.commit()
    t0 = time.time()
    while store.load("TASK-dead")["state"] != "FAILED" and time.time() - t0 < 5:
        time.sleep(0.05)
    assert store.load("TASK-dead")["state"] == "FAILED" and "process restarted" in store.load("TASK-dead")["errors"]
    assert states() == ("CREATED", "AWAITING_APPROVAL")
    # ... and the owner finishes its work normally.
    a.decide_approval(a.pending_approvals(parked.id)[0].id, True)
    assert parked.state is TaskState.COMPLETED and b.record(parked.id)["state"] == "COMPLETED"
    for h in (a, b, c):
        h.close()
    # A restart of the *same* configured instance id sweeps its own previous incarnation at once.
    blue = make_config(cfg, agentic={"instance_id": "blue", "lease_s": 90.0})
    first = AgentHarness(TradingGraph(blue, **QUIET))
    mine = first.submit(Task("EURUSD", AS_OF, Role.TRADER))
    first.close()
    second = AgentHarness(TradingGraph(blue, **QUIET))
    assert store.load(mine.id)["state"] == "FAILED" and second.record(mine.id)["state"] == "FAILED"
    second.close()
    store.close()


# ------------------------------------------------- 49: bounded retention, no thread leak
def test_retained_runs_and_threads_stay_bounded():
    cfg = make_config(CFG, agentic={"max_retained_runs": 3, "use_alpha_tool": False})
    h = harness(cfg)
    first = h.run(Task("AAPL", AS_OF, Role.TRADER))
    assert first.state is TaskState.COMPLETED and first._executor is None and first._provider is None
    time.sleep(0.2)
    baseline = threading.active_count()
    ids = [first.id]
    for sym in ("MSFT", "EURUSD", "USDJPY", "AAPL", "MSFT"):
        ids.append(h.run(Task(sym, AS_OF, Role.TRADER)).id)
    time.sleep(0.3)
    assert len(h.runs) <= 3 and set(h.runs) == set(ids[-3:])
    assert threading.active_count() <= baseline + 1
    assert all(h.record(i) is not None and h.record(i)["state"] == "COMPLETED" for i in ids)   # evicted -> archive
    assert len(h.archive) <= 3 and len(h.policy.decisions) <= h.policy.decisions.maxlen
    assert {r["task_id"] for r in h.archived_summaries()} == set(ids[:-3])


# ------------------------------------------------- 51: one Prometheus exposition
def _parse_exposition(text):
    types, samples = Counter(), Counter()
    for line in text.splitlines():
        if not line:
            continue
        if line.startswith("# TYPE"):
            types[line.split()[2]] += 1
        elif not line.startswith("#"):
            m = re.fullmatch(r'([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})? (-?[0-9.e+]+|\+Inf|NaN)', line)
            assert m, line
            samples[m.group(1) + (m.group(2) or "")] += 1
    return types, samples


def test_metrics_is_one_exposition_aggregated_across_runs():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    h = harness(gateway=QueuedApprovalGateway())
    c = TestClient(create_app(harness=h))
    for sym in ("AAPL", "MSFT"):
        r = c.post("/tasks", json={"symbol": sym, "as_of": "2024-03-01"}, headers=KEY["trader"])
        run = h.runs[r.json()["task_id"]]
        t0 = time.time()
        while not run.done and time.time() - t0 < 120:
            time.sleep(0.05)
        assert run.state is TaskState.COMPLETED
    text = c.get("/metrics").text
    types, samples = _parse_exposition(text)
    assert types["task_transitions_total"] == 1 and types["tool_calls_total"] == 1 and types["tool_latency_ms"] == 1
    assert all(v == 1 for v in types.values()) and all(v == 1 for v in samples.values())
    assert 'task_transitions_total{state="COMPLETED"} 2\n' in text
    assert 'tool_calls_total{outcome="ok",tool="market_data.history"} 2' in text or \
        re.search(r'tool_calls_total\{outcome="ok",tool="market_data.history"\} ([3-9]|\d\d+)\n', text)
    assert h.metrics.counter("task_transitions_total", state="COMPLETED") == 2
    m = Metrics()
    m.inc("x", tool='a"b\\c\nd')
    assert m.render() == '# TYPE x counter\nx{tool="a\\"b\\\\c\\nd"} 1\n'


# ------------------------------------------------- 52: create_app honours the approval mode
@pytest.mark.parametrize("mode,cls", [("auto", AutoApprovalGateway), ("queued", QueuedApprovalGateway),
                                      ("deny", DenyApprovalGateway)])
def test_create_app_installs_the_configured_gateway(mode, cls):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    app = create_app(config=make_config(memory_path=None, agentic={"approval": mode}))
    assert isinstance(app.state.harness.gateway, cls)
    c = TestClient(app)
    assert c.get("/health").json()["approval"] == mode
    listing = c.get("/approvals", headers=KEY["risk"])
    decide = c.post("/approvals/APPROVAL-nope", json={"approve": True}, headers=KEY["risk"])
    if mode == "queued":
        assert listing.status_code == 200 and listing.json() == [] and decide.status_code == 404
    else:
        assert listing.status_code == 409 and decide.status_code == 409
        assert mode in listing.json()["detail"]
    # The mode is what the executor sees: a state-changing call under deny is refused, under
    # auto approved and evidenced.
    h = app.state.harness
    ex = h._executor(h.submit(Task("AAPL", AS_OF, Role.TRADER)))
    res = ex.call("execution.submit_order", **_ticket(h, "AAPL", 0.1))
    if mode == "deny":
        assert not res.ok and "approval rejected" in res.error and not h.tools.orders
    elif mode == "auto":
        assert res.ok and any(e.type is EvidenceType.APPROVAL and e.source == "auto" for e in ex.evidence)
    else:
        assert not res.ok and "awaiting approval" in res.error and len(h.pending_approvals()) == 1


# ------------------------------------------------- 48: malformed model critiques
def test_critic_tolerates_malformed_model_critiques():
    st, _ = TradingGraph(CFG, **QUIET).propagate("AAPL", AS_OF)

    class Reply:
        def __init__(self, text):
            self.text = text

        def complete(self, system, prompt, *, deep):
            if isinstance(self.text, Exception):
                raise self.text
            return self.text
    for text in (json.dumps({"concerns": None, "confidence_multiplier": 0.9}),
                 json.dumps({"concerns": 0, "confidence_multiplier": 0.9}),
                 json.dumps({"concerns": "thin", "confidence_multiplier": 0.9}),
                 json.dumps({"concerns": {"a": 1}, "confidence_multiplier": 0.9})):
        rep = Critic(CFG, Reply(text)).review(st, [], EvidenceStore())
        assert rep.llm_concerns == [] and rep.llm_multiplier == pytest.approx(0.9) and rep.multiplier == pytest.approx(0.9)
        bad = [c for c in rep.checks if c.name == "llm_critique_wellformed"]
        assert len(bad) == 1 and not bad[0].passed and "concerns is" in bad[0].detail and rep.passed
    for text in (json.dumps({"concerns": ["x"]}), json.dumps({"concerns": ["x"], "confidence_multiplier": "abc"}),
                 json.dumps({"concerns": ["x"], "confidence_multiplier": None}), "no json here", "[1, 2]"):
        rep = Critic(CFG, Reply(text)).review(st, [], EvidenceStore())
        assert rep.llm_multiplier is None and rep.multiplier == 1.0 and rep.passed
        assert any(c.name == "llm_critique_wellformed" and not c.passed for c in rep.checks)
    rep = Critic(CFG, Reply(RuntimeError("model down"))).review(st, [], EvidenceStore())
    assert rep.passed and rep.multiplier == 1.0 and rep.llm_multiplier is None
    assert any("RuntimeError: model down" in c.detail for c in rep.checks)
    ok = Critic(CFG, Reply(json.dumps({"concerns": ["thin"], "confidence_multiplier": 0.5}))).review(st, [], EvidenceStore())
    assert ok.llm_concerns == ["thin"] and ok.multiplier == pytest.approx(0.5)
    assert not any(c.name == "llm_critique_wellformed" for c in ok.checks)

    # End to end: the run completes with a report and the deterministic checks intact.
    class CriticOnly:
        def complete(self, system, prompt, *, deep):
            return json.dumps({"concerns": None, "confidence_multiplier": 0.8}) if "critic" in system else None
    cfg = make_config(CFG, agentic={"llm_reporter": False, "llm_planner": False})
    run = AgentHarness(TradingGraph(cfg, llm=CriticOnly(), **QUIET)).run(Task("AAPL", AS_OF, Role.TRADER))
    assert run.state is TaskState.COMPLETED and run.report is not None and run.critic is not None
    assert run.critic.llm_multiplier == pytest.approx(0.8)
    assert {c.name for c in run.critic.checks} >= {"evidence_resolves", "firm_limits", "llm_critique_wellformed"}


# ------------------------------------------------- 47 / 58: MCP fails closed and is governed
def test_remote_tools_without_annotations_fail_closed(monkeypatch):
    pytest.importorskip("mcp")
    from mcp import StdioServerParameters
    from agentic_trader.agentic import mcp_server as ms
    from agentic_trader.agentic.mcp_server import classify_remote_tool
    unannotated = {"name": "broker__submit_order", "annotated": False, "read_only": False, "meta": {}}
    ann = classify_remote_tool(unannotated)
    assert ann.read_only is False and ann.risk is RiskLevel.HIGH and ann.required == {Capability.PROPOSE_TRADES}
    lying = {"name": "broker__wire", "annotated": False, "read_only": False, "meta": {"risk": "low", "required": []}}
    assert classify_remote_tool(lying).risk is RiskLevel.HIGH          # meta is not read without annotations
    honest = {"name": "data__quote", "annotated": True, "read_only": True,
              "meta": {"risk": "low", "required": ["read_market_data"]}}
    assert classify_remote_tool(honest) == ann.__class__(True, RiskLevel.LOW, frozenset({Capability.READ_MARKET_DATA}),
                                                         EvidenceType.DATA)
    junk = {"name": "x__y", "annotated": True, "read_only": True, "meta": {"risk": "trivial", "required": ["root"]}}
    assert classify_remote_tool(junk).risk is RiskLevel.HIGH and classify_remote_tool(junk).required == {Capability.PROPOSE_TRADES}
    over = classify_remote_tool(unannotated, {"read_only": True, "risk": "low", "required": ["read_market_data"]})
    assert over.read_only and over.risk is RiskLevel.LOW

    monkeypatch.setattr(ms, "_server_params",
                        lambda args=None: StdioServerParameters(command=sys.executable, args=[__file__, "--serve"]))
    tools = ms.discover()
    assert [t["name"] for t in tools] == ["broker__submit_order"] and tools[0]["annotated"] is False
    reg = ms.registry_from_stdio()
    d = reg.get("broker.submit_order").descriptor
    assert d.annotations.read_only is False and d.annotations.risk is RiskLevel.HIGH
    viewer = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.VIEWER, DenyApprovalGateway())
    r = viewer.call("broker.submit_order", symbol="AAPL", side="buy", quantity=100)
    assert not r.ok and "lacks propose_trades" in r.error and r.payload is None
    trader = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.TRADER, DenyApprovalGateway())
    r = trader.call("broker.submit_order", symbol="AAPL", side="buy", quantity=100)
    assert not r.ok and "approval rejected" in r.error and r.payload is None
    assert not any(e.type is EvidenceType.APPROVAL for e in trader.evidence)
    # A plan can never schedule it either (the validator drops state-changing tools).
    plan = validate_plan([{"type": "tool", "name": "broker.submit_order", "arguments": {"symbol": "AAPL"}}],
                         Task("AAPL", AS_OF), Instrument.parse("AAPL"), ["technical"], reg)
    assert not [s for s in plan.steps if s.type is StepType.TOOL]
    # The operator allowlist is the only way to relax it.
    relaxed = ms.registry_from_stdio(overrides={"broker.submit_order": {"read_only": True, "risk": "low",
                                                                        "required": ["read_market_data"]}})
    r = ToolExecutor(relaxed, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.VIEWER,
                     DenyApprovalGateway()).call("broker.submit_order", symbol="AAPL", side="buy", quantity=1)
    assert r.ok and r.payload["status"] == "filled"


def test_mcp_server_routes_every_call_through_policy_approval_and_evidence():
    pytest.importorskip("mcp")
    from agentic_trader.agentic.mcp_server import build_mcp_server, call, governed_executor
    tools = DeskTools(SyntheticProvider(CFG), CFG)
    reg = build_registry(tools)
    ticket = ticket_from_plan(tools.plan("AAPL", AS_OF, 0.1))

    def call_local(server, name, args):
        try:
            return asyncio.run(server.call_tool(name, args)), None
        except Exception as e:  # noqa: BLE001 - the SDK wraps the handler's error
            return None, str(e) + " " + str(getattr(e, "__cause__", ""))
    # deny gateway: the order is refused server-side and the refusal is evidence
    cfg_deny = make_config(CFG, agentic={"approval": "deny", "symbol_universe": ["AAPL"]})
    deny = build_mcp_server(reg, executor=governed_executor(reg, cfg_deny, Role.TRADER, order_cap=tools.order_cap))
    _, err = call_local(deny, "execution__submit_order", ticket)
    assert err and "approval rejected" in err and tools.orders == []
    _, err = call_local(deny, "market_data__news", {"symbol": "ZZZQ", "as_of": "2024-03-01", "lookback_days": 7})
    assert err and "outside the configured universe" in err
    _, err = call_local(deny, "market_data__news", {"symbol": "AAPL", "as_of": "2999-01-01", "lookback_days": 7})
    assert err and "in the future" in err
    ev = list(deny.executor.evidence)
    assert len(ev) == 3 and all("FAILED" in e.summary for e in ev)
    res, err = call_local(deny, "market_data__news", {"symbol": "AAPL", "as_of": "2024-03-01", "lookback_days": 7})
    assert err is None and len(deny.executor.evidence) == 4 and list(deny.executor.evidence)[-1].source == "market_data.news"
    assert deny.executor.tracer.metrics.counter("tool_calls_total", tool="market_data.news", outcome="ok") == 1
    # viewer role: no state-changing tool at all
    viewer = build_mcp_server(reg, executor=governed_executor(reg, cfg_deny, Role.VIEWER))
    _, err = call_local(viewer, "execution__submit_order", ticket)
    assert err and "lacks propose_trades" in err and tools.orders == []
    # auto gateway: the approval is recorded as evidence before the ticket is written
    auto = build_mcp_server(reg, executor=governed_executor(reg, make_config(CFG, agentic={"approval": "auto"}),
                                                           Role.TRADER, order_cap=tools.order_cap))
    res, err = call_local(auto, "execution__submit_order", ticket)
    assert err is None and len(tools.orders) == 1
    kinds = [e.type for e in auto.executor.evidence]
    assert kinds == [EvidenceType.APPROVAL, EvidenceType.DECISION]
    # and the same over a real stdio round trip: the server's own flags decide
    with pytest.raises(RuntimeError, match="approval rejected"):
        call("execution__submit_order", ticket, ["--approval", "deny"])
    with pytest.raises(RuntimeError, match="lacks propose_trades"):
        call("execution__submit_order", ticket, ["--role", "viewer"])
