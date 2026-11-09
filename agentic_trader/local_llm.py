"""A local open-weight model behind the ``LLM`` protocol, over the Ollama HTTP API.

Plan item 2.1 (docs/review/PLAN.md, OD-6). The desk talks to a model served on this machine
by Ollama (``POST /api/chat``); nothing leaves the host and nothing is billed. Structured
replies use Ollama's JSON-schema constrained decoding: the contract schema from
``contracts.py`` goes in the request's ``format`` field, and the agent's contract check stays
the second gate exactly as it does for Claude.

Status: run on the development machine since v0.15 with qwen2.5:7b-instruct under Ollama
(``docs/results/v15_local/redteam_compliance.json``, ``text_analysts.json``; the P2 study
uses the same backend). The unit tests still use a fake HTTP server only.

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


class LocalUsageTracker(UsageTracker):
    """``UsageTracker`` for a local model: tokens are counted, the cost is zero by definition
    (no list price applies), so a local model id is never reported as unpriced."""

    def _cost_usd(self) -> float:
        return 0.0

    def _unpriced_models(self) -> list[str]:
        return []

    def summary(self) -> dict[str, Any]:
        out = super().summary()
        for row in out["by_model"].values():
            row["cost_usd"] = 0.0
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
    ``local_llm_model``, ``local_llm_timeout_s``, ``local_llm_seed``, ``max_tokens`` (sent as
    ``num_predict``) and ``llm_strict_model``. Run locally since v0.15 (see the
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
        options: dict[str, Any] = {"temperature": 0.0, "num_predict": self.max_tokens}
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
        return self.read_response(data)

    def _fail(self, counter: str | None, problem: str) -> None:
        log.warning("%s; using rule-based fallback", problem)
        if counter is not None:
            self.usage.count(counter)
        self.usage.count("errors")
        return None

    def read_response(self, data: dict[str, Any]) -> str | None:
        """Book usage, record evidence and return the reply text (``None`` on an empty reply or,
        with ``llm_strict_model`` on, a reply served by another model)."""
        served = data.get("model") or self.model
        self.usage.add(served, SimpleNamespace(input_tokens=data.get("prompt_eval_count") or 0,
                                               output_tokens=data.get("eval_count") or 0))
        drift = not served_matches(self.model, served)
        self._tls.last = {"model_configured": self.model, "model_served": served,
                          "stop_reason": data.get("done_reason"), "refusal_category": None,
                          "fallbacks": [], "model_drift": drift}
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
