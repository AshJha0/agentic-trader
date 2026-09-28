"""Policy engine and approval gateways.

The engine evaluates ordered rules against a tool request made on behalf of a
role. The first rule that decides wins and is named in the decision, so every
ALLOW / DENY / REQUIRE_APPROVAL is explainable. Rules are plain callables and
can be extended; the defaults are:

1. **deny list** - tools that are never callable through the agent path;
2. **required capabilities** - the role must hold every capability the tool asks for;
3. **argument guards** - symbols (scalar ``symbol`` and every element of a
   ``symbols`` list, capped in length) must be in the configured universe, proposed
   weights must be finite and within the max position (``current_weight`` is a fact
   about the book, not a proposal: finite, but never capped, so a position above the
   limit can be reduced), dates must not be in the future, order quantities must be
   finite and positive and the notional below the per-order cap (``max_order_notional``);
4. **read-only** - a non-read-only tool needs ``PROPOSE_TRADES`` and approval;
5. **risk level** - HIGH-risk tools always require approval, even for admins.

The guards run before the approval outcome on purpose: a state-changing request
with a bad argument is refused outright, never parked for a person to approve.

Approval gateways decide what happens to REQUIRE_APPROVAL:

* ``AutoApprovalGateway`` approves everything (development);
* ``QueuedApprovalGateway`` parks the request and lets a person decide later
  (the API exposes it); the harness moves the task to AWAITING_APPROVAL;
* ``DenyApprovalGateway`` rejects everything (locked-down batch runs).
"""
from __future__ import annotations

import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from ..instruments import Instrument
from .domain import (Capability, PolicyDecision, PolicyOutcome, RiskLevel, Role, ROLE_CAPABILITIES,
                     ToolDescriptor, ToolRequest, new_id, utc_now)

Rule = Callable[["PolicyContext"], PolicyDecision | None]


@dataclass(frozen=True)
class PolicyContext:
    request: ToolRequest
    tool: ToolDescriptor
    role: Role
    capabilities: frozenset[Capability]
    config: dict[str, Any]


# ---------------------------------------------------------------- rules
def deny_list_rule(ctx: PolicyContext) -> PolicyDecision | None:
    denied = set(ctx.config.get("deny_tools", ()))
    if ctx.tool.name in denied:
        return PolicyDecision(PolicyOutcome.DENY, "deny_list", f"{ctx.tool.name} is on the deny list")
    return None


def capability_rule(ctx: PolicyContext) -> PolicyDecision | None:
    missing = ctx.tool.annotations.required - ctx.capabilities
    if missing:
        names = ", ".join(sorted(c.value for c in missing))
        return PolicyDecision(PolicyOutcome.DENY, "required_capabilities",
                              f"role {ctx.role.value} lacks {names}")
    return None


def read_only_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if ctx.tool.annotations.read_only:
        return None
    if Capability.PROPOSE_TRADES not in ctx.capabilities:
        return PolicyDecision(PolicyOutcome.DENY, "read_only",
                              f"{ctx.tool.name} changes state and role {ctx.role.value} cannot propose trades")
    return PolicyDecision(PolicyOutcome.REQUIRE_APPROVAL, "read_only",
                          f"{ctx.tool.name} changes state; approval required")


DEFAULT_MAX_SYMBOLS_PER_CALL = 60


def _deny(reason: str) -> PolicyDecision:
    return PolicyDecision(PolicyOutcome.DENY, "argument_guard", reason)


def argument_guard_rule(ctx: PolicyContext) -> PolicyDecision | None:
    args = ctx.request.arguments
    universe = ctx.config.get("symbol_universe")
    allowed = {s.upper() for s in universe} if universe else None
    candidates: list[Any] = []
    sym = args.get("symbol")
    if sym is not None:
        candidates.append(sym)
    syms = args.get("symbols")
    if syms is not None:
        if not isinstance(syms, (list, tuple)):
            return _deny("symbols must be a list")
        cap = int(ctx.config.get("max_symbols_per_call", DEFAULT_MAX_SYMBOLS_PER_CALL))
        if len(syms) > cap:
            return _deny(f"symbols lists {len(syms)} names; at most {cap} per call")
        candidates.extend(syms)
    for s in candidates:
        try:
            ins = Instrument.parse(str(s))
        except ValueError as e:
            return _deny(str(e))
        if allowed is not None and ins.symbol not in allowed:
            return _deny(f"{ins.symbol} is outside the configured universe")
    qty = args.get("quantity")
    if qty is not None:
        try:
            fq = float(qty)
        except (TypeError, ValueError):
            return _deny("quantity is not a number")
        if isinstance(qty, bool) or not math.isfinite(fq) or fq <= 0:
            return _deny("quantity must be a finite positive number")
    for key in ("as_of", "start", "end"):
        v = args.get(key)
        if isinstance(v, str):
            try:
                v = date.fromisoformat(v)
            except ValueError:
                return PolicyDecision(PolicyOutcome.DENY, "argument_guard", f"{key}={v!r} is not a date")
        if isinstance(v, date) and v > date.today():
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", f"{key} {v} is in the future")
    for key in ("weight", "target_weight", "current_weight", "proposed_weight"):
        v = args.get(key)
        if v is None:
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", f"{key} is not a number")
        if isinstance(v, bool) or not math.isfinite(fv):
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", f"{key} is not finite")
        if key == "current_weight":   # the position held: a fact to size from, whatever the cap
            continue
        cap = float(ctx.config.get("max_position", 1.0))
        if abs(fv) > cap:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard",
                                  f"{key} {fv:+.2f} exceeds the max position {cap:.2f}")
    lookback = args.get("lookback_days")
    if lookback is not None and (not isinstance(lookback, (int, float)) or not 0 < lookback <= 3660):
        return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "lookback_days must be in (0, 3660]")
    notional = args.get("notional")
    if notional is not None:   # an order's size is bounded before it can reach an approver
        try:
            nv = float(notional)
        except (TypeError, ValueError):
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "notional is not a number")
        if not math.isfinite(nv) or nv <= 0:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "notional must be a positive finite number")
        cap = ctx.config.get("max_order_notional")
        if cap is not None and nv > float(cap):
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard",
                                  f"notional {nv:,.0f} exceeds the per-order cap {float(cap):,.0f}")
    return None


def risk_level_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if ctx.tool.annotations.risk is RiskLevel.HIGH:
        return PolicyDecision(PolicyOutcome.REQUIRE_APPROVAL, "risk_level",
                              f"{ctx.tool.name} is high risk; approval required")
    return None


def allow_rule(ctx: PolicyContext) -> PolicyDecision:
    return PolicyDecision(PolicyOutcome.ALLOW, "default_allow",
                          f"{ctx.tool.name} is read-only, {ctx.tool.annotations.risk.value} risk, "
                          f"and role {ctx.role.value} holds the required capabilities")


DEFAULT_RULES: tuple[Rule, ...] = (deny_list_rule, capability_rule, argument_guard_rule,
                                   read_only_rule, risk_level_rule, allow_rule)
MAX_DECISIONS_KEPT = 1000


# --------------------------------------------------------------- engine
class PolicyEngine:
    def __init__(self, config: dict[str, Any] | None = None, rules: tuple[Rule, ...] = DEFAULT_RULES,
                 role_capabilities: dict[Role, frozenset[Capability]] | None = None):
        self.config = dict(config or {})
        self.rules = rules
        self.role_capabilities = role_capabilities or ROLE_CAPABILITIES
        self.decisions: deque[tuple[str, PolicyDecision]] = deque(maxlen=MAX_DECISIONS_KEPT)
        self._lock = threading.Lock()

    def capabilities(self, role: Role) -> frozenset[Capability]:
        return self.role_capabilities.get(role, frozenset())

    def evaluate(self, request: ToolRequest, tool: ToolDescriptor, role: Role) -> PolicyDecision:
        ctx = PolicyContext(request, tool, role, self.capabilities(role), self.config)
        decision = None
        for rule in self.rules:
            decision = rule(ctx)
            if decision is not None:
                break
        if decision is None:  # a custom rule set with no terminal rule: fail closed
            decision = PolicyDecision(PolicyOutcome.DENY, "no_rule", "no rule decided; denied")
        with self._lock:
            self.decisions.append((request.tool, decision))
        return decision


# ------------------------------------------------------------ approvals
@dataclass
class ApprovalRequest:
    id: str
    task_id: str
    request: ToolRequest
    reason: str
    created_at: Any = field(default_factory=utc_now)
    decided: bool = False
    approved: bool | None = None
    decided_by: str | None = None
    note: str = ""


class ApprovalGateway:
    """Base: ``decide`` returns True (approved), False (rejected) or None (pending)."""

    name = "base"

    def decide(self, task_id: str, request: ToolRequest, reason: str) -> bool | None:
        raise NotImplementedError


class AutoApprovalGateway(ApprovalGateway):
    name = "auto"

    def decide(self, task_id: str, request: ToolRequest, reason: str) -> bool | None:
        return True


class DenyApprovalGateway(ApprovalGateway):
    name = "deny"

    def decide(self, task_id: str, request: ToolRequest, reason: str) -> bool | None:
        return False


class QueuedApprovalGateway(ApprovalGateway):
    """Parks requests for a person. ``resolve`` is what the API / CLI call."""

    name = "queued"

    def __init__(self) -> None:
        self._queue: dict[str, ApprovalRequest] = {}
        self._lock = threading.Lock()

    def decide(self, task_id: str, request: ToolRequest, reason: str) -> bool | None:
        # The same request asked again (a resumed task) finds its earlier entry.
        with self._lock:
            existing = next((a for a in self._queue.values()
                             if a.task_id == task_id and a.request.request_id == request.request_id), None)
            if existing is None:
                existing = ApprovalRequest(new_id("APPROVAL"), task_id, request, reason)
                self._queue[existing.id] = existing
            return existing.approved if existing.decided else None

    def pending(self, task_id: str | None = None) -> list[ApprovalRequest]:
        with self._lock:
            return [a for a in self._queue.values()
                    if not a.decided and (task_id is None or a.task_id == task_id)]

    def all(self) -> list[ApprovalRequest]:
        with self._lock:
            return list(self._queue.values())

    def get(self, approval_id: str) -> ApprovalRequest:
        with self._lock:
            a = self._queue.get(approval_id)
        if a is None:
            raise KeyError(f"unknown approval {approval_id}")
        return a

    def withdraw(self, task_id: str, note: str = "run finished") -> int:
        """Close a finished run's pending requests: they leave the pending list and can no
        longer be decided (``approved`` stays None), so nothing waits on a run that is over."""
        n = 0
        with self._lock:
            for a in self._queue.values():
                if a.task_id == task_id and not a.decided:
                    a.decided, a.decided_by, a.note = True, "harness", note
                    n += 1
        return n

    def forget(self, task_id: str) -> int:
        """Drop every request of a task whose run left the harness (evicted): bounded memory."""
        with self._lock:
            gone = [k for k, a in self._queue.items() if a.task_id == task_id]
            for k in gone:
                del self._queue[k]
        return len(gone)

    def resolve(self, approval_id: str, approve: bool, decided_by: str = "human", note: str = "") -> ApprovalRequest:
        with self._lock:
            a = self._queue.get(approval_id)
            if a is None:
                raise KeyError(f"unknown approval {approval_id}")
            if a.decided:
                raise ValueError(f"approval {approval_id} already decided")
            a.decided, a.approved, a.decided_by, a.note = True, bool(approve), decided_by, note
            return a
