"""The desk's tools as a real MCP server over stdio, and a client for it.

Server::

    python -m agentic_trader.agentic.mcp_server            # synthetic data
    python -m agentic_trader.agentic.mcp_server --data yahoo

Any MCP client (an IDE, Claude Desktop, another agent) can list and call the
same catalogue the in-process harness uses. The optional dependency is the
official ``mcp`` SDK (``pip install "agentic-trader[mcp]"``).

Client helpers (``discover``, ``call``, ``registry_from_stdio``) run the async
SDK synchronously so the harness can be pointed at a remote server: discovered
descriptors become entries in a ``ToolRegistry`` whose functions forward over
stdio. Policy, evidence and tracing then apply unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date
from typing import Any

from ..config import make_config
from ..data import get_provider
from .domain import Capability, EvidenceType, RiskLevel, ToolAnnotations, ToolDescriptor
from .servers import DeskTools, build_registry
from .tools import ToolRegistry


def _require_mcp():
    try:
        import mcp  # noqa: F401
    except ImportError as e:  # pragma: no cover
        raise ImportError("the MCP server needs `pip install \"agentic-trader[mcp]\"`") from e


# ------------------------------------------------------------------ server
def build_mcp_server(registry: ToolRegistry, name: str = "agentic-trader"):
    """An ``MCPServer`` exposing every registered tool with its annotations."""
    _require_mcp()
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations as McpAnnotations

    server = MCPServer(name, instructions="Point-in-time market data, quant analytics, policy "
                                          "knowledge and execution simulation for a trading desk.")
    for d in registry.descriptors():
        fn = registry.get(d.name).fn
        ann = McpAnnotations(read_only_hint=d.annotations.read_only,
                             destructive_hint=not d.annotations.read_only)
        server.tool(name=d.name.replace(".", "__"), description=d.description, annotations=ann,
                    meta={"risk": d.annotations.risk.value,
                          "required": sorted(c.value for c in d.annotations.required),
                          "evidence_type": d.annotations.evidence_type.value})(fn)
    return server


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="agentic-trader MCP server (stdio)")
    p.add_argument("--data", choices=["synthetic", "yahoo", "csv"], default="synthetic")
    p.add_argument("--csv-dir", default=None)
    args = p.parse_args(argv)
    over = {"data_provider": args.data}
    if args.csv_dir:
        over["csv_dir"] = args.csv_dir
    cfg = make_config(over)
    registry = build_registry(DeskTools(get_provider(cfg), cfg))
    build_mcp_server(registry).run(transport="stdio")
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
    """List the remote server's tools (name, description, input schema, annotations)."""
    _require_mcp()

    async def go(s):
        res = await s.list_tools()
        return [{"name": t.name, "description": t.description or "", "input_schema": t.input_schema,
                 "read_only": bool(getattr(t.annotations, "read_only_hint", True)),
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


def registry_from_stdio(server_args: list[str] | None = None) -> ToolRegistry:
    """A local registry whose tools forward to the stdio server.

    Descriptors come from discovery, so the executor validates arguments against
    the remote schema and applies policy exactly as for in-process tools.
    """
    reg = ToolRegistry()
    for t in discover(server_args):
        server, short = t["name"].split("__", 1) if "__" in t["name"] else ("remote", t["name"])
        meta = t["meta"]
        ann = ToolAnnotations(
            read_only=t["read_only"],
            risk=RiskLevel(meta.get("risk", "low")),
            required=frozenset(Capability(c) for c in meta.get("required", ["read_market_data"])),
            evidence_type=EvidenceType(meta.get("evidence_type", "DATA")))
        schema = dict(t["input_schema"])
        schema.setdefault("additionalProperties", False)
        remote_name = t["name"]

        def forward(_name=remote_name, **kwargs):
            return call(_name, kwargs, server_args)
        reg.register_descriptor(ToolDescriptor(f"{server}.{short}", server, t["description"], schema, ann), forward)
    return reg


if __name__ == "__main__":
    sys.exit(main())
