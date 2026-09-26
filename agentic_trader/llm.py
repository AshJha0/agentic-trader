"""LLM access for the agents.

Two model tiers: a *quick-thinking* model for analysts that summarise tool
output, and a *deep-thinking* model for the reasoning-heavy roles (researchers,
facilitator, trader, risk team, portfolio manager).

``complete`` returns ``None`` on any failure (missing key, network, refusal,
unparseable output) and the calling agent then falls back to its rule-based
reasoning, so a pipeline run never dies because of the LLM.

Every class here is safe to share between threads: a parallel evaluation runs
one backtest per instrument against a single client and a single call budget.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback (beta).
_FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens (input, output), first-party API list prices. Cache reads
# are billed at 0.1x input and cache writes at 1.25x input. Update when prices change.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


class LLM(Protocol):
    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None: ...


@dataclass
class ModelUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def cost(self, model: str) -> float | None:
        price = PRICES_PER_MTOK.get(model)
        if price is None:
            return None
        pin, pout = price
        return (self.input_tokens * pin + self.output_tokens * pout
                + self.cache_read_tokens * pin * 0.1 + self.cache_write_tokens * pin * 1.25) / 1e6


@dataclass
class UsageTracker:
    """Thread-safe token and outcome accounting, keyed by the model that served each call."""
    by_model: dict[str, ModelUsage] = field(default_factory=dict)
    refusals: int = 0
    errors: int = 0
    empty: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, usage: Any) -> None:
        with self._lock:
            u = self.by_model.setdefault(model, ModelUsage())
            u.calls += 1
            u.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            u.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            u.cache_read_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            u.cache_write_tokens += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    def count(self, what: str) -> None:
        with self._lock:
            setattr(self, what, getattr(self, what) + 1)

    @property
    def calls(self) -> int:
        return sum(u.calls for u in self.by_model.values())

    @property
    def cost_usd(self) -> float:
        return sum(u.cost(m) or 0.0 for m, u in self.by_model.items())

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.calls, "refusals": self.refusals, "errors": self.errors,
            "empty_replies": self.empty, "cost_usd": round(self.cost_usd, 4),
            "by_model": {m: {**u.__dict__, "cost_usd": None if u.cost(m) is None else round(u.cost(m), 4)}
                         for m, u in self.by_model.items()},
        }


class AnthropicLLM:
    def __init__(self, config: dict):
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise ImportError("llm_provider='anthropic' needs `pip install anthropic`") from e
        self._anthropic = anthropic
        # Credentials: ANTHROPIC_API_KEY or an `ant auth login` profile.
        self.client = anthropic.Anthropic(timeout=float(config.get("llm_timeout_s", 300)))
        self.config = config
        self.usage = UsageTracker()

    @property
    def calls(self) -> int:
        return self.usage.calls

    def _request(self, deep: bool) -> dict[str, Any]:
        model = self.config["deep_think_llm" if deep else "quick_think_llm"]
        kwargs: dict[str, Any] = {"model": model, "max_tokens": self.config["max_tokens"]}
        # Haiku 4.5 predates adaptive thinking / effort; everything newer takes both.
        if not model.startswith("claude-haiku-4-5"):
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {
                "effort": self.config["deep_effort" if deep else "quick_effort"]}
        return kwargs

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        a = self._anthropic
        kwargs = self._request(deep)
        kwargs.update(system=system, messages=[{"role": "user", "content": prompt}])
        try:
            if self.config.get("use_refusal_fallback") and kwargs["model"] in _FALLBACK_MODELS:
                resp = self.client.beta.messages.create(
                    betas=[_FALLBACK_BETA], extra_body={"fallbacks": "default"}, **kwargs)
            else:
                resp = self.client.messages.create(**kwargs)
        except a.RateLimitError as e:
            log.warning("rate limited after SDK retries: %s", e)
            self.usage.count("errors")
            return None
        except a.APIStatusError as e:
            log.warning("Claude API error %s: %s", e.status_code, e.message)
            self.usage.count("errors")
            return None
        except a.APIConnectionError as e:
            log.warning("cannot reach Claude API: %s", e)
            self.usage.count("errors")
            return None
        self.usage.add(getattr(resp, "model", kwargs["model"]), getattr(resp, "usage", None))
        if resp.stop_reason == "refusal":
            log.warning("model declined the request; using rule-based fallback")
            self.usage.count("refusals")
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        if not text:
            self.usage.count("empty")
        return text or None


class BudgetedLLM:
    """Hard cap on model calls and / or estimated spend. Past either cap every call
    returns ``None``, so each agent falls back to its rule-based reasoning and the
    run finishes normally.

    Protects backtests from runaway cost: at default settings one decision makes
    14 calls, so a 1-year weekly backtest of one instrument is ~730 calls, and an
    Opus call costs roughly 15x a Haiku call, so a call count alone does not bound
    the bill. The dollar cap uses the inner model's ``UsageTracker`` (list prices,
    cache-aware) and is checked before each call, so the overshoot is at most one
    call. Thread-safe: parallel backtests sharing one budget never exceed it.
    """

    def __init__(self, inner: LLM, max_calls: int | None = None, max_cost_usd: float | None = None):
        if max_calls is None and max_cost_usd is None:
            raise ValueError("BudgetedLLM needs max_calls and/or max_cost_usd")
        if max_calls is not None and max_calls < 0:
            raise ValueError("max_calls must be >= 0")
        if max_cost_usd is not None and max_cost_usd < 0:
            raise ValueError("max_cost_usd must be >= 0")
        self.inner, self.max_calls, self.max_cost_usd = inner, max_calls, max_cost_usd
        self.calls = 0
        self.refused = 0
        self._lock = threading.Lock()

    @property
    def usage(self) -> UsageTracker | None:
        return getattr(self.inner, "usage", None)

    @property
    def spent_usd(self) -> float:
        u = self.usage
        return u.cost_usd if u is not None else 0.0

    @property
    def exhausted(self) -> bool:
        if self.max_calls is not None and self.calls >= self.max_calls:
            return True
        return self.max_cost_usd is not None and self.spent_usd >= self.max_cost_usd

    def _why_exhausted(self) -> str | None:
        if self.max_calls is not None and self.calls >= self.max_calls:
            return f"LLM call budget of {self.max_calls} reached"
        if self.max_cost_usd is not None and self.spent_usd >= self.max_cost_usd:
            return f"LLM spend budget of ${self.max_cost_usd:.2f} reached (${self.spent_usd:.2f} spent)"
        return None

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        with self._lock:
            why = self._why_exhausted()
            if why is not None:
                if self.refused == 0:
                    log.warning("%s; agents fall back to rules", why)
                self.refused += 1
                return None
            self.calls += 1
        return self.inner.complete(system, prompt, deep=deep)


def budget_llm(llm: LLM, config: dict) -> LLM:
    """Wrap ``llm`` in a ``BudgetedLLM`` when the config sets a call or dollar cap."""
    cap, spend = config.get("max_llm_calls"), config.get("max_llm_cost_usd")
    if cap is None and spend is None:
        return llm
    if isinstance(llm, BudgetedLLM):
        return llm
    return BudgetedLLM(llm, None if cap is None else int(cap), None if spend is None else float(spend))


def get_llm(config: dict) -> LLM | None:
    provider = config.get("llm_provider", "offline")
    if provider == "offline":
        return None
    if provider == "anthropic":
        llm: LLM = AnthropicLLM(config)
    else:
        raise ValueError(f"unknown llm_provider {provider!r} (use 'offline' or 'anthropic')")
    return budget_llm(llm, config)


def llm_usage(llm: LLM | None) -> dict[str, Any] | None:
    """Usage summary for an AnthropicLLM (possibly budget-wrapped), else None."""
    tracker = getattr(llm, "usage", None)
    return tracker.summary() if isinstance(tracker, UsageTracker) else None


_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def extract_json(text: str | None) -> dict[str, Any] | None:
    """Pull the first JSON object out of a model reply (fenced or bare)."""
    if not text:
        return None
    m = _JSON_BLOCK.search(text)
    candidates = [m.group(1)] if m else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start:end + 1])
    for c in candidates:
        try:
            data = json.loads(c)
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            continue
    return None
