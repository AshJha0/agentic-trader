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
import threading
from datetime import date
from typing import Any

from ..graph import TradingGraph
from .domain import Capability, ROLE_CAPABILITIES, Role, Task
from .harness import AgentHarness
from .policy import QueuedApprovalGateway


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
    app = FastAPI(title="agentic-trader", version="0.4.0",
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

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "tasks": len(harness.runs), "tools": len(harness.registry)}

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

    @app.get("/tasks/{task_id}")
    def get_task(task_id: str, role: Role = Depends(role_of)) -> dict[str, Any]:
        return get_run(task_id).to_dict(include_report=False)

    @app.get("/tasks/{task_id}/report")
    def get_report(task_id: str, format: str = "json", role: Role = Depends(role_of)):
        run = get_run(task_id)
        if run.report is None:
            raise HTTPException(409, f"task is {run.state.value}; no report yet")
        if format == "markdown":
            return PlainTextResponse(run.report.to_markdown())
        return run.report.to_dict()

    @app.get("/tasks/{task_id}/trace")
    def get_trace(task_id: str, role: Role = Depends(role_of)) -> dict[str, Any]:
        run = get_run(task_id)
        return {"summary": run.tracer.summary(), "spans": run.tracer.to_list()}

    @app.get("/tasks/{task_id}/evidence")
    def get_evidence(task_id: str, role: Role = Depends(role_of)) -> list[dict[str, Any]]:
        return get_run(task_id).evidence.summary_rows()

    @app.post("/tasks/{task_id}/cancel")
    def cancel_task(task_id: str, role: Role = Depends(role_of)) -> dict[str, Any]:
        require(role, Capability.RUN_ANALYTICS)
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


def serve(host: str = "127.0.0.1", port: int = 8000, config: dict | None = None) -> None:
    try:
        import uvicorn
    except ImportError as e:  # pragma: no cover
        raise ImportError("serving needs `pip install \"agentic-trader[api]\"`") from e
    uvicorn.run(create_app(config=config), host=host, port=port)
