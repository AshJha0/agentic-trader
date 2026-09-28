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
state-changing tools down, ``auto`` approves them and records the approval, and
``queued`` is refused (nothing on a stdio server could ever answer, so every
parked request would wait forever).
The optional dependency is the official ``mcp`` SDK (``pip install "agentic-trader[mcp]"``).

Client helpers (``discover``, ``call``, ``registry_from_stdio``) run the async
SDK synchronously so the harness can be pointed at a remote server: discovered
descriptors become entries in a ``ToolRegistry`` whose functions forward over
one live stdio session (the desk behind it keeps its book, plans and tickets
across calls). The classification that drives the local policy never trusts the
remote server: a discovered tool is state-changing, HIGH risk and needs
``PROPOSE_TRADES`` whatever it annotates or puts in ``meta`` (those are reported
for display only); the operator's ``overrides`` map is the only relaxation, and
it defaults to the desk's own catalogue because the server this client launches
is this package's own module.
"""
from __future__ import annotations

import argparse
import asyncio
import concurrent.futures
import json
import sys
import threading
import weakref
from datetime import date
from functools import wraps
from typing import Any

from ..config import make_config
from ..data import get_provider
from .domain import Capability, EvidenceType, RiskLevel, Role, ToolAnnotations, ToolDescriptor
from .evidence import EvidenceStore
from .policy import ApprovalGateway, PolicyEngine, QueuedApprovalGateway
from .servers import DeskTools, build_registry, default_order_cap
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
    builds from the configuration (including the desk's per-order notional cap, the
    configuration's default when ``order_cap`` is not given), the configured approval
    gateway, its own evidence store and tracer."""
    from .harness import _gateway
    acfg = config.get("agentic", {})
    policy = PolicyEngine({"symbol_universe": acfg.get("symbol_universe"), "deny_tools": acfg.get("deny_tools", ()),
                           "max_position": config["risk"]["max_position"],
                           "max_order_notional": default_order_cap(config) if order_cap is None else float(order_cap),
                           "max_symbols_per_call": acfg.get("max_symbols_per_call", 60)})
    return ToolExecutor(registry, policy, EvidenceStore(), role, gateway or _gateway(acfg.get("approval", "auto")),
                        Tracer(), ExecutorConfig(float(acfg.get("tool_timeout_s", 30.0))), task_id="mcp")


def build_mcp_server(registry: ToolRegistry, name: str = "agentic-trader", executor: ToolExecutor | None = None,
                     config: dict[str, Any] | None = None, role: Role = Role.TRADER,
                     gateway: ApprovalGateway | None = None, order_cap: float | None = None):
    """An ``MCPServer`` exposing every registered tool with its annotations.

    Handlers never bind a tool function directly: each call goes through ``executor``
    (built with ``governed_executor`` from ``config`` when not given, with ``order_cap``
    the desk's cap or the configuration's default), so policy, approval and evidence
    apply exactly as in-process. A refused or failed call is an MCP tool error carrying
    the executor's reason. A queued gateway is refused: nobody on a stdio server can
    decide, so every parked request would wait forever.
    """
    _require_mcp()
    from mcp.server.mcpserver import MCPServer
    from mcp.types import ToolAnnotations as McpAnnotations

    ex = executor or governed_executor(registry, config or make_config(), role, gateway, order_cap)
    if isinstance(ex.gateway, QueuedApprovalGateway):
        raise ValueError("the MCP server cannot use the queued approval gateway: nothing on a stdio server "
                         "can decide a parked request; use --approval deny (or auto)")
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
                   help="gateway for tools that need approval (default: agentic.approval); queued is refused")
    args = p.parse_args(argv)
    over: dict[str, Any] = {"data_provider": args.data}
    if args.csv_dir:
        over["csv_dir"] = args.csv_dir
    if args.approval:
        over["agentic"] = {"approval": args.approval}
    cfg = make_config(over)
    if cfg["agentic"].get("approval") == "queued":
        p.error("--approval queued cannot work on a stdio server: nothing can decide a parked request, so every "
                "state-changing call would wait forever; use --approval deny (locked down) or auto")
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
        return [_describe(t) for t in (await s.list_tools()).tools]
    return _run(_with_session(_server_params(server_args), go))


def _describe(t: Any) -> dict[str, Any]:
    """A discovered tool as a plain dict; the annotation fields are the server's claims."""
    return {"name": t.name, "description": t.description or "", "input_schema": t.input_schema,
            "annotated": t.annotations is not None,
            "read_only": t.annotations is not None and t.annotations.read_only_hint is True,
            "meta": t.meta or {}}


def _json_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in arguments.items()}


def _payload(res: Any) -> Any:
    """The JSON payload of a ``call_tool`` result (raises ``RuntimeError`` on a tool error)."""
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


def call(name: str, arguments: dict[str, Any], server_args: list[str] | None = None) -> Any:
    """Call one remote tool on a fresh server and return its JSON payload (raises on a tool
    error). A registry built by ``registry_from_stdio`` keeps one session instead."""
    _require_mcp()
    args = _json_arguments(arguments)

    async def go(s):
        return _payload(await s.call_tool(name, args))
    return _run(_with_session(_server_params(server_args), go))


class StdioSession:
    """One live stdio server for the lifetime of a registry.

    The session runs on its own thread inside a single coroutine (the SDK's context
    managers are entered and left by the same task), and every ``call`` is handed to
    it through a queue and served as its own task: calls run concurrently over the one
    session (MCP multiplexes by request id), so a call the executor abandons at its
    deadline never delays the next one. The desk behind the server keeps its book, the
    plans it produced and the tickets it wrote across calls, which a fresh process per
    call would forget before the order citing a plan arrives.
    """

    def __init__(self, params: Any, start_timeout_s: float = 60.0):
        self._params = params
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None
        self._tasks: set[asyncio.Task] = set()
        self._ready: concurrent.futures.Future = concurrent.futures.Future()
        self._closed = False
        self._thread = threading.Thread(target=self._main, name="mcp-stdio-session", daemon=True)
        self._thread.start()
        try:
            self._ready.result(timeout=start_timeout_s)
        except BaseException:
            self.close()
            raise

    def _main(self) -> None:
        try:
            asyncio.run(self._serve())
        except BaseException as e:  # noqa: BLE001 - reported to the constructor or to the pending calls
            if not self._ready.done():
                self._ready.set_exception(_leaf(e))
        finally:
            self._closed = True
            if not self._ready.done():
                self._ready.set_exception(RuntimeError("stdio server ended before it was ready"))
            self._drain(RuntimeError("stdio server ended"))

    async def _serve(self) -> None:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client
        self._loop = asyncio.get_running_loop()
        self._queue = asyncio.Queue()
        async with stdio_client(self._params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                self._ready.set_result(True)
                while True:
                    item = await self._queue.get()
                    if item is None:
                        break
                    request, fut = item
                    task = asyncio.create_task(self._handle(request, fut, s))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                for task in list(self._tasks):
                    task.cancel()
                await asyncio.gather(*self._tasks, return_exceptions=True)

    @staticmethod
    async def _handle(request, fut: concurrent.futures.Future, session) -> None:
        try:
            result = await request(session)
        except asyncio.CancelledError:
            if not fut.done():
                fut.set_exception(RuntimeError("stdio session is closed"))
        except BaseException as e:  # noqa: BLE001 - re-raised on the calling thread
            if not fut.done():
                fut.set_exception(_leaf(e))
        else:
            if not fut.done():
                fut.set_result(result)

    def _drain(self, error: Exception) -> None:
        q = self._queue
        while q is not None and not q.empty():
            item = q.get_nowait()
            if item is not None and not item[1].done():
                item[1].set_exception(error)

    def _submit(self, request) -> Any:
        """Run ``request(session)`` (a coroutine factory) on the session's thread and wait."""
        if self._closed or self._loop is None or self._queue is None:
            raise RuntimeError("stdio session is closed")
        fut: concurrent.futures.Future = concurrent.futures.Future()
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (request, fut))
        except RuntimeError:
            raise RuntimeError("stdio session is closed") from None
        if not self._thread.is_alive():
            self._drain(RuntimeError("stdio server ended"))
        try:
            return fut.result()
        except RuntimeError:
            raise
        except Exception as e:  # noqa: BLE001 - one plain error for the executor, as ``call`` gives
            raise RuntimeError(f"{type(e).__name__}: {e}") from None

    def list_tools(self) -> list[Any]:
        return self._submit(lambda s: s.list_tools()).tools

    def call(self, name: str, arguments: dict[str, Any], timeout_s: float | None = None) -> Any:
        """One remote call; ``timeout_s`` bounds the wait for its result on the server side
        too, so a request the caller has given up on is cancelled rather than left running."""
        args = _json_arguments(arguments)
        return _payload(self._submit(lambda s: s.call_tool(name, args, read_timeout_seconds=timeout_s)))

    def close(self) -> None:
        """End the session and the server process; pending calls fail."""
        if self._closed:
            return
        self._closed = True
        if self._loop is not None and self._queue is not None and self._thread.is_alive():
            try:
                self._loop.call_soon_threadsafe(self._queue.put_nowait, None)
            except RuntimeError:   # the loop already stopped
                pass
        self._thread.join(timeout=10.0)


def _leaf(e: BaseException) -> BaseException:
    while hasattr(e, "exceptions") and e.exceptions:
        e = e.exceptions[0]
    return e


_DESK_OVERRIDES: dict[str, dict[str, Any]] = {}


def desk_overrides() -> dict[str, dict[str, Any]]:
    """The operator override map for this package's own server: every desk tool with the
    annotations its local catalogue declares (``server.tool`` -> read_only, risk,
    required, evidence_type). A tool the desk does not have is not in it, so anything a
    server adds stays fail-closed."""
    if not _DESK_OVERRIDES:
        reg = build_registry(DeskTools(None, make_config()))   # type: ignore[arg-type]  # the functions are never called
        _DESK_OVERRIDES.update({d.name: {"read_only": d.annotations.read_only, "risk": d.annotations.risk.value,
                                         "required": sorted(c.value for c in d.annotations.required),
                                         "evidence_type": d.annotations.evidence_type.value}
                                for d in reg.descriptors()})
    return {k: dict(v) for k, v in _DESK_OVERRIDES.items()}


def classify_remote_tool(tool: dict[str, Any], override: dict[str, Any] | None = None) -> ToolAnnotations:
    """Local annotations for a discovered tool, failing closed.

    A remote tool is state-changing, HIGH risk, needs ``PROPOSE_TRADES`` and yields DATA
    evidence whatever the server annotated (``read_only_hint``) or put in ``meta`` (risk,
    required, evidence_type): those are the remote's claims and are kept for display
    only. ``override`` (an operator's allowlist entry: ``read_only``, ``risk``,
    ``required``, ``evidence_type``) is the only thing that relaxes the classification.
    """
    read_only, risk = False, RiskLevel.HIGH
    required, evidence = frozenset({Capability.PROPOSE_TRADES}), EvidenceType.DATA
    if override:
        read_only = bool(override.get("read_only", read_only))
        risk = RiskLevel(override.get("risk", risk.value))
        required = frozenset(Capability(c) for c in override.get("required", [c.value for c in required]))
        evidence = EvidenceType(override.get("evidence_type", evidence.value))
    return ToolAnnotations(read_only=read_only, risk=risk, required=required, evidence_type=evidence)


def registry_from_stdio(server_args: list[str] | None = None,
                        overrides: dict[str, dict[str, Any]] | None = None,
                        call_timeout_s: float | None = None) -> ToolRegistry:
    """A local registry whose tools forward to one stdio server session.

    Descriptors come from discovery, so the executor validates arguments against
    the remote schema and applies policy exactly as for in-process tools; the
    classification is ``classify_remote_tool`` (fail closed) relaxed only by
    ``overrides``, keyed by the local ``server.tool`` name. ``None`` means the desk's
    own catalogue (``desk_overrides``: the server this client launches is this
    package's own module); pass ``{}`` to relax nothing. ``call_timeout_s`` is the
    per-call server-side deadline (give it the executor's ``tool_timeout_s`` so an
    abandoned call is cancelled on the server too; ``None`` waits). The session lives
    with the registry (``registry.session.close()`` ends it early).
    """
    _require_mcp()
    if overrides is None:
        overrides = desk_overrides()
    session = StdioSession(_server_params(server_args))
    try:
        tools = session.list_tools()
    except BaseException:
        session.close()
        raise
    reg = ToolRegistry()
    for t in tools:
        raw = _describe(t)
        server, short = raw["name"].split("__", 1) if "__" in raw["name"] else ("remote", raw["name"])
        local = f"{server}.{short}"
        ann = classify_remote_tool(raw, overrides.get(local))
        schema = dict(raw["input_schema"])
        schema.setdefault("additionalProperties", False)
        remote_name = raw["name"]

        def forward(_name=remote_name, **kwargs):
            return session.call(_name, kwargs, call_timeout_s)
        reg.register_descriptor(ToolDescriptor(local, server, raw["description"], schema, ann), forward)
    reg.session = session   # type: ignore[attr-defined]
    weakref.finalize(reg, session.close)
    return reg


if __name__ == "__main__":
    sys.exit(main())
