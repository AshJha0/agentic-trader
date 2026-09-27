"""The desk's tools as a real MCP server over stdio, and a client for it.

Server::

    python -m agentic_trader.agentic.mcp_server            # synthetic data
    python -m agentic_trader.agentic.mcp_server --data yahoo --role trader --approval deny

Any MCP client (an IDE, Claude Desktop, another agent) can list and call the
same catalogue the in-process harness uses. Every call the server receives goes
through the same ``ToolExecutor`` as the HTTP path: the ``PolicyEngine`` built
from the configuration (symbol universe, deny list, argument guards) for the
configured ``--role``, the approval gateway named by ``--approval`` /
``agentic.approval`` for state-changing and HIGH-risk tools, an evidence record
per call and a trace span. Stdio carries no identity, so the role is the
operator's choice for the whole session; ``--approval deny`` locks the
state-changing tools down, ``queued`` parks them with nobody to answer (the call
fails ``awaiting approval``), ``auto`` approves them and records the approval.
The optional dependency is the official ``mcp`` SDK (``pip install "agentic-trader[mcp]"``).

Client helpers (``discover``, ``call``, ``registry_from_stdio``) run the async
SDK synchronously so the harness can be pointed at a remote server: discovered
descriptors become entries in a ``ToolRegistry`` whose functions forward over
stdio. The classification that drives the local policy fails closed: a remote
tool is treated as state-changing and HIGH risk unless it carries annotations
saying otherwise, and an operator ``overrides`` map has the last word.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from functools import wraps
from typing import Any

from ..config import make_config
from ..data import get_provider
from .domain import Capability, EvidenceType, RiskLevel, Role, ToolAnnotations, ToolDescriptor
from .evidence import EvidenceStore
from .policy import ApprovalGateway, PolicyEngine
from .servers import DeskTools, build_registry
from .tools import ExecutorConfig, ToolExecutor, ToolRegistry
from .tracing import Tracer


def _require_mcp():
    try:
        import mcp  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise ImportError("the MCP server needs `pip install \"agentic-trader[mcp]\"`") from e


# ------------------------------------------------------------------ server
def governed_executor(registry: ToolRegistry, config: dict[str, Any], role: Role = Role.TRADER,
                      gateway: ApprovalGateway | None = None, order_cap: float | None = None) -> ToolExecutor:
    """The executor the server routes every call through: the same policy the harness
    builds from the configuration, the configured approval gateway, its own evidence
    store and tracer."""
    from .harness import _gateway
    acfg = config.get("agentic", {})
    policy = PolicyEngine({"symbol_universe": acfg.get("symbol_universe"), "deny_tools": acfg.get("deny_tools", ()),
                           "max_position": config["risk"]["max_position"],
                           "max_order_notional": order_cap,
                           "max_symbols_per_call": acfg.get("max_symbols_per_call", 60)})
    return ToolExecutor(registry, policy, EvidenceStore(), role, gateway or _gateway(acfg.get("approval", "auto")),
                        Tracer(), ExecutorConfig(float(acfg.get("tool_timeout_s", 30.0))), task_id="mcp")


def build_mcp_server(registry: ToolRegistry, name: str = "agentic-trader", executor: ToolExecutor | None = None,
                     config: dict[str, Any] | None = None, role: Role = Role.TRADER,
                     gateway: ApprovalGateway | None = None):
    """An ``MCPServer`` exposing every registered tool with its annotations.

    Handlers never bind a tool function directly: each call goes through ``executor``
    (built with ``governed_executor`` from ``config`` when not given), so policy,
    approval and evidence apply exactly as in-process. A refused or failed call is an
    MCP tool error carrying the executor's reason.
    """
    _require_mcp()
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations as McpAnnotations

    ex = executor or governed_executor(registry, config or make_config(), role, gateway)
    server = MCPServer(name, instructions="Point-in-time market data, quant analytics, policy "
                                          "knowledge and execution simulation for a trading desk. "
                                          f"Calls run under policy for role {ex.role.value}; approval "
                                          f"mode {ex.gateway.name}.")
    for d in registry.descriptors():
        fn = registry.get(d.name).fn
        ann = McpAnnotations(read_only_hint=d.annotations.read_only,
                             destructive_hint=not d.annotations.read_only)
        server.tool(name=d.name.replace(".", "__"), description=d.description, annotations=ann,
                    meta={"risk": d.annotations.risk.value,
                          "required": sorted(c.value for c in d.annotations.required),
                          "evidence_type": d.annotations.evidence_type.value})(_governed(ex, d.name, fn))
    server.executor = ex   # type: ignore[attr-defined]  # evidence and metrics stay reachable for tests / operators
    return server


def _governed(ex: ToolExecutor, name: str, fn):
    from mcp.server.mcpserver.exceptions import ToolError

    # ``wraps`` keeps the tool's signature, so the SDK derives the same input schema it
    # would from the bare function; the body runs the policy-gated executor instead. A
    # refusal is a ``ToolError`` so the caller reads the policy's reason (the SDK hides
    # any other exception's message).
    @wraps(fn)
    def handler(**kwargs):
        res = ex.call(name, requested_by="mcp", **kwargs)
        if not res.ok:
            raise ToolError(res.error or "tool call failed")
        return res.payload
    return handler


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="agentic-trader MCP server (stdio)")
    p.add_argument("--data", choices=["synthetic", "yahoo", "csv"], default="synthetic")
    p.add_argument("--csv-dir", default=None)
    p.add_argument("--role", choices=[r.value for r in Role], default=Role.TRADER.value,
                   help="the role every call is evaluated for (stdio carries no identity)")
    p.add_argument("--approval", choices=["auto", "queued", "deny"], default=None,
                   help="gateway for tools that need approval (default: agentic.approval)")
    args = p.parse_args(argv)
    over: dict[str, Any] = {"data_provider": args.data}
    if args.csv_dir:
        over["csv_dir"] = args.csv_dir
    if args.approval:
        over["agentic"] = {"approval": args.approval}
    cfg = make_config(over)
    tools = DeskTools(get_provider(cfg), cfg)
    registry = build_registry(tools)
    ex = governed_executor(registry, cfg, Role(args.role), order_cap=tools.order_cap)
    build_mcp_server(registry, executor=ex).run(transport="stdio")
    return 0


# ------------------------------------------------------------------ client
def _server_params(args: list[str] | None = None):
    from mcp import StdioServerParameters
    return StdioServerParameters(command=sys.executable,
                                 args=["-m", "agentic_trader.agentic.mcp_server", *(args or [])])


async def _with_session(params, coro):
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            return await coro(s)


def _run(coro) -> Any:
    """Run a client coroutine; unwrap anyio's exception groups into one plain error."""
    try:
        return asyncio.run(coro)
    except Exception as e:  # noqa: BLE001 - re-raised below as a single RuntimeError
        leaf = e
        while hasattr(leaf, "exceptions") and leaf.exceptions:
            leaf = leaf.exceptions[0]
        if isinstance(leaf, RuntimeError):
            raise leaf from None
        raise RuntimeError(f"{type(leaf).__name__}: {leaf}") from None


def discover(server_args: list[str] | None = None) -> list[dict[str, Any]]:
    """List the remote server's tools (name, description, input schema, annotations).

    ``read_only`` is True only when the server annotated the tool as read-only; a tool
    with no annotations is reported as state-changing (``annotated`` says which case).
    """
    _require_mcp()

    async def go(s):
        res = await s.list_tools()
        return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema,
                 "annotated": t.annotations is not None,
                 "read_only": t.annotations is not None and t.annotations.read_only_hint is True,
                 "meta": t.meta or {}} for t in res.tools]
    return _run(_with_session(_server_params(server_args), go))


def call(name: str, arguments: dict[str, Any], server_args: list[str] | None = None) -> Any:
    """Call one remote tool and return its JSON payload (raises on a tool error)."""
    _require_mcp()
    args = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in arguments.items()}

    async def go(s):
        res = await s.call_tool(name, args)
        if res.is_error:
            raise RuntimeError("".join(getattr(c, "text", "") for c in res.content) or "tool error")
        if res.structured_content is not None:
            sc = res.structured_content
            return sc["result"] if isinstance(sc, dict) and set(sc) == {"result"} else sc
        text = "".join(getattr(c, "text", "") for c in res.content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return _run(_with_session(_server_params(server_args), go))


def classify_remote_tool(tool: dict[str, Any], override: dict[str, Any] | None = None) -> ToolAnnotations:
    """Local annotations for a discovered tool, failing closed.

    Without annotations the tool is state-changing, HIGH risk and needs
    ``PROPOSE_TRADES``; with annotations the read-only hint is honoured and the
    server's ``meta`` (risk, required, evidence_type) is read, unknown values falling
    back to HIGH / ``PROPOSE_TRADES``. ``override`` (an operator's allowlist entry:
    ``read_only``, ``risk``, ``required``, ``evidence_type``) wins over both.
    """
    annotated, read_only = bool(tool.get("annotated")), bool(tool.get("read_only"))
    meta = tool.get("meta") or {}
    risk, required, evidence = RiskLevel.HIGH, frozenset({Capability.PROPOSE_TRADES}), EvidenceType.DATA
    if annotated:
        try:
            risk = RiskLevel(meta.get("risk", "high"))
        except ValueError:
            risk = RiskLevel.HIGH
        try:
            required = frozenset(Capability(c) for c in meta.get("required", ["propose_trades"]))
        except ValueError:
            required = frozenset({Capability.PROPOSE_TRADES})
        try:
            evidence = EvidenceType(meta.get("evidence_type", "DATA"))
        except ValueError:
            evidence = EvidenceType.DATA
    if override:
        read_only = bool(override.get("read_only", read_only))
        risk = RiskLevel(override.get("risk", risk.value))
        required = frozenset(Capability(c) for c in override.get("required", [c.value for c in required]))
        evidence = EvidenceType(override.get("evidence_type", evidence.value))
    return ToolAnnotations(read_only=read_only, risk=risk, required=required, evidence_type=evidence)


def registry_from_stdio(server_args: list[str] | None = None,
                        overrides: dict[str, dict[str, Any]] | None = None) -> ToolRegistry:
    """A local registry whose tools forward to the stdio server.

    Descriptors come from discovery, so the executor validates arguments against
    the remote schema and applies policy exactly as for in-process tools; the
    classification is ``classify_remote_tool`` (fail closed), ``overrides`` keyed by
    the local ``server.tool`` name.
    """
    reg = ToolRegistry()
    for t in discover(server_args):
        server, short = t["name"].split("__", 1) if "__" in t["name"] else ("remote", t["name"])
        local = f"{server}.{short}"
        ann = classify_remote_tool(t, (overrides or {}).get(local))
        schema = dict(t["input_schema"])
        schema.setdefault("additionalProperties", False)
        remote_name = t["name"]

        def forward(_name=remote_name, **kwargs):
            return call(_name, kwargs, server_args)
        reg.register_descriptor(ToolDescriptor(local, server, t["description"], schema, ann), forward)
    return reg


if __name__ == "__main__":
    sys.exit(main())
