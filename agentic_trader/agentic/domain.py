"""Domain model of the agentic layer: frozen, framework-free dataclasses.

Nothing here imports the LLM SDK, MCP, a web framework or pandas. Every other
module in ``agentic_trader.agentic`` builds on these types, so the vocabulary is
fixed in one place:

* a **Task** is a request ("decide on EURUSD as of 2024-03-01 for role trader");
* a **Plan** is an ordered list of **PlanStep**s restricted to a known catalogue;
* a **ToolDescriptor** describes a callable capability (schema derived from the
  Python signature) and its **ToolAnnotations** (read-only, risk level, required
  capabilities);
* every tool call yields an **Evidence** record with a SHA-256 digest of its
  payload, so an audit trail exists before any agent interprets the data;
* a **Finding** is a claim made by an agent, citing evidence ids;
* a **PolicyDecision** says whether a tool call may run, and which rule decided.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any


# ------------------------------------------------------------------ enums
class TaskState(str, Enum):
    CREATED = "CREATED"
    PLANNING = "PLANNING"
    VALIDATING_PLAN = "VALIDATING_PLAN"
    EXECUTING = "EXECUTING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    CRITIQUING = "CRITIQUING"
    VALIDATING_EVIDENCE = "VALIDATING_EVIDENCE"
    FINALISING = "FINALISING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED})

# Legal transitions. The harness refuses anything else, so a bug cannot skip
# governance steps by jumping straight to COMPLETED.
TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    TaskState.CREATED: frozenset({TaskState.PLANNING, TaskState.CANCELLED}),
    TaskState.PLANNING: frozenset({TaskState.VALIDATING_PLAN, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.VALIDATING_PLAN: frozenset({TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.EXECUTING: frozenset({TaskState.AWAITING_APPROVAL, TaskState.CRITIQUING,
                                    TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.AWAITING_APPROVAL: frozenset({TaskState.EXECUTING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.CRITIQUING: frozenset({TaskState.VALIDATING_EVIDENCE, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.VALIDATING_EVIDENCE: frozenset({TaskState.FINALISING, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.FINALISING: frozenset({TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELLED}),
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELLED: frozenset(),
}


class StepType(str, Enum):
    TOOL = "tool"            # call a catalogued tool (policy-gated, yields evidence)
    AGENT = "agent"          # run one of the firm's agents / stages
    CRITIC = "critic"        # governance: deterministic + optional LLM critique
    VALIDATE = "validate"    # governance: drop findings whose evidence does not resolve
    FINALISE = "finalise"    # governance: audited report
    HUMAN_APPROVAL = "human_approval"  # explicit pause for a person


GOVERNANCE_STEPS = (StepType.CRITIC, StepType.VALIDATE, StepType.FINALISE)


class EvidenceType(str, Enum):
    DATA = "DATA"                  # raw provider output (prices, headlines, rates)
    CALCULATION = "CALCULATION"    # deterministic derivation (indicators, VaR, alpha)
    DOCUMENT = "DOCUMENT"          # retrieved knowledge passage
    MODEL_OUTPUT = "MODEL_OUTPUT"  # LLM reply (structured)
    DECISION = "DECISION"          # an agent's structured decision document
    APPROVAL = "APPROVAL"          # a human or gateway approval record


class RiskLevel(str, Enum):
    LOW = "low"        # read-only data and calculations
    MEDIUM = "medium"  # retrieval, model calls, decision documents
    HIGH = "high"      # anything that would move capital or change configuration


class PolicyOutcome(str, Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class Role(str, Enum):
    VIEWER = "viewer"
    ANALYST = "analyst"
    TRADER = "trader"
    RISK = "risk"
    ADMIN = "admin"


class Capability(str, Enum):
    READ_MARKET_DATA = "read_market_data"
    READ_KNOWLEDGE = "read_knowledge"
    RUN_ANALYTICS = "run_analytics"
    RUN_MODELS = "run_models"
    PROPOSE_TRADES = "propose_trades"
    APPROVE_TRADES = "approve_trades"
    ADMIN = "admin"


ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.VIEWER: frozenset({Capability.READ_MARKET_DATA, Capability.READ_KNOWLEDGE}),
    Role.ANALYST: frozenset({Capability.READ_MARKET_DATA, Capability.READ_KNOWLEDGE,
                             Capability.RUN_ANALYTICS, Capability.RUN_MODELS}),
    Role.TRADER: frozenset({Capability.READ_MARKET_DATA, Capability.READ_KNOWLEDGE,
                            Capability.RUN_ANALYTICS, Capability.RUN_MODELS,
                            Capability.PROPOSE_TRADES}),
    Role.RISK: frozenset({Capability.READ_MARKET_DATA, Capability.READ_KNOWLEDGE,
                          Capability.RUN_ANALYTICS, Capability.RUN_MODELS,
                          Capability.APPROVE_TRADES}),
    Role.ADMIN: frozenset(Capability),
}


# --------------------------------------------------------------- helpers
def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def canonical_json(obj: Any) -> str:
    """Deterministic JSON for hashing: sorted keys, dates as ISO, floats as repr."""
    def default(o: Any) -> Any:
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        if isinstance(o, Enum):
            return o.value
        if hasattr(o, "tolist"):          # numpy arrays / scalars
            return o.tolist()
        if hasattr(o, "to_dict"):         # pandas objects
            return o.to_dict()
        if hasattr(o, "__dataclass_fields__"):
            return {k: getattr(o, k) for k in o.__dataclass_fields__}
        return repr(o)
    return json.dumps(obj, sort_keys=True, default=default, separators=(",", ":"), allow_nan=True)


def digest(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ tools
@dataclass(frozen=True)
class ToolAnnotations:
    read_only: bool = True
    risk: RiskLevel = RiskLevel.LOW
    required: frozenset[Capability] = frozenset({Capability.READ_MARKET_DATA})
    evidence_type: EvidenceType = EvidenceType.DATA


@dataclass(frozen=True)
class ToolDescriptor:
    name: str                       # "server.tool", e.g. "market_data.news"
    server: str
    description: str
    input_schema: dict[str, Any]    # JSON schema derived from the Python signature
    annotations: ToolAnnotations = ToolAnnotations()

    @property
    def short(self) -> str:
        return self.name.split(".", 1)[1]


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    arguments: dict[str, Any]
    correlation_id: str
    requested_by: str = "harness"

    @property
    def request_id(self) -> str:
        """Identity of the request for approvals: the tool and its arguments.

        Deliberately excludes the correlation id, so a request re-submitted after
        a person approved it (a resumed task, or the same ad-hoc call) is
        recognised as the approved one.
        """
        return digest({"tool": self.tool, "arguments": self.arguments})[:16]


@dataclass(frozen=True)
class ToolResult:
    request: ToolRequest
    ok: bool
    payload: Any = None
    error: str | None = None
    elapsed_ms: float = 0.0
    attempts: int = 1


# --------------------------------------------------------------- evidence
@dataclass(frozen=True)
class Evidence:
    id: str
    type: EvidenceType
    source: str                     # tool name, agent name or document id
    summary: str                    # one line, human-readable
    digest: str                     # SHA-256 of the canonical payload
    correlation_id: str
    created_at: datetime = field(default_factory=utc_now)
    arguments: dict[str, Any] = field(default_factory=dict)
    payload: Any = field(default=None, compare=False, repr=False)

    @staticmethod
    def build(type_: EvidenceType, source: str, summary: str, payload: Any,
              correlation_id: str, arguments: dict[str, Any] | None = None,
              prefix: str | None = None) -> "Evidence":
        return Evidence(id=new_id(prefix or _PREFIX[type_]), type=type_, source=source,
                        summary=summary, digest=digest(payload), correlation_id=correlation_id,
                        arguments=dict(arguments or {}), payload=payload)


_PREFIX = {EvidenceType.DATA: "DATA", EvidenceType.CALCULATION: "CALC",
           EvidenceType.DOCUMENT: "DOC", EvidenceType.MODEL_OUTPUT: "MODEL",
           EvidenceType.DECISION: "DEC", EvidenceType.APPROVAL: "APPR"}


@dataclass
class Finding:
    """A claim by an agent. ``evidence_ids`` must resolve in the task's store."""
    id: str
    agent: str
    claim: str
    confidence: float
    evidence_ids: tuple[str, ...]
    numbers: dict[str, float] = field(default_factory=dict)  # figures the claim rests on
    tags: tuple[str, ...] = ()

    @staticmethod
    def make(agent: str, claim: str, confidence: float, evidence_ids: list[str] | tuple[str, ...],
             numbers: dict[str, float] | None = None, tags: tuple[str, ...] = ()) -> "Finding":
        return Finding(new_id("FIND"), agent, claim, float(confidence), tuple(evidence_ids),
                       dict(numbers or {}), tags)


# ----------------------------------------------------------------- policy
@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    rule: str                       # name of the rule that decided
    reason: str

    @property
    def allowed(self) -> bool:
        return self.outcome is PolicyOutcome.ALLOW


# ------------------------------------------------------------------- plan
@dataclass(frozen=True)
class PlanStep:
    id: str
    type: StepType
    name: str                       # tool name, agent stage name, or governance name
    arguments: dict[str, Any] = field(default_factory=dict)
    depends_on: tuple[str, ...] = ()
    rationale: str = ""

    @staticmethod
    def make(type_: StepType, name: str, arguments: dict[str, Any] | None = None,
             depends_on: tuple[str, ...] = (), rationale: str = "", id_: str | None = None) -> "PlanStep":
        return PlanStep(id_ or new_id("STEP"), type_, name, dict(arguments or {}), depends_on, rationale)


@dataclass(frozen=True)
class Plan:
    steps: tuple[PlanStep, ...]
    source: str = "canonical"       # "canonical" | "llm" | "llm+repaired"
    notes: tuple[str, ...] = ()     # what the validator changed


# ------------------------------------------------------------------- task
@dataclass(frozen=True)
class Task:
    symbol: str
    as_of: date
    role: Role = Role.TRADER
    current_weight: float | None = None
    question: str = ""              # free text from the requester, shown to the planner
    id: str = field(default_factory=lambda: new_id("TASK"))
    created_at: datetime = field(default_factory=utc_now)
