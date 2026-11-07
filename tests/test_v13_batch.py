"""BatchLLM (plan item 1.5): stage-wise batching across an offline 3-name x 5-date walk-forward."""
from types import SimpleNamespace

import pytest

from agentic_trader import make_config, run_agent_backtest
from agentic_trader.batch import (AnthropicBatchBackend, BatchLLM, FakeBatchBackend, Outcome,
                                  custom_id)

CFG = make_config(memory_path=None)
NAMES = ("AAPL", "MSFT", "EURUSD")
START, END, EVERY = "2024-01-01", "2024-02-05", 5   # 25 bars -> 5 decisions per name


class StubLLM:
    """Canned replies per role, so every agent's LLM branch runs (as in test_pipeline)."""

    def complete(self, system, prompt, *, deep):
        if "Researcher" in system:
            return "Evidence-based argument."
        if "Facilitator" in system:
            return '{"winner": "bull", "score": 0.6, "conviction": 0.7, "summary": "Bull wins."}'
        if "Trader." in system:
            return ('{"action": "BUY", "target_weight": 0.5, "confidence": 0.7, "stop_loss": null, '
                    '"take_profit": null, "horizon_days": 5, "rationale": "r"}')
        if "Risk Analyst" in system:
            return '{"recommended_weight": 0.4, "argument": "fine"}'
        if "Portfolio Manager" in system:
            return '{"target_weight": 0.3, "confidence": 0.6, "rationale": "pm"}'
        return '{"signal": 0.5, "confidence": 0.8, "summary": "LLM view", "key_points": ["a"]}'


STUB = StubLLM()


def respond(params):
    return STUB.complete(params["system"], params["prompt"], deep=params["deep"])


def walk_forward(llm):
    return [d for s in NAMES
            for d in run_agent_backtest(s, START, END, CFG, rebalance_every=EVERY, llm=llm).decisions]


def key(decisions):
    return [(d.symbol, d.as_of, d.action, d.target_weight, d.source) for d in decisions]


@pytest.fixture(scope="module")
def direct():
    return walk_forward(STUB)


MAX_PASSES = 60   # the held weight chains the dates: passes ~ pipeline stages x decision dates


@pytest.fixture(scope="module")
def batched(tmp_path_factory):
    """One batched walk-forward (results returned in reversed order) shared by the tests below."""
    store = tmp_path_factory.mktemp("batch") / "store.jsonl"
    backend = FakeBatchBackend(respond, shuffle=True)
    llm = BatchLLM(None, backend, store)
    passes = []
    final = llm.run_until_complete(lambda: passes.append(1) or walk_forward(llm), max_passes=MAX_PASSES)
    return SimpleNamespace(llm=llm, backend=backend, store=store, passes=len(passes), final=final)


def test_batched_walk_forward_matches_direct(batched, direct):
    assert 1 < batched.passes < MAX_PASSES
    assert len(batched.backend.batches) == batched.passes - 1
    assert len(batched.final) == 15 and all(d.source == "llm" for d in batched.final)
    assert key(batched.final) == key(direct)   # also proves shuffled result order is harmless
    assert batched.llm.summary["failed"] == 0


def test_resume_from_store_submits_nothing(batched, direct):
    backend = FakeBatchBackend(respond)
    again = BatchLLM(None, backend, batched.store)
    assert key(again.run_until_complete(lambda: walk_forward(again))) == key(direct)
    assert backend.batches == []


def test_expired_then_succeeded_resubmits(tmp_path):
    seen: dict[str, int] = {}

    def flaky(params):
        seen[params["prompt"]] = seen.get(params["prompt"], 0) + 1
        return Outcome("expired") if seen[params["prompt"]] == 1 else "ok"

    backend = FakeBatchBackend(flaky)
    llm = BatchLLM(None, backend, tmp_path / "s.jsonl")
    out = llm.run_until_complete(lambda: llm.complete("sys", "p", deep=False))
    assert out == "ok" and len(backend.batches) == 2
    assert llm.summary == {"succeeded": 1, "resubmitted": 1, "failed": 0, "from_store": 0}


def test_retries_spent_and_permanent_error_fall_back(tmp_path):
    backend = FakeBatchBackend(lambda p: Outcome("errored", retryable=p["prompt"] == "busy"))
    llm = BatchLLM(None, backend, tmp_path / "s.jsonl", max_resubmits=2)
    out = llm.run_until_complete(lambda: (llm.complete("s", "busy", deep=False),
                                          llm.complete("s", "bad", deep=True)))
    assert out == (None, None)
    assert [len(b) for b in backend.batches] == [2, 1, 1]   # "bad" final at once, "busy" twice more
    assert llm.summary["failed"] == 2 and llm.summary["resubmitted"] == 2


def test_custom_id_stable_and_short():
    a = custom_id("sys", "p", deep=False, schema={"b": 1, "a": 2})
    assert a == custom_id("sys", "p", deep=False, schema={"a": 2, "b": 1})
    assert len(a) <= 64
    assert a != custom_id("sys", "p", deep=True, schema={"a": 2, "b": 1})
    assert a != custom_id("sys", "p", deep=False, schema=None)


def test_store_is_idempotent(tmp_path):
    path = tmp_path / "s.jsonl"
    llm = BatchLLM(None, FakeBatchBackend(lambda p: "x"), path)
    llm.run_until_complete(lambda: llm.complete("s", "p", deep=False))
    llm._record(custom_id("s", "p", deep=False, schema=None), "other")
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


class FakeBatches:
    def __init__(self, results):
        self._results, self.created, self.polls = results, None, 0

    def create(self, requests):
        self.created = requests
        return SimpleNamespace(id="b1")

    def retrieve(self, batch_id):
        self.polls += 1
        return SimpleNamespace(processing_status="ended" if self.polls >= 3 else "in_progress")

    def results(self, batch_id):
        return iter(self._results)


def test_anthropic_backend_against_fake_client():
    def item(cid, rtype, **kw):
        return SimpleNamespace(custom_id=cid, result=SimpleNamespace(type=rtype, **kw))

    def err(t):
        return SimpleNamespace(error=SimpleNamespace(type=t))

    results = [item("d", "expired"), item("a", "succeeded", message="MSG"),
               item("b", "errored", error=err("overloaded_error")),
               item("c", "errored", error=err("invalid_request_error"))]
    batches = FakeBatches(results)
    client = SimpleNamespace(messages=SimpleNamespace(batches=batches))
    sleeps = []
    backend = AnthropicBatchBackend(client, read=lambda m, model: f"{m}/{model}", sleep=sleeps.append)
    params = {"model": "m1", "max_tokens": 10, "betas": ["x"], "extra_body": {"fallbacks": "default"}}
    out = backend.run({cid: dict(params) for cid in "abcd"})
    assert out["a"] == Outcome("succeeded", "MSG/m1")
    assert out["b"] == Outcome("errored", retryable=True)
    assert out["c"] == Outcome("errored", retryable=False)
    assert out["d"] == Outcome("expired")
    assert len(sleeps) == 2
    assert all(set(r["params"]) == {"model", "max_tokens"} for r in batches.created)
