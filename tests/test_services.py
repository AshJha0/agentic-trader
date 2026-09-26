"""The service surfaces: the HTTP API (FastAPI test client), the MCP stdio server
(a real subprocess round trip) and the new CLI commands. All offline."""
import json
import sys
import time
from datetime import date

import pytest

from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic import AgentHarness, EvidenceStore, PolicyEngine, QueuedApprovalGateway, Role, Task
from agentic_trader.agentic.tools import ToolExecutor
from agentic_trader.cli import main
from agentic_trader.memory import DecisionMemory

CFG = make_config(memory_path=None)
QUIET = dict(memory=DecisionMemory(None), on_event=lambda *_: None)
fastapi = pytest.importorskip("fastapi")
mcp = pytest.importorskip("mcp")


# ------------------------------------------------------------------- API
@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from agentic_trader.agentic.api import create_app
    h = AgentHarness(TradingGraph(CFG, **QUIET), gateway=QueuedApprovalGateway())
    return TestClient(create_app(harness=h)), h


def _wait(client, tid, key="dev-viewer-key", timeout=30):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = client.get(f"/tasks/{tid}", headers={"X-API-Key": key}).json()
        if st["state"] in ("COMPLETED", "FAILED", "CANCELLED", "AWAITING_APPROVAL"):
            return st
        time.sleep(0.02)
    raise TimeoutError


def test_api_auth_roles_and_task_lifecycle(client):
    c, h = client
    assert c.get("/health").json()["status"] == "ok"
    assert c.get("/tools").status_code == 401
    assert c.get("/tools", headers={"X-API-Key": "nope"}).status_code == 401
    assert len(c.get("/tools", headers={"X-API-Key": "dev-viewer-key"}).json()) == 16
    assert c.post("/tasks", json={"symbol": "AAPL", "as_of": "2024-03-01"},
                  headers={"X-API-Key": "dev-viewer-key"}).status_code == 403
    r = c.post("/tasks", json={"symbol": "AAPL", "as_of": "2024-03-01", "current_weight": 0.1},
               headers={"X-API-Key": "dev-trader-key"})
    assert r.status_code == 202
    tid = r.json()["task_id"]
    st = _wait(c, tid)
    assert st["state"] == "COMPLETED" and st["decision"]["symbol"] == "AAPL" and st["role"] == "trader"
    rep = c.get(f"/tasks/{tid}/report", headers={"X-API-Key": "dev-viewer-key"}).json()
    assert rep["warnings"] == [] and rep["sections"]["decision"]["action"] in ("BUY", "SELL", "HOLD")
    md = c.get(f"/tasks/{tid}/report?format=markdown", headers={"X-API-Key": "dev-viewer-key"}).text
    assert md.startswith("# AAPL decision")
    tr = c.get(f"/tasks/{tid}/trace", headers={"X-API-Key": "dev-viewer-key"}).json()
    assert tr["summary"]["spans"] > 5 and tr["spans"][0]["name"] == "plan"
    ev = c.get(f"/tasks/{tid}/evidence", headers={"X-API-Key": "dev-viewer-key"}).json()
    assert len(ev) >= 15 and {"id", "type", "digest"} <= set(ev[0])
    assert c.get("/tasks/TASK-nope", headers={"X-API-Key": "dev-viewer-key"}).status_code == 404
    assert "task_transitions_total" in c.get("/metrics").text


def test_api_validation_and_failure_paths(client):
    c, _ = client
    assert c.post("/tasks", json={"symbol": "AAPL"}, headers={"X-API-Key": "dev-trader-key"}).status_code == 422
    r = c.post("/tasks", json={"symbol": "EUR/XYZ", "as_of": "2024-03-01"}, headers={"X-API-Key": "dev-trader-key"})
    st = _wait(c, r.json()["task_id"])
    assert st["state"] == "FAILED" and "not a recognised currency pair" in st["errors"][0]
    assert c.get(f"/tasks/{r.json()['task_id']}/report", headers={"X-API-Key": "dev-viewer-key"}).status_code == 409


def test_api_approval_flow(client):
    c, h = client
    run = h.submit(Task("AAPL", date(2024, 3, 1), Role.TRADER))
    ex = h._executor(run)
    res = ex.call("execution.submit_order", symbol="AAPL", side="buy", quantity=10)
    assert not res.ok and "awaiting approval" in res.error
    assert c.get("/approvals", headers={"X-API-Key": "dev-trader-key"}).status_code == 403
    pend = c.get("/approvals", headers={"X-API-Key": "dev-risk-key"}).json()
    assert len(pend) == 1 and pend[0]["tool"] == "execution.submit_order"
    assert c.post(f"/approvals/{pend[0]['id']}", json={"approve": True},
                  headers={"X-API-Key": "dev-risk-key"}).status_code == 200
    assert c.post(f"/approvals/{pend[0]['id']}", json={"approve": True},
                  headers={"X-API-Key": "dev-risk-key"}).status_code == 409         # already decided
    assert c.post("/approvals/APPROVAL-nope", json={"approve": False},
                  headers={"X-API-Key": "dev-risk-key"}).status_code == 404
    assert ex.call("execution.submit_order", symbol="AAPL", side="buy", quantity=10).ok
    assert h.tools.orders[0]["status"] == "ticketed"


def test_api_cancel(client):
    c, h = client
    r = c.post("/tasks", json={"symbol": "EURUSD", "as_of": "2024-03-01"}, headers={"X-API-Key": "dev-analyst-key"})
    tid = r.json()["task_id"]
    st = _wait(c, tid)
    assert st["state"] == "COMPLETED"
    assert c.post(f"/tasks/{tid}/cancel", headers={"X-API-Key": "dev-analyst-key"}).json()["state"] == "COMPLETED"


# ------------------------------------------------------------------- MCP
def test_mcp_stdio_round_trip_and_remote_registry():
    from agentic_trader.agentic.mcp_server import call, discover, registry_from_stdio
    tools = discover()
    names = {t["name"] for t in tools}
    assert len(tools) == 16 and "market_data__news" in names and "execution__submit_order" in names
    order = next(t for t in tools if t["name"] == "execution__submit_order")
    assert order["read_only"] is False and order["meta"]["risk"] == "high"
    docs = call("knowledge__list_documents", {})
    assert "risk_limits_policy" in docs
    news = call("market_data__news", {"symbol": "AAPL", "as_of": date(2024, 3, 1), "lookback_days": 7})
    assert isinstance(news, list) and all(n["published"] <= "2024-03-01" for n in news)
    with pytest.raises(RuntimeError):
        call("market_data__news", {"symbol": "EUR/XYZ", "as_of": "2024-03-01", "lookback_days": 7})

    reg = registry_from_stdio()
    assert len(reg) == 16 and "quant.technical" in reg
    ex = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.TRADER)
    r = ex.call("quant.technical", symbol="AAPL", as_of="2024-03-01")
    assert r.ok and "rsi14" in r.payload and len(ex.evidence) == 1
    assert ex.evidence.resolve(list(ex.evidence)[0].id)
    # Policy applies to remote tools too: the order needs approval (auto-granted here) and
    # the approval itself becomes evidence before the remote call runs.
    order = ex.call("execution.submit_order", symbol="AAPL", side="buy", quantity=1)
    assert order.ok and order.payload["status"] == "ticketed"
    assert any(e.type.value == "APPROVAL" for e in ex.evidence)
    viewer = ToolExecutor(reg, PolicyEngine({"max_position": 1.0}), EvidenceStore(), Role.VIEWER)
    assert "lacks propose_trades" in viewer.call("execution.submit_order", symbol="AAPL", side="buy", quantity=1).error


# ------------------------------------------------------------------- CLI
def test_cli_task_tools_and_research_commands(tmp_path, capsys):
    assert main(["task", "EURUSD", "--date", "2024-03-01", "--position", "0.2", "--no-memory"]) == 0
    out = capsys.readouterr().out
    assert "state: COMPLETED" in out and "## Evidence" in out and "## Critic" in out
    assert main(["task", "AAPL", "--date", "2024-03-01", "--role", "viewer", "--no-memory"]) == 1
    assert "denied by policy" in capsys.readouterr().out
    assert main(["task", "AAPL", "--date", "2024-03-01", "--json", "--no-memory"]) == 0
    body = capsys.readouterr().out
    rec = json.loads(body[body.index("{"):body.rindex("}") + 1])
    assert rec["state"] == "COMPLETED" and rec["report"]["warnings"] == []

    assert main(["tools"]) == 0
    assert "16 tools on 5 servers" in capsys.readouterr().out
    assert main(["tools", "--json"]) == 0
    cat = capsys.readouterr().out
    assert json.loads(cat[cat.index("["):])[0]["name"] == "market_data.history"

    assert main(["alpha", "USDJPY", "--start", "2021-01-04", "--end", "2024-03-28", "--out", str(tmp_path / "s.csv")]) == 0
    assert "IC by horizon" in capsys.readouterr().out and (tmp_path / "s.csv").exists()
    assert main(["alpha", "AAPL", "--start", "2024-01-01", "--end", "2024-03-01"]) == 2  # too short

    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.6", "--current", "0.1"]) == 0
    assert "implementation shortfall" in capsys.readouterr().out
    assert main(["execute", "EURUSD", "--date", "2024-03-01", "--target", "-0.5", "--algo", "ac"]) == 0
    assert "TWAP" not in capsys.readouterr().out.split("via")[1][:4]
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.3", "--current", "0.3"]) == 0
    assert "nothing to trade" in capsys.readouterr().out

    assert main(["portfolio", "AAPL,EURUSD", "--start", "2024-01-02", "--end", "2024-02-29", "--every", "10",
                 "--weighting", "inverse_vol"]) == 0
    assert "latest capital allocation" in capsys.readouterr().out

    import numpy as np
    import pandas as pd
    path = tmp_path / "r.csv"
    pd.DataFrame({"r": np.random.default_rng(0).normal(0.0004, 0.01, 600)},
                 index=pd.bdate_range("2021-01-01", periods=600)).to_csv(path)
    assert main(["stats", str(path), "--trials", "16"]) == 0
    assert "deflated_sharpe_prob" in capsys.readouterr().out
    assert main(["stats", str(path), "--column", "nope"]) == 2


def test_cli_mcp_entry_point_is_wired():
    from agentic_trader.cli import build_parser
    args = build_parser().parse_args(["mcp", "--data", "synthetic"])
    assert args.func.__name__ == "cmd_mcp"
    args = build_parser().parse_args(["serve", "--port", "9"])
    assert args.func.__name__ == "cmd_serve" and args.approval == "queued"
    assert sys.executable  # the MCP server is launched with the running interpreter
