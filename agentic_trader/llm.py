"""LLM access for the agents.

Two model tiers, as in the paper: a *quick-thinking* model for analysts that
summarise tool output, and a *deep-thinking* model for the reasoning-heavy roles
(researchers, facilitator, trader, risk team, portfolio manager).

``complete`` returns ``None`` on any failure (missing key, network, refusal,
unparseable output) and the calling agent then falls back to its rule-based
reasoning, so a pipeline run never dies because of the LLM.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

log = logging.getLogger(__name__)

# Models that accept the server-side refusal fallback (beta).
_FALLBACK_MODELS = {"claude-opus-5", "claude-fable-5-1"}
_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class LLM(Protocol):
    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None: ...


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
        self.calls = 0

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
            return None
        except a.APIStatusError as e:
            log.warning("Claude API error %s: %s", e.status_code, e.message)
            return None
        except a.APIConnectionError as e:
            log.warning("cannot reach Claude API: %s", e)
            return None
        self.calls += 1
        if resp.stop_reason == "refusal":
            log.warning("model declined the request; using rule-based fallback")
            return None
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        return text or None


class BudgetedLLM:
    """Hard cap on model calls. Past the cap every call returns ``None``, so each
    agent falls back to its rule-based reasoning and the run finishes normally.

    Protects backtests from runaway cost: at default settings one decision makes
    14 calls, so a 1-year weekly backtest of one instrument is ~730 calls.
    """

    def __init__(self, inner: LLM, max_calls: int):
        if max_calls < 0:
            raise ValueError("max_calls must be >= 0")
        self.inner, self.max_calls = inner, max_calls
        self.calls = 0
        self.refused = 0

    @property
    def exhausted(self) -> bool:
        return self.calls >= self.max_calls

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        if self.exhausted:
            if self.refused == 0:
                log.warning("LLM call budget of %d reached; agents fall back to rules",
                            self.max_calls)
            self.refused += 1
            return None
        self.calls += 1
        return self.inner.complete(system, prompt, deep=deep)


def get_llm(config: dict) -> LLM | None:
    provider = config.get("llm_provider", "offline")
    if provider == "offline":
        return None
    if provider == "anthropic":
        llm: LLM = AnthropicLLM(config)
    else:
        raise ValueError(f"unknown llm_provider {provider!r} (use 'offline' or 'anthropic')")
    cap = config.get("max_llm_calls")
    return BudgetedLLM(llm, int(cap)) if cap is not None else llm


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
