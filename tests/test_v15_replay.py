"""v0.15 P4 items 4.8 (replay mode) and 4.9 (stage SLOs, optional OpenTelemetry export,
golden transcripts of the canonical plan).

Golden files live in tests/golden/. Regenerate them deliberately, never to make a red test
green without reading the diff:

    AGENTIC_TRADER_REGEN_GOLDEN=1 python -m pytest tests/test_v15_replay.py -k golden
"""

import json
import os
from datetime import date
from pathlib import Path

import pytest

from agentic_trader import make_config
from agentic_trader.agentic import Role, Task
from agentic_trader.agentic.replay import (
    RecordingLLM,
    ReplayLLM,
    ReplayMismatch,
    ReplayMissingPayload,
    Tape,
    decision_fingerprint,
    load_recording,
    record_task,
    recording_path,
    replay,
)
from agentic_trader.agentic.tracing import SLO, Metrics, Tracer, export_otel, slos_from_config

GOLDEN = Path(__file__).parent / "golden"
REGEN = os.environ.get("AGENTIC_TRADER_REGEN_GOLDEN") == "1"
FROZEN_STATES = {  # the canonical (rules) plan on three frozen states
    "aapl_2024-03-01": ("AAPL", date(2024, 3, 1), None),
    "eurusd_2024-03-01": ("EURUSD", date(2024, 3, 1), None),
    "nvda_2023-06-01_held": ("NVDA", date(2023, 6, 1), 0.3),
}


class JsonLLM:
    """A deterministic stand-in model: one valid-looking JSON object for every role."""

    def __init__(self):
        self.calls = 0

    def complete(self, system, prompt, *, deep):
        self.calls += 1
        return json.dumps(
            {
                "signal": "bullish",
                "confidence": 0.6,
                "summary": "steady trend",
                "winner": "bull",
                "score": 0.2,
                "action": "BUY",
                "target_weight": 0.2,
                "rationale": "trend",
                "recommended_weight": 0.2,
                "argument": "ok",
                "concerns": [],
                "confidence_multiplier": 1.0,
            }
        )


def _cfg():
    return make_config(memory_path=None)


@pytest.fixture(scope="module")
def recorded():
    out = {}
    for name, (sym, d, w) in FROZEN_STATES.items():
        out[name] = record_task(_cfg(), Task(sym, d, Role.TRADER, w))
    return out


# ------------------------------------------------------------------ 4.8 replay
def test_replay_reaches_the_recorded_decision_on_every_frozen_state(recorded):
    for name, (run, rec) in recorded.items():
        assert run.state.value == "COMPLETED", name
        assert len(rec.data_tape) > 0 and rec.llm_tape is None
        res = replay(rec)
        assert res.matches and res.replayed == decision_fingerprint(run.decision)
        assert res.run.id == run.id


def test_replay_serves_model_answers_from_the_tape_and_never_calls_the_model(tmp_path):
    llm = JsonLLM()
    run, rec = record_task(_cfg(), Task("MSFT", date(2024, 3, 1)), llm=llm)
    made = llm.calls
    assert made > 0 and len(rec.llm_tape) == made
    rec2 = load_recording(rec.save(tmp_path / "r.replay.pkl"))
    res = replay(rec2)
    assert res.matches and llm.calls == made  # the live model was not touched


def test_missing_data_payload_fails_loudly_instead_of_falling_through(recorded):
    _, rec = recorded["aapl_2024-03-01"]
    entries = dict(rec.data_tape.entries)
    entries.pop(next(iter(entries)))
    rec.data_tape, saved = Tape(entries, rec.data_tape.labels), rec.data_tape
    try:
        with pytest.raises(ReplayMissingPayload, match="unrecorded payload"):
            replay(rec)
    finally:
        rec.data_tape = saved


def test_missing_model_answer_fails_loudly_even_though_agents_fall_back_to_rules():
    run, rec = record_task(_cfg(), Task("MSFT", date(2024, 3, 1)), llm=JsonLLM())
    rec.llm_tape = Tape({}, {})  # every model answer gone
    with pytest.raises(ReplayMissingPayload, match="model complete"):
        replay(rec)


def test_a_diverging_decision_is_reported(recorded):
    _, rec = recorded["eurusd_2024-03-01"]
    saved = rec.decision
    rec.decision = {**saved, "target_weight": 123.0}
    try:
        with pytest.raises(ReplayMismatch, match="target_weight"):
            replay(rec)
        assert not replay(rec, check=False).matches
    finally:
        rec.decision = saved


def test_replay_llm_is_a_standalone_fixture_and_hides_complete_json_unless_recorded():
    tape = Tape()
    live = RecordingLLM(JsonLLM(), tape)
    assert not hasattr(live, "complete_json")
    answer = live.complete("sys", "prompt", deep=False)
    fixture = ReplayLLM(Tape(tape.entries, tape.labels))
    assert fixture.complete("sys", "prompt", deep=False) == answer
    assert not hasattr(fixture, "complete_json")
    with pytest.raises(ReplayMissingPayload):
        fixture.complete("sys", "another prompt", deep=False)
    with pytest.raises(ReplayMissingPayload):
        fixture.complete("sys", "prompt", deep=True)  # the tier is part of the key


def test_recorded_exceptions_are_replayed():
    class Boom:
        def complete(self, system, prompt, *, deep):
            raise TimeoutError("slow")

    tape = Tape()
    with pytest.raises(TimeoutError):
        RecordingLLM(Boom(), tape).complete("s", "p", deep=False)
    with pytest.raises(TimeoutError, match="slow"):
        ReplayLLM(tape).complete("s", "p", deep=False)


def test_recording_path_refuses_path_tricks():
    assert recording_path("TASK-1", "d") == Path("d") / "TASK-1.replay.pkl"
    for bad in ("../x", "a/b", "", ".hidden", "c:x"):
        with pytest.raises(ValueError):
            recording_path(bad)


def test_cli_task_record_then_replay(tmp_path, capsys):
    from agentic_trader.cli import main

    d = str(tmp_path / "rec")
    assert main(["task", "AAPL", "--date", "2024-03-01", "--record", d]) == 0
    out = capsys.readouterr().out
    task_id = out.split("agentic-trader replay ")[1].split()[0]
    assert main(["replay", task_id, "--dir", d]) == 0
    assert "MATCH" in capsys.readouterr().out
    assert main(["replay", "TASK-nope", "--dir", d]) == 2


# --------------------------------------------------------------------- 4.9 SLOs
def test_spans_feed_stage_metrics_and_the_slo_report_flags_breaches():
    m = Metrics()
    tr = Tracer(m)
    for _ in range(3):
        with tr.span("tool:market_data.history"):
            pass
    with pytest.raises(RuntimeError):
        with tr.span("tool:x"):
            raise RuntimeError("down")
    assert m.stages() == ["tool"]
    assert m.stage_failure_rate("tool") == (0.25, 4)
    rep = m.slo_report({"tool": SLO(latency_ms=10_000, max_failure_rate=0.1)})
    assert not rep.ok and "failure rate 0.250 > 0.100" in rep.breaches[0]["breaches"][0]
    assert "BREACH" in rep.to_markdown()
    assert m.slo_report({"tool": SLO(max_failure_rate=0.5)}).ok
    assert m.slo_report({"tool": SLO(max_failure_rate=0.1, min_samples=10)}).ok  # too few runs to judge
    assert "stage_latency_ms_bucket" in m.render() and 'stage_runs_total{outcome="error",stage="tool"} 1' in m.render()


def test_latency_quantile_reads_buckets_and_breaches_a_tight_objective():
    m = Metrics()
    for ms in (3, 4, 30, 40, 900):
        m.observe("stage_latency_ms", ms, stage="agent")
        m.inc("stage_runs_total", stage="agent", outcome="ok")
    assert m.stage_quantile("agent", 0.5) == 50.0
    assert m.stage_quantile("agent", 1.0) == 900.0  # capped at the observed max
    rep = m.slo_report(default=SLO(latency_ms=100.0))
    assert rep.breaches[0]["stage"] == "agent" and "p95 latency 900 ms > 100 ms" in rep.breaches[0]["breaches"]
    assert m.stage_quantile("nothing", 0.5) is None


def test_slos_come_from_config_with_stage_entries_inheriting_the_default():
    cfg = {"agentic": {"slos": {"default": {"latency_ms": 500, "max_failure_rate": 0.01}, "tool": {"latency_ms": 2000}}}}
    per, default = slos_from_config(cfg)
    assert default == SLO(latency_ms=500, max_failure_rate=0.01)
    assert per["tool"] == SLO(latency_ms=2000, max_failure_rate=0.01)
    assert slos_from_config({}) == ({}, SLO())
    for bad in ({"latency_quantile": 0}, {"max_failure_rate": 2}, {"min_samples": 0}, {"latency_ms": -1}):
        with pytest.raises(ValueError):
            SLO(**bad)


def test_a_real_run_meets_generous_slos(recorded):
    run, _ = recorded["aapl_2024-03-01"]
    rep = run.tracer.metrics.slo_report(default=SLO(latency_ms=None, max_failure_rate=0.5))
    stages = {r["stage"] for r in rep.rows}
    assert {"plan", "prepare", "agent"} <= stages and rep.ok


def test_otel_export_to_an_in_memory_exporter():
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    tr = Tracer()
    with tr.span("plan", k="v"):
        with tr.span("tool:x"):
            pass
    exp = InMemorySpanExporter()
    assert export_otel(tr, exporter=exp) == 2
    got = {s.name: s for s in exp.get_finished_spans()}
    assert got["tool:x"].parent.span_id == got["plan"].context.span_id


def test_otel_export_without_the_extra_says_how_to_install(monkeypatch):
    import builtins

    real = builtins.__import__

    def no_otel(name, *a, **k):
        if name.startswith("opentelemetry"):
            raise ImportError(name)
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_otel)
    with pytest.raises(ImportError, match=r"\[otel\]"):
        export_otel(Tracer())


# ----------------------------------------------------------- golden transcripts
def _round(x):
    if isinstance(x, float):
        return float(f"{x:.6g}")
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v) for v in x]
    return x


def transcript(run) -> dict:
    """What the canonical plan did, without ids, clocks or free text that carries numbers."""
    d = decision_fingerprint(run.decision) or {}
    return _round(
        {
            "state": run.state.value,
            "plan_source": run.plan.source,
            "steps": [[s.type.value, s.name, {k: str(v) for k, v in sorted(s.arguments.items())}] for s in run.plan.steps],
            "states": [h[0] for h in run.history],
            "decision": {k: d.get(k) for k in ("action", "target_weight", "confidence", "evidence_ids")},
            "findings": [[f.agent, round(f.confidence, 4)] for f in run.findings],
            "evidence_sources": sorted({r["source"] for r in run.evidence.summary_rows()}),
            "errors": list(run.errors),
        }
    )


@pytest.mark.parametrize("name", sorted(FROZEN_STATES))
def test_golden_transcript_of_the_canonical_plan(recorded, name):
    got = transcript(recorded[name][0])
    path = GOLDEN / f"{name}.json"
    if REGEN or not path.exists():
        if not REGEN:
            pytest.fail(f"missing golden file {path}; set AGENTIC_TRADER_REGEN_GOLDEN=1 to write it")
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(got, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    assert got == json.loads(path.read_text(encoding="utf-8"))
