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
import random
import re
import threading
import time
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
# Reply size reserved per call under a dollar cap when the config does not say (llm_reserve_output_tokens).
DEFAULT_RESERVE_OUTPUT_TOKENS = 2000
# Status codes retried besides rate limits and every 5xx (what the SDK's own loop retries).
_RETRY_STATUS = frozenset({408, 409, 429})
MAX_RETRY_DELAY_S = 8.0
# A retry-after header is honoured up to this many seconds (as the SDK's own loop does); a
# longer wait falls back to the backoff rather than parking a worker for minutes.
MAX_RETRY_AFTER_S = 60.0
BUDGET_MODES = ("hard", "estimate")

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


def check_effort(effort: Any) -> str:
    """``effort`` when it is one of ``EFFORT_LEVELS``; ``ValueError`` otherwise. A typo in the
    config is a configuration error, not a request for ``high``."""
    if effort not in EFFORT_LEVELS:
        raise ValueError(f"effort must be one of {EFFORT_LEVELS}, not {effort!r}")
    return str(effort)


def request_shape(model: str, effort: str, max_tokens: int) -> dict[str, Any]:
    """The Messages API parameters for ``model``: only what that family accepts.

    An effort level the family lacks is lowered to the nearest one it has (``xhigh``
    becomes ``high`` on the 4.6 generation) and logged once; a family that takes no
    effort parameter gets none. An effort outside ``EFFORT_LEVELS`` raises.
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
        want = check_effort(effort)
        if want not in efforts:
            rank = EFFORT_LEVELS.index(want)
            lower = [e for e in efforts if EFFORT_LEVELS.index(e) <= rank]
            want = max(lower, key=EFFORT_LEVELS.index) if lower else min(efforts, key=EFFORT_LEVELS.index)
            _warn_once(f"effort:{model}:{effort}", "model %r does not take effort %r; using %r",
                       model, effort, want)
        kwargs["output_config"] = {"effort": want}
    return kwargs


def estimate_call_cost(model: str, output_tokens: int,
                       input_tokens: int = ESTIMATED_INPUT_TOKENS) -> float:
    """List-price cost of one call with a typical prompt and ``output_tokens`` of reply.
    ``inf`` for an unpriced id, so a budget that reserves it fails closed."""
    price = price_for(model)
    if price is None:
        return math.inf
    pin, pout = price
    return (input_tokens * pin + output_tokens * pout) / 1e6


def _whole_number(config: dict, key: str, default: int, minimum: int) -> int:
    v = config.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v) or v < minimum:
        raise ValueError(f"{key} must be a whole number >= {minimum}, got {v!r}")
    return int(v)


def _seconds(config: dict, key: str, default: float) -> float:
    v = config.get(key, default)
    try:
        f = float(v)
    except (TypeError, ValueError):
        f = math.nan
    if isinstance(v, bool) or not math.isfinite(f) or f < 0:
        raise ValueError(f"{key} must be a finite number of seconds >= 0, got {v!r}")
    return f


def retry_after_seconds(error: Any) -> float | None:
    """The wait a rate-limit or overload reply asked for, from the ``retry-after-ms`` or
    ``retry-after`` header the SDK exposes on ``error.response``: seconds when the header is
    present, parseable and at most ``MAX_RETRY_AFTER_S``; ``None`` otherwise (the caller then
    uses its backoff). An HTTP-date form is measured from now."""
    headers = getattr(getattr(error, "response", None), "headers", None)
    if headers is None:
        return None
    try:
        ms = headers.get("retry-after-ms")
        wait = float(ms) / 1000.0 if ms is not None else None
        if wait is None:
            raw = headers.get("retry-after")
            if raw is None:
                return None
            try:
                wait = float(raw)
            except ValueError:
                from email.utils import parsedate_to_datetime
                wait = (parsedate_to_datetime(str(raw)).timestamp() - time.time())
    except (TypeError, ValueError, AttributeError):
        return None
    if not math.isfinite(wait) or wait < 0 or wait > MAX_RETRY_AFTER_S:
        return None
    return wait


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

    # Every read of by_model takes the lock: add() can insert a key from another worker's
    # thread while a budget check iterates, and CPython raises on a dict that changes size.
    def _calls(self) -> int:
        return sum(u.calls for u in self.by_model.values())

    def _cost_usd(self) -> float:
        return sum(u.cost(m) or 0.0 for m, u in self.by_model.items())

    def _unpriced_models(self) -> list[str]:
        return sorted(m for m, u in self.by_model.items() if u.cost(m) is None)

    @property
    def calls(self) -> int:
        with self._lock:
            return self._calls()

    @property
    def cost_usd(self) -> float:
        with self._lock:
            return self._cost_usd()

    @property
    def unpriced_models(self) -> list[str]:
        """Served ids with no list price: their spend is unknown, not zero."""
        with self._lock:
            return self._unpriced_models()

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return {
                "calls": self._calls(), "refusals": self.refusals, "errors": self.errors,
                "empty_replies": self.empty, "timeouts": self.timeouts, "cost_usd": round(self._cost_usd(), 4),
                "unpriced_models": self._unpriced_models(),
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
        for key in ("deep_effort", "quick_effort"):
            try:
                check_effort(config[key])
            except ValueError as e:
                raise ValueError(f"{key}: {e}") from None
        self.max_retries = _whole_number(config, "llm_max_retries", 2, 0)
        self.retry_backoff_s = _seconds(config, "llm_retry_backoff_s", 0.5)
        self.reserve_output_tokens = _whole_number(config, "llm_reserve_output_tokens",
                                                   DEFAULT_RESERVE_OUTPUT_TOKENS, 1)
        self.budget_mode = str(config.get("llm_budget_mode", "hard"))
        if self.budget_mode not in BUDGET_MODES:
            raise ValueError(f"llm_budget_mode must be one of {BUDGET_MODES}, got {config.get('llm_budget_mode')!r}")
        # Credentials: ANTHROPIC_API_KEY or an `ant auth login` profile. The client makes no
        # retries of its own: ``complete`` runs the loop, so every attempt is observed and billed.
        self.client = anthropic.Anthropic(timeout=float(config.get("llm_timeout_s", 300)), max_retries=0)
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
        """What one call on this tier is reserved at before it is dispatched. Under
        ``llm_budget_mode="hard"`` it is the most the call can cost -- a typical prompt plus a
        full ``max_tokens`` reply, which is also what a timed-out attempt is billed at -- so the
        dollar cap is a bound on spend. Under ``"estimate"`` it is the prompt plus
        ``llm_reserve_output_tokens`` of reply: a realistic size that admits more concurrent
        calls but lets spend overshoot the cap by what replies exceed the reserve."""
        out = self.config["max_tokens"] if self.budget_mode == "hard" else self.reserve_output_tokens
        return estimate_call_cost(self.model_for(deep), int(out))

    def _create(self, kwargs: dict[str, Any]) -> Any:
        if self.config.get("use_refusal_fallback") and kwargs["model"] in _FALLBACK_MODELS:
            return self.client.beta.messages.create(betas=[_FALLBACK_BETA], extra_body={"fallbacks": "default"},
                                                    **kwargs)
        return self.client.messages.create(**kwargs)

    def _retry_delay(self, attempt: int) -> float:
        return min(self.retry_backoff_s * 2 ** (attempt - 1), MAX_RETRY_DELAY_S) * (1.0 - 0.25 * random.random())

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        a = self._anthropic
        kwargs = self._request(deep)
        kwargs.update(system=system, messages=[{"role": "user", "content": prompt}])
        for attempt in range(1, self.max_retries + 2):
            wait = None
            try:
                resp = self._create(kwargs)
                break
            except a.RateLimitError as e:
                problem, retry, wait = f"rate limited: {e}", True, retry_after_seconds(e)
            except a.APIStatusError as e:
                problem = f"Claude API error {e.status_code}: {e.message}"
                retry = e.status_code in _RETRY_STATUS or e.status_code >= 500
                wait = retry_after_seconds(e)
            except a.APIConnectionError as e:
                if isinstance(e, a.APITimeoutError):
                    # The server can finish (and bill) a request the client abandoned; an unknown
                    # charge is booked at its maximum, per attempt, whatever a later attempt does.
                    self.usage.add_estimate(kwargs["model"], ESTIMATED_INPUT_TOKENS, kwargs["max_tokens"])
                    self.usage.count("timeouts")
                    problem = f"Claude API request timed out (attempt {attempt}, billed at the estimated maximum): {e}"
                else:
                    problem = f"cannot reach Claude API: {e}"
                retry = True
            if not retry or attempt > self.max_retries:
                log.warning("%s; giving up after %d attempt(s)", problem, attempt)
                self.usage.count("errors")
                return None
            log.warning("%s; retry %d of %d", problem, attempt, self.max_retries)
            time.sleep(self._retry_delay(attempt) if wait is None else wait)
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
    """Cap on model calls and / or estimated spend. Past either cap every call returns
    ``None``, so each agent falls back to its rule-based reasoning and the run finishes
    normally.

    Protects backtests from runaway cost: at default settings one decision makes
    14 calls, so a 1-year weekly backtest of one instrument is ~730 calls, and an
    Opus call costs roughly 15x a Haiku call, so a call count alone does not bound
    the bill. The dollar cap uses the inner model's ``UsageTracker`` (list prices,
    cache-aware). Before a call is dispatched its reservation (``inner.estimate_cost``)
    is taken under the lock, and calls in flight count against the cap, so parallel
    workers sharing one budget cannot each slip one more call past it. What is reserved
    is the inner model's ``llm_budget_mode``: ``"hard"`` (the default) reserves the most a
    call can cost, so spend never exceeds the cap; ``"estimate"`` reserves a realistic
    reply and the cap is soft by the amount replies run over the reserve. A cap below one
    reservation refuses every call on that tier, before any spend, and ``exhausted_for``
    (and ``exhausted``, the deep tier) report that state the same way ``complete`` acts on
    it. A served model with no list price makes the spend unknowable and the budget
    treats it as exhausted (fail closed) rather than as free.
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
        """True when the next deep-tier call would be refused (the tier every reasoning role
        uses; ``exhausted_for(False)`` asks about the quick tier)."""
        return self.exhausted_for(True)

    def exhausted_for(self, deep: bool) -> bool:
        """True when the next call on this tier would be refused: its reservation, on top of
        what is spent and reserved for calls in flight, would reach the cap."""
        with self._lock:
            return self._why_exhausted(self._reserve(deep)) is not None

    def _estimate(self, deep: bool) -> float:
        est = getattr(self.inner, "estimate_cost", None)
        return float(est(deep)) if callable(est) else 0.0

    def _reserve(self, deep: bool) -> float:
        return self._estimate(deep) if self.max_cost_usd is not None else 0.0

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
        reserve = self._reserve(deep)
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
