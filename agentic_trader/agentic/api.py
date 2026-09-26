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
import logging
import os
import threading
from datetime import date
from typing import Any

from ..graph import TradingGraph
from .domain import Capability, ROLE_CAPABILITIES, Role, Task
from .harness import AgentHarness
from .policy import QueuedApprovalGateway

log = logging.getLogger(__name__)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def create_app(harness: "AgentHarness | None" = None, graph: "TradingGraph | None" = None,
               config: "dict | None" = None, api_keys: "dict[str, str] | None" = None):
    try:
        from fastapi import Depends, FastAPI, Header, HTTPException
        from fastapi.responses import PlainTextResponse
        from pydantic import BaseModel, Field
    except ImportError as e:  # pragma: no cover
        raise ImportError("the API needs `pip install \"agentic-trader[api]\"`") from e

    if harness is None:
        graph = graph or TradingGraph(config)
        gateway = QueuedApprovalGateway() if graph.config.get("agentic", {}).get("approval", "queued") != "auto" \
            else None
        harness = AgentHarness(graph, gateway=gateway or QueuedApprovalGateway())
    keys = {k: Role(v) for k, v in (api_keys or harness.config.get("agentic", {}).get("api_keys", {})).items()}
    app = FastAPI(title="agentic-trader", version="0.5.0",
                  description="Policy-gated, evidence-backed trading decisions for equities and FX.")
    app.state.harness = harness
    workers: dict[str, threading.Thread] = {}

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
        return {"status": "ok", "tasks": len(harness.runs) + len(harness.archive), "live": len(harness.runs),
                "archived": len(harness.archive), "persistent": harness.store is not None,
                "tools": len(harness.registry)}

    @app.get("/metrics", response_class=PlainTextResponse)
    def metrics() -> str:
        out = []
        for run in list(harness.runs.values()):
            out.append(run.tracer.metrics.render())
        return "".join(out) or "# no tasks yet\n"

    @app.get("/tools")
    def tools(role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        return harness.registry.catalogue()

    @app.post("/tasks", status_code=202)
    def create_task(body: TaskIn, role: Role = Depends(role_of)) -> dict[str, Any]:
        require(role, Capability.RUN_ANALYTICS)
        task = Task(body.symbol, body.as_of, role, body.current_weight, body.question)
        run = harness.submit(task)
        t = threading.Thread(target=harness.resume, args=(run,), daemon=True, name=f"task-{task.id}")
        workers[task.id] = t
        t.start()
        return {"task_id": task.id, "state": run.state.value}

    @app.get("/tasks")
    def list_tasks(role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        live = [{"task_id": r.id, "symbol": r.task.symbol, "as_of": r.task.as_of.isoformat(),
                 "role": r.task.role.value, "state": r.state.value, "live": True}
                for r in list(harness.runs.values())]
        archived = [{"task_id": r["task_id"], "symbol": r["symbol"], "as_of": r["as_of"], "role": r["role"],
                     "state": r["state"], "live": False}
                    for tid, r in harness.archive.items() if tid not in harness.runs]
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
            if task_id in harness.archive:
                raise HTTPException(409, "archived task from a previous process; nothing to cancel")
            raise HTTPException(404, f"unknown task {task_id}")
        return {"task_id": task_id, "state": harness.cancel(task_id).state.value}

    @app.get("/approvals")
    def approvals(role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        require(role, Capability.APPROVE_TRADES)
        return [{"id": a.id, "task_id": a.task_id, "tool": a.request.tool, "arguments": a.request.arguments,
                 "reason": a.reason, "created_at": a.created_at.isoformat()} for a in harness.pending_approvals()]

    @app.post("/approvals/{approval_id}")
    def decide(approval_id: str, body: ApprovalIn, role: Role = Depends(role_of)) -> dict[str, Any]:
        require(role, Capability.APPROVE_TRADES)
        try:
            run = harness.decide_approval(approval_id, body.approve, role.value, body.note)
        except KeyError:
            raise HTTPException(404, f"unknown approval {approval_id}")
        except ValueError as e:
            raise HTTPException(409, str(e))
        return {"approval_id": approval_id, "approved": body.approve, "task_id": run.id,
                "state": run.state.value}

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


def serve(host: str = "127.0.0.1", port: int = 8000, config: dict | None = None,
          ssl_certfile: str | None = None, ssl_keyfile: str | None = None,
          allow_dev_keys: bool = False) -> None:
    try:
        import uvicorn
    except ImportError as e:  # pragma: no cover
        raise ImportError("serving needs `pip install \"agentic-trader[api]\"`") from e
    from ..config import make_config
    cfg = make_config(config)
    opts = serve_options(host, cfg, ssl_certfile, ssl_keyfile, allow_dev_keys)
    uvicorn.run(create_app(config=cfg), host=host, port=port, **opts)
