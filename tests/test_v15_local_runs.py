"""Offline checks for scripts/v15_local_runs.py and the recorded local-model plan fixture."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import v15_governance as gov  # noqa: E402
import v15_local_runs as runs  # noqa: E402


def test_synthetic_inputs_are_well_formed():
    assert len(runs.MACRO_CASES) == 12 and {c[2] for c in runs.MACRO_CASES} == {"hawkish", "dovish", "neutral"}
    assert len(runs.FILING_CASES) == 10 and all(len(c) == 4 for c in runs.FILING_CASES)


def test_survival_labels_recorded_fixture(tmp_path):
    from agentic_trader import make_config
    from agentic_trader.agentic.servers import DeskTools, build_registry
    from agentic_trader.data import SyntheticProvider

    cfg = make_config()
    registry = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
    fx = tmp_path / "plans.jsonl"
    task, _ = gov.tasks()[0]
    fx.write_text(json.dumps({"task_id": task.id, "synthetic": False, "model": "m:7b", "steps": None}) + "\n", encoding="utf-8")
    rows = {r["source"]: r for r in gov.survival(cfg, registry, fx)}
    assert rows["model plans (local m:7b, recorded)"]["tasks"] == 1


def test_recorded_local_plans_fixture_if_present():
    fx = ROOT / "tests" / "data" / "v15_local_model_plans.jsonl"
    if not fx.exists():
        return
    rows = [json.loads(x) for x in fx.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(rows) == 200 and all(r["synthetic"] is False for r in rows)


def test_compact_plan_prompt_is_shorter_and_default_prompt_unchanged():
    from agentic_trader.agentic.planner import propose_plan
    from agentic_trader.agentic.servers import DeskTools, build_registry
    from agentic_trader.config import make_config
    from agentic_trader.data import SyntheticProvider

    tasks = gov.tasks
    cfg = make_config()
    reg = build_registry(DeskTools(SyntheticProvider(cfg), cfg))
    task, inst = tasks()[0]
    seen = []

    class Fake:
        def complete(self, system, prompt, deep=False):
            seen.append(prompt)
            return '{"steps": []}'

    propose_plan(Fake(), task, inst, ["technical"], reg)
    propose_plan(Fake(), task, inst, ["technical"], reg, compact=True)
    full, short = seen
    assert '"rationale": "..."}]}' in full and "at most 8 words" in short
    assert len(short) < 0.7 * len(full)


def test_plans_run_records_failures_and_resumes(tmp_path, monkeypatch):
    import argparse

    calls = []

    class FakeLLM:
        def complete(self, system, prompt, deep=False):
            calls.append(prompt)
            return None if len(calls) == 2 else '{"steps": [{"type": "agent", "name": "trader", "arguments": {}}]}'

    monkeypatch.setattr(runs, "_llm", lambda *a, **k: FakeLLM())
    monkeypatch.setattr(runs, "_meta", lambda llm, t0: {})
    out = tmp_path / "plans.jsonl"
    ns = argparse.Namespace(model="m", timeout=1, max_tokens=10, limit=3, compact=True, structured=False, out=str(out))
    runs.cmd_plans(ns)
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert [r["steps"] is None for r in rows] == [False, True, False]
    assert rows[1]["error"] and all(r["compact"] for r in rows)
    assert "at most 8 words" in calls[0]
    runs.cmd_plans(ns)  # resume: nothing left to do
    assert len(calls) == 3 and len(out.read_text().splitlines()) == 3
