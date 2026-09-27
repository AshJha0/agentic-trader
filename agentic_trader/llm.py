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
import math
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
    "claude-mythos-5-1": (10.0, 50.0),
    "claude-mythos-5": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
_ALL = EFFORT_LEVELS
_NO_XHIGH = ("low", "medium", "high", "max")
_PRE_46 = ("low", "medium", "high")

# Request parameters each model family accepts: (thinking mode, effort levels).
#   "always"   thinking cannot be configured; omit the parameter (Fable / Mythos 5.x)
#   "adaptive" send thinking={"type": "adaptive"}
#   None       no thinking parameter (pre-4.6 generations reject "adaptive")
# An id outside the table gets a plain request (no thinking, no effort), which every
# generation accepts, rather than parameters that turn every call into a 400.
MODEL_CAPABILITIES: dict[str, tuple[str | None, tuple[str, ...]]] = {
    "claude-fable-5-1": ("always", _ALL),
    "claude-fable-5": ("always", _ALL),
    "claude-mythos-5-1": ("always", _ALL),
    "claude-mythos-5": ("always", _ALL),
    "claude-opus-5-5": ("adaptive", _ALL),
    "claude-opus-5": ("adaptive", _ALL),
    "claude-opus-4-8": ("adaptive", _ALL),
    "claude-opus-4-7": ("adaptive", _ALL),
    "claude-opus-4-6": ("adaptive", _NO_XHIGH),
    "claude-sonnet-5": ("adaptive", _ALL),
    "claude-sonnet-4-6": ("adaptive", _NO_XHIGH),
    "claude-opus-4-5": (None, _PRE_46),
    "claude-sonnet-4-5": (None, ()),
    "claude-haiku-4-5": (None, ()),
}

# Input size assumed when a call has to be priced before (or without) a usage record:
# the deep-tier prompts carry the analyst digest, debate and facts, a few thousand tokens.
ESTIMATED_INPUT_TOKENS = 8000

_warned: set[str] = set()
_warned_lock = threading.Lock()


def _warn_once(key: str, msg: str, *args: Any) -> None:
    with _warned_lock:
        if key in _warned:
            return
        _warned.add(key)
    log.warning(msg, *args)


def _family(model: str, table: dict[str, Any]) -> str | None:
    """The longest table key ``model`` starts with (ids can carry a date suffix)."""
    if model in table:
        return model
    return max((k for k in table if model.startswith(k)), key=len, default=None)


def price_for(model: str) -> tuple[float, float] | None:
    """List price for a model id, matching the longest table key the id starts with.

    The API reports the model that served a call, which can carry a date suffix
    (``claude-haiku-4-5-20251001``); the table is keyed by family.
    """
    fam = _family(model, PRICES_PER_MTOK)
    return PRICES_PER_MTOK[fam] if fam else None


def request_shape(model: str, effort: str, max_tokens: int) -> dict[str, Any]:
    """The Messages API parameters for ``model``: only what that family accepts.

    An effort level the family lacks is lowered to the nearest one it has (``xhigh``
    becomes ``high`` on the 4.6 generation) and logged once; a family that takes no
    effort parameter gets none.
    """
    kwargs: dict[str, Any] = {"model": model, "max_tokens": int(max_tokens)}
    fam = _family(model, MODEL_CAPABILITIES)
    if fam is None:
        _warn_once(f"family:{model}", "model %r is not in MODEL_CAPABILITIES; sending a plain "
                   "request without thinking or effort", model)
        return kwargs
    thinking, efforts = MODEL_CAPABILITIES[fam]
    if thinking == "adaptive":
        kwargs["thinking"] = {"type": "adaptive"}
    if efforts:
        want = effort if effort in EFFORT_LEVELS else "high"
        if want not in efforts:
            rank = EFFORT_LEVELS.index(want)
            lower = [e for e in efforts if EFFORT_LEVELS.index(e) <= rank]
            want = max(lower, key=EFFORT_LEVELS.index) if lower else min(efforts, key=EFFORT_LEVELS.index)
            _warn_once(f"effort:{model}:{effort}", "model %r does not take effort %r; using %r",
                       model, effort, want)
        kwargs["output_config"] = {"effort": want}
    return kwargs


def estimate_call_cost(model: str, max_tokens: int,
                       input_tokens: int = ESTIMATED_INPUT_TOKENS) -> float:
    """Conservative list-price cost of one call: a typical prompt plus a full ``max_tokens``
    reply. ``inf`` for an unpriced id, so a budget that reserves it fails closed."""
    price = price_for(model)
    if price is None:
        return math.inf
    pin, pout = price
    return (input_tokens * pin + max_tokens * pout) / 1e6


class LLM(Protocol):
    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None: ...


@dataclass
class ModelUsage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    estimated_calls: int = 0  # timed-out requests billed at an estimate (no usage record)

    def cost(self, model: str) -> float | None:
        price = price_for(model)
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
    timeouts: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, model: str, usage: Any) -> None:
        with self._lock:
            u = self.by_model.setdefault(model, ModelUsage())
            u.calls += 1
            u.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            u.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            u.cache_read_tokens += int(getattr(usage, "cache_read_input_tokens", 0) or 0)
            u.cache_write_tokens += int(getattr(usage, "cache_creation_input_tokens", 0) or 0)

    def add_estimate(self, model: str, input_tokens: int, output_tokens: int, attempts: int = 1) -> None:
        """Bill a request that returned no usage record (the client gave up on it) as if
        every attempt the SDK made had been served in full."""
        with self._lock:
            u = self.by_model.setdefault(model, ModelUsage())
            u.estimated_calls += attempts
            u.input_tokens += int(input_tokens) * attempts
            u.output_tokens += int(output_tokens) * attempts

    def count(self, what: str) -> None:
        with self._lock:
            setattr(self, what, getattr(self, what) + 1)

    @property
    def calls(self) -> int:
        return sum(u.calls for u in self.by_model.values())

    @property
    def cost_usd(self) -> float:
        return sum(u.cost(m) or 0.0 for m, u in self.by_model.items())

    @property
    def unpriced_models(self) -> list[str]:
        """Served ids with no list price: their spend is unknown, not zero."""
        return sorted(m for m, u in self.by_model.items() if u.cost(m) is None)

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.calls, "refusals": self.refusals, "errors": self.errors,
            "empty_replies": self.empty, "timeouts": self.timeouts, "cost_usd": round(self.cost_usd, 4),
            "unpriced_models": self.unpriced_models,
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
        self.max_retries = int(config.get("llm_max_retries", 2))
        # Credentials: ANTHROPIC_API_KEY or an `ant auth login` profile.
        self.client = anthropic.Anthropic(timeout=float(config.get("llm_timeout_s", 300)),
                                          max_retries=self.max_retries)
        self.config = config
        self.usage = UsageTracker()

    @property
    def calls(self) -> int:
        return self.usage.calls

    def model_for(self, deep: bool) -> str:
        return self.config["deep_think_llm" if deep else "quick_think_llm"]

    def _request(self, deep: bool) -> dict[str, Any]:
        return request_shape(self.model_for(deep),
                             self.config["deep_effort" if deep else "quick_effort"],
                             self.config["max_tokens"])

    def estimate_cost(self, deep: bool) -> float:
        """What one call on this tier can cost at most (a full max_tokens reply)."""
        return estimate_call_cost(self.model_for(deep), int(self.config["max_tokens"]))

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
            if isinstance(e, a.APITimeoutError):
                # The server can finish (and bill) a request the client abandoned, once per
                # attempt the SDK made; an unknown charge is booked at its maximum, not at $0.
                self.usage.add_estimate(kwargs["model"], ESTIMATED_INPUT_TOKENS, kwargs["max_tokens"],
                                        attempts=self.max_retries + 1)
                self.usage.count("timeouts")
                log.warning("Claude API request timed out after %d attempt(s); billed at the "
                            "estimated maximum: %s", self.max_retries + 1, e)
            else:
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
    cache-aware). Before a call is dispatched its maximum cost (``inner.estimate_cost``,
    a full ``max_tokens`` reply) is reserved under the lock, and calls in flight count
    against the cap, so parallel workers sharing one budget cannot each slip one more
    call past it. A served model with no list price makes the spend unknowable and the
    budget treats it as exhausted (fail closed) rather than as free.
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
        self.in_flight = 0
        self.reserved_usd = 0.0
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
        return self._why_exhausted() is not None

    def _estimate(self, deep: bool) -> float:
        est = getattr(self.inner, "estimate_cost", None)
        return float(est(deep)) if callable(est) else 0.0

    def _why_exhausted(self, reserve: float = 0.0) -> str | None:
        if self.max_calls is not None and self.calls >= self.max_calls:
            return f"LLM call budget of {self.max_calls} reached"
        if self.max_cost_usd is not None:
            u = self.usage
            unpriced = u.unpriced_models if u is not None else []
            if unpriced:
                return (f"LLM spend budget of ${self.max_cost_usd:.2f} cannot be enforced: calls were "
                        f"served by unpriced model(s) {unpriced}; treating the budget as exhausted")
            committed = self.spent_usd + self.reserved_usd + reserve
            if committed >= self.max_cost_usd:
                return (f"LLM spend budget of ${self.max_cost_usd:.2f} reached (${self.spent_usd:.2f} "
                        f"spent, ${self.reserved_usd + reserve:.2f} reserved for calls in flight)")
        return None

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        reserve = self._estimate(deep) if self.max_cost_usd is not None else 0.0
        with self._lock:
            why = self._why_exhausted(reserve)
            if why is not None:
                if self.refused == 0:
                    log.warning("%s; agents fall back to rules", why)
                self.refused += 1
                return None
            self.calls += 1
            self.in_flight += 1
            self.reserved_usd += reserve
        try:
            return self.inner.complete(system, prompt, deep=deep)
        finally:
            with self._lock:
                self.in_flight -= 1
                self.reserved_usd -= reserve


def budget_llm(llm: LLM, config: dict) -> LLM:
    """Wrap ``llm`` in a ``BudgetedLLM`` when the config sets a call or dollar cap.

    A dollar cap needs a list price for both configured model ids; an unpriced id would
    spend without bound, so it is refused here instead of at the end of a run.
    """
    cap, spend = config.get("max_llm_calls"), config.get("max_llm_cost_usd")
    if cap is None and spend is None:
        return llm
    if spend is not None:
        for key in ("deep_think_llm", "quick_think_llm"):
            model = config.get(key)
            if model and price_for(str(model)) is None:
                raise ValueError(f"max_llm_cost_usd needs priced model ids: {key}={model!r} is not in "
                                 f"PRICES_PER_MTOK (known families: {sorted(PRICES_PER_MTOK)})")
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


def _no_constants(name: str) -> Any:
    # json.loads accepts bare NaN / Infinity by default; a numeric field holding one is
    # not a number the desk can act on, so the whole candidate is rejected.
    raise ValueError(f"non-finite JSON constant {name}")


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
            data = json.loads(c, parse_constant=_no_constants)
            if isinstance(data, dict):
                return data
        except ValueError:  # includes JSONDecodeError
            continue
    return None
