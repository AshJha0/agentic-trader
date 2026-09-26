"""Policy engine and approval gateways.

The engine evaluates ordered rules against a tool request made on behalf of a
role. The first rule that decides wins and is named in the decision, so every
ALLOW / DENY / REQUIRE_APPROVAL is explainable. Rules are plain callables and
can be extended; the defaults are:

1. **deny list** - tools that are never callable through the agent path;
2. **required capabilities** - the role must hold every capability the tool asks for;
3. **read-only** - a non-read-only tool needs ``PROPOSE_TRADES`` and approval;
4. **argument guards** - symbols must be in the configured universe, weights
   must be finite and within the max position, dates must not be in the future;
5. **risk level** - HIGH-risk tools always require approval, even for admins.

Approval gateways decide what happens to REQUIRE_APPROVAL:

* ``AutoApprovalGateway`` approves everything (development);
* ``QueuedApprovalGateway`` parks the request and lets a person decide later
  (the API exposes it); the harness moves the task to AWAITING_APPROVAL;
* ``DenyApprovalGateway`` rejects everything (locked-down batch runs).
"""
from __future__ import annotations

import math
import threading
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


def argument_guard_rule(ctx: PolicyContext) -> PolicyDecision | None:
    args = ctx.request.arguments
    universe = ctx.config.get("symbol_universe")
    sym = args.get("symbol")
    if sym is not None:
        try:
            ins = Instrument.parse(str(sym))
        except ValueError as e:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", str(e))
        if universe and ins.symbol not in {s.upper() for s in universe}:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard",
                                  f"{ins.symbol} is outside the configured universe")
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
        if not math.isfinite(fv):
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", f"{key} is not finite")
        cap = float(ctx.config.get("max_position", 1.0))
        if abs(fv) > cap:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard",
                                  f"{key} {fv:+.2f} exceeds the max position {cap:.2f}")
    lookback = args.get("lookback_days")
    if lookback is not None and (not isinstance(lookback, (int, float)) or not 0 < lookback <= 3660):
        return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "lookback_days must be in (0, 3660]")
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


DEFAULT_RULES: tuple[Rule, ...] = (deny_list_rule, capability_rule, read_only_rule,
                                   argument_guard_rule, risk_level_rule, allow_rule)


# --------------------------------------------------------------- engine
class PolicyEngine:
    def __init__(self, config: dict[str, Any] | None = None, rules: tuple[Rule, ...] = DEFAULT_RULES,
                 role_capabilities: dict[Role, frozenset[Capability]] | None = None):
        self.config = dict(config or {})
        self.rules = rules
        self.role_capabilities = role_capabilities or ROLE_CAPABILITIES
        self.decisions: list[tuple[str, PolicyDecision]] = []
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

    def resolve(self, approval_id: str, approve: bool, decided_by: str = "human", note: str = "") -> ApprovalRequest:
        with self._lock:
            a = self._queue.get(approval_id)
            if a is None:
                raise KeyError(f"unknown approval {approval_id}")
            if a.decided:
                raise ValueError(f"approval {approval_id} already decided")
            a.decided, a.approved, a.decided_by, a.note = True, bool(approve), decided_by, note
            return a
