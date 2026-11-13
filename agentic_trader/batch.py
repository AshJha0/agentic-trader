"""Message Batches backend for the desk: the same ``LLM`` protocol, answered in bulk.

A walk-forward backtest asks the model thousands of questions, and each one depends only on
the date, the instrument and the replies earlier in that day's pipeline. ``BatchLLM`` exploits
that. On a pass over the backtest it answers every question it already holds a result for and
queues the rest, returning ``None`` for them so the agents fall back to rules for that pass.
``run_until_complete`` then submits the queue as one batch, stores the results and runs the
backtest again; each pass unlocks the next stage of every day's pipeline at once. The pass that
queues nothing is the real run, and it is identical to calling the model directly, because
prompts are deterministic given the earlier replies.

Results live in an append-only JSONL store keyed by ``custom_id`` (a hash of the request), so
results may arrive in any order and a crashed run resumes without paying again. Note that the
server-side ``fallbacks`` parameter is rejected on Batches: the request body is built from
``AnthropicLLM.build_request`` alone, which never carries it.

NEVER RUN AGAINST THE LIVE API (review 2026-11-09, section d): ``BatchLLM`` and
``AnthropicBatchBackend`` are tested only against ``FakeBatchBackend``. No funded batch has
been submitted. Frozen until one is; see the box in ``llm.py``.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

SUCCEEDED, ERRORED, EXPIRED, CANCELED = "succeeded", "errored", "expired", "canceled"
_RETRYABLE_ERRORS = {"overloaded_error", "api_error", "rate_limit_error", "timeout_error"}


@dataclass(frozen=True)
class Outcome:
    """One request's batch result. ``text`` is set only for ``succeeded`` (and may still be
    ``None`` after a refusal); ``retryable`` marks an ``errored`` result worth resubmitting."""
    type: str
    text: str | None = None
    retryable: bool = False


class BatchBackend(Protocol):
    """Submits ``{custom_id: params}`` as one batch, waits for it, and returns an outcome per id."""

    def run(self, requests: dict[str, dict[str, Any]]) -> dict[str, Outcome]: ...


class RequestBuilder(Protocol):
    """What ``BatchLLM`` needs from the direct backend (``AnthropicLLM`` satisfies it)."""

    def build_request(self, system: str, prompt: str, *, deep: bool,
                      schema: dict[str, Any] | None = None) -> dict[str, Any]: ...


def custom_id(system: str, prompt: str, *, deep: bool, schema: dict[str, Any] | None) -> str:
    """Stable request id: sha256 over (deep, schema as sorted JSON, system, prompt), 64 hex chars
    (the Batches API caps ``custom_id`` at 64)."""
    payload = json.dumps([deep, json.dumps(schema, sort_keys=True), system, prompt], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:64]


class BatchLLM:
    """``LLM`` served from stored batch results; unknown requests are queued and answered ``None``.

    ``inner`` builds the Messages API parameters (``AnthropicLLM``); with ``inner=None`` the
    parameters are the raw call (``system``, ``prompt``, ``deep``, ``schema``), which is what a
    fake backend wants. A request whose final result is ``None`` (refusal, permanent error,
    retries spent) stays ``None``: the agents use rules for it on every later pass.
    """

    def __init__(self, inner: RequestBuilder | None, backend: BatchBackend, store_path: str | Path,
                 *, max_resubmits: int = 2):
        self.inner = inner
        self.backend = backend
        self.store_path = Path(store_path)
        self.max_resubmits = max_resubmits
        self.incomplete = False
        self.submissions = 0
        self.misses = 0   # lookups answered None because no result is held yet (read by run_jobs)
        self.summary: dict[str, int] = {"succeeded": 0, "resubmitted": 0, "failed": 0, "from_store": 0}
        self._lock = threading.Lock()
        self._results: dict[str, str | None] = {}
        self._queue: dict[str, dict[str, Any]] = {}
        self._attempts: dict[str, int] = {}
        if self.store_path.exists():
            for line in self.store_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self._results.setdefault(rec["custom_id"], rec["text"])
            self.summary["from_store"] = len(self._results)

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        return self._lookup(system, prompt, deep=deep, schema=None)

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
        return self._lookup(system, prompt, deep=deep, schema=schema)

    def _lookup(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any] | None) -> str | None:
        cid = custom_id(system, prompt, deep=deep, schema=schema)
        with self._lock:
            if cid in self._results:
                return self._results[cid]
            if cid not in self._queue:
                self._queue[cid] = (self.inner.build_request(system, prompt, deep=deep, schema=schema)
                                    if self.inner is not None else
                                    {"system": system, "prompt": prompt, "deep": deep, "schema": schema})
            self.incomplete = True
            self.misses += 1
            return None

    def _record(self, cid: str, text: str | None) -> None:
        """Store a final result; a known id is left as it is (idempotent append)."""
        if cid in self._results:
            return
        self._results[cid] = text
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with self.store_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"custom_id": cid, "text": text}, ensure_ascii=False) + "\n")

    def flush(self) -> int:
        """Submit the queue as one batch and settle every outcome. Returns the requests sent.
        Retryable failures go back on the queue for the next pass until ``max_resubmits``."""
        with self._lock:
            pending, self._queue = self._queue, {}
            self.incomplete = False
        if not pending:
            return 0
        self.submissions += 1
        outcomes = self.backend.run(pending)
        with self._lock:
            for cid, params in pending.items():
                out = outcomes.get(cid, Outcome(EXPIRED))   # a missing result is treated as expired
                if out.type == SUCCEEDED:
                    self.summary["succeeded"] += 1
                    self._record(cid, out.text)
                    continue
                transient = out.type in (EXPIRED, CANCELED) or (out.type == ERRORED and out.retryable)
                self._attempts[cid] = self._attempts.get(cid, 0) + 1
                if transient and self._attempts[cid] <= self.max_resubmits:
                    self.summary["resubmitted"] += 1
                    self._queue[cid] = params
                else:
                    log.warning("batch request %s ended %s; using rules for it", cid[:12], out.type)
                    self.summary["failed"] += 1
                    self._record(cid, None)
        return len(pending)

    def run_until_complete(self, run_fn: Callable[[], T], max_passes: int = 12) -> T:
        """Run ``run_fn`` until a pass queues nothing, flushing one batch between passes.

        Resubmissions left over from a flush count as queued work, so the loop also ends only
        once they settle. Raises ``RuntimeError`` if ``max_passes`` is reached first: the last
        pass still contained rule-based stand-ins and must not be reported as the model's run.
        """
        for _ in range(max_passes):
            result = run_fn()
            with self._lock:
                done = not self.incomplete and not self._queue
            if done:
                return result
            self.flush()
        raise RuntimeError(f"batch run did not converge in {max_passes} passes")


class PassPending(Exception):
    """Raised by a job's ``stop`` check to end that job's pass early (see ``run_jobs``)."""


def run_jobs(llm: BatchLLM, jobs: Sequence[Callable[[Callable[[], bool]], T]],
             max_passes: int = 64, *, stop_at_pending: bool = False) -> list[T]:
    """Batch-friendly driver (plan item 1.5b): independent jobs advance together, one batch per pass.

    Each job (one instrument, or one rebalance offset of one instrument) keeps its dates in
    sequence; all jobs share each batch, so a run needs about the passes of its slowest job, not
    the sum over jobs. A job that completes a pass with no miss is final and is not re-run.

    A job is called with a ``stop`` callable. With ``stop_at_pending=False`` (default) it always
    returns False: later dates run on rule stand-ins and their questions are queued
    speculatively. The ones that do not depend on the held weight (the analysts) are the final
    questions, so they are answered early and the pass count stays lowest; the ones that do are
    paid for and never used. With ``stop_at_pending=True`` it returns True once the job has asked
    a question with no stored answer, and a job that raises ``PassPending`` then ends its pass at
    the first date still waiting: no wasted request, but each date's analysts wait for the date
    before, so more passes. Returns results in job order; ``RuntimeError`` after ``max_passes``.
    """
    results: dict[int, T] = {}
    for _ in range(max_passes):
        for j, job in enumerate(jobs):
            if j in results:
                continue
            before = llm.misses
            try:
                out = job((lambda before=before: llm.misses > before) if stop_at_pending else (lambda: False))  # type: ignore[misc]  # lambda default-arg binds this pass
            except PassPending:
                continue
            if llm.misses == before:
                results[j] = out
        with llm._lock:
            pending = bool(llm._queue)
        if len(results) == len(jobs) and not pending:
            return [results[j] for j in range(len(jobs))]
        llm.flush()
    raise RuntimeError(f"batched jobs did not converge in {max_passes} passes")


def walk_forward_jobs(llm: BatchLLM, symbols: Sequence[str], start: Any, end: Any,
                      config: dict | None = None, *, rebalance_every: int = 5,
                      offsets: Sequence[int] = (0,), stop_at_pending: bool = False,
                      max_passes: int = 64, **kwargs: Any) -> list[Any]:
    """``run_agent_backtest`` for every (symbol, offset) pair through ``run_jobs``.

    Returns ``ComparisonReport`` objects in (symbol, offset) order; each equals the report a
    direct, unbatched call returns, because every decision is computed from stored answers only.
    """
    from .backtest import run_agent_backtest

    def job(sym: str, off: int) -> Callable[[Callable[[], bool]], Any]:
        return lambda stop: run_agent_backtest(sym, start, end, config, rebalance_every=rebalance_every,
                                               llm=llm, rebalance_offset=off, stop_check=stop, **kwargs)
    return run_jobs(llm, [job(s, o) for s in symbols for o in offsets], max_passes,
                    stop_at_pending=stop_at_pending)


class FakeBatchBackend:
    """Offline backend: ``responder(params)`` returns the reply text or an ``Outcome``
    (to inject errors, expiry or cancellation). ``shuffle`` reverses result order to prove
    results are matched by ``custom_id`` only. ``batches`` records each submission's ids."""

    def __init__(self, responder: Callable[[dict[str, Any]], str | None | Outcome], *, shuffle: bool = False):
        self.responder = responder
        self.shuffle = shuffle
        self.batches: list[list[str]] = []

    def run(self, requests: dict[str, dict[str, Any]]) -> dict[str, Outcome]:
        self.batches.append(list(requests))
        items = list(requests.items())
        if self.shuffle:
            items.reverse()
        out: dict[str, Outcome] = {}
        for cid, params in items:
            r = self.responder(params)
            out[cid] = r if isinstance(r, Outcome) else Outcome(SUCCEEDED, r)
        return out


class AnthropicBatchBackend:
    """Message Batches over an ``anthropic`` client. ``read(message, model)`` turns a succeeded
    message into reply text (pass ``AnthropicLLM.read_response`` so usage and evidence are
    booked exactly as for a direct call). Polls ``retrieve`` every ``poll_s`` seconds through
    the injectable ``sleep`` until ``processing_status == "ended"``."""

    def __init__(self, client: Any, read: Callable[[Any, str], str | None], *,
                 poll_s: float = 30.0, sleep: Callable[[float], None] = time.sleep):
        self.client = client
        self.read = read
        self.poll_s = poll_s
        self.sleep = sleep

    def run(self, requests: dict[str, dict[str, Any]]) -> dict[str, Outcome]:
        batches = self.client.messages.batches
        body = []
        for cid, params in requests.items():
            params = {k: v for k, v in params.items() if k not in ("betas", "extra_body")}
            body.append({"custom_id": cid, "params": params})
        batch = batches.create(requests=body)
        while batches.retrieve(batch.id).processing_status != "ended":
            self.sleep(self.poll_s)
        out: dict[str, Outcome] = {}
        for item in batches.results(batch.id):
            res = item.result
            if res.type == SUCCEEDED:
                out[item.custom_id] = Outcome(SUCCEEDED, self.read(res.message, requests[item.custom_id]["model"]))
            elif res.type == ERRORED:
                err = getattr(getattr(res, "error", None), "error", None)
                out[item.custom_id] = Outcome(ERRORED, retryable=getattr(err, "type", "") in _RETRYABLE_ERRORS)
            else:
                out[item.custom_id] = Outcome(res.type)
        return out
