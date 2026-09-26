"""The agent harness: an explicit state machine that runs a plan for a task.

    CREATED -> PLANNING -> VALIDATING_PLAN -> EXECUTING (<-> AWAITING_APPROVAL)
            -> CRITIQUING -> VALIDATING_EVIDENCE -> FINALISING -> COMPLETED
    (FAILED / CANCELLED from any non-terminal state)

The harness owns the control plane; agents never control the loop. It:

* builds the tool registry over the desk's data provider and runs every tool
  call through the policy-gated ``ToolExecutor`` (evidence, retry, timeout);
* runs the desk's agent stages through ``TradingGraph`` with a recording
  provider, so the analysts' data access is policy-checked and evidenced;
* batches consecutive independent tool steps in parallel;
* pauses in AWAITING_APPROVAL when a tool needs a human, and resumes from the
  same step once the approval queue has an answer;
* honours cancellation between steps;
* always runs the governance steps: critic, evidence validation, audited report.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..agents.risk import risk_facts
from ..graph import TradingGraph
from ..instruments import Instrument
from ..state import TradingState
from .critic import Critic, CriticReport
from .domain import (EvidenceType, Finding, Plan, PlanStep, PolicyOutcome, StepType, Task, TaskState,
                     TERMINAL_STATES, TRANSITIONS, ToolRequest, new_id, utc_now)
from .evidence import EvidenceStore
from .planner import ANALYST_PREFIX, make_plan, plan_to_dict
from .policy import (ApprovalGateway, AutoApprovalGateway, DenyApprovalGateway, PolicyEngine,
                     QueuedApprovalGateway)
from .rag import KnowledgeBase
from .reporter import Report, build_report
from .servers import DeskTools, RecordingProvider, build_registry
from .tools import ExecutorConfig, ToolExecutor, ToolRegistry
from .tracing import Tracer

log = logging.getLogger(__name__)


class IllegalTransition(RuntimeError):
    pass


@dataclass
class TaskRun:
    task: Task
    state: TaskState = TaskState.CREATED
    plan: Plan | None = None
    trading_state: TradingState | None = None
    findings: list[Finding] = field(default_factory=list)
    critic: CriticReport | None = None
    report: Report | None = None
    evidence: EvidenceStore = field(default_factory=EvidenceStore)
    tracer: Tracer = field(default_factory=Tracer)
    history: list[tuple[str, str]] = field(default_factory=list)   # (state, iso time + note)
    completed_steps: set[str] = field(default_factory=set)
    step_results: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    pending_step: str | None = None
    cancel_requested: bool = False
    started_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    correlation_id: str = field(default_factory=lambda: new_id("CID"))
    _executor: ToolExecutor | None = field(default=None, repr=False)
    _provider: RecordingProvider | None = field(default=None, repr=False)

    @property
    def id(self) -> str:
        return self.task.id

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def decision(self):
        return self.trading_state.decision if self.trading_state else None

    def to_dict(self, include_report: bool = True) -> dict[str, Any]:
        d = {"task_id": self.id, "symbol": self.task.symbol, "as_of": self.task.as_of.isoformat(),
             "role": self.task.role.value, "state": self.state.value, "history": self.history,
             "errors": self.errors, "pending_step": self.pending_step,
             "plan": plan_to_dict(self.plan) if self.plan else None,
             "completed_steps": sorted(self.completed_steps),
             "decision": self.decision.to_dict() if self.decision else None,
             "findings": [{"agent": f.agent, "claim": f.claim, "confidence": round(f.confidence, 3),
                           "evidence_ids": list(f.evidence_ids)} for f in self.findings],
             "critic": self.critic.to_dict() if self.critic else None,
             "evidence_count": len(self.evidence), "trace": self.tracer.summary(),
             "started_at": self.started_at.isoformat(),
             "finished_at": self.finished_at.isoformat() if self.finished_at else None}
        if include_report and self.report:
            d["report"] = self.report.to_dict()
        return d


def _gateway(kind: str) -> ApprovalGateway:
    try:
        return {"auto": AutoApprovalGateway, "queued": QueuedApprovalGateway, "deny": DenyApprovalGateway}[kind]()
    except KeyError:
        raise ValueError(f"unknown approval gateway {kind!r} (auto, queued or deny)") from None


class AgentHarness:
    def __init__(self, graph: TradingGraph, policy: PolicyEngine | None = None,
                 gateway: ApprovalGateway | None = None, knowledge: KnowledgeBase | None = None,
                 positions: dict[str, float] | None = None, capital: float | None = None):
        self.graph = graph
        self.config = graph.config
        acfg = self.config.get("agentic", {})
        self.tools = DeskTools(graph.provider, self.config, knowledge, positions, capital)
        self.registry: ToolRegistry = build_registry(self.tools)
        self.policy = policy or PolicyEngine({
            "symbol_universe": acfg.get("symbol_universe"), "deny_tools": acfg.get("deny_tools", ()),
            "max_position": self.config["risk"]["max_position"]})
        self.gateway = gateway or _gateway(acfg.get("approval", "auto"))
        self.critic = Critic(self.config, graph.llm)
        self.runs: dict[str, TaskRun] = {}
        self._lock = threading.Lock()

    # ----------------------------------------------------------- control
    def submit(self, task: Task) -> TaskRun:
        run = TaskRun(task)
        with self._lock:
            self.runs[task.id] = run
        return run

    def cancel(self, task_id: str) -> TaskRun:
        run = self.runs[task_id]
        run.cancel_requested = True
        if run.state is TaskState.AWAITING_APPROVAL:
            self._transition(run, TaskState.CANCELLED, "cancelled while awaiting approval")
            run.finished_at = utc_now()
        return run

    def run(self, task: Task) -> TaskRun:
        return self.resume(self.submit(task))

    def resume(self, run: TaskRun) -> TaskRun:
        """Drive a run to a terminal state or to AWAITING_APPROVAL."""
        if run.done:
            return run
        try:
            if run.state is TaskState.CREATED:
                self._plan(run)
            if run.state is TaskState.AWAITING_APPROVAL:
                self._transition(run, TaskState.EXECUTING, "resuming after approval")
            if run.state is TaskState.EXECUTING:
                self._execute(run)
            if run.state is TaskState.CRITIQUING:
                self._critique(run)
            if run.state is TaskState.VALIDATING_EVIDENCE:
                self._validate(run)
            if run.state is TaskState.FINALISING:
                self._finalise(run)
        except IllegalTransition:
            raise
        except Exception as e:  # any bug ends in FAILED with the reason, never a half-run
            if isinstance(e, (ValueError, KeyError)):   # expected refusals: bad input, policy denial
                log.warning("task %s failed: %s", run.id, e)
            else:
                log.exception("task %s failed", run.id)
            run.errors.append(f"{type(e).__name__}: {e}")
            if not run.done:
                self._transition(run, TaskState.FAILED, str(e)[:200])
        if run.done:
            run.finished_at = utc_now()
        return run

    def _transition(self, run: TaskRun, new: TaskState, note: str = "") -> None:
        if new not in TRANSITIONS[run.state]:
            raise IllegalTransition(f"{run.state.value} -> {new.value} is not allowed")
        run.state = new
        run.history.append((new.value, utc_now().isoformat() + (f" {note}" if note else "")))
        run.tracer.metrics.inc("task_transitions_total", state=new.value)

    # ------------------------------------------------------------ phases
    def _plan(self, run: TaskRun) -> None:
        self._transition(run, TaskState.PLANNING)
        ins = Instrument.parse(run.task.symbol)
        analysts = self.graph.analyst_names(ins)
        with run.tracer.span("plan"):
            run.plan = make_plan(run.task, ins, analysts, self.config, self.registry, self.graph.llm)
        self._transition(run, TaskState.VALIDATING_PLAN, run.plan.source)
        # Pre-check every tool step against policy so an impossible plan fails before it runs.
        for s in run.plan.steps:
            if s.type is StepType.TOOL:
                d = self.policy.evaluate(ToolRequest(s.name, s.arguments, run.correlation_id, "planner"),
                                         self.registry.get(s.name).descriptor, run.task.role)
                if d.outcome is PolicyOutcome.DENY:
                    raise ValueError(f"plan step {s.name} denied by policy ({d.rule}): {d.reason}")
        self._transition(run, TaskState.EXECUTING)

    def _executor(self, run: TaskRun) -> ToolExecutor:
        if run._executor is None:
            acfg = self.config.get("agentic", {})
            run._executor = ToolExecutor(self.registry, self.policy, run.evidence, run.task.role, self.gateway,
                                         run.tracer, ExecutorConfig(float(acfg.get("tool_timeout_s", 30.0))),
                                         run.id)
            run._provider = RecordingProvider(run._executor, self.graph.provider, run.correlation_id)
        return run._executor

    def _execute(self, run: TaskRun) -> None:
        ex = self._executor(run)
        ex.pending_approval = False
        if run.trading_state is None:
            with run.tracer.span("prepare"):
                run.trading_state = self.graph.prepare(run.task.symbol, run.task.as_of,
                                                       current_weight=run.task.current_weight,
                                                       provider=run._provider)
        steps = [s for s in run.plan.steps if s.type in (StepType.TOOL, StepType.AGENT)]
        i = 0
        while i < len(steps):
            if run.cancel_requested:
                self._transition(run, TaskState.CANCELLED, "cancelled between steps")
                return
            step = steps[i]
            if step.id in run.completed_steps:
                i += 1
                continue
            if step.type is StepType.TOOL:
                # Batch consecutive, not-yet-completed tool steps and run them in parallel.
                batch = []
                while i < len(steps) and steps[i].type is StepType.TOOL:
                    if steps[i].id not in run.completed_steps:
                        batch.append(steps[i])
                    i += 1
                self._run_tool_batch(run, ex, batch)
                if ex.pending_approval:
                    waiting = next(s for s in batch if s.id not in run.completed_steps)
                    run.pending_step = waiting.id
                    self._transition(run, TaskState.AWAITING_APPROVAL, f"{waiting.name} needs approval")
                    return
            else:
                with run.tracer.span(f"agent:{step.name}", step=step.id):
                    self._run_agent_step(run, step)
                run.completed_steps.add(step.id)
                i += 1
        run.pending_step = None
        self._transition(run, TaskState.CRITIQUING)

    def _run_tool_batch(self, run: TaskRun, ex: ToolExecutor, batch: list[PlanStep]) -> None:
        def one(step: PlanStep):
            return step, ex.call(step.name, correlation_id=run.correlation_id, requested_by="plan", **step.arguments)

        if len(batch) == 1:
            results = [one(batch[0])]
        else:
            with ThreadPoolExecutor(max_workers=min(4, len(batch))) as pool:
                results = list(pool.map(one, batch))
        for step, res in results:
            if not res.ok and "awaiting approval" in (res.error or ""):
                continue  # not completed: the run pauses and retries this step on resume
            run.step_results[step.id] = res.payload if res.ok else {"error": res.error}
            run.completed_steps.add(step.id)
            if res.ok and step.name == "knowledge.search" and isinstance(res.payload, list):
                run.trading_state.knowledge = res.payload
            if res.ok and step.name == "quant.alpha" and isinstance(res.payload, dict):
                run.trading_state.alpha = res.payload
            if not res.ok:
                run.errors.append(f"{step.name}: {res.error}")

    def _run_agent_step(self, run: TaskRun, step: PlanStep) -> None:
        st, ev = run.trading_state, run.evidence
        before = len(ev)
        if step.name.startswith(ANALYST_PREFIX):
            name = step.name[len(ANALYST_PREFIX):]
            r = self.graph.run_analyst(st, name, provider=run._provider)
            ev.record(EvidenceType.CALCULATION, f"analyst.{name}", f"{name} facts", r.facts, run.correlation_id)
            ev.record(EvidenceType.DECISION, f"analyst.{name}", r.summary,
                      {"signal": r.signal, "confidence": r.confidence, "abstained": r.abstained,
                       "source": r.source, "key_points": r.key_points}, run.correlation_id)
            r.evidence_ids = tuple(ev.ids_since(before))
            if not r.abstained:
                run.findings.append(Finding.make(name, r.summary, r.confidence, r.evidence_ids,
                                                 {"signal": r.signal}, ("analyst", r.source)))
        elif step.name == "debate":
            d = self.graph.run_debate(st)
            dec = ev.record(EvidenceType.DECISION, "facilitator", d.summary,
                            {"winner": d.winner, "score": d.score, "conviction": d.conviction,
                             "turns": [t.__dict__ for t in d.turns]}, run.correlation_id)
            cited = tuple(dict.fromkeys(i for r in st.reports.values() for i in r.evidence_ids)) + (dec.id,)
            d.evidence_ids = cited
            run.findings.append(Finding.make("facilitator", d.summary, d.conviction, cited,
                                             {"score": d.score}, ("debate", d.source)))
        elif step.name == "trader":
            p = self.graph.run_trader(st)
            dec = ev.record(EvidenceType.DECISION, "trader", p.rationale,
                            {"action": p.action.value, "target_weight": p.target_weight,
                             "stop_loss": p.stop_loss, "take_profit": p.take_profit,
                             "horizon_days": p.horizon_days}, run.correlation_id)
            p.evidence_ids = (st.debate.evidence_ids if st.debate else ()) + (dec.id,)
            run.findings.append(Finding.make("trader", p.rationale, p.confidence, p.evidence_ids,
                                             {"target_weight": p.target_weight}, ("proposal", p.source)))
        elif step.name == "risk":
            facts = risk_facts(st, self.config)
            fev = ev.record(EvidenceType.CALCULATION, "quant.risk", "risk facts for the proposal", facts,
                            run.correlation_id)
            d = self.graph.run_risk(st)
            for v in st.risk_views:
                vev = ev.record(EvidenceType.DECISION, f"risk.{v.stance}", v.argument,
                                {"weight": v.recommended_weight, "round": v.round}, run.correlation_id)
                v.evidence_ids = (fev.id, vev.id)
            dev = ev.record(EvidenceType.DECISION, "portfolio_manager", d.rationale, d.to_dict(),
                            run.correlation_id)
            d.evidence_ids = tuple(dict.fromkeys(
                (st.proposal.evidence_ids if st.proposal else ()) + (fev.id,)
                + tuple(i for v in st.risk_views for i in v.evidence_ids) + (dev.id,)))
            run.findings.append(Finding.make("portfolio_manager", d.rationale, d.confidence, d.evidence_ids,
                                             {"target_weight": d.target_weight}, ("decision", d.source)))
            run.step_results["risk_facts"] = facts
        else:
            raise ValueError(f"unknown agent stage {step.name}")

    def _critique(self, run: TaskRun) -> None:
        with run.tracer.span("critic"):
            run.critic = self.critic.review(run.trading_state, run.findings, run.evidence,
                                            run.step_results.get("risk_facts"))
        run.completed_steps.add("STEP-critic")
        self._transition(run, TaskState.VALIDATING_EVIDENCE,
                         "critic passed" if run.critic.passed else "critic flagged errors")

    def _validate(self, run: TaskRun) -> None:
        with run.tracer.span("validate_evidence"):
            kept = []
            for f in run.findings:
                bad = run.evidence.unresolved(f.evidence_ids)
                if bad:
                    run.errors.append(f"finding by {f.agent} dropped: unresolved evidence {bad}")
                else:
                    kept.append(f)
            run.findings = kept
        run.completed_steps.add("STEP-validate")
        self._transition(run, TaskState.FINALISING)

    def _finalise(self, run: TaskRun) -> None:
        with run.tracer.span("finalise"):
            acfg = self.config.get("agentic", {})
            llm = self.graph.llm if acfg.get("llm_reporter", True) else None
            run.report = build_report(run.task, run.trading_state, run.findings, run.critic, run.evidence, llm)
            if run.critic is not None and run.trading_state.decision is not None:
                run.trading_state.decision.confidence = round(
                    run.trading_state.decision.confidence * run.critic.multiplier, 4)
            self.graph.record(run.trading_state)
        run.completed_steps.add("STEP-finalise")
        self._transition(run, TaskState.COMPLETED)

    # ---------------------------------------------------------- approvals
    def pending_approvals(self, task_id: str | None = None):
        if isinstance(self.gateway, QueuedApprovalGateway):
            return self.gateway.pending(task_id)
        return []

    def decide_approval(self, approval_id: str, approve: bool, decided_by: str = "human",
                        note: str = "") -> TaskRun:
        if not isinstance(self.gateway, QueuedApprovalGateway):
            raise ValueError("approvals are not queued in this harness")
        a = self.gateway.resolve(approval_id, approve, decided_by, note)
        run = self.runs[a.task_id]
        run.evidence.record(EvidenceType.APPROVAL, decided_by,
                            f"{'approved' if approve else 'rejected'} {a.request.tool}",
                            {"approval": a.id, "note": note}, run.correlation_id)
        return self.resume(run)


def wait_until_done(run: TaskRun, timeout_s: float = 60.0) -> TaskRun:
    """Block until a run (driven elsewhere) reaches a terminal or waiting state."""
    t0 = time.perf_counter()
    while not run.done and run.state is not TaskState.AWAITING_APPROVAL:
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError("run did not finish in time")
        time.sleep(0.02)
    return run
