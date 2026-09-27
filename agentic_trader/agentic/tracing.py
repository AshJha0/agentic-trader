"""Observability without dependencies: spans, JSON-lines logs, Prometheus text metrics.

* ``Tracer.span(name, **attrs)`` records a span with start/end, attributes and
  status; nested spans keep their parent id. Spans mirror to the
  ``agentic_trader.trace`` logger as JSON lines when it is enabled at INFO.
* ``Metrics`` keeps counters and histograms with labels and renders them in the
  Prometheus text exposition format (``/metrics`` on the API).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from .domain import new_id, utc_now

trace_log = logging.getLogger("agentic_trader.trace")

_HIST_BUCKETS = (5.0, 10.0, 25.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0, 10000.0)


def _label_key(labels: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((k, str(v)) for k, v in labels.items()))


def _new_hist() -> dict[str, Any]:
    return {"count": 0, "sum": 0.0, "min": None, "max": None, "buckets": [0] * len(_HIST_BUCKETS)}


class Metrics:
    """Counters and histograms. A histogram keeps count, sum, min, max and cumulative counts
    for the fixed buckets, never the observations themselves, so a process-level instance
    stays the same size however many calls it has seen."""

    def __init__(self) -> None:
        self._counters: dict[str, dict[tuple, float]] = {}
        self._hists: dict[str, dict[tuple, dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def inc(self, name: str, value: float = 1.0, **labels: Any) -> None:
        with self._lock:
            self._counters.setdefault(name, {})
            key = _label_key(labels)
            self._counters[name][key] = self._counters[name].get(key, 0.0) + value

    def observe(self, name: str, value: float, **labels: Any) -> None:
        x = float(value)
        with self._lock:
            h = self._hists.setdefault(name, {}).setdefault(_label_key(labels), _new_hist())
            h["count"] += 1
            h["sum"] += x
            h["min"] = x if h["min"] is None else min(h["min"], x)
            h["max"] = x if h["max"] is None else max(h["max"], x)
            for i, b in enumerate(_HIST_BUCKETS):
                if x <= b:
                    h["buckets"][i] += 1

    def counter(self, name: str, **labels: Any) -> float:
        return self._counters.get(name, {}).get(_label_key(labels), 0.0)

    def histogram(self, name: str, **labels: Any) -> dict[str, Any] | None:
        """``{count, sum, min, max, buckets}`` of a series (cumulative bucket counts), or None."""
        with self._lock:
            h = self._hists.get(name, {}).get(_label_key(labels))
            return None if h is None else {**h, "buckets": list(h["buckets"])}

    def render(self) -> str:
        """Prometheus text exposition format."""
        lines = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                for key, v in sorted(series.items()):
                    lines.append(f"{name}{_fmt_labels(key)} {_num(v)}")
            for name, series in sorted(self._hists.items()):
                lines.append(f"# TYPE {name} histogram")
                for key, h in sorted(series.items()):
                    for b, n in zip(_HIST_BUCKETS, h["buckets"]):
                        lines.append(f"{name}_bucket{_fmt_labels(key + (('le', str(b)),))} {n}")
                    lines.append(f"{name}_bucket{_fmt_labels(key + (('le', '+Inf'),))} {h['count']}")
                    lines.append(f"{name}_sum{_fmt_labels(key)} {_num(h['sum'])}")
                    lines.append(f"{name}_count{_fmt_labels(key)} {h['count']}")
        return "\n".join(lines) + ("\n" if lines else "")


def _num(v: float) -> str:
    """A sample value, exactly: integral values as integers (a counter of 1,234,567 is not
    ``1.23457e+06``), anything else with repr's round-trip precision."""
    f = float(v)
    if f.is_integer() and abs(f) < 2 ** 53:
        return str(int(f))
    return repr(f)


def _fmt_labels(key: tuple[tuple[str, str], ...]) -> str:
    if not key:
        return ""
    inner = ",".join(f'{k}="{_escape(v)}"' for k, v in key)
    return "{" + inner + "}"


def _escape(v: str) -> str:
    """Label value escaping per the exposition format: backslash, quote, newline."""
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


@dataclass
class Span:
    id: str
    name: str
    parent_id: str | None
    started_at: float
    attributes: dict[str, Any] = field(default_factory=dict)
    ended_at: float | None = None
    status: str = "ok"
    error: str | None = None

    def set(self, **attrs: Any) -> None:
        self.attributes.update(attrs)

    def fail(self, error: str) -> None:
        self.status, self.error = "error", error

    @property
    def duration_ms(self) -> float | None:
        return None if self.ended_at is None else (self.ended_at - self.started_at) * 1000

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "parent_id": self.parent_id,
                "duration_ms": None if self.duration_ms is None else round(self.duration_ms, 2),
                "status": self.status, "error": self.error, "attributes": self.attributes}


class Tracer:
    def __init__(self, metrics: Metrics | None = None) -> None:
        self.spans: list[Span] = []
        self.metrics = metrics or Metrics()
        self._local = threading.local()
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name: str, **attrs: Any) -> Iterator[Span]:
        parent = getattr(self._local, "current", None)
        sp = Span(new_id("SPAN"), name, parent.id if parent else None, time.perf_counter(), dict(attrs))
        self._local.current = sp
        with self._lock:
            self.spans.append(sp)
        try:
            yield sp
        except Exception as e:
            sp.fail(f"{type(e).__name__}: {e}")
            raise
        finally:
            sp.ended_at = time.perf_counter()
            self._local.current = parent
            if trace_log.isEnabledFor(logging.INFO):
                trace_log.info(json.dumps({"ts": utc_now().isoformat(), **sp.to_dict()}, default=str))

    def to_list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self.spans]

    def summary(self) -> dict[str, Any]:
        spans = self.to_list()
        by_name: dict[str, list[float]] = {}
        for s in spans:
            if s["duration_ms"] is not None:
                by_name.setdefault(s["name"].split(":")[0], []).append(s["duration_ms"])
        return {"spans": len(spans), "errors": sum(s["status"] == "error" for s in spans),
                "ms_by_kind": {k: round(sum(v), 1) for k, v in by_name.items()}}


def configure_json_logging(level: int = logging.INFO) -> None:
    """Route ``agentic_trader.*`` loggers to JSON lines on stderr."""
    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            msg = record.getMessage()
            try:
                body = json.loads(msg) if msg.startswith("{") else {"message": msg}
            except json.JSONDecodeError:
                body = {"message": msg}
            return json.dumps({"ts": utc_now().isoformat(), "level": record.levelname,
                               "logger": record.name, **body}, default=str)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("agentic_trader")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False
