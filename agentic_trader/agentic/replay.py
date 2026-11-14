"""Replay mode: re-run a recorded ``TaskRun`` with every market-data call and every model call
served from the payloads recorded the first time, and check it reaches the same decision.

Recording happens at the two boundaries where the outside world enters a run:

* ``RecordingMarketData`` wraps the desk's data provider. Every tool and every analyst reads
  market data through it (the harness's ``RecordingProvider`` and ``DeskTools`` both sit on
  top of ``graph.provider``), so the tape holds exactly what the run saw.
* ``RecordingLLM`` wraps the model (``complete`` and, when the backend has it,
  ``complete_json``), keyed by the full request: system text, prompt, tier and schema.

A ``Recording`` is the tape plus the task, the run's book, the configuration (with the
decision memory switched off, since the memory file is state outside the run) and the
decision the run reached. ``replay`` rebuilds the graph and harness on a ``ReplayMarketData``
and a ``ReplayLLM`` and runs the task again. There is no live provider or model behind
either: a request that is not on the tape raises ``ReplayMissingPayload``, and because an
agent may catch a model error and fall back to its rules, every miss is also logged on the
tape and ``replay`` raises after the run if there was any, so a gap can never pass silently.

The same ``ReplayLLM`` is the fixture mechanism for model tests: record a run once against a
local model, save it, and serve the model's answers from the file in an offline test.

Recordings are pickled (exact DataFrames and floats, so the replay is bit-for-bit). Load
only recordings you made yourself: unpickling runs code from the file. Since v0.17 (review
A7, second half) that rule is enforced: ``Recording.save`` writes the SHA-256 of the file's
bytes to a digest allowlist outside the recording directory (``replay_allowlist_path``:
``$AGENTIC_TRADER_REPLAY_ALLOWLIST`` or ``~/.agentic_trader/replay_allowlist.txt``), and
``load_recording`` hashes the bytes and refuses to unpickle a file whose digest is not listed
(an edited recording, or one made on another machine). ``allow_recording(path)`` lists a file
you have checked; ``trust=True`` skips the check for one call.

Request keys (v0.17 R2.4, format 2) are SHA-256 digests of a canonical JSON form of the
request (``canonical``: sorted keys, floats by ``repr``, dates ISO, frames by
``to_json(orient="split")``), not of a pickle byte stream, so a key does not change when
pandas, numpy or Python change their pickle output. Format-1 recordings (pickle keys) cannot
be re-keyed, because a digest cannot be inverted; ``load_recording`` refuses them with a
message to record the run again.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import pickle
import threading
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from ..data.base import MarketDataProvider
from ..memory import series_basis

FORMAT_VERSION = 2  # 2: canonical JSON request keys (v0.17); 1: pickle keys
DEFAULT_DIR = "results/replay"
ALLOWLIST_ENV = "AGENTIC_TRADER_REPLAY_ALLOWLIST"


class ReplayUntrusted(ValueError):
    """A recording whose bytes are not on the digest allowlist (not made, or not checked, here)."""


def replay_allowlist_path() -> Path:
    """Where recording digests are listed: ``$AGENTIC_TRADER_REPLAY_ALLOWLIST`` when set, else
    ``~/.agentic_trader/replay_allowlist.txt`` (outside any recording directory)."""
    import os

    env = os.environ.get(ALLOWLIST_ENV)
    return Path(env) if env else Path.home() / ".agentic_trader" / "replay_allowlist.txt"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _allowed_digests(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    return {ln.split()[0] for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def allow_recording(path: str | Path, allowlist: str | Path | None = None) -> str:
    """Add the SHA-256 of ``path``'s current bytes to the allowlist; returns the digest."""
    al = Path(allowlist) if allowlist is not None else replay_allowlist_path()
    d = _digest(Path(path).read_bytes())
    if d not in _allowed_digests(al):
        al.parent.mkdir(parents=True, exist_ok=True)
        with open(al, "a", encoding="utf-8") as f:
            f.write(f"{d} {Path(path).name}\n")
    return d


class ReplayMissingPayload(RuntimeError):
    """A replayed run asked for data or a model answer that the recording does not hold."""


class ReplayMismatch(AssertionError):
    """A replayed run reached a different decision (or end state) from the recorded one."""


def canonical(obj: Any) -> Any:
    """A JSON-ready, version-stable form of a request part. Types are tagged where two types
    could print alike (a float and its string, a tuple and a list, a date and its ISO text).
    Raises ``TypeError`` for a type it does not know rather than guess an unstable form."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, np.integer)) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        x = float(obj)
        return {"$f": repr(x)}
    if isinstance(obj, Enum):
        return {"$enum": type(obj).__name__, "v": canonical(obj.value)}
    if isinstance(obj, pd.Timestamp):
        return {"$ts": obj.isoformat()}
    if isinstance(obj, datetime):
        return {"$dt": obj.isoformat()}
    if isinstance(obj, date):
        return {"$d": obj.isoformat()}
    if isinstance(obj, pd.DataFrame):
        return {"$df": obj.to_json(orient="split", date_format="iso", double_precision=15)}
    if isinstance(obj, pd.Series):
        return {"$s": obj.to_json(orient="split", date_format="iso", double_precision=15)}
    if isinstance(obj, pd.Index):
        return {"$ix": [canonical(v) for v in obj.tolist()]}
    if isinstance(obj, np.ndarray):
        return {"$nd": [canonical(v) for v in obj.tolist()]}
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {"$dc": type(obj).__name__, "v": {f.name: canonical(getattr(obj, f.name)) for f in dataclasses.fields(obj)}}
    if isinstance(obj, dict):
        items = sorted(((json.dumps(canonical(k), sort_keys=True), canonical(v)) for k, v in obj.items()))
        return {"$map": [[k, v] for k, v in items]}
    if isinstance(obj, tuple):
        return {"$t": [canonical(v) for v in obj]}
    if isinstance(obj, (list, set, frozenset)):
        vals = [canonical(v) for v in obj]
        if isinstance(obj, (set, frozenset)):
            return {"$set": sorted(vals, key=lambda v: json.dumps(v, sort_keys=True))}
        return vals
    raise TypeError(f"replay key: no canonical form for {type(obj).__name__}")


def _key(kind: str, *parts: Any) -> str:
    body = json.dumps(canonical((kind, parts)), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("ascii")).hexdigest()


class Tape:
    """Recorded results keyed by request digest. Repeated identical requests are kept in
    order; a replay serves them in that order and then repeats the last one (identical
    requests of a deterministic source give identical answers)."""

    def __init__(self, entries: dict[str, list[tuple[str, Any]]] | None = None, labels: dict[str, str] | None = None) -> None:
        self.entries: dict[str, list[tuple[str, Any]]] = entries or {}
        self.labels: dict[str, str] = labels or {}
        self.misses: list[str] = []
        self._served: dict[str, int] = {}
        self._lock = threading.Lock()

    def put(self, key: str, label: str, outcome: str, value: Any) -> None:
        with self._lock:
            self.entries.setdefault(key, []).append((outcome, copy.deepcopy(value)))
            self.labels[key] = label

    def call(self, key: str, label: str, fn: Callable[[], Any]) -> Any:
        """Record ``fn()`` (its value or the exception it raised) under ``key``."""
        try:
            value = fn()
        except Exception as e:
            self.put(key, label, "raise", e)
            raise
        self.put(key, label, "return", value)
        return value

    def serve(self, key: str, label: str) -> Any:
        with self._lock:
            got = self.entries.get(key)
            if not got:
                self.misses.append(label)
                raise ReplayMissingPayload(f"no recorded payload for {label}")
            i = self._served.get(key, 0)
            self._served[key] = i + 1
            outcome, value = got[min(i, len(got) - 1)]
        if outcome == "raise":
            raise copy.deepcopy(value)
        return copy.deepcopy(value)

    def __len__(self) -> int:
        return sum(len(v) for v in self.entries.values())


_DATA_METHODS = ("history", "news", "social", "fundamentals", "macro", "carry_series", "risk_free_series")


class RecordingMarketData(MarketDataProvider):
    """Pass-through provider that records every answer of ``inner``."""

    def __init__(self, inner: MarketDataProvider, tape: Tape | None = None) -> None:
        super().__init__(inner.config)
        self.inner, self.tape = inner, tape if tape is not None else Tape()
        self.name, self.real_world = inner.name, inner.real_world
        self.price_basis = series_basis(inner)
        self.macro_sources = inner.macro_sources

    def reconfigured(self, config: dict) -> "MarketDataProvider":
        return RecordingMarketData(self.inner.reconfigured(config), self.tape)

    def _rec(self, method: str, *args: Any) -> Any:
        return self.tape.call(
            _key("data", method, args), f"market data {method}{_short(args)}", lambda: getattr(self.inner, method)(*args)
        )

    def history(self, instrument, start, end):
        return self._rec("history", instrument, start, end)

    def news(self, instrument, as_of, lookback_days):
        return self._rec("news", instrument, as_of, lookback_days)

    def social(self, instrument, as_of, lookback_days):
        return self._rec("social", instrument, as_of, lookback_days)

    def fundamentals(self, instrument, as_of):
        return self._rec("fundamentals", instrument, as_of)

    def macro(self, instrument, as_of):
        return self._rec("macro", instrument, as_of)

    def carry_series(self, instrument, dates):
        return self._rec("carry_series", instrument, dates)

    def risk_free_series(self, dates):
        return self._rec("risk_free_series", dates)


class ReplayMarketData(MarketDataProvider):
    """Serves market data from a tape only; nothing behind it."""

    def __init__(self, tape: Tape, config: dict, attrs: dict[str, Any]) -> None:
        super().__init__(config)
        self.tape = tape
        self.name = attrs.get("name", "replay")
        self.real_world = attrs.get("real_world", True)
        self.price_basis = attrs.get("price_basis", "close")

    def reconfigured(self, config: dict) -> "MarketDataProvider":
        return ReplayMarketData(
            self.tape, config, {"name": self.name, "real_world": self.real_world, "price_basis": self.price_basis}
        )

    def _serve(self, method: str, *args: Any) -> Any:
        return self.tape.serve(_key("data", method, args), f"market data {method}{_short(args)}")

    def history(self, instrument, start, end):
        return self._serve("history", instrument, start, end)

    def news(self, instrument, as_of, lookback_days):
        return self._serve("news", instrument, as_of, lookback_days)

    def social(self, instrument, as_of, lookback_days):
        return self._serve("social", instrument, as_of, lookback_days)

    def fundamentals(self, instrument, as_of):
        return self._serve("fundamentals", instrument, as_of)

    def macro(self, instrument, as_of):
        return self._serve("macro", instrument, as_of)

    def carry_series(self, instrument, dates):
        return self._serve("carry_series", instrument, dates)

    def risk_free_series(self, dates):
        return self._serve("risk_free_series", dates)


def _llm_key(method: str, system: str, prompt: str, deep: bool, schema: Any = None) -> str:
    return _key(
        "llm", method, system, prompt, bool(deep), None if schema is None else json.dumps(schema, sort_keys=True, default=str)
    )


class RecordingLLM:
    """Pass-through model wrapper recording each answer. ``complete_json`` and ``last_call``
    exist on the wrapper only when the inner backend has them, so callers that probe for
    structured outputs take the same branch as without the wrapper."""

    def __init__(self, inner: Any, tape: Tape | None = None) -> None:
        self.inner, self.tape = inner, tape if tape is not None else Tape()
        self.has_json = hasattr(inner, "complete_json")

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        return self.tape.call(
            _llm_key("complete", system, prompt, deep),
            f"model complete (deep={deep})",
            lambda: self.inner.complete(system, prompt, deep=deep),
        )

    def __getattr__(self, name: str) -> Any:
        if name == "complete_json" and self.has_json:

            def complete_json(system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
                return self.tape.call(
                    _llm_key("complete_json", system, prompt, deep, schema),
                    f"model complete_json (deep={deep})",
                    lambda: self.inner.complete_json(system, prompt, deep=deep, schema=schema),
                )

            return complete_json
        if name in ("inner", "tape", "has_json"):
            raise AttributeError(name)
        return getattr(self.inner, name)


class ReplayLLM:
    """A model that only answers from a tape. Usable on its own as an offline test fixture
    (``ReplayLLM.from_recording(load_recording(path))``)."""

    def __init__(self, tape: Tape, has_json: bool = False) -> None:
        self.tape, self.has_json = tape, has_json

    @classmethod
    def from_recording(cls, rec: "Recording") -> "ReplayLLM":
        if rec.llm_tape is None:
            raise ReplayMissingPayload("the recording has no model calls (it was made offline)")
        return cls(Tape(rec.llm_tape.entries, rec.llm_tape.labels), rec.llm_has_json)

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        return self.tape.serve(_llm_key("complete", system, prompt, deep), f"model complete (deep={deep})")

    def __getattr__(self, name: str) -> Any:
        if name == "complete_json" and self.has_json:

            def complete_json(system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
                return self.tape.serve(
                    _llm_key("complete_json", system, prompt, deep, schema), f"model complete_json (deep={deep})"
                )

            return complete_json
        raise AttributeError(name)


def _short(args: tuple) -> str:
    out = []
    for a in args:
        s = getattr(a, "symbol", None) or (a.isoformat() if isinstance(a, date) else None)
        out.append(str(s) if s is not None else type(a).__name__ if hasattr(a, "__len__") else repr(a))
    return "(" + ", ".join(out) + ")"


def decision_fingerprint(decision: Any) -> dict[str, Any] | None:
    """The decision as a dict without its evidence ids (fresh random ids on every run);
    the number of cited ids is kept."""
    if decision is None:
        return None
    d = decision.to_dict() if hasattr(decision, "to_dict") else dict(decision)
    d = dict(d)
    d["evidence_ids"] = len(d.get("evidence_ids") or ())
    return d


@dataclass
class Recording:
    task_id: str
    task: dict[str, Any]
    positions: dict[str, float] | None
    config: dict[str, Any]
    provider_attrs: dict[str, Any]
    data_tape: Tape
    llm_tape: Tape | None
    llm_has_json: bool
    state: str
    decision: dict[str, Any] | None
    evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    version: int = FORMAT_VERSION

    def save(self, path: str | Path, allowlist: str | Path | None = None) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        body = {k: v for k, v in self.__dict__.items() if k not in ("data_tape", "llm_tape")}
        body["data_tape"] = (self.data_tape.entries, self.data_tape.labels)
        body["llm_tape"] = None if self.llm_tape is None else (self.llm_tape.entries, self.llm_tape.labels)
        p.write_bytes(pickle.dumps(body, protocol=4))
        allow_recording(p, allowlist)
        return p


def load_recording(path: str | Path, *, allowlist: str | Path | None = None, trust: bool = False) -> Recording:
    """Load a recording written by ``Recording.save``. The file's SHA-256 must be on the digest
    allowlist (``replay_allowlist_path``) before anything is unpickled; ``trust=True`` skips
    that check for a file you have inspected yourself. Raises ``ReplayUntrusted`` otherwise."""
    data = Path(path).read_bytes()
    if not trust:
        al = Path(allowlist) if allowlist is not None else replay_allowlist_path()
        if _digest(data) not in _allowed_digests(al):
            raise ReplayUntrusted(
                f"{path}: SHA-256 {_digest(data)[:16]}... is not on the replay allowlist {al}; unpickling "
                "runs code from the file, so only recordings saved here (or added with "
                "allow_recording after checking them) are loaded"
            )
    body = pickle.loads(data)  # noqa: S301 - digest-allowlisted own recordings only
    if body.get("version") == 1:
        raise ValueError(
            f"{path}: replay format 1 keys requests by a pickle digest, which v0.17 replaced "
            "with canonical JSON keys (format 2); a digest cannot be re-keyed, so record the "
            "run again with `task --record`"
        )
    if body.get("version") != FORMAT_VERSION:
        raise ValueError(f"{path}: replay format {body.get('version')!r}, expected {FORMAT_VERSION}")
    body["data_tape"] = Tape(*body["data_tape"])
    body["llm_tape"] = None if body["llm_tape"] is None else Tape(*body["llm_tape"])
    return Recording(**body)


def recording_path(task_id: str, directory: str | Path = DEFAULT_DIR) -> Path:
    if not task_id or any(c in task_id for c in "/\\:") or task_id.startswith("."):
        raise ValueError(f"not a task run id: {task_id!r}")
    return Path(directory) / f"{task_id}.replay.pkl"


class Recorder:
    """Builds a graph whose provider and model are recorded, and turns a finished run into
    a ``Recording``. The decision memory is switched off (``memory_path=None``)."""

    def __init__(
        self, config: dict, provider: MarketDataProvider | None = None, llm: Any = None, on_event: Callable | None = None
    ) -> None:
        from ..config import make_config
        from ..data import get_provider
        from ..graph import TradingGraph
        from ..llm import get_llm

        cfg = make_config(config)
        cfg["memory_path"] = None
        self.config = cfg
        inner = provider or get_provider(cfg)
        self.provider = RecordingMarketData(inner)
        model = llm if llm is not None else get_llm(cfg)
        self.llm = RecordingLLM(model) if model is not None else None
        self.graph = TradingGraph(cfg, provider=self.provider, llm=self.llm, on_event=on_event)

    def recording(self, run: Any, positions: dict[str, float] | None = None) -> Recording:
        t = run.task
        return Recording(
            task_id=run.id,
            task={
                "symbol": t.symbol,
                "as_of": t.as_of,
                "role": t.role.value,
                "current_weight": t.current_weight,
                "question": t.question,
                "id": t.id,
            },
            positions=None if positions is None else dict(positions),
            config=copy.deepcopy(self.config),
            provider_attrs={
                "name": self.provider.name,
                "real_world": self.provider.real_world,
                "price_basis": self.provider.price_basis,
            },
            data_tape=self.provider.tape,
            llm_tape=self.llm.tape if self.llm else None,
            llm_has_json=bool(self.llm and self.llm.has_json),
            state=run.state.value,
            decision=decision_fingerprint(run.decision),
            evidence_rows=run.evidence.summary_rows(),
        )


def record_task(
    config: dict,
    task: Any,
    positions: dict[str, float] | None = None,
    provider: MarketDataProvider | None = None,
    llm: Any = None,
    harness_kwargs: dict[str, Any] | None = None,
) -> tuple[Any, Recording]:
    """Run ``task`` on a recording graph; returns ``(run, recording)``."""
    from .harness import AgentHarness

    rec = Recorder(config, provider, llm, on_event=lambda *_: None)
    harness = AgentHarness(rec.graph, positions=positions, **(harness_kwargs or {}))
    try:
        run = harness.run(task)
    finally:
        harness.close()
    return run, rec.recording(run, positions)


@dataclass
class ReplayResult:
    run: Any
    recorded: dict[str, Any] | None
    replayed: dict[str, Any] | None
    recorded_state: str
    replayed_state: str

    @property
    def matches(self) -> bool:
        return self.recorded == self.replayed and self.recorded_state == self.replayed_state

    def diff(self) -> dict[str, tuple[Any, Any]]:
        a, b = self.recorded or {}, self.replayed or {}
        out = {k: (a.get(k), b.get(k)) for k in sorted(set(a) | set(b)) if a.get(k) != b.get(k)}
        if self.recorded_state != self.replayed_state:
            out["state"] = (self.recorded_state, self.replayed_state)
        return out


def replay(rec: Recording, *, check: bool = True) -> ReplayResult:
    """Re-run a recording offline. Raises ``ReplayMissingPayload`` if the run asked for anything
    the tape does not hold and, with ``check``, ``ReplayMismatch`` if the decision differs."""
    from ..graph import TradingGraph
    from .domain import Role, Task
    from .harness import AgentHarness

    cfg = copy.deepcopy(rec.config)
    cfg["memory_path"] = None
    cfg["llm_provider"] = "offline"  # never build a live backend; the model is the tape
    data = Tape(rec.data_tape.entries, rec.data_tape.labels)
    provider = ReplayMarketData(data, cfg, rec.provider_attrs)
    llm = None
    if rec.llm_tape is not None:
        llm = ReplayLLM(Tape(rec.llm_tape.entries, rec.llm_tape.labels), rec.llm_has_json)
    graph = TradingGraph(cfg, provider=provider, llm=llm, on_event=lambda *_: None)
    t = rec.task
    task = Task(t["symbol"], t["as_of"], Role(t["role"]), t["current_weight"], t["question"] or "", id=t["id"])
    harness = AgentHarness(graph, positions=rec.positions)
    try:
        run = harness.run(task)
    finally:
        harness.close()
    misses = data.misses + (llm.tape.misses if llm is not None else [])
    if misses:
        raise ReplayMissingPayload(
            f"replay of {rec.task_id} asked for {len(misses)} unrecorded payload(s): " + "; ".join(sorted(set(misses))[:5])
        )
    res = ReplayResult(run, rec.decision, decision_fingerprint(run.decision), rec.state, run.state.value)
    if check and not res.matches:
        raise ReplayMismatch(f"replay of {rec.task_id} diverged: {res.diff()}")
    return res
