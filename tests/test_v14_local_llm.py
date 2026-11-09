"""LocalLLM (plan 2.1) against a fake Ollama server on 127.0.0.1, and the study driver (2.2).

No model is involved: the server below answers with canned ``/api/chat`` bodies."""
from __future__ import annotations

import importlib.util
import json
import math
import sys
import threading
import urllib.error
import urllib.request
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from agentic_trader import contracts
from agentic_trader.config import make_config
from agentic_trader.graph import TradingGraph
from agentic_trader.llm import BudgetedLLM, get_llm, llm_usage
from agentic_trader.local_llm import LocalLLM, reachable, served_matches

MODEL = "llama3.1:8b"


class FakeOllama(BaseHTTPRequestHandler):
    replies: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    delay_s = 0.0

    def do_GET(self) -> None:
        self._send({"models": [{"name": MODEL}]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).requests.append({"path": self.path, "body": body})
        time.sleep(type(self).delay_s)
        reply = type(self).replies.pop(0) if type(self).replies else _reply('{"signal": 0.1}')
        self._send(reply)

    def _send(self, obj: dict[str, Any]) -> None:
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:
        pass


def _reply(content: str, model: str = MODEL, done_reason: str = "stop") -> dict[str, Any]:
    return {"model": model, "message": {"role": "assistant", "content": content}, "done": True,
            "done_reason": done_reason, "prompt_eval_count": 120, "eval_count": 30}


@pytest.fixture
def server() -> Iterator[str]:
    FakeOllama.replies, FakeOllama.requests, FakeOllama.delay_s = [], [], 0.0
    httpd = HTTPServer(("127.0.0.1", 0), FakeOllama)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _llm(url: str, **kw: Any) -> LocalLLM:
    return LocalLLM(make_config(llm_provider="local", local_llm_model=MODEL, local_llm_url=url, **kw))


def test_request_shape_puts_the_schema_in_format(server: str) -> None:
    llm = _llm(server, local_llm_seed=3, max_tokens=512)
    assert llm.complete_json("sys", "prompt", deep=True, schema=contracts.ANALYST) == '{"signal": 0.1}'
    req = FakeOllama.requests[-1]
    assert req["path"] == "/api/chat"
    body = req["body"]
    assert body["model"] == MODEL and body["stream"] is False
    assert body["format"] == contracts.ANALYST
    assert body["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "prompt"}]
    assert body["options"] == {"temperature": 0.0, "num_predict": 512, "seed": 3}
    llm.complete("sys", "plain", deep=False)
    assert "format" not in FakeOllama.requests[-1]["body"]


def test_evidence_and_usage(server: str) -> None:
    llm = _llm(server)
    FakeOllama.replies = [_reply("  hello  ", model=MODEL, done_reason="length")]
    assert llm.complete("s", "p", deep=True) == "hello"
    assert llm.last_call == {"model_configured": MODEL, "model_served": MODEL, "stop_reason": "length",
                             "refusal_category": None, "fallbacks": [], "model_drift": False,
                             "llm_host": "127.0.0.1", "remote_llm_allowed": False}
    s = llm_usage(llm)
    assert s["calls"] == 1 and s["errors"] == 0 and s["cost_usd"] == 0.0 and s["unpriced_models"] == []
    assert s["by_model"][MODEL]["input_tokens"] == 120 and s["by_model"][MODEL]["output_tokens"] == 30
    assert s["by_model"][MODEL]["cost_usd"] == 0.0
    assert llm.estimate_cost(True, 10_000) == 0.0


def test_model_drift_rejected_when_strict(server: str) -> None:
    llm = _llm(server)
    FakeOllama.replies = [_reply("x", model="qwen2.5:7b")]
    assert llm.complete("s", "p", deep=True) is None
    assert llm.last_call["model_drift"] is True and llm.usage.model_drift == 1
    loose = _llm(server, llm_strict_model=False)
    FakeOllama.replies = [_reply("x", model="qwen2.5:7b")]
    assert loose.complete("s", "p", deep=True) == "x"


def test_untagged_model_matches_latest() -> None:
    assert served_matches("llama3.1", "llama3.1:latest")
    assert not served_matches("llama3.1:8b", "llama3.1:70b")
    assert not served_matches(MODEL, None)


def test_timeout_returns_none_and_counts(server: str) -> None:
    llm = _llm(server, local_llm_timeout_s=0.2)
    FakeOllama.delay_s = 1.0
    assert llm.complete("s", "p", deep=True) is None
    assert llm.last_call is None
    assert llm.usage.timeouts == 1 and llm.usage.errors == 1 and llm.usage.calls == 0


def test_refused_connection_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: Any, **kw: Any) -> Any:
        raise urllib.error.URLError(ConnectionRefusedError(10061, "refused"))
    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    llm = _llm("http://127.0.0.1:9")
    assert llm.complete("s", "p", deep=True) is None
    assert llm.usage.errors == 1 and llm.usage.timeouts == 0
    assert not reachable("http://127.0.0.1:9")


def test_reachable_and_empty_reply(server: str) -> None:
    assert reachable(server)
    llm = _llm(server)
    FakeOllama.replies = [_reply("   ")]
    assert llm.complete("s", "p", deep=True) is None and llm.usage.empty == 1


def test_get_llm_local_applies_the_call_cap(server: str) -> None:
    cfg = make_config(llm_provider="local", local_llm_model=MODEL, local_llm_url=server,
                      max_llm_calls=2, max_llm_cost_usd=1.0)
    llm = get_llm(cfg)
    assert isinstance(llm, BudgetedLLM) and isinstance(llm.inner, LocalLLM)
    assert llm.complete("s", "p", deep=True) is not None
    assert llm.complete_json("s", "p", deep=True, schema=contracts.RISK_VIEW) is not None
    assert llm.complete("s", "p", deep=True) is None          # third call refused by the cap
    assert llm.refused == 1 and len(FakeOllama.requests) == 2 and llm.last_call is None
    assert llm.spent_usd == 0.0


def test_local_needs_a_model_name() -> None:
    with pytest.raises(ValueError, match="local_llm_model"):
        get_llm(make_config(llm_provider="local"))


def test_one_decision_through_the_desk(server: str) -> None:
    """Smoke test of 2.1 on the fake server: a full decision, anonymised, evidence per call."""
    cfg = make_config(llm_provider="local", local_llm_model=MODEL, local_llm_url=server,
                      memory_path=None, llm_anonymize=True)
    state, dec = TradingGraph(cfg, on_event=lambda a, b: None).propagate("AAPL", "2019-03-01")
    assert len(FakeOllama.requests) == 14 and len(state.llm_calls) == 14
    assert all(c["model_served"] == MODEL for c in state.llm_calls)
    assert not any("AAPL" in json.dumps(r["body"]["messages"]) for r in FakeOllama.requests)
    assert math.isfinite(dec.target_weight)


# ---- study driver ---------------------------------------------------------------------------

def _study() -> Any:
    path = Path(__file__).resolve().parents[1] / "scripts" / "llm_study.py"
    spec = importlib.util.spec_from_file_location("llm_study", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_study"] = mod        # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    return mod


def test_dry_run_table_is_deterministic() -> None:
    study = _study()
    cfg = make_config(study.STUDY_BASE)
    a = study.dry_run_table(["AAPL", "EURUSD"], 3, 2, cfg)
    b = study.dry_run_table(["AAPL", "EURUSD"], 3, 2, cfg)
    assert a == b
    per = {r["cell"]: r["calls_per_decision"] for r in a}
    assert per == {"rules": 0, "local_all": 14, "local_text": 4, "local_pm": 1, "local_analysts": 4, "no_debate": 9,
                   "debate_1": 12, "neutral_risk": 12}
    for r in a:
        assert r["decisions"] == 12 and r["calls"] == r["calls_per_decision"] * 12
        assert (r["est_usd"] > 0) == (r["calls"] > 0) and r["ceiling_usd"] >= r["est_usd"]
    assert "| local_all |" in study.render(a, cfg)


def test_cells_are_described_and_live_refuses_without_server(capsys: pytest.CaptureFixture[str]) -> None:
    study = _study()
    names = [c.name for c in study.CELLS]
    assert len(names) == len(set(names)) == 8
    assert all(c["trial_name"].startswith("P2 ") for c in (cell.describe() for cell in study.CELLS))
    assert study.design_dates(40)[0].isoformat() == "2016-01-01" and len(study.design_dates(40)) == 40
    assert study.main(["--live", "--model", MODEL, "--url", "http://127.0.0.1:9"]) == 2
    assert "refusing --live" in capsys.readouterr().err
