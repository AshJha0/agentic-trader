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

import hashlib
import hmac
import json
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from ..instruments import Instrument
from .domain import (
    Capability,
    PolicyDecision,
    PolicyOutcome,
    RiskLevel,
    Role,
    ROLE_CAPABILITIES,
    ToolDescriptor,
    ToolRequest,
    new_id,
    utc_now,
)

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
        return PolicyDecision(PolicyOutcome.DENY, "required_capabilities", f"role {ctx.role.value} lacks {names}")
    return None


def read_only_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if ctx.tool.annotations.read_only:
        return None
    if Capability.PROPOSE_TRADES not in ctx.capabilities:
        return PolicyDecision(
            PolicyOutcome.DENY, "read_only", f"{ctx.tool.name} changes state and role {ctx.role.value} cannot propose trades"
        )
    return PolicyDecision(PolicyOutcome.REQUIRE_APPROVAL, "read_only", f"{ctx.tool.name} changes state; approval required")


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
        if key == "current_weight":  # the position held: a fact to size from, whatever the cap
            continue
        wcap = float(ctx.config.get("max_position", 1.0))
        if abs(fv) > wcap:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", f"{key} {fv:+.2f} exceeds the max position {wcap:.2f}")
    lookback = args.get("lookback_days")
    if lookback is not None and (not isinstance(lookback, (int, float)) or not 0 < lookback <= 3660):
        return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "lookback_days must be in (0, 3660]")
    notional = args.get("notional")
    if notional is not None:  # an order's size is bounded before it can reach an approver
        try:
            nv = float(notional)
        except (TypeError, ValueError):
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "notional is not a number")
        if not math.isfinite(nv) or nv <= 0:
            return PolicyDecision(PolicyOutcome.DENY, "argument_guard", "notional must be a positive finite number")
        ncap = ctx.config.get("max_order_notional")
        if ncap is not None and nv > float(ncap):
            return PolicyDecision(
                PolicyOutcome.DENY, "argument_guard", f"notional {nv:,.0f} exceeds the per-order cap {float(ncap):,.0f}"
            )
    return None


def risk_level_rule(ctx: PolicyContext) -> PolicyDecision | None:
    if ctx.tool.annotations.risk is RiskLevel.HIGH:
        return PolicyDecision(PolicyOutcome.REQUIRE_APPROVAL, "risk_level", f"{ctx.tool.name} is high risk; approval required")
    return None


def allow_rule(ctx: PolicyContext) -> PolicyDecision:
    return PolicyDecision(
        PolicyOutcome.ALLOW,
        "default_allow",
        f"{ctx.tool.name} is read-only, {ctx.tool.annotations.risk.value} risk, "
        f"and role {ctx.role.value} holds the required capabilities",
    )


DEFAULT_RULES: tuple[Rule, ...] = (
    deny_list_rule,
    capability_rule,
    argument_guard_rule,
    read_only_rule,
    risk_level_rule,
    allow_rule,
)
MAX_DECISIONS_KEPT = 1000


# --------------------------------------------------------------- engine
class PolicyEngine:
    def __init__(
        self,
        config: dict[str, Any] | None = None,
        rules: tuple[Rule, ...] = DEFAULT_RULES,
        role_capabilities: dict[Role, frozenset[Capability]] | None = None,
    ):
        self.config = dict(config or {})
        self.rules = rules
        # ``is None``, not ``or``: an explicitly empty map grants nothing (fail closed).
        self.role_capabilities = ROLE_CAPABILITIES if role_capabilities is None else role_capabilities
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
            existing = next(
                (a for a in self._queue.values() if a.task_id == task_id and a.request.request_id == request.request_id), None
            )
            if existing is None:
                existing = ApprovalRequest(new_id("APPROVAL"), task_id, request, reason)
                self._queue[existing.id] = existing
            return existing.approved if existing.decided else None

    def pending(self, task_id: str | None = None) -> list[ApprovalRequest]:
        with self._lock:
            return [a for a in self._queue.values() if not a.decided and (task_id is None or a.task_id == task_id)]

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

    def resolve(
        self, approval_id: str, approve: bool, decided_by: str = "human", note: str = "", signature: str | None = None
    ) -> ApprovalRequest:
        # ``signature`` is ignored here; ``SignedApprovalGateway`` requires it.
        with self._lock:
            a = self._queue.get(approval_id)
            if a is None:
                raise KeyError(f"unknown approval {approval_id}")
            if a.decided:
                raise ValueError(f"approval {approval_id} already decided")
            a.decided, a.approved, a.decided_by, a.note = True, bool(approve), decided_by, note
            return a


# ------------------------------------------------------------ signed approvals (plan 4.5)
def approval_message(approval_id: str, request: ToolRequest, approve: bool) -> bytes:
    """The canonical bytes an approver signs: the approval, the exact request (tool and
    arguments, via ``request_id``) and the verdict. A signature for one verdict or one
    request does not verify for another."""
    return json.dumps(
        {"approval": approval_id, "request": request.request_id, "tool": request.tool, "approve": bool(approve)}, sort_keys=True
    ).encode()


def sign_approval(secret: bytes, approval_id: str, request: ToolRequest, approve: bool) -> str:
    """LEGACY mode: HMAC-SHA256 (stdlib only) of ``approval_message`` under a shared secret.

    Tamper-evident, not non-repudiable: the server holds the same secret as the approver,
    so anyone with server access can mint a valid signature. Prefer ``sign_approval_ed25519``."""
    return hmac.new(secret, approval_message(approval_id, request, approve), hashlib.sha256).hexdigest()


def ed25519_keypair() -> tuple[bytes, bytes]:
    """A new Ed25519 key pair as raw bytes ``(private32, public32)``. The private half
    belongs to the approver (their machine, a hardware token); the server only ever needs
    the public half. Uses the ``cryptography`` package (pinned in requirements-lock.txt)."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.generate()
    raw = serialization.Encoding.Raw
    priv = sk.private_bytes(raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    return priv, sk.public_key().public_bytes(raw, serialization.PublicFormat.Raw)


def sign_approval_ed25519(private_key: bytes, approval_id: str, request: ToolRequest, approve: bool) -> str:
    """Ed25519 signature (hex) of ``approval_message``. Run by the approver, never by the
    server: the server cannot produce this without the approver's private key."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    sk = Ed25519PrivateKey.from_private_bytes(bytes(private_key))
    return sk.sign(approval_message(approval_id, request, approve)).hex()


def verify_approval_ed25519(public_key: bytes, signature: str, approval_id: str, request: ToolRequest, approve: bool) -> bool:
    """True when ``signature`` (hex) is a valid Ed25519 signature of the approval message."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        Ed25519PublicKey.from_public_bytes(bytes(public_key)).verify(
            bytes.fromhex(str(signature)), approval_message(approval_id, request, approve)
        )
        return True
    except (InvalidSignature, ValueError):
        return False


class AppendOnlyApprovalLog:
    """A second, append-only record of approval events: one JSON line per event, each line
    carrying the SHA-256 of the previous line, so an edited, removed or reordered line breaks
    ``verify``. The file is only ever opened in append mode. Optional; independent of the
    in-memory queue and of the evidence store."""

    GENESIS = "0" * 64

    def __init__(self, path: str | os.PathLike) -> None:
        self.path = os.fspath(path)
        self._lock = threading.Lock()

    def _lines(self) -> list[str]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, encoding="utf-8") as f:
            return [x.rstrip("\n") for x in f if x.strip()]

    def append(self, event: dict[str, Any]) -> None:
        with self._lock:
            lines = self._lines()
            prev = hashlib.sha256(lines[-1].encode()).hexdigest() if lines else self.GENESIS
            line = json.dumps({**event, "prev": prev}, sort_keys=True, default=str)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def entries(self) -> list[dict[str, Any]]:
        return [json.loads(x) for x in self._lines()]

    def verify(self) -> bool:
        prev = self.GENESIS
        for line in self._lines():
            try:
                if json.loads(line).get("prev") != prev:
                    return False
            except ValueError:
                return False
            prev = hashlib.sha256(line.encode()).hexdigest()
        return True


def _valid_price(px: float | None) -> bool:
    """A price the re-pricing check can use: present, finite and positive."""
    return px is not None and math.isfinite(px) and px > 0


class SignedApprovalGateway(QueuedApprovalGateway):
    """A queued gateway whose decisions are signed by named approvers (opt-in).

    * **identity + signature** -- every decision names an approver from ``public_keys``
      (approver id -> raw 32-byte Ed25519 public key; the approver signs with
      ``sign_approval_ed25519`` on their own machine, the server holds public material only,
      which gives non-repudiation) or, in LEGACY mode, from ``keys`` (approver id -> shared
      HMAC secret held by the server too: tamper-evident only); an approver id may appear in
      one map, not both; an unknown
      approver, a missing or bad signature, or a second signature by the same approver is
      refused and nothing is recorded;
    * **N-of-M** -- ``quorum`` maps a tool to the number of distinct approvers it needs
      (default: two for ``execution.submit_order``, ``default_quorum`` otherwise); one valid
      rejection rejects at once;
    * **TTL** -- an approval older than ``ttl_s`` seconds when the request executes is
      rejected as expired;
    * **re-pricing** -- with ``price_fn(request) -> float | None`` the price is captured when
      the quorum is reached and read again at execution; a relative move beyond
      ``price_tolerance`` rejects the stale approval, and so does a missing, non-finite or
      non-positive price at either point (the check fails closed: a data outage at quorum
      time or at execution can never switch it off);
    * **second store** -- every signature, decision and execution-time check is also written
      to ``store`` (an ``AppendOnlyApprovalLog``) when given.
    """

    name = "signed"

    def __init__(
        self,
        keys: dict[str, bytes] | None = None,
        quorum: dict[str, int] | None = None,
        default_quorum: int = 1,
        ttl_s: float | None = None,
        price_fn: Callable[[ToolRequest], float | None] | None = None,
        price_tolerance: float = 0.01,
        store: AppendOnlyApprovalLog | None = None,
        clock: Callable[[], float] = time.time,
        public_keys: dict[str, bytes] | None = None,
    ) -> None:
        super().__init__()
        self.keys = {k: bytes(v) for k, v in (keys or {}).items()}
        self.public_keys = {k: bytes(v) for k, v in (public_keys or {}).items()}
        if not self.keys and not self.public_keys:
            raise ValueError("a signed gateway needs at least one approver key")
        both = set(self.keys) & set(self.public_keys)
        if both:
            raise ValueError(f"approver(s) {sorted(both)} have both an HMAC secret and a public key")
        for k, v in self.public_keys.items():
            if len(v) != 32:
                raise ValueError(f"public key for {k!r} must be 32 raw Ed25519 bytes")
        n_approvers = len(self.keys) + len(self.public_keys)
        self.quorum = {"execution.submit_order": 2} if quorum is None else dict(quorum)
        self.default_quorum = int(default_quorum)
        for tool, n in {**self.quorum, "*": self.default_quorum}.items():
            if not 1 <= n <= n_approvers:
                raise ValueError(f"quorum {n} for {tool} must be between 1 and {n_approvers} approvers")
        self.ttl_s, self.price_fn, self.price_tolerance = ttl_s, price_fn, float(price_tolerance)
        self.store, self.clock = store, clock
        self._sigs: dict[str, dict[str, str]] = {}  # approval id -> approver -> signature
        self._approved_at: dict[str, float] = {}
        self._price_at: dict[str, float | None] = {}

    def needed(self, tool: str) -> int:
        return self.quorum.get(tool, self.default_quorum)

    def _price(self, request: ToolRequest) -> float | None:
        """``price_fn(request)``; an exception is no price (which the check treats as a failure)."""
        assert self.price_fn is not None
        try:
            px = self.price_fn(request)
            return None if px is None else float(px)
        except Exception:  # noqa: BLE001 - a failed price lookup is "no price", which rejects
            return None

    def signatures(self, approval_id: str) -> dict[str, str]:
        with self._lock:
            return dict(self._sigs.get(approval_id, {}))

    def _log(self, **event: Any) -> None:
        if self.store is not None:
            self.store.append({"at": self.clock(), **event})

    def resolve(
        self, approval_id: str, approve: bool, decided_by: str = "human", note: str = "", signature: str | None = None
    ) -> ApprovalRequest:
        """Add one approver's signed decision; ``decided_by`` is the approver id. The request
        stays pending until the quorum is reached (or one approver rejects)."""
        secret, public = self.keys.get(decided_by), self.public_keys.get(decided_by)
        if secret is None and public is None:
            raise ValueError(f"unknown approver {decided_by!r}")
        if not signature:
            raise ValueError("a signed gateway needs the approver's signature")
        with self._lock:
            a = self._queue.get(approval_id)
            if a is None:
                raise KeyError(f"unknown approval {approval_id}")
            if a.decided:
                raise ValueError(f"approval {approval_id} already decided")
            if public is not None:
                ok = verify_approval_ed25519(public, str(signature), approval_id, a.request, approve)
            else:
                assert secret is not None
                ok = hmac.compare_digest(sign_approval(secret, approval_id, a.request, approve), str(signature))
            if not ok:
                raise ValueError(f"bad signature from {decided_by!r} on approval {approval_id}")
            sigs = self._sigs.setdefault(approval_id, {})
            if decided_by in sigs:
                raise ValueError(f"{decided_by!r} already signed approval {approval_id}")
            sigs[decided_by] = str(signature)
            need = self.needed(a.request.tool)
            if not approve:
                a.decided, a.approved, a.decided_by, a.note = True, False, decided_by, note
            elif len(sigs) >= need:
                a.decided, a.approved, a.decided_by, a.note = True, True, ",".join(sorted(sigs)), note
                self._approved_at[approval_id] = self.clock()
                self._price_at[approval_id] = self._price(a.request) if self.price_fn else None
            else:
                a.note = f"{len(sigs)} of {need} signatures"
        self._log(
            kind="signature",
            approval=approval_id,
            approver=decided_by,
            approve=bool(approve),
            request=a.request.request_id,
            tool=a.request.tool,
            signature=str(signature),
            scheme="ed25519" if public is not None else "hmac-legacy",
        )
        if a.decided:
            self._log(
                kind="decision", approval=approval_id, approved=a.approved, by=a.decided_by, price=self._price_at.get(approval_id)
            )
        return a

    def decide(self, task_id: str, request: ToolRequest, reason: str) -> bool | None:
        verdict = super().decide(task_id, request, reason)
        if verdict is not True:
            return verdict
        with self._lock:
            a = next(x for x in self._queue.values() if x.task_id == task_id and x.request.request_id == request.request_id)
            approved_at, price_at = self._approved_at.get(a.id), self._price_at.get(a.id)
        problem = None
        now = self.clock()
        if self.ttl_s is not None and approved_at is not None and now - approved_at > self.ttl_s:
            problem = f"approval expired ({now - approved_at:.0f}s > ttl {self.ttl_s:.0f}s)"
        elif self.price_fn is not None:
            # Round 1 (A9/E-2): fail closed. No valid price at quorum time, or none now, means
            # the re-pricing check cannot run, so the approval is treated as stale.
            if not _valid_price(price_at):
                problem = (
                    f"no valid price was captured when the quorum was reached ({price_at!r}): "
                    "the re-pricing check cannot run, so the approval is refused"
                )
            else:
                assert price_at is not None
                px = self._price(request)
                if not _valid_price(px):
                    problem = f"no valid price at execution ({px!r}): the re-pricing check cannot run"
                elif abs(px / price_at - 1.0) > self.price_tolerance:  # type: ignore[operator]
                    problem = f"price moved since approval ({price_at:g} -> {px}); tolerance {self.price_tolerance:.2%}"
        if problem is not None:
            with self._lock:
                a.approved, a.note = False, problem
            self._log(kind="stale", approval=a.id, reason=problem)
            return False
        self._log(kind="executed", approval=a.id, request=request.request_id)
        return True
