"""Tool registry, schema derivation and the policy-gated executor.

A **tool** is an ordinary Python function registered under ``server.name``. Its
JSON schema is derived from the signature (type hints, defaults, docstring), so
one definition serves the in-process client, the LLM planner's catalogue and the
optional MCP server.

The **ToolExecutor** is the only way agents reach data. Every call:

1. is checked by the policy engine for the calling role (ALLOW / DENY / REQUIRE_APPROVAL);
2. runs with a per-call timeout and bounded retry on transient errors;
3. yields an **Evidence** record (arguments, correlation id, SHA-256 digest of the
   payload) in the task's evidence store, whether it succeeded or failed;
4. is traced and counted.
"""
from __future__ import annotations

import inspect
import logging
import threading
import time
import typing
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable

from .domain import (Capability, Evidence, EvidenceType, PolicyOutcome, RiskLevel, Role,
                     ToolAnnotations, ToolDescriptor, ToolRequest, ToolResult, new_id)
from .evidence import EvidenceStore
from .policy import ApprovalGateway, AutoApprovalGateway, PolicyEngine
from .tracing import Tracer

log = logging.getLogger(__name__)

_JSON_TYPES = {int: "integer", float: "number", str: "string", bool: "boolean",
               list: "array", dict: "object", date: "string"}


def schema_from_signature(fn: Callable[..., Any]) -> dict[str, Any]:
    """JSON schema for a function's parameters (ignores ``self`` and ``ctx``)."""
    sig = inspect.signature(fn)
    try:
        hints = typing.get_type_hints(fn)
    except Exception:  # forward references that cannot be resolved: fall back to raw annotations
        hints = {k: p.annotation for k, p in sig.parameters.items()}
    props, required = {}, []
    for name, p in sig.parameters.items():
        if name in ("self", "ctx") or p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        ann = hints.get(name, p.annotation)
        spec = _type_spec(ann)
        if p.default is inspect.Parameter.empty:
            required.append(name)
        else:
            spec["default"] = p.default.isoformat() if isinstance(p.default, date) else p.default
        props[name] = spec
    return {"type": "object", "properties": props, "required": required, "additionalProperties": False}


def _type_spec(ann: Any) -> dict[str, Any]:
    origin = typing.get_origin(ann)
    if origin is typing.Union or (origin is not None and origin.__name__ == "UnionType"):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        spec = _type_spec(args[0]) if len(args) == 1 else {"anyOf": [_type_spec(a) for a in args]}
        spec["nullable"] = True
        return spec
    if origin in (list, tuple):
        inner = typing.get_args(ann)
        return {"type": "array", "items": _type_spec(inner[0]) if inner else {}}
    if origin is dict:
        return {"type": "object"}
    if ann is date:
        return {"type": "string", "format": "date"}
    if ann in _JSON_TYPES:
        return {"type": _JSON_TYPES[ann]}
    if ann is inspect.Parameter.empty or ann is Any:
        return {}
    return {"type": "string", "description": getattr(ann, "__name__", str(ann))}


def coerce_arguments(schema: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate and coerce JSON-ish arguments against a schema (dates, numbers).

    Raises ``ValueError`` for unknown or missing arguments so a planner cannot
    smuggle extra parameters into a tool, and so that a typo is a loud failure.
    """
    props = schema.get("properties", {})
    unknown = set(arguments) - set(props)
    if unknown:
        raise ValueError(f"unknown arguments: {sorted(unknown)}")
    missing = [r for r in schema.get("required", []) if r not in arguments]
    if missing:
        raise ValueError(f"missing arguments: {missing}")
    out = {}
    for k, v in arguments.items():
        spec = props[k]
        if v is None:
            if not spec.get("nullable"):
                raise ValueError(f"argument {k} may not be null")
            out[k] = None
            continue
        t = spec.get("type")
        if spec.get("format") == "date":
            out[k] = date.fromisoformat(v) if isinstance(v, str) else v
            if not isinstance(out[k], date):
                raise ValueError(f"argument {k} must be a date")
        elif t == "integer":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
                raise ValueError(f"argument {k} must be an integer")
            out[k] = int(v)
        elif t == "number":
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"argument {k} must be a number")
            out[k] = float(v)
        elif t == "boolean":
            if not isinstance(v, bool):
                raise ValueError(f"argument {k} must be a boolean")
            out[k] = v
        elif t == "string":
            if not isinstance(v, str):
                raise ValueError(f"argument {k} must be a string")
            if len(v) > 2000:
                raise ValueError(f"argument {k} is too long")
            out[k] = v
        elif t == "array":
            if not isinstance(v, (list, tuple)) or len(v) > 1000:
                raise ValueError(f"argument {k} must be a list of at most 1000 items")
            out[k] = list(v)
        else:
            out[k] = v
    return out


@dataclass
class RegisteredTool:
    descriptor: ToolDescriptor
    fn: Callable[..., Any]


class ToolRegistry:
    """Catalogue of tools, grouped by server name."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    def register(self, server: str, fn: Callable[..., Any], name: str | None = None,
                 annotations: ToolAnnotations | None = None,
                 description: str | None = None) -> ToolDescriptor:
        short = name or fn.__name__
        full = f"{server}.{short}"
        if full in self._tools:
            raise ValueError(f"tool {full} already registered")
        desc = ToolDescriptor(full, server, (description or inspect.getdoc(fn) or short).strip(),
                              schema_from_signature(fn), annotations or ToolAnnotations())
        self._tools[full] = RegisteredTool(desc, fn)
        return desc

    def tool(self, server: str, *, read_only: bool = True, risk: RiskLevel = RiskLevel.LOW,
             required: frozenset[Capability] | set[Capability] = frozenset({Capability.READ_MARKET_DATA}),
             evidence_type: EvidenceType = EvidenceType.DATA, name: str | None = None):
        """Decorator form of ``register``."""
        ann = ToolAnnotations(read_only, risk, frozenset(required), evidence_type)

        def deco(fn):
            self.register(server, fn, name, ann)
            return fn
        return deco

    def register_descriptor(self, descriptor: ToolDescriptor, fn: Callable[..., Any]) -> ToolDescriptor:
        """Register a tool whose schema is already known (a remote MCP tool)."""
        if descriptor.name in self._tools:
            raise ValueError(f"tool {descriptor.name} already registered")
        self._tools[descriptor.name] = RegisteredTool(descriptor, fn)
        return descriptor

    def get(self, name: str) -> RegisteredTool:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"unknown tool {name!r}") from None

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def descriptors(self, server: str | None = None) -> list[ToolDescriptor]:
        return [t.descriptor for t in self._tools.values() if server is None or t.descriptor.server == server]

    def servers(self) -> list[str]:
        return sorted({t.descriptor.server for t in self._tools.values()})

    def catalogue(self) -> list[dict[str, Any]]:
        """JSON-ready listing for the planner prompt and the API."""
        return [{"name": d.name, "description": d.description, "input_schema": d.input_schema,
                 "read_only": d.annotations.read_only, "risk": d.annotations.risk.value,
                 "required": sorted(c.value for c in d.annotations.required)}
                for d in self.descriptors()]

    def __len__(self) -> int:
        return len(self._tools)


TRANSIENT = (ConnectionError, TimeoutError, OSError)


@dataclass
class ExecutorConfig:
    timeout_s: float = 30.0
    max_attempts: int = 2
    retry_backoff_s: float = 0.2


@dataclass
class ToolExecutor:
    """Policy-gated, traced, evidence-producing tool calls."""
    registry: ToolRegistry
    policy: PolicyEngine
    evidence: EvidenceStore
    role: Role = Role.TRADER
    gateway: ApprovalGateway = field(default_factory=AutoApprovalGateway)
    tracer: Tracer = field(default_factory=Tracer)
    config: ExecutorConfig = field(default_factory=ExecutorConfig)
    task_id: str = "adhoc"
    _pool: ThreadPoolExecutor = field(default_factory=lambda: ThreadPoolExecutor(max_workers=8), repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    pending_approval: bool = False

    def call(self, name: str, correlation_id: str | None = None, requested_by: str = "harness",
             **arguments: Any) -> ToolResult:
        cid = correlation_id or new_id("CID")
        req = ToolRequest(name, dict(arguments), cid, requested_by)
        with self.tracer.span(f"tool:{name}", tool=name, correlation_id=cid) as span:
            try:
                tool = self.registry.get(name)
            except KeyError as e:
                span.fail(str(e))
                self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="unknown")
                return self._fail(req, str(e))

            decision = self.policy.evaluate(req, tool.descriptor, self.role)
            span.set(policy=decision.outcome.value, rule=decision.rule)
            if decision.outcome is PolicyOutcome.DENY:
                self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="denied")
                return self._fail(req, f"denied by policy ({decision.rule}): {decision.reason}",
                                  evidence_type=tool.descriptor.annotations.evidence_type)
            if decision.outcome is PolicyOutcome.REQUIRE_APPROVAL:
                verdict = self.gateway.decide(self.task_id, req, decision.reason)
                if verdict is None:
                    self.pending_approval = True
                    self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="awaiting_approval")
                    return self._fail(req, f"awaiting approval ({decision.rule}): {decision.reason}",
                                      evidence_type=tool.descriptor.annotations.evidence_type)
                if verdict is False:
                    self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="rejected")
                    return self._fail(req, f"approval rejected ({decision.rule}): {decision.reason}",
                                      evidence_type=tool.descriptor.annotations.evidence_type)
                self.evidence.record(EvidenceType.APPROVAL, self.gateway.name,
                                     f"approved {name} ({decision.rule})", {"request": req.request_id,
                                                                            "reason": decision.reason}, cid)

            try:
                args = coerce_arguments(tool.descriptor.input_schema, req.arguments)
            except ValueError as e:
                span.fail(str(e))
                self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="bad_arguments")
                return self._fail(req, f"bad arguments: {e}",
                                  evidence_type=tool.descriptor.annotations.evidence_type)

            t0 = time.perf_counter()
            payload, error, attempts = None, None, 0
            for attempt in range(1, self.config.max_attempts + 1):
                attempts = attempt
                try:
                    payload = self._pool.submit(tool.fn, **args).result(timeout=self.config.timeout_s)
                    error = None
                    break
                except FutureTimeout:
                    error = f"timed out after {self.config.timeout_s}s"
                except TRANSIENT as e:
                    error = f"transient error: {e}"
                except Exception as e:  # a bug or a bad input: do not retry
                    error = f"{type(e).__name__}: {e}"
                    break
                if attempt < self.config.max_attempts:
                    time.sleep(self.config.retry_backoff_s * attempt)
            elapsed = (time.perf_counter() - t0) * 1000
            self.tracer.metrics.observe("tool_latency_ms", elapsed, tool=name)
            if error is not None:
                span.fail(error)
                self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="error")
                return self._fail(req, error, elapsed, attempts, tool.descriptor.annotations.evidence_type)

            ev = self.evidence.record(tool.descriptor.annotations.evidence_type, name,
                                      _summarise(name, args, payload), payload, cid, args)
            span.set(evidence=ev.id, elapsed_ms=round(elapsed, 1))
            self.tracer.metrics.inc("tool_calls_total", tool=name, outcome="ok")
            return ToolResult(req, True, payload, None, elapsed, attempts)

    def _fail(self, req: ToolRequest, error: str, elapsed: float = 0.0, attempts: int = 1,
              evidence_type: EvidenceType = EvidenceType.DATA) -> ToolResult:
        # A failed call is evidence too: the report can say what was *not* available.
        self.evidence.record(evidence_type, req.tool, f"FAILED {req.tool}: {error[:120]}",
                             {"error": error, "arguments": req.arguments}, req.correlation_id, req.arguments)
        log.info("tool %s failed: %s", req.tool, error)
        return ToolResult(req, False, None, error, elapsed, attempts)

    def evidence_for(self, result: ToolResult) -> Evidence | None:
        """The evidence record produced by a call (successful or failed)."""
        for ev in reversed(list(self.evidence)):
            if ev.correlation_id == result.request.correlation_id and ev.source == result.request.tool:
                return ev
        return None


def _summarise(name: str, args: dict[str, Any], payload: Any) -> str:
    keys = ", ".join(f"{k}={v}" for k, v in list(args.items())[:3])
    if isinstance(payload, list):
        size = f"{len(payload)} items"
    elif isinstance(payload, dict):
        size = f"{len(payload)} fields"
    else:
        size = type(payload).__name__
    return f"{name}({keys}) -> {size}"
