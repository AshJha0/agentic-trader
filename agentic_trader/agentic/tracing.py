"""Observability without dependencies: spans, JSON-lines logs, Prometheus text metrics.

* ``Tracer.span(name, **attrs)`` records a span with start/end, attributes and
  status; nested spans keep their parent id. Spans mirror to the
  ``agentic_trader.trace`` logger as JSON lines when it is enabled at INFO.
* ``Metrics`` keeps counters and histograms with labels and renders them in the
  Prometheus text exposition format (``/metrics`` on the API).
* Every span feeds ``stage_latency_ms{stage}`` and ``stage_runs_total{stage,outcome}``
  (stage = the span name before any ``:``), and ``Metrics.slo_report`` checks them against
  per-stage service-level objectives: a latency quantile and a failure rate.
* ``export_otel`` sends a tracer's spans to a local OpenTelemetry collector (optional
  ``[otel]`` extra, imported only when called).
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

    def stages(self) -> list[str]:
        with self._lock:
            keys = list(self._hists.get("stage_latency_ms", {}))
        return sorted({dict(k).get("stage", "") for k in keys} - {""})

    def stage_quantile(self, stage: str, q: float) -> float | None:
        """Upper bound of the bucket holding the ``q`` quantile of a stage's latency (ms), capped
        at the observed max (which is also the answer past the last bucket). ``None`` without
        observations."""
        h = self.histogram("stage_latency_ms", stage=stage)
        if not h or not h["count"]:
            return None
        need = q * h["count"]
        for b, n in zip(_HIST_BUCKETS, h["buckets"]):
            if n >= need:
                return min(b, h["max"])
        return h["max"]

    def stage_failure_rate(self, stage: str) -> tuple[float, int]:
        """(failure rate, runs) of a stage from ``stage_runs_total``."""
        ok = self.counter("stage_runs_total", stage=stage, outcome="ok")
        bad = self.counter("stage_runs_total", stage=stage, outcome="error")
        n = int(ok + bad)
        return (bad / n if n else 0.0), n

    def slo_report(self, slos: "dict[str, SLO] | None" = None, default: "SLO | None" = None) -> "SLOReport":
        """Check every observed stage against its objective (``slos[stage]``, else ``default``,
        else ``SLO()``). A stage with fewer than ``min_samples`` runs is listed, not judged."""
        slos = slos or {}
        rows = []
        for stage in sorted(set(self.stages()) | set(slos)):
            slo = slos.get(stage) or default or SLO()
            rate, n = self.stage_failure_rate(stage)
            lat = self.stage_quantile(stage, slo.latency_quantile)
            breaches = []
            if n >= slo.min_samples:
                if slo.latency_ms is not None and lat is not None and lat > slo.latency_ms:
                    breaches.append(f"p{round(slo.latency_quantile * 100)} latency {lat:g} ms > {slo.latency_ms:g} ms")
                if slo.max_failure_rate is not None and rate > slo.max_failure_rate:
                    breaches.append(f"failure rate {rate:.3f} > {slo.max_failure_rate:.3f}")
            rows.append(
                {
                    "stage": stage,
                    "runs": n,
                    "latency_ms": lat,
                    "quantile": slo.latency_quantile,
                    "latency_objective_ms": slo.latency_ms,
                    "failure_rate": round(rate, 6),
                    "failure_objective": slo.max_failure_rate,
                    "judged": n >= slo.min_samples,
                    "breaches": breaches,
                }
            )
        return SLOReport(rows)

    def render(self) -> str:
        """Prometheus text exposition format."""
        lines = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                lines.append(f"# TYPE {name} counter")
                for key, v in sorted(series.items()):
                    lines.append(f"{name}{_fmt_labels(key)} {_num(v)}")
            for name, hseries in sorted(self._hists.items()):
                lines.append(f"# TYPE {name} histogram")
                for key, h in sorted(hseries.items()):
                    for b, n in zip(_HIST_BUCKETS, h["buckets"]):
                        lines.append(f"{name}_bucket{_fmt_labels(key + (('le', str(b)),))} {n}")
                    lines.append(f"{name}_bucket{_fmt_labels(key + (('le', '+Inf'),))} {h['count']}")
                    lines.append(f"{name}_sum{_fmt_labels(key)} {_num(h['sum'])}")
                    lines.append(f"{name}_count{_fmt_labels(key)} {h['count']}")
        return "\n".join(lines) + ("\n" if lines else "")


@dataclass(frozen=True)
class SLO:
    """A per-stage objective: the ``latency_quantile`` of the stage's latency stays at or under
    ``latency_ms`` and its failure rate at or under ``max_failure_rate`` (``None`` = not
    checked), judged once the stage has ``min_samples`` runs. The quantile is read from the
    histogram buckets, so it is conservative (a bucket's upper bound)."""

    latency_ms: float | None = 10000.0
    max_failure_rate: float | None = 0.05
    latency_quantile: float = 0.95
    min_samples: int = 1

    def __post_init__(self) -> None:
        if not 0.0 < self.latency_quantile <= 1.0:
            raise ValueError(f"latency_quantile must be in (0, 1], got {self.latency_quantile}")
        if self.max_failure_rate is not None and not 0.0 <= self.max_failure_rate <= 1.0:
            raise ValueError(f"max_failure_rate must be in [0, 1], got {self.max_failure_rate}")
        if self.latency_ms is not None and not self.latency_ms > 0:
            raise ValueError(f"latency_ms must be positive, got {self.latency_ms}")
        if self.min_samples < 1:
            raise ValueError("min_samples must be at least 1")


def slos_from_config(config: dict[str, Any]) -> tuple[dict[str, SLO], SLO]:
    """``agentic.slos``: ``{"default": {...}, "<stage>": {"latency_ms": .., "max_failure_rate": ..,
    "latency_quantile": .., "min_samples": ..}}`` -> (per-stage objectives, default). A stage
    entry inherits every field it does not set from ``default``."""
    raw = dict((config.get("agentic") or {}).get("slos") or {})
    default = SLO(**raw.pop("default", {}))
    return {k: SLO(**{**default.__dict__, **v}) for k, v in raw.items()}, default


@dataclass
class SLOReport:
    rows: list[dict[str, Any]]

    @property
    def breaches(self) -> list[dict[str, Any]]:
        return [r for r in self.rows if r["breaches"]]

    @property
    def ok(self) -> bool:
        return not self.breaches

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "stages": self.rows}

    def to_markdown(self) -> str:
        lines = [
            "| stage | runs | latency (ms) | objective | failure rate | objective | status |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in self.rows:
            if r["breaches"]:
                status = "BREACH: " + "; ".join(r["breaches"])
            else:
                status = "ok" if r["judged"] else "too few runs"
            lines.append(
                f"| {r['stage']} | {r['runs']} | {_opt(r['latency_ms'])} | "
                f"{_opt(r['latency_objective_ms'])} | {r['failure_rate']:.3f} | "
                f"{_opt(r['failure_objective'])} | {status} |"
            )
        return "\n".join(lines)


def _opt(v: Any) -> str:
    return "-" if v is None else f"{v:g}"


def _num(v: float) -> str:
    """A sample value, exactly: integral values as integers (a counter of 1,234,567 is not
    ``1.23457e+06``), anything else with repr's round-trip precision."""
    f = float(v)
    if f.is_integer() and abs(f) < 2**53:
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
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "duration_ms": None if self.duration_ms is None else round(self.duration_ms, 2),
            "status": self.status,
            "error": self.error,
            "attributes": self.attributes,
        }


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
            stage = name.split(":")[0]
            dur = sp.duration_ms
            assert dur is not None  # ended_at was set just above
            self.metrics.observe("stage_latency_ms", dur, stage=stage)
            self.metrics.inc("stage_runs_total", stage=stage, outcome=sp.status)
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
        return {
            "spans": len(spans),
            "errors": sum(s["status"] == "error" for s in spans),
            "ms_by_kind": {k: round(sum(v), 1) for k, v in by_name.items()},
        }


def configure_json_logging(level: int = logging.INFO) -> None:
    """Route ``agentic_trader.*`` loggers to JSON lines on stderr."""

    class JsonFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            msg = record.getMessage()
            try:
                body = json.loads(msg) if msg.startswith("{") else {"message": msg}
            except json.JSONDecodeError:
                body = {"message": msg}
            return json.dumps(
                {"ts": utc_now().isoformat(), "level": record.levelname, "logger": record.name, **body}, default=str
            )

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("agentic_trader")
    root.handlers = [handler]
    root.setLevel(level)
    root.propagate = False


def export_otel(
    tracer: "Tracer",
    endpoint: str = "http://localhost:4318/v1/traces",
    *,
    service_name: str = "agentic-trader",
    exporter: Any = None,
) -> int:
    """Send a tracer's finished spans to an OpenTelemetry collector over OTLP/HTTP (a local
    one by default). Needs the optional ``[otel]`` extra, imported only here; ``exporter``
    replaces the OTLP exporter (tests pass an in-memory one). Returns the spans exported."""
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.trace import Status, StatusCode, set_span_in_context
    except ImportError as e:  # pragma: no cover - only without the extra
        raise ImportError(
            "OpenTelemetry export needs the optional extra: pip install opentelemetry-sdk opentelemetry-exporter-otlp-proto-http ([otel] extra)"
        ) from e
    if exporter is None:
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        except ImportError as e:  # pragma: no cover
            raise ImportError("OTLP export needs opentelemetry-exporter-otlp-proto-http ([otel] extra)") from e
        exporter = OTLPSpanExporter(endpoint=endpoint)
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    otel = provider.get_tracer("agentic_trader")
    with tracer._lock:
        ended = [(s, s.ended_at) for s in tracer.spans if s.ended_at is not None]
    spans = [s for s, _ in ended]
    offset_ns = time.time_ns() - int(time.perf_counter() * 1e9)  # perf_counter -> wall clock
    made: dict[str, Any] = {}
    for s in sorted(spans, key=lambda x: x.started_at):
        parent = made.get(s.parent_id) if s.parent_id is not None else None
        ctx = set_span_in_context(parent) if parent is not None else None
        o = otel.start_span(
            s.name,
            context=ctx,
            start_time=offset_ns + int(s.started_at * 1e9),
            attributes={k: v if isinstance(v, (str, bool, int, float)) else str(v) for k, v in s.attributes.items()},
        )
        if s.status == "error":
            o.set_status(Status(StatusCode.ERROR, s.error or ""))
        made[s.id] = o
    for s, ended_at in sorted(ended, key=lambda x: x[1], reverse=True):
        made[s.id].end(end_time=offset_ns + int(ended_at * 1e9))
    provider.shutdown()
    return len(spans)
