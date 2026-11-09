"""v0.13 foundation (plan P1 items 1.1-1.4, 1.6-1.8): model tables, structured outputs,
prompt caching, server-side refusal fallback evidence, token counting in budget admission,
and served-model drift. Everything runs offline against a stand-in ``anthropic`` module."""
from __future__ import annotations

import os
import sys
import threading
import time
import types
from types import SimpleNamespace

import pytest

from agentic_trader import contracts
from agentic_trader.agents.base import Agent
from agentic_trader.config import DEFAULT_CONFIG, make_config
from agentic_trader.llm import (
    MODEL_CAPABILITIES, PRICES_PER_MTOK, AnthropicLLM, budget_llm, estimate_tokens,
    forced_tool_choice_supported, model_matches, price_for, refusal_fallback_supported,
    request_shape,
)


class _StatusError(Exception):
    def __init__(self, status_code=500, message="err", response=None):
        super().__init__(message)
        self.status_code, self.message, self.response = status_code, message, response


class _RateLimit(_StatusError):
    def __init__(self):
        super().__init__(429, "rate limited")


class _ConnError(Exception):
    pass


class _Timeout(_ConnError):
    pass


def install(monkeypatch, reply=None, fail=None, delay=0.0, count=None):
    """Stand-in ``anthropic``. ``reply(kwargs) -> response``; ``fail(kwargs) -> exception or
    None``; ``count`` = input_tokens returned by ``count_tokens`` (raises when None)."""
    sent = {"create": [], "beta": [], "count": []}
    lock = threading.Lock()

    def default_reply(kw):
        return SimpleNamespace(model=kw["model"], stop_reason="end_turn", stop_details=None,
                               usage=SimpleNamespace(input_tokens=100, output_tokens=20,
                                                     cache_read_input_tokens=80,
                                                     cache_creation_input_tokens=10),
                               content=[SimpleNamespace(type="text", text='{"signal": 0.4}')])

    def make(kind):
        def create(**kw):
            with lock:
                sent[kind].append(kw)
            if delay:
                time.sleep(delay)
            exc = fail(kw) if fail else None
            if exc is not None:
                raise exc
            return (reply or default_reply)(kw)
        return create

    def count_tokens(**kw):
        sent["count"].append(kw)
        if count is None:
            raise _StatusError(500, "count down")
        return SimpleNamespace(input_tokens=count)

    class Client:
        def __init__(self, **kw):
            self.messages = SimpleNamespace(create=make("create"), count_tokens=count_tokens)
            self.beta = SimpleNamespace(messages=SimpleNamespace(create=make("beta")))

    fake = types.ModuleType("anthropic")
    fake.Anthropic = Client
    fake.APIStatusError, fake.RateLimitError = _StatusError, _RateLimit
    fake.APIConnectionError, fake.APITimeoutError = _ConnError, _Timeout
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return sent


def cfg(**kw):
    return make_config(llm_provider="anthropic", llm_retry_backoff_s=0.0, **kw)


# ---- 1.1 model defaults and tables ---------------------------------------------------
def test_defaults_are_the_current_generation():
    assert DEFAULT_CONFIG["quick_think_llm"] == "claude-haiku-5-5"
    assert DEFAULT_CONFIG["deep_think_llm"] == "claude-sonnet-5-5"
    assert DEFAULT_CONFIG["deep_effort"] == "medium"


@pytest.mark.parametrize("model,price", [
    ("claude-haiku-5-5", (0.10, 0.50)), ("claude-sonnet-5-5", (2.0, 10.0)),
    ("claude-opus-5-5", (4.0, 20.0)),
])
def test_price_table_pins_5_5_family(model, price):
    assert PRICES_PER_MTOK[model] == price and price_for(model + "-20261101") == price


@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"])
def test_5_5_models_take_adaptive_thinking_and_every_effort(model):
    shape = request_shape(model, "medium", 1000)
    assert shape["thinking"] == {"type": "adaptive"} and shape["output_config"] == {"effort": "medium"}


def test_forced_tool_choice_and_fallback_capabilities():
    for m in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-1"):
        assert not forced_tool_choice_supported(m) and refusal_fallback_supported(m)
    assert forced_tool_choice_supported("claude-haiku-5-5")
    assert not refusal_fallback_supported("claude-haiku-5-5")     # Haiku 5.5 has no server-side fallback
    assert not refusal_fallback_supported("claude-sonnet-5")


# ---- 1.6 drift: configured ids resolve in both tables ----------------------------------
@pytest.mark.parametrize("key", ["deep_think_llm", "quick_think_llm"])
def test_default_ids_resolve_in_both_tables(key):
    model = DEFAULT_CONFIG[key]
    assert price_for(model) is not None and model in MODEL_CAPABILITIES
    assert price_for("claude-opus-5-5") is not None and "claude-opus-5-5" in MODEL_CAPABILITIES


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs a key (models.retrieve is free)")
def test_default_ids_exist_on_the_api():  # pragma: no cover - runs only with a key
    import anthropic
    client = anthropic.Anthropic()
    for key in ("deep_think_llm", "quick_think_llm"):
        assert client.models.retrieve(DEFAULT_CONFIG[key]).id == DEFAULT_CONFIG[key]


# ---- 1.2 structured outputs ---------------------------------------------------------
def test_complete_json_sends_output_config_format_alongside_effort(monkeypatch):
    sent = install(monkeypatch)
    llm = AnthropicLLM(cfg(use_refusal_fallback=False))
    assert llm.complete_json("sys", "p", deep=False, schema=contracts.ANALYST) == '{"signal": 0.4}'
    oc = sent["create"][0]["output_config"]
    assert oc["effort"] == "low" and oc["format"] == {"type": "json_schema", "schema": contracts.api_schema(contracts.ANALYST)}
    assert "tool_choice" not in sent["create"][0]          # never forced (400 on 5.5 models)


@pytest.mark.parametrize("schema", list(contracts.ALL.values()))
def test_schemas_follow_the_api_rules(schema):
    assert schema["type"] == "object" and schema["additionalProperties"] is False
    assert set(schema["required"]) <= set(schema["properties"])


class _Probe(Agent):
    name, role = "probe", "Probe"


class _SchemaLLM:
    """Records which path the agent took and replies with a fixture."""
    def __init__(self, text):
        self.text, self.schemas = text, []

    def complete(self, system, prompt, *, deep):
        self.schemas.append(None)
        return self.text

    def complete_json(self, system, prompt, *, deep, schema):
        self.schemas.append(schema)
        return self.text


def test_ask_json_uses_structured_outputs_and_keeps_the_contract_gate():
    llm = _SchemaLLM('{"signal": "high", "confidence": 0.5, "summary": "s"}')
    a = _Probe(llm, {})
    got = a.ask_json("p", ("signal", "confidence", "summary"), numeric=("signal", "confidence"),
                     schema=contracts.ANALYST)
    assert llm.schemas == [contracts.ANALYST] and got is None   # schema-valid is not enough: gate 2 rejects


def test_ask_json_without_complete_json_falls_back_to_plain_completion():
    class Plain:
        def complete(self, system, prompt, *, deep):
            return '{"signal": 0.1, "confidence": 0.5, "summary": "s"}'
    got = _Probe(Plain(), {}).ask_json("p", ("signal",), schema=contracts.ANALYST)
    assert got == {"signal": 0.1, "confidence": 0.5, "summary": "s"}


FIXTURES = {   # recorded-shape replies, one per contract: each must parse and pass its gate
    "analyst": ('{"signal": 0.3, "confidence": 0.6, "summary": "s", "key_points": ["a"]}',
                ("signal", "confidence", "summary"), ("signal", "confidence")),
    "facilitator": ('{"winner": "bear", "score": -0.2, "conviction": null, "summary": "s"}',
                    ("winner", "score", "summary"), ("score", "conviction")),
    "risk_view": ('{"recommended_weight": 0.1, "argument": "a"}',
                  ("recommended_weight", "argument"), ("recommended_weight",)),
    "portfolio_manager": ('{"target_weight": 0.2, "confidence": 0.5, "rationale": "r"}',
                          ("target_weight", "rationale"), ("target_weight", "confidence")),
    "trader": ('{"action": "BUY", "target_weight": 0.4, "confidence": 0.7, "stop_loss": null, '
               '"take_profit": 120.5, "horizon_days": 5, "rationale": "r"}',
               ("action", "target_weight", "rationale"),
               ("target_weight", "confidence", "stop_loss", "take_profit", "horizon_days")),
}


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_every_contract_fixture_parses_with_zero_failures(name):
    text, required, numeric = FIXTURES[name]
    schema = contracts.ALL[name]
    assert set(required) == set(schema["required"])          # schema and gate agree
    assert set(numeric) <= set(schema["properties"])
    assert _Probe(_SchemaLLM(text), {}).ask_json("p", required, numeric=numeric, schema=schema) is not None


# ---- 1.3 prompt caching -------------------------------------------------------------
def test_system_is_one_cached_block_and_usage_reports_cache_fields(monkeypatch):
    sent = install(monkeypatch)
    llm = AnthropicLLM(cfg(use_refusal_fallback=False))
    llm.complete("FIRM + role", "p", deep=True)
    assert sent["create"][0]["system"] == [{"type": "text", "text": "FIRM + role",
                                            "cache_control": {"type": "ephemeral"}}]
    s = llm.usage.summary()
    assert s["cache_read_tokens"] == 80 and s["cache_write_tokens"] == 10
    assert s["by_model"]["claude-sonnet-5-5"]["cache_read_tokens"] == 80


# ---- 1.4 server-side refusal fallback -----------------------------------------------
def test_fallback_default_on_supported_models_and_evidence_recorded(monkeypatch):
    def reply(kw):
        return SimpleNamespace(
            model="claude-opus-5-5", stop_reason="end_turn", stop_details=None, usage=None,
            content=[SimpleNamespace(type="fallback", from_=SimpleNamespace(model="claude-sonnet-5-5"),
                                     to=SimpleNamespace(model="claude-opus-5-5")),
                     SimpleNamespace(type="text", text="ok")])
    sent = install(monkeypatch, reply=reply)
    llm = AnthropicLLM(cfg())
    assert llm.complete("s", "p", deep=True) == "ok"            # a recorded fallback is not drift
    kw = sent["beta"][0]
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["extra_body"] == {"fallbacks": "default"}
    ev = llm.last_call
    assert ev["fallbacks"] == [{"from": "claude-sonnet-5-5", "to": "claude-opus-5-5"}] and not ev["model_drift"]
    assert llm.usage.fallbacks == 1


def test_no_fallback_parameter_on_haiku(monkeypatch):
    sent = install(monkeypatch)
    AnthropicLLM(cfg()).complete("s", "p", deep=False)
    assert sent["create"] and not sent["beta"]


def test_refusal_category_is_evidence(monkeypatch):
    def reply(kw):
        return SimpleNamespace(model=kw["model"], stop_reason="refusal", usage=None, content=[],
                               stop_details=SimpleNamespace(category="cyber"))
    install(monkeypatch, reply=reply)
    llm = AnthropicLLM(cfg())
    assert llm.complete("s", "p", deep=True) is None
    assert llm.last_call["refusal_category"] == "cyber" and llm.usage.refusals == 1


# ---- 1.8 served-model drift ---------------------------------------------------------
def test_model_matches():
    assert model_matches("claude-haiku-5-5", "claude-haiku-5-5")
    assert model_matches("claude-haiku-5-5", "claude-haiku-5-5-20261101")
    assert not model_matches("claude-haiku-5", "claude-haiku-5-5")
    assert not model_matches("claude-haiku-5-5", None)


@pytest.mark.parametrize("strict,expect", [(True, None), (False, '{"signal": 0.4}')])
def test_drift_is_rejected_when_strict_and_always_counted(monkeypatch, strict, expect):
    def reply(kw):
        return SimpleNamespace(model="claude-haiku-4-5", stop_reason="end_turn", stop_details=None,
                               usage=None, content=[SimpleNamespace(type="text", text='{"signal": 0.4}')])
    install(monkeypatch, reply=reply)
    llm = AnthropicLLM(cfg(llm_strict_model=strict))
    assert llm.complete("s", "p", deep=False) == expect
    assert llm.last_call["model_drift"] and llm.usage.model_drift == 1


def test_served_model_is_stored_per_decision(monkeypatch):
    from agentic_trader.graph import TradingGraph
    from agentic_trader.memory import DecisionMemory
    install(monkeypatch)
    g = TradingGraph(cfg(), memory=DecisionMemory(None), on_event=lambda *_: None)
    state, dec = g.propagate("AAPL", "2024-03-01")
    assert state.llm_calls and all(c["model_served"] in ("claude-haiku-5-5", "claude-sonnet-5-5")
                                   for c in state.llm_calls)
    assert set(dec.models_served) <= {"claude-haiku-5-5", "claude-sonnet-5-5"} and dec.models_served
    assert dec.to_dict()["models_served"] == list(dec.models_served)


def test_budget_refusal_leaves_no_stale_evidence(monkeypatch):
    install(monkeypatch)
    llm = budget_llm(AnthropicLLM(cfg()), cfg(max_llm_calls=1))
    llm.complete("s", "p", deep=True)
    assert llm.last_call is not None
    assert llm.complete("s", "p", deep=True) is None and llm.last_call is None


# ---- 1.7 token counting in budget admission -----------------------------------------
def test_local_estimate_scales_with_text_and_is_conservative():
    short, long = estimate_tokens("a" * 300), estimate_tokens("a" * 30_000)
    assert long > 90 * short / 2 and estimate_tokens("a" * 3000) >= 1000


def test_count_tokens_used_only_with_a_key_and_falls_back(monkeypatch):
    sent = install(monkeypatch, count=1234)
    llm = AnthropicLLM(cfg())
    assert llm.count_input_tokens(True, "s", "p") == estimate_tokens("s", "p") and not sent["count"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    assert llm.count_input_tokens(True, "s", "p") == 1234
    assert sent["count"][0]["model"] == "claude-sonnet-5-5"
    sent = install(monkeypatch, count=None)                  # endpoint down -> estimate
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")
    assert AnthropicLLM(cfg()).count_input_tokens(True, "s", "p") == estimate_tokens("s", "p")


def test_admission_prices_the_real_prompt(monkeypatch):
    install(monkeypatch)
    llm = AnthropicLLM(cfg())
    small = llm.estimate_cost(True, system="s", prompt="p")
    big = llm.estimate_cost(True, system="s", prompt="x" * 300_000)
    assert big > small > 0


@pytest.mark.parametrize("calls_affordable,all_succeed", [(5.5, False), (16.5, True)])
def test_workers_at_the_cap_during_a_retry_storm_never_overspend(monkeypatch, calls_affordable, all_succeed):
    """Eight workers share a dollar cap while every first attempt is rate limited: each retry
    is reserved before it is sent, so booked spend never passes the cap in hard mode. A cap of
    5.5 reservations must refuse some retries (which ones depends on thread timing, so only
    the bound is asserted); a cap of 16.5 affords every call and its one retry, so all succeed."""
    lock, seen = threading.Lock(), {}

    def fail(kw):
        key = kw["messages"][0]["content"]
        with lock:
            seen[key] = seen.get(key, 0) + 1
            return _RateLimit() if seen[key] == 1 else None
    install(monkeypatch, fail=fail, delay=0.01)
    c = cfg(max_tokens=1000, llm_max_retries=2)
    inner = AnthropicLLM(c)
    per_call = inner.estimate_cost(True, system="s", prompt="p-00")
    cap = per_call * calls_affordable
    llm = budget_llm(inner, make_config(c, max_llm_cost_usd=cap))
    results = []
    threads = [threading.Thread(target=lambda i=i: results.append(llm.complete("s", f"p-{i:02d}", deep=True)))
               for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert llm.spent_usd <= cap and llm.reserved_usd == pytest.approx(0.0, abs=1e-12) and llm.in_flight == 0
    assert len(results) == 8
    if all_succeed:
        assert all(r is not None for r in results)
