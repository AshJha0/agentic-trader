"""A local open-weight model behind the ``LLM`` protocol, over the Ollama HTTP API.

Plan item 2.1 (docs/review/PLAN.md, OD-6). The desk talks to a model served on this machine
by Ollama (``POST /api/chat``); nothing leaves the host and nothing is billed. Structured
replies use Ollama's JSON-schema constrained decoding: the contract schema from
``contracts.py`` goes in the request's ``format`` field, and the agent's contract check stays
the second gate exactly as it does for Claude.

Status: unrun here. The development machine has 15.6 GB of RAM, below the plan's 16 GB bar
for a 7-8B model, and no Ollama install, so this module is built and tested against a fake
HTTP server only. No model has answered a desk prompt through it yet.

What carries over from ``AnthropicLLM`` unchanged:

* anonymisation -- the agents scrub every prompt before it reaches any backend;
* the call cap -- ``BudgetedLLM`` counts calls whatever the backend; ``estimate_cost``
  returns 0.0, so a dollar cap never binds on a local model, but ``max_llm_calls`` does;
* evidence -- ``last_call`` has the same keys (configured and served model, stop reason,
  fallbacks, refusal category, drift), so ``state.llm_calls`` reads the same;
* failure semantics -- a timeout, a refused connection, an HTTP error or an unreadable body
  returns ``None`` (the agent's rules apply) and is counted in ``usage``.

There are no retries: a local server that times out once is overloaded or down, and the rules
answer is the documented fallback. Requests use ``urllib`` from the standard library, so the
backend adds no dependency.
"""
from __future__ import annotations

import json
import logging
import socket
import threading
import urllib.error
import urllib.request
from types import SimpleNamespace
from typing import Any

from .llm import UsageTracker

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:11434"
# Context window sent on every request (review N4). Without it Ollama applies its own default
# (2,048 or 4,096 tokens by version) and silently drops the oldest tokens -- the system prompt
# and the fence instructions first. 8,192 fits a 7B Q4 model in about 6 GB.
DEFAULT_NUM_CTX = 8192
# A call is flagged ``truncated`` when the server evaluated fewer prompt tokens than this share
# of a neutral character-based estimate, filled the window, or stopped with done_reason
# "length". The neutral estimate is chars / 4 (no safety margin): English prose runs about 4
# characters per token on Llama/Qwen tokenisers and number-heavy JSON fewer, so a real count
# below 0.9 x chars/4 means part of the prompt was not evaluated. ``llm.estimate_tokens`` is
# deliberately conservative (x1.35) for budgets and must not be used here: it would flag
# every call. Heuristic, not a tokeniser; the window-full test is exact.
TRUNCATION_RATIO = 0.9
NEUTRAL_CHARS_PER_TOKEN = 4.0


def neutral_token_estimate(*texts: str) -> int:
    """Unmargined prompt-token estimate used only for the truncation test."""
    return int(sum(len(t or "") for t in texts) / NEUTRAL_CHARS_PER_TOKEN)


def truncation_flag(prompt_eval_count: int | None, estimate: int | None, done_reason: str | None,
                    num_ctx: int | None = None) -> bool:
    """True when a reply shows signs of a cut prompt or a cut reply (review N4): the server
    stopped on length, evaluated fewer than ``TRUNCATION_RATIO`` of the estimated prompt
    tokens, or evaluated exactly ``num_ctx`` tokens (the window was full)."""
    if done_reason == "length":
        return True
    if prompt_eval_count is None:
        return False
    if num_ctx and prompt_eval_count >= num_ctx:
        return True
    return bool(estimate) and prompt_eval_count < TRUNCATION_RATIO * float(estimate or 0)


class LocalUsageTracker(UsageTracker):
    """``UsageTracker`` for a local model: tokens are counted, the cost is zero by definition
    (no list price applies), so a local model id is never reported as unpriced. ``truncated``
    counts replies flagged by ``truncation_flag`` (review N4)."""

    truncated = 0

    def _cost_usd(self) -> float:
        return 0.0

    def _unpriced_models(self) -> list[str]:
        return []

    def summary(self) -> dict[str, Any]:
        out = super().summary()
        for row in out["by_model"].values():
            row["cost_usd"] = 0.0
        out["truncated"] = self.truncated
        return out


def served_matches(configured: str, served: str | None) -> bool:
    """Ollama reports an untagged model as ``name:latest``; any other difference is drift."""
    if not served:
        return False
    if ":" not in configured:
        configured += ":latest"
    if ":" not in served:
        served += ":latest"
    return served == configured


class LocalLLM:
    """``LLM`` over Ollama's ``/api/chat``. One model serves both tiers (``deep`` is accepted
    for protocol compatibility and recorded nowhere else); ``config`` keys: ``local_llm_url``,
    ``local_llm_model``, ``local_llm_timeout_s``, ``local_llm_seed``, ``local_llm_num_ctx``
    (default 8192, sent as ``num_ctx``), ``local_llm_temperature`` (default 0),
    ``local_llm_digest`` (optional pinned model digest, review N5), ``max_tokens`` (sent as
    ``num_predict``) and ``llm_strict_model``. Unrun on the development machine (see the
    module docstring)."""

    def __init__(self, config: dict):
        model = config.get("local_llm_model")
        if not model:
            raise ValueError("llm_provider 'local' needs local_llm_model (an Ollama model name, "
                             "e.g. 'llama3.1:8b-instruct-q4_K_M')")
        self.config = config
        self.model = str(model)
        self.url = str(config.get("local_llm_url") or DEFAULT_URL).rstrip("/")
        self.timeout_s = float(config.get("local_llm_timeout_s", 120))
        if not self.timeout_s > 0:
            raise ValueError("local_llm_timeout_s must be > 0")
        self.seed = config.get("local_llm_seed")
        self.max_tokens = int(config.get("max_tokens", 16000))
        self.num_ctx = int(config.get("local_llm_num_ctx") or DEFAULT_NUM_CTX)
        if self.num_ctx <= 0:
            raise ValueError("local_llm_num_ctx must be > 0")
        self.temperature = float(config.get("local_llm_temperature") or 0.0)
        self.digest = config.get("local_llm_digest") or None
        self.usage = LocalUsageTracker()
        self._tls = threading.local()

    @property
    def calls(self) -> int:
        return self.usage.calls

    def model_for(self, deep: bool) -> str:
        return self.model

    def estimate_cost(self, deep: bool, prompt_chars: int = 0, *, system: str | None = None,
                      prompt: str | None = None) -> float:
        """A local call costs nothing; ``BudgetedLLM``'s call cap is the only binding limit."""
        return 0.0

    @property
    def last_call(self) -> dict[str, Any] | None:
        """Evidence for the most recent call on this thread, same keys as ``AnthropicLLM``."""
        return getattr(self._tls, "last", None)

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        return self._run(system, prompt, schema=None)

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
        """Like ``complete`` with decoding constrained to ``schema`` (Ollama ``format``)."""
        return self._run(system, prompt, schema=schema)

    def build_request(self, system: str, prompt: str, schema: dict[str, Any] | None = None) -> dict[str, Any]:
        """The ``/api/chat`` body for one call."""
        options: dict[str, Any] = {"temperature": float(self.temperature), "num_predict": self.max_tokens,
                                   "num_ctx": self.num_ctx}
        if self.seed is not None:
            options["seed"] = int(self.seed)
        body: dict[str, Any] = {
            "model": self.model, "stream": False, "options": options,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if schema is not None:
            body["format"] = schema
        return body

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(self.url + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("reply body is not a JSON object")
        return data

    def _run(self, system: str, prompt: str, schema: dict[str, Any] | None) -> str | None:
        self._tls.last = None
        try:
            data = self._post(self.build_request(system, prompt, schema))
        except (TimeoutError, socket.timeout) as e:
            self._fail("timeouts", f"local model timed out after {self.timeout_s:g} s: {e}")
            return None
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), (TimeoutError, socket.timeout)):
                self._fail("timeouts", f"local model timed out after {self.timeout_s:g} s: {e}")
            else:
                self._fail(None, f"cannot reach local model at {self.url}: {e}")
            return None
        except (ValueError, OSError) as e:     # unreadable body, reset connection
            self._fail(None, f"local model reply unusable: {e}")
            return None
        return self.read_response(data, prompt_estimate=neutral_token_estimate(system, prompt))

    def _fail(self, counter: str | None, problem: str) -> None:
        log.warning("%s; using rule-based fallback", problem)
        if counter is not None:
            self.usage.count(counter)
        self.usage.count("errors")
        return None

    def read_response(self, data: dict[str, Any], prompt_estimate: int | None = None) -> str | None:
        """Book usage, record evidence and return the reply text (``None`` on an empty reply or,
        with ``llm_strict_model`` on, a reply served by another model)."""
        served = data.get("model") or self.model
        self.usage.add(served, SimpleNamespace(input_tokens=data.get("prompt_eval_count") or 0,
                                               output_tokens=data.get("eval_count") or 0))
        drift = not served_matches(self.model, served)
        pec, ec = data.get("prompt_eval_count"), data.get("eval_count")
        truncated = truncation_flag(pec, prompt_estimate, data.get("done_reason"), self.num_ctx)
        self._tls.last = {"model_configured": self.model, "model_served": served,
                          "stop_reason": data.get("done_reason"), "refusal_category": None,
                          "fallbacks": [], "model_drift": drift,
                          "prompt_eval_count": pec, "eval_count": ec, "prompt_tok_est": prompt_estimate,
                          "num_ctx": self.num_ctx, "truncated": truncated}
        if truncated:
            self.usage.count("truncated")
        if drift:
            self.usage.count("model_drift")
            log.warning("configured local model %r but the server answered as %r", self.model, served)
            if self.config.get("llm_strict_model", True):
                return None
        message = data.get("message")
        text = (message.get("content") if isinstance(message, dict) else None) or ""
        text = text.strip() if isinstance(text, str) else ""
        if not text:
            self.usage.count("empty")
        return text or None


def reachable(url: str, timeout_s: float = 3.0) -> bool:
    """True when an Ollama server answers ``GET /api/tags`` at ``url``."""
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=timeout_s) as resp:
            return 200 <= resp.status < 300
    except (OSError, ValueError):
        return False


def _get_json(url: str, timeout_s: float = 5.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def server_version(url: str, timeout_s: float = 5.0) -> str | None:
    """Ollama's ``GET /api/version`` (``None`` when unreachable or unreadable)."""
    try:
        data = _get_json(url.rstrip("/") + "/api/version", timeout_s)
    except (OSError, ValueError):
        return None
    v = data.get("version") if isinstance(data, dict) else None
    return str(v) if v else None


def model_digest(url: str, model: str, timeout_s: float = 5.0) -> dict[str, Any] | None:
    """The served model's entry from ``GET /api/tags``: digest, size, quantisation, family.
    ``None`` when the server is unreachable or does not list ``model``. A re-pulled tag with new
    weights keeps its name but changes its digest, so the digest is what pins the weights."""
    try:
        data = _get_json(url.rstrip("/") + "/api/tags", timeout_s)
    except (OSError, ValueError):
        return None
    for m in (data.get("models") or []) if isinstance(data, dict) else []:
        if isinstance(m, dict) and served_matches(model, m.get("name") or m.get("model")):
            det: dict[str, Any] = m["details"] if isinstance(m.get("details"), dict) else {}
            return {"name": m.get("name") or m.get("model"), "digest": m.get("digest"), "size": m.get("size"),
                    "quantization": det.get("quantization_level"), "family": det.get("family"),
                    "parameter_size": det.get("parameter_size")}
    return None
