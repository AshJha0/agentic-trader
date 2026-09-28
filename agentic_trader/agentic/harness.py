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
* drives each run from exactly one thread at a time: ``resume`` holds the run's
  driving lock and a second caller returns at once, so two approval decisions
  can never execute the same step twice; the lock is handed back under the
  harness lock together with the last pending-approval check, so a decision or a
  cancellation that lands while the driver parks is never lost;
* honours cancellation between steps;
* gives each run its own position book -- the desk's positions overlaid with an explicit
  map on ``submit`` and the task's declared ``current_weight`` -- which is the single source
  of the current position: the planner drops a model-written ``current_weight`` for a
  symbol the book holds, the agents' ``TradingState`` is prepared from the book's weight,
  and the run's tools read (and a ticket updates) the same book, so the agents, the
  report and the tools agree and no task rewrites the desk's book for another;
* always runs the governance steps: critic, evidence validation, audited report;
* keeps a bounded number of finished runs in memory (``agentic.max_retained_runs``);
  the persistent store holds the rest, and the metrics are one process-level set;
* with a store, records which instance owns each live run and heartbeats it, so
  the interrupted-run sweep only fails runs whose lease has expired.
"""
from __future__ import annotations

import logging
import math
import os
import socket
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from ..agents.risk import risk_facts
from ..graph import TradingGraph
from ..instruments import Instrument
from ..state import TradingState
from .critic import Critic, CriticReport, decision_untrusted
from .domain import (EvidenceType, Finding, Plan, PlanStep, PolicyOutcome, StepType, Task, TaskState,
                     TERMINAL_STATES, TRANSITIONS, ToolRequest, new_id, utc_now)
from .evidence import EvidenceStore
from .planner import ANALYST_PREFIX, make_plan, max_plan_lookback_bars, plan_cost_bars, plan_to_dict
from .policy import (ApprovalGateway, AutoApprovalGateway, DenyApprovalGateway, PolicyEngine,
                     QueuedApprovalGateway)
from .rag import KnowledgeBase
from .reporter import Report, build_report
from .servers import DeskTools, RecordingProvider, build_registry
from .store import TaskStore, record_of
from .tools import ExecutorConfig, ToolExecutor, ToolRegistry
from .tracing import Metrics, Tracer

log = logging.getLogger(__name__)
_TERMINAL_VALUES = frozenset(s.value for s in TERMINAL_STATES)


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
    positions: dict[str, float] = field(default_factory=dict)     # this run's book, read by its tools
    _executor: ToolExecutor | None = field(default=None, repr=False)
    _provider: RecordingProvider | None = field(default=None, repr=False)
    _driving: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def id(self) -> str:
        return self.task.id

    @property
    def done(self) -> bool:
        return self.state in TERMINAL_STATES

    @property
    def driving(self) -> bool:
        """True while a thread is inside ``AgentHarness.resume`` for this run."""
        return self._driving.locked()

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
                           "evidence_ids": list(f.evidence_ids), "untrusted": f.untrusted} for f in self.findings],
             "critic": self.critic.to_dict() if self.critic else None,
             "evidence_count": len(self.evidence), "trace": self.tracer.summary(),
             "positions": dict(self.positions), "started_at": self.started_at.isoformat(),
             "finished_at": self.finished_at.isoformat() if self.finished_at else None}
        if include_report and self.report:
            d["report"] = self.report.to_dict()
        return d


def _gateway(kind: str) -> ApprovalGateway:
    try:
        return {"auto": AutoApprovalGateway, "queued": QueuedApprovalGateway, "deny": DenyApprovalGateway}[kind]()
    except KeyError:
        raise ValueError(f"unknown approval gateway {kind!r} (auto, queued or deny)") from None


def default_instance_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


class AgentHarness:
    def __init__(self, graph: TradingGraph, policy: PolicyEngine | None = None,
                 gateway: ApprovalGateway | None = None, knowledge: KnowledgeBase | None = None,
                 positions: dict[str, float] | None = None, capital: float | None = None,
                 store: TaskStore | None = None, sweep_interrupted: bool | None = None):
        self.graph = graph
        self.config = graph.config
        acfg = self.config.get("agentic", {})
        self.tools = DeskTools(graph.provider, self.config, knowledge, positions, capital)
        self.registry: ToolRegistry = build_registry(self.tools)
        self.policy = policy or PolicyEngine({
            "symbol_universe": acfg.get("symbol_universe"), "deny_tools": acfg.get("deny_tools", ()),
            "max_position": self.config["risk"]["max_position"],
            "max_order_notional": self.tools.order_cap,
            "max_symbols_per_call": acfg.get("max_symbols_per_call", 60)})
        self.gateway = gateway or _gateway(acfg.get("approval", "auto"))
        self.critic = Critic(self.config, graph.llm)
        self.metrics = Metrics()          # one exposition for the process; every run's tracer feeds it
        self.runs: dict[str, TaskRun] = {}
        self.max_retained = max(1, int(acfg.get("max_retained_runs", 256)))
        self._lock = threading.Lock()
        self.owner: str = str(acfg.get("instance_id") or default_instance_id())
        self.lease_s = float(acfg.get("lease_s", 90.0))
        if not (self.lease_s >= 1.0):   # a shorter lease would let the periodic sweep fail this instance's own runs
            raise ValueError(f"agentic.lease_s must be at least 1 second, got {acfg.get('lease_s')!r}")
        # Persistence: records of every run this process makes, plus a bounded cache of
        # terminal records (a previous process's, or a sibling's once finished). A record
        # that is not terminal is never served from the cache: it is re-read from the store.
        if store is None and acfg.get("task_db"):
            store = TaskStore(acfg["task_db"])
        self.store = store
        self.archive: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        if store is not None:
            sweep = acfg.get("sweep_interrupted", True) if sweep_interrupted is None else sweep_interrupted
            if sweep:
                # Only records whose lease has expired (or that predate leases): a sibling that
                # is alive keeps heartbeating its runs, whatever instance id it is configured with.
                interrupted = store.mark_interrupted(lease_s=self.lease_s)
                if interrupted:
                    log.warning("%d task(s) were in flight when the previous process stopped; marked FAILED",
                                interrupted)
            for rec in store.load_all():
                if rec.get("state") in _TERMINAL_VALUES:
                    self._archive_put(rec["task_id"], rec)
            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, name="harness-heartbeat",
                                                      daemon=True)
            self._heartbeat_thread.start()

    # -------------------------------------------------------------- records
    def _archive_put(self, task_id: str, rec: dict[str, Any]) -> None:
        with self._lock:
            self.archive[task_id] = rec
            self.archive.move_to_end(task_id)
            while len(self.archive) > self.max_retained:
                self.archive.popitem(last=False)

    def record(self, task_id: str) -> dict[str, Any] | None:
        """The JSON record of a live run, a cached terminal one, or the store's current
        copy of a run another process drives (``None`` if unknown)."""
        run = self.runs.get(task_id)
        if run is not None:
            return record_of(run)
        rec = self.archive.get(task_id)
        if rec is not None and rec.get("state") in _TERMINAL_VALUES:
            return rec
        if self.store is not None:
            fresh = self.store.load(task_id)
            if fresh is not None:
                rec = fresh
                if rec.get("state") in _TERMINAL_VALUES:
                    self._archive_put(task_id, rec)
        return rec

    def archived_summaries(self) -> list[dict[str, Any]]:
        """Every record in the store (all processes), or the in-memory archive without one."""
        if self.store is not None:
            return self.store.summaries()
        return [{"task_id": r["task_id"], "symbol": r["symbol"], "as_of": r["as_of"], "role": r["role"],
                 "state": r["state"]} for r in list(self.archive.values())]

    def _persist(self, run: TaskRun) -> None:
        if self.store is not None:
            try:
                self.store.save(run, self.owner)
            except Exception as e:  # persistence must never take a decision down with it
                log.exception("could not persist task %s: %s", run.id, e)

    def _heartbeat_loop(self) -> None:
        interval = max(self.lease_s / 3.0, 0.02)
        while not self._stop.wait(interval):
            try:
                with self._lock:
                    live = [r.id for r in self.runs.values() if not r.done]
                self.store.heartbeat(self.owner, live)
                # Periodic sweep of records whose owner stopped heartbeating (a crashed
                # sibling, or a predecessor that died within the lease before we started).
                swept = self.store.mark_interrupted(lease_s=self.lease_s)
                if swept:
                    log.warning("%d task(s) lost their owner's heartbeat; marked FAILED", swept)
            except Exception as e:  # noqa: BLE001 - a closed store ends the loop, anything else is logged
                if getattr(self.store, "closed", False):
                    return
                log.debug("heartbeat failed: %s", e)

    def close(self) -> None:
        """Stop the heartbeat thread (the store stays open for the caller to close)."""
        self._stop.set()
        if self._heartbeat_thread is not None:
            self._heartbeat_thread.join(timeout=2.0)

    # ----------------------------------------------------------- control
    def _book_for(self, task: Task, positions: dict[str, float] | None) -> dict[str, float]:
        """The run's own book: the desk's positions, overlaid with the caller's explicit map and
        with the task's declared ``current_weight`` (the freshest fact about its symbol), so
        ``portfolio.position``, ``execution.plan`` and ``submit_order`` agree with the task's
        facts. Nothing a task declares is written to the desk's book."""
        book = dict(self.tools.positions)
        for sym, w in (positions or {}).items():
            try:
                ins = Instrument.parse(str(sym))
            except ValueError as e:
                raise ValueError(f"positions: {e}") from None
            fw = float(w)
            if not math.isfinite(fw):
                raise ValueError(f"positions: weight for {ins.symbol} must be a finite number")
            book[ins.symbol] = fw
        if task.current_weight is not None:
            w = float(task.current_weight)
            if not math.isfinite(w):
                raise ValueError("current_weight must be a finite number")
            try:
                book[Instrument.parse(task.symbol).symbol] = w
            except ValueError:   # an unparseable task symbol fails the run at planning, as it always did
                pass
        return book

    def submit(self, task: Task, positions: dict[str, float] | None = None) -> TaskRun:
        run = TaskRun(task, tracer=Tracer(self.metrics), positions=self._book_for(task, positions))
        with self._lock:
            self.runs[task.id] = run
        self._persist(run)
        return run

    def cancel(self, task_id: str) -> TaskRun:
        run = self.runs[task_id]
        run.cancel_requested = True
        # A parked run is cancelled here. A run another thread drives sees the flag at its
        # next step or, when it is about to park, under the harness lock before it hands the
        # driving lock back (``resume``), so the attempt below and that check never miss each
        # other: either this thread gets the lock and the run is parked, or the driver applies it.
        with self._lock:
            got = run._driving.acquire(blocking=False)
        if got:
            try:
                if run.state is TaskState.AWAITING_APPROVAL:
                    self._transition(run, TaskState.CANCELLED, "cancelled while awaiting approval")
                    self._finish(run)
                    self._persist(run)
            finally:
                run._driving.release()
        return run

    def run(self, task: Task) -> TaskRun:
        return self.resume(self.submit(task))

    def resume(self, run: TaskRun) -> TaskRun:
        """Drive a run to a terminal state or to AWAITING_APPROVAL.

        Exactly one thread drives a run at a time; a concurrent call returns the run
        untouched. The driving lock is released under the harness lock, in the same critical
        section as the final check for undecided approvals and a pending cancellation, so a
        decision or a cancel that lands while the run is being driven is either seen by this
        driver (which carries on) or arrives after the release (``continuation_due`` /
        ``cancel`` then see nobody driving). No approval is lost and no step runs twice.
        """
        if not run._driving.acquire(blocking=False):
            log.info("task %s is already being driven; resume ignored", run.id)
            return run
        held = True
        try:
            while True:
                self._drive(run)
                with self._lock:
                    if run.state is TaskState.AWAITING_APPROVAL and (run.cancel_requested or self._all_decided(run)):
                        continue
                    run._driving.release()
                    held = False
                    return run
        finally:
            if held:
                run._driving.release()

    def _all_decided(self, run: TaskRun) -> bool:
        return isinstance(self.gateway, QueuedApprovalGateway) and not self.gateway.pending(run.id)

    def continuation_due(self, run: TaskRun) -> bool:
        """True when a decision has just been recorded for a parked run nobody is driving
        (the API then schedules ``resume`` on its pool)."""
        with self._lock:
            return run.state is TaskState.AWAITING_APPROVAL and not run.driving

    def _drive(self, run: TaskRun) -> None:
        if run.done:
            return
        if run.cancel_requested and run.state in (TaskState.CREATED, TaskState.AWAITING_APPROVAL):
            # cancelled while queued or parked: do no work, resume nothing
            note = "cancelled before start" if run.state is TaskState.CREATED else "cancelled while awaiting approval"
            self._transition(run, TaskState.CANCELLED, note)
            self._finish(run)
            self._persist(run)
            return
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
        except Exception as e:  # any bug ends in FAILED with the reason, never a half-run
            if isinstance(e, (ValueError, KeyError)):   # expected refusals: bad input, policy denial
                log.warning("task %s failed: %s", run.id, e)
            else:
                log.exception("task %s failed", run.id)
            run.errors.append(f"{type(e).__name__}: {e}")
            if not run.done:
                self._transition(run, TaskState.FAILED, str(e)[:200])
        if run.done:
            self._finish(run)
        self._persist(run)

    def _finish(self, run: TaskRun) -> None:
        """Bookkeeping for a run that just reached a terminal state: stamp it, drop its
        executor, and evict the oldest finished runs beyond the retention cap."""
        run.finished_at = utc_now()
        run._executor = None
        run._provider = None
        with self._lock:
            done = [r for r in self.runs.values() if r.done and r is not run]
            excess = len(done) + 1 - self.max_retained
            evicted = done[:excess] if excess > 0 else []
            for r in evicted:
                self.runs.pop(r.id, None)
        # A finished run never asks its gateway again: its pending approvals are withdrawn
        # (deciding one is refused with the run's state), and an evicted run's requests are
        # dropped altogether, so the queue is bounded by the runs the harness retains.
        if isinstance(self.gateway, QueuedApprovalGateway):
            self.gateway.withdraw(run.id, f"run {run.state.value}")
            for r in evicted:
                self.gateway.forget(r.id)
        for r in evicted:
            if self.store is None:
                self._archive_put(r.id, record_of(r))

    def _transition(self, run: TaskRun, new: TaskState, note: str = "") -> None:
        if new not in TRANSITIONS[run.state]:
            raise IllegalTransition(f"{run.state.value} -> {new.value} is not allowed")
        run.state = new
        run.history.append((new.value, utc_now().isoformat() + (f" {note}" if note else "")))
        run.tracer.metrics.inc("task_transitions_total", state=new.value)
        if new in TERMINAL_STATES or new is TaskState.AWAITING_APPROVAL:
            self._persist(run)

    # ------------------------------------------------------------ phases
    def _plan(self, run: TaskRun) -> None:
        self._transition(run, TaskState.PLANNING)
        ins = Instrument.parse(run.task.symbol)
        analysts = self.graph.analyst_names(ins)
        with run.tracer.span("plan"):
            run.plan = make_plan(run.task, ins, analysts, self.config, self.registry, self.graph.llm,
                                 book=run.positions)
        self._transition(run, TaskState.VALIDATING_PLAN, run.plan.source)
        # Pre-check every tool step against policy, and the plan's data budget as a whole,
        # so an impossible plan fails before it runs.
        for s in run.plan.steps:
            if s.type is StepType.TOOL:
                d = self.policy.evaluate(ToolRequest(s.name, s.arguments, run.correlation_id, "planner"),
                                         self.registry.get(s.name).descriptor, run.task.role)
                if d.outcome is PolicyOutcome.DENY:
                    raise ValueError(f"plan step {s.name} denied by policy ({d.rule}): {d.reason}")
        cost, cap = plan_cost_bars(run.plan.steps, self.config), max_plan_lookback_bars(self.config)
        if cost > cap:
            raise ValueError(f"plan would load {cost} bars of history, over max_plan_lookback_bars={cap}")
        self._transition(run, TaskState.EXECUTING)

    def _executor(self, run: TaskRun) -> ToolExecutor:
        """The run's executor: the desk's tools over this run's book (same catalogue and
        descriptors as ``self.registry``, which the planner and the pre-check use)."""
        if run._executor is None:
            acfg = self.config.get("agentic", {})
            registry = build_registry(self.tools.for_book(run.positions))
            run._executor = ToolExecutor(registry, self.policy, run.evidence, run.task.role, self.gateway,
                                         run.tracer, ExecutorConfig(float(acfg.get("tool_timeout_s", 30.0))),
                                         run.id)
            run._provider = RecordingProvider(run._executor, self.graph.provider, run.correlation_id)
        return run._executor

    def _execute(self, run: TaskRun) -> None:
        ex = self._executor(run)
        ex.pending_approval = False
        if run.trading_state is None:
            with run.tracer.span("prepare"):
                held = run.positions.get(Instrument.parse(run.task.symbol).symbol, run.task.current_weight)
                run.trading_state = self.graph.prepare(run.task.symbol, run.task.as_of, current_weight=held,
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
                                                 {"signal": r.signal}, ("analyst", r.source), untrusted=r.untrusted))
        elif step.name == "debate":
            d = self.graph.run_debate(st)
            dec = ev.record(EvidenceType.DECISION, "facilitator", d.summary,
                            {"winner": d.winner, "score": d.score, "conviction": d.conviction,
                             "turns": [t.__dict__ for t in d.turns]}, run.correlation_id)
            cited = tuple(dict.fromkeys(i for r in st.reports.values() for i in r.evidence_ids)) + (dec.id,)
            d.evidence_ids = cited
            run.findings.append(Finding.make("facilitator", d.summary, d.conviction, cited,
                                             {"score": d.score}, ("debate", d.source), untrusted=d.untrusted))
        elif step.name == "trader":
            p = self.graph.run_trader(st)
            dec = ev.record(EvidenceType.DECISION, "trader", p.rationale,
                            {"action": p.action.value, "target_weight": p.target_weight,
                             "stop_loss": p.stop_loss, "take_profit": p.take_profit,
                             "horizon_days": p.horizon_days}, run.correlation_id)
            p.evidence_ids = (st.debate.evidence_ids if st.debate else ()) + (dec.id,)
            run.findings.append(Finding.make("trader", p.rationale, p.confidence, p.evidence_ids,
                                             {"target_weight": p.target_weight}, ("proposal", p.source),
                                             untrusted=p.untrusted))
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
                                             {"target_weight": d.target_weight}, ("decision", d.source),
                                             untrusted=decision_untrusted(st)))
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
                        note: str = "", resume: bool = True) -> TaskRun:
        """Record a decision and, by default, resume the run on the calling thread when it
        is parked and nobody else drives it; the API passes ``resume=False`` and hands the
        continuation to its task pool instead (see ``continuation_due``). A decision for a
        run that is being driven, or that is not waiting, is only recorded: the driver
        asks the gateway at the step."""
        if not isinstance(self.gateway, QueuedApprovalGateway):
            raise ValueError("approvals are not queued in this harness")
        a = self.gateway.get(approval_id)           # KeyError when unknown (or withdrawn with its run)
        run = self.runs.get(a.task_id)
        if run is None or run.done:
            rec = self.record(a.task_id) if run is None else None
            state = run.state.value if run is not None else (rec["state"] if rec else "evicted")
            raise ValueError(f"task {a.task_id} is {state}; approval {approval_id} can no longer be decided")
        a = self.gateway.resolve(approval_id, approve, decided_by, note)
        run.evidence.record(EvidenceType.APPROVAL, decided_by,
                            f"{'approved' if approve else 'rejected'} {a.request.tool}",
                            {"approval": a.id, "note": note}, run.correlation_id)
        if resume and self.continuation_due(run):
            return self.resume(run)
        return run


def wait_until_done(run: TaskRun, timeout_s: float = 60.0) -> TaskRun:
    """Block until a run (driven elsewhere) reaches a terminal or waiting state."""
    t0 = time.perf_counter()
    while not run.done and run.state is not TaskState.AWAITING_APPROVAL:
        if time.perf_counter() - t0 > timeout_s:
            raise TimeoutError("run did not finish in time")
        time.sleep(0.02)
    return run
