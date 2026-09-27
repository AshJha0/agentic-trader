"""HTTP gateway for the agentic layer (optional: ``pip install "agentic-trader[api]"``).

    agentic-trader serve                 # http://127.0.0.1:8000/docs

Every request carries ``X-API-Key``; keys map to roles (``config["agentic"]["api_keys"]``)
and the role decides what the task and the approval endpoints may do.

| method | path                       | role         | what                                   |
|--------|----------------------------|--------------|----------------------------------------|
| POST   | /tasks                     | analyst+     | start a task (202 + task id)           |
| GET    | /tasks/{id}                | viewer+      | state, plan, decision, findings, critic|
| GET    | /tasks/{id}/report         | viewer+      | the audited report (JSON or markdown)  |
| GET    | /tasks/{id}/trace          | viewer+      | spans                                  |
| GET    | /tasks/{id}/evidence       | viewer+      | evidence records                       |
| POST   | /tasks/{id}/cancel         | analyst+     | cooperative cancellation               |
| GET    | /approvals                 | risk, admin  | pending approvals                      |
| POST   | /approvals/{id}            | risk, admin  | approve or reject, resumes the task    |
| GET    | /tools                     | viewer+      | the tool catalogue                     |
| GET    | /health, /metrics          | none         | liveness; Prometheus text metrics      |

No ``from __future__ import annotations`` here: FastAPI resolves the request
models by their runtime annotations, and these models are built inside the app
factory (so the optional dependency is imported lazily).
"""
import json
import logging
import os
import tempfile
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import date
from typing import Any

from ..graph import TradingGraph
from .domain import Capability, ROLE_CAPABILITIES, Role, Task
from .harness import AgentHarness
from .policy import QueuedApprovalGateway

log = logging.getLogger(__name__)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def create_app(harness: "AgentHarness | None" = None, graph: "TradingGraph | None" = None,
               config: "dict | None" = None, api_keys: "dict[str, str] | None" = None,
               workers: "int | None" = None, queue_limit: "int | None" = None):
    """The FastAPI app.

    Tasks run on a bounded thread pool (``workers``, default ``config["agentic"]["workers"]``)
    instead of one unbounded thread per request; ``queue_limit`` (default
    ``config["agentic"]["queue_limit"]``) caps the tasks accepted but not yet finished,
    beyond which ``POST /tasks`` answers ``503`` with a ``Retry-After`` header rather than
    letting a burst of requests pile up threads and LLM spend.
    """
    try:
        from contextlib import asynccontextmanager

        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.responses import PlainTextResponse
        from pydantic import BaseModel, Field
    except ImportError as e:  # pragma: no cover
        raise ImportError("the API needs `pip install \"agentic-trader[api]\"`") from e

    if harness is None:
        validate_app_config(config or {}, workers, queue_limit)
        graph = graph or TradingGraph(config)
        harness = AgentHarness(graph)   # the gateway follows config["agentic"]["approval"]: auto | queued | deny
    acfg = harness.config.get("agentic", {})
    n_workers = int(workers if workers is not None else acfg.get("workers", 4))
    limit = int(queue_limit if queue_limit is not None else acfg.get("queue_limit", 64))
    if n_workers < 1 or limit < 0:
        raise ValueError("workers must be >= 1 and queue_limit >= 0")
    keys = {k: Role(v) for k, v in (api_keys or acfg.get("api_keys", {})).items()}
    pool = ThreadPoolExecutor(max_workers=n_workers, thread_name_prefix="task")
    futures: dict[str, Future] = {}
    futures_lock = threading.Lock()   # request handlers run on FastAPI's own thread pool

    @asynccontextmanager
    async def lifespan(_app):
        yield
        # Stopping the server must not drain the queue: cancel what has not started and
        # ask the running tasks to stop at their next step.
        for run in list(harness.runs.values()):
            if not run.done:
                run.cancel_requested = True
        pool.shutdown(wait=False, cancel_futures=True)

    from ..provenance import package_version
    app = FastAPI(title="agentic-trader", version=package_version(), lifespan=lifespan,
                  description="Policy-gated, evidence-backed trading decisions for equities and FX.")
    app.state.harness = harness
    app.state.pool = pool

    def in_flight() -> int:
        with futures_lock:
            return sum(1 for f in futures.values() if not f.done())

    def _log_outcome(task_id: str):
        def cb(fut: Future) -> None:
            if fut.cancelled():
                return
            exc = fut.exception()
            if exc is not None:
                log.error("task %s: continuation raised %s: %s", task_id, type(exc).__name__, exc)
        return cb

    def schedule(task_id: str, run) -> None:
        """Run ``harness.resume(run)`` on the pool; the Future's exception is logged, never lost."""
        fut = pool.submit(harness.resume, run)
        fut.add_done_callback(_log_outcome(task_id))
        futures[task_id] = fut

    class TaskIn(BaseModel):
        symbol: str = Field(examples=["AAPL", "EURUSD"])
        as_of: date
        current_weight: float | None = None
        question: str = ""

    class ApprovalIn(BaseModel):
        approve: bool
        note: str = ""

    def role_of(x_api_key: str | None = Header(default=None)) -> Role:
        if x_api_key is None or x_api_key not in keys:
            raise HTTPException(401, "missing or unknown API key")
        return keys[x_api_key]

    def require(role: Role, cap: Capability) -> None:
        if cap not in ROLE_CAPABILITIES[role]:
            raise HTTPException(403, f"role {role.value} lacks {cap.value}")

    def get_run(task_id: str):
        run = harness.runs.get(task_id)
        if run is None:
            raise HTTPException(404, f"unknown task {task_id}")
        return run

    def get_record(task_id: str) -> dict[str, Any]:
        """A live run's record, or an archived one from the persistent store."""
        rec = harness.record(task_id)
        if rec is None:
            raise HTTPException(404, f"unknown task {task_id}")
        return rec

    @app.get("/health")
    def health() -> dict[str, Any]:
        busy = in_flight()
        archived = len(harness.store) if harness.store is not None else len(harness.archive)
        return {"status": "ok", "tasks": len(harness.runs) + archived, "live": len(harness.runs),
                "archived": archived, "persistent": harness.store is not None,
                "tools": len(harness.registry), "workers": n_workers, "queue_limit": limit,
                "in_flight": busy, "running": min(busy, n_workers), "queued": max(0, busy - n_workers),
                "worker_pid": os.getpid(), "approval": harness.gateway.name, "instance": harness.owner}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        # One exposition for the process: every run's tracer writes to the harness's Metrics,
        # so each family appears once and the counters are the service's totals.
        return harness.metrics.render() or "# no tasks yet\n"

    @app.get("/tools")
    def tools(role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        return harness.registry.catalogue()

    @app.post("/tasks", status_code=202)
    def create_task(body: TaskIn, role: Role = Depends(role_of)) -> dict[str, Any]:
        require(role, Capability.RUN_ANALYTICS)
        with futures_lock:
            for tid in [t for t, f in futures.items() if f.done()]:
                futures.pop(tid, None)
            busy = sum(1 for f in futures.values() if not f.done())
            if busy >= limit:
                raise HTTPException(503, f"{limit} tasks already in flight; retry later",
                                    headers={"Retry-After": "5"})
            task = Task(body.symbol, body.as_of, role, body.current_weight, body.question)
            run = harness.submit(task)
            schedule(task.id, run)
        return {"task_id": task.id, "state": run.state.value}

    @app.get("/tasks")
    def list_tasks(role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        live = [{"task_id": r.id, "symbol": r.task.symbol, "as_of": r.task.as_of.isoformat(),
                 "role": r.task.role.value, "state": r.state.value, "live": True}
                for r in list(harness.runs.values())]
        archived = [{"task_id": r["task_id"], "symbol": r["symbol"], "as_of": r["as_of"], "role": r["role"],
                     "state": r["state"], "live": False}
                    for r in harness.archived_summaries() if r["task_id"] not in harness.runs]
        return archived + live

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, role: Role = Depends(role_of)) -> dict[str, Any]:
        rec = dict(get_record(task_id))
        for k in ("report", "evidence_rows", "spans"):
            rec.pop(k, None)
        rec["live"] = task_id in harness.runs
        return rec

    @app.get("/tasks/{task_id}/report")
    def get_report(task_id: str, format: str = "json", role: Role = Depends(role_of)):
        rec = get_record(task_id)
        rep = rec.get("report")
        if rep is None:
            raise HTTPException(409, f"task is {rec['state']}; no report yet")
        if format == "markdown":
            from .reporter import Report
            return PlainTextResponse(Report(**rep).to_markdown())
        return rep

    @app.get("/tasks/{task_id}/trace")
    def get_trace(task_id: str, role: Role = Depends(role_of)) -> dict[str, Any]:
        rec = get_record(task_id)
        return {"summary": rec.get("trace", {}), "spans": rec.get("spans", [])}

    @app.get("/tasks/{task_id}/evidence")
    def get_evidence(task_id: str, role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        return get_record(task_id).get("evidence_rows", [])

    @app.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str, role: Role = Depends(role_of)) -> dict[str, Any]:
        require(role, Capability.RUN_ANALYTICS)
        if task_id not in harness.runs:
            if harness.record(task_id) is not None:
                raise HTTPException(409, "task belongs to another worker process or a previous run; "
                                         "nothing to cancel here")
            raise HTTPException(404, f"unknown task {task_id}")
        with futures_lock:
            fut = futures.get(task_id)
            if fut is not None:
                fut.cancel()   # still queued: it never starts
        run = harness.cancel(task_id)
        if run.state.value == "CREATED" and (fut is None or fut.cancelled()):
            run = harness.resume(run)   # applies the cancellation without doing any work
        return {"task_id": task_id, "state": run.state.value}

    @app.get("/approvals")
    def approvals(role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        require(role, Capability.APPROVE_TRADES)
        if not isinstance(harness.gateway, QueuedApprovalGateway):
            raise HTTPException(409, f"approvals are not queued on this service (approval mode "
                                     f"{harness.gateway.name})")
        return [{"id": a.id, "task_id": a.task_id, "tool": a.request.tool, "arguments": a.request.arguments,
                 "reason": a.reason, "created_at": a.created_at.isoformat()} for a in harness.pending_approvals()]

    @app.post("/approvals/{approval_id}")
    def decide(approval_id: str, body: ApprovalIn, role: Role = Depends(role_of)) -> dict[str, Any]:
        require(role, Capability.APPROVE_TRADES)
        try:
            run = harness.decide_approval(approval_id, body.approve, role.value, body.note, resume=False)
        except KeyError:
            raise HTTPException(404, f"unknown approval {approval_id} (approvals live on the process that queued them)")
        except ValueError as e:
            raise HTTPException(409, str(e))
        # Only a parked run nobody is driving gets a continuation (on the pool, under the same
        # bound as a new task); a running driver sees the decision at the step, and a second
        # thread can never enter the same run (the harness's per-run driving lock).
        resumed = False
        with futures_lock:
            if harness.continuation_due(run):
                schedule(run.id, run)
                resumed = True
        return {"approval_id": approval_id, "approved": body.approve, "task_id": run.id,
                "state": run.state.value, "resumed": resumed}

    return app


def uses_dev_keys(api_keys: dict[str, str]) -> bool:
    """True when any configured API key is one of the shipped development keys."""
    from ..config import DEFAULT_CONFIG
    shipped = set(DEFAULT_CONFIG["agentic"]["api_keys"])
    return any(k in shipped or k.startswith("dev-") for k in api_keys)


def serve_options(host: str, config: dict, ssl_certfile: str | None = None, ssl_keyfile: str | None = None,
                  allow_dev_keys: bool = False) -> dict[str, Any]:
    """Validate the deployment posture and return uvicorn keyword arguments.

    * TLS needs both a certificate and a key (``ssl_certfile`` / ``ssl_keyfile``).
    * Binding a non-loopback interface with the shipped development API keys is
      refused unless ``allow_dev_keys`` is set explicitly.
    * Binding a non-loopback interface without TLS logs a warning: put a TLS
      terminator in front of it or pass a certificate.
    """
    if (ssl_certfile is None) != (ssl_keyfile is None):
        raise ValueError("TLS needs both ssl_certfile and ssl_keyfile")
    for f in (ssl_certfile, ssl_keyfile):
        if f is not None and not os.path.exists(f):
            raise ValueError(f"TLS file not found: {f}")
    loopback = host in LOOPBACK_HOSTS
    keys = config.get("agentic", {}).get("api_keys", {})
    if not loopback and uses_dev_keys(keys) and not allow_dev_keys:
        raise ValueError(f"refusing to bind {host} with the shipped development API keys; set "
                         "config['agentic']['api_keys'] to real keys (or pass allow_dev_keys=True "
                         "for a throwaway test)")
    if not loopback and ssl_certfile is None:
        log.warning("serving plain HTTP on %s: API keys travel in clear text. Put a TLS terminator "
                    "in front of it or pass ssl_certfile / ssl_keyfile", host)
    opts: dict[str, Any] = {}
    if ssl_certfile is not None:
        opts.update(ssl_certfile=ssl_certfile, ssl_keyfile=ssl_keyfile)
    return opts


CONFIG_ENV = "AGENTIC_TRADER_APP_CONFIG"


def validate_app_config(config: dict, workers: "int | None" = None, queue_limit: "int | None" = None) -> None:
    """Raise ``ValueError`` for a configuration ``create_app`` would refuse -- checked in the
    parent before worker processes are forked, so a bad value fails once, loudly."""
    acfg = config.get("agentic", {})
    n_workers = int(workers if workers is not None else acfg.get("workers", 4))
    limit = int(queue_limit if queue_limit is not None else acfg.get("queue_limit", 64))
    if n_workers < 1 or limit < 0:
        raise ValueError("workers must be >= 1 and queue_limit >= 0")
    for k, v in acfg.get("api_keys", {}).items():
        try:
            Role(v)
        except ValueError:
            raise ValueError(f"api key {k[:4]}... maps to unknown role {v!r}") from None


def multiprocess_options(processes: int, config: dict) -> dict[str, Any]:
    """Validate a multi-process deployment and return the extra uvicorn arguments.

    Each process holds its own harness and thread pool, so the task store is what makes
    the processes one service: every process reads records the others wrote
    (``GET /tasks/{id}``, ``/report``, ``/evidence`` work from any process) while
    cancellation and approvals must reach the process that owns the live run --
    a request that lands elsewhere answers ``409``. A process count above one
    therefore requires ``config["agentic"]["task_db"]``, and a queued approval
    gateway is only reliable behind a sticky load balancer or with one process.
    """
    if processes < 1:
        raise ValueError("processes must be >= 1")
    if processes == 1:
        return {}
    if not config.get("agentic", {}).get("task_db"):
        raise ValueError("more than one process needs a shared task store: set agentic.task_db "
                         "(serve --task-db FILE) so every process can serve every task's record")
    validate_app_config(config)
    return {"workers": processes}


def app_factory():
    """uvicorn entry point for multi-process serving: the config travels as a JSON file."""
    from ..config import make_config
    from pathlib import Path
    path = os.environ.get(CONFIG_ENV)
    cfg = make_config(json.loads(Path(path).read_text(encoding="utf-8")) if path else None)
    return create_app(config=cfg)


def serve(host: str = "127.0.0.1", port: int = 8000, config: dict | None = None,
          ssl_certfile: str | None = None, ssl_keyfile: str | None = None,
          allow_dev_keys: bool = False, processes: int = 1) -> None:
    try:
        import uvicorn
    except ImportError as e:  # pragma: no cover
        raise ImportError("serving needs `pip install \"agentic-trader[api]\"`") from e
    from ..config import make_config
    cfg = make_config(config)
    opts = serve_options(host, cfg, ssl_certfile, ssl_keyfile, allow_dev_keys)
    opts.update(multiprocess_options(processes, cfg))
    if processes == 1:
        uvicorn.run(create_app(config=cfg), host=host, port=port, **opts)
        return
    # Worker processes are spawned fresh, so the app is built from an import string and
    # the configuration is handed over through a private temp file (keys are not
    # exposed on the command line or in the environment itself). The interrupted-run
    # sweep is done here, once, so a worker starting later cannot fail its siblings' runs.
    from .store import TaskStore
    swept = TaskStore(cfg["agentic"]["task_db"]).mark_interrupted(lease_s=float(cfg["agentic"].get("lease_s", 90.0)))
    if swept:
        log.warning("%d task(s) were in flight when the previous service stopped; marked FAILED", swept)
    cfg = make_config(cfg, agentic={"sweep_interrupted": False})
    fd, path = tempfile.mkstemp(prefix="agentic-trader-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(cfg, f, default=str)
    os.environ[CONFIG_ENV] = path
    try:
        uvicorn.run("agentic_trader.agentic.api:app_factory", factory=True, host=host, port=port, **opts)
    finally:
        os.environ.pop(CONFIG_ENV, None)
        try:
            os.unlink(path)
        except OSError:
            pass
