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

Retries (v0.19): off by default, so a desk call that fails returns ``None`` at once and the
rules answer is the documented fallback. A long study run sets ``local_llm_retry_budget_s``
(e.g. 600): a transient failure (timeout, refused or reset connection, HTTP 5xx) is then retried
with bounded exponential backoff until the budget is spent, each retry logged, and an exhausted
budget raises ``LocalLLMUnavailable`` so a hung server stops the run loudly instead of silently
turning every later row into a rules fallback. A 4xx or an unreadable body is never retried.
The request body is built once per call, so a retry sends the same bytes (seed, options and
the recorded request digest are unchanged). Requests use ``urllib`` from the standard library, so the
backend adds no dependency.
"""

from __future__ import annotations

import ipaddress
import json
import logging
import re
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from types import SimpleNamespace
from typing import Any, Callable

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
# Backoff for transient failures when ``local_llm_retry_budget_s`` > 0: base, doubling, capped.
RETRY_BASE_S = 2.0
RETRY_MAX_DELAY_S = 60.0


class ModelDigestMismatch(RuntimeError):
    """The served model's weights are not the pinned ``local_llm_digest`` (review A17)."""


class LocalLLMUnavailable(ConnectionError):
    """The local server stayed unreachable for the whole retry budget."""


def is_transient(exc: BaseException) -> bool:
    """True for failures worth retrying: timeouts, refused/reset connections, HTTP 5xx.
    A 4xx (bad request, unknown model) and an unreadable body (``ValueError``) are not."""
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500
    if isinstance(exc, (TimeoutError, socket.timeout, urllib.error.URLError, ConnectionError)):
        return True
    if isinstance(exc, ValueError):
        return False
    return isinstance(exc, OSError)


def backoff_delays(budget_s: float, base_s: float = RETRY_BASE_S, max_delay_s: float = RETRY_MAX_DELAY_S) -> list[float]:
    """The sleep before each retry: base, 2*base, ... capped at ``max_delay_s``, the sum
    bounded by ``budget_s`` (the last delay is trimmed to fit). Empty when the budget is 0."""
    out: list[float] = []
    d, left = base_s, float(budget_s)
    while left > 1e-9 and base_s > 0:
        step = min(d, max_delay_s, left)
        out.append(step)
        left -= step
        d *= 2
    return out


NEUTRAL_CHARS_PER_TOKEN = 4.0


def neutral_token_estimate(*texts: str) -> int:
    """Unmargined prompt-token estimate used only for the truncation test."""
    return int(sum(len(t or "") for t in texts) / NEUTRAL_CHARS_PER_TOKEN)


def truncation_flag(
    prompt_eval_count: int | None, estimate: int | None, done_reason: str | None, num_ctx: int | None = None
) -> bool:
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
    retries = 0

    def _cost_usd(self) -> float:
        return 0.0

    def _unpriced_models(self) -> list[str]:
        return []

    def summary(self) -> dict[str, Any]:
        out = super().summary()
        for row in out["by_model"].values():
            row["cost_usd"] = 0.0
        out["truncated"] = self.truncated
        out["retries"] = self.retries
        return out


def llm_host(url: str) -> str:
    """The host part of a model URL (``http://127.0.0.1:11434`` -> ``127.0.0.1``)."""
    return (urllib.parse.urlsplit(url if "//" in url else "//" + url).hostname or "").lower()


def is_loopback_host(host: str) -> bool:
    """True for ``localhost`` and loopback IP literals (127.0.0.0/8, ::1). A name other than
    ``localhost`` is not resolved: it counts as remote, since DNS can point it anywhere."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
    (default 8192, sent as ``num_ctx``), ``local_llm_temperature`` (default 0: greedy, so the seed has no effect),
    ``local_llm_digest`` (optional pinned model digest, review N5; enforced before the first
    call since Round 1, see ``verify_digest``), ``max_tokens`` (sent as
    ``num_predict``) and ``llm_strict_model``. Run locally since v0.15 (see the
    module docstring)."""

    def __init__(self, config: dict):
        model = config.get("local_llm_model")
        if not model:
            raise ValueError("llm_provider 'local' needs local_llm_model (an Ollama model name, e.g. 'qwen2.5:7b-instruct')")
        self.config = config
        self.model = str(model)
        self.url = str(config.get("local_llm_url") or DEFAULT_URL).rstrip("/")
        self.host = llm_host(self.url)
        self.allow_remote = bool(config.get("allow_remote_llm"))
        if not is_loopback_host(self.host) and not self.allow_remote:
            raise ValueError(
                f"local_llm_url {self.url!r} is not a loopback address: prompts would leave "
                "this machine. Set allow_remote_llm: True to allow it deliberately"
            )
        if not is_loopback_host(self.host):
            log.warning("local model at non-loopback host %s (allow_remote_llm is set): prompts leave this machine", self.host)
        self.timeout_s = float(config.get("local_llm_timeout_s", 120))
        if not self.timeout_s > 0:
            raise ValueError("local_llm_timeout_s must be > 0")
        self.seed = config.get("local_llm_seed")
        self.temperature = float(config.get("local_llm_temperature") or 0.0)
        if self.temperature < 0:
            raise ValueError("local_llm_temperature must be >= 0")
        self.max_tokens = int(config.get("max_tokens", 16000))
        self.num_ctx = int(config.get("local_llm_num_ctx") or DEFAULT_NUM_CTX)
        if self.num_ctx <= 0:
            raise ValueError("local_llm_num_ctx must be > 0")
        self.digest = str(config.get("local_llm_digest") or "").strip().lower().removeprefix("sha256:") or None
        if self.digest is not None and (len(self.digest) < 12 or not re.fullmatch(r"[0-9a-f]+", self.digest)):
            raise ValueError(
                f"local_llm_digest must be a hex model digest (at least 12 characters), got {config.get('local_llm_digest')!r}"
            )
        self._digest_fn: Callable[[str, str], dict[str, Any] | None] = model_digest
        self._digest_verified = False
        self.retry_budget_s = float(config.get("local_llm_retry_budget_s") or 0.0)
        if self.retry_budget_s < 0:
            raise ValueError("local_llm_retry_budget_s must be >= 0")
        self.retry_base_s = float(config.get("local_llm_retry_base_s") or RETRY_BASE_S)
        self._sleep: Callable[[float], None] = time.sleep
        self.usage = LocalUsageTracker()
        self._tls = threading.local()

    @property
    def calls(self) -> int:
        return self.usage.calls

    def model_for(self, deep: bool) -> str:
        return self.model

    def estimate_cost(self, deep: bool, prompt_chars: int = 0, *, system: str | None = None, prompt: str | None = None) -> float:
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
        options: dict[str, Any] = {
            "temperature": float(self.temperature),
            "num_predict": self.max_tokens,
            "num_ctx": self.num_ctx,
        }
        if self.seed is not None:
            options["seed"] = int(self.seed)
        body: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "options": options,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if schema is not None:
            body["format"] = schema
        return body

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        req = urllib.request.Request(
            self.url + "/api/chat",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("reply body is not a JSON object")
        return data

    def verify_digest(self) -> None:
        """Round 1 (review A17): with ``local_llm_digest`` pinned, the served model's digest
        (``GET /api/tags``) must start with the pin before any call is made, so a re-pulled tag
        with new weights under the same name stops the run instead of drifting silently.
        Checked once per instance; a mismatch, or a model the server does not list, raises
        ``ModelDigestMismatch``. Without a pin nothing is checked."""
        if self.digest is None or self._digest_verified:
            return
        entry = self._digest_fn(self.url, self.model)
        served = str((entry or {}).get("digest") or "").strip().lower().removeprefix("sha256:")
        if not served:
            raise ModelDigestMismatch(
                f"pinned digest {self.digest[:12]} for {self.model!r}, but the server at "
                f"{self.url} does not list the model with a digest"
            )
        if not served.startswith(self.digest):
            raise ModelDigestMismatch(f"pinned digest {self.digest[:12]} for {self.model!r}, served {served[:12]}")
        self._digest_verified = True

    def _run(self, system: str, prompt: str, schema: dict[str, Any] | None) -> str | None:
        self._tls.last = None
        self.verify_digest()
        body = self.build_request(system, prompt, schema)  # built once: retries resend it
        try:
            data = self._post_with_retry(body)
        except LocalLLMUnavailable:
            self.usage.count("errors")
            raise
        except (TimeoutError, socket.timeout) as e:
            self._fail("timeouts", f"local model timed out after {self.timeout_s:g} s: {e}")
            return None
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), (TimeoutError, socket.timeout)):
                self._fail("timeouts", f"local model timed out after {self.timeout_s:g} s: {e}")
            else:
                self._fail(None, f"cannot reach local model at {self.url}: {e}")
            return None
        except (ValueError, OSError) as e:  # unreadable body, reset connection
            self._fail(None, f"local model reply unusable: {e}")
            return None
        return self.read_response(data, prompt_estimate=neutral_token_estimate(system, prompt))

    def _post_with_retry(self, body: dict[str, Any]) -> dict[str, Any]:
        """``_post`` with bounded backoff on transient errors (only when a budget is set)."""
        delays = backoff_delays(self.retry_budget_s, self.retry_base_s)
        for attempt in range(len(delays) + 1):
            try:
                return self._post(body)
            except Exception as e:
                if not delays or not is_transient(e):
                    raise
                if attempt == len(delays):
                    raise LocalLLMUnavailable(
                        f"local model at {self.url} unreachable after {attempt + 1} attempts over "
                        f"{self.retry_budget_s:g} s budget: {e}"
                    ) from e
                self.usage.count("retries")
                log.warning("local model call failed (%s); retry %d/%d in %.1f s", e, attempt + 1, len(delays), delays[attempt])
                self._sleep(delays[attempt])
        raise AssertionError("unreachable")  # pragma: no cover

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
        self.usage.add(
            served, SimpleNamespace(input_tokens=data.get("prompt_eval_count") or 0, output_tokens=data.get("eval_count") or 0)
        )
        drift = not served_matches(self.model, served)
        pec, ec = data.get("prompt_eval_count"), data.get("eval_count")
        truncated = truncation_flag(pec, prompt_estimate, data.get("done_reason"), self.num_ctx)
        self._tls.last = {
            "model_configured": self.model,
            "model_served": served,
            "stop_reason": data.get("done_reason"),
            "refusal_category": None,
            "fallbacks": [],
            "model_drift": drift,
            "prompt_eval_count": pec,
            "eval_count": ec,
            "prompt_tok_est": prompt_estimate,
            "num_ctx": self.num_ctx,
            "truncated": truncated,
        }
        self._tls.last.update(llm_host=self.host, remote_llm_allowed=self.allow_remote)
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
            return {
                "name": m.get("name") or m.get("model"),
                "digest": m.get("digest"),
                "size": m.get("size"),
                "quantization": det.get("quantization_level"),
                "family": det.get("family"),
                "parameter_size": det.get("parameter_size"),
            }
    return None
