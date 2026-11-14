"""v0.19 open items: provider retries in run_recall / run_calibration / _fwd, and atomic,
fingerprinted trial files in measure_v08.run_trials. Offline, fake LLMs and fake engine only."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import measure_v08 as m08  # noqa: E402
import v16_local_study as v16  # noqa: E402
from agentic_trader import evaluation  # noqa: E402
from agentic_trader.study_robust import ProviderMiss  # noqa: E402
from test_v16_p2_a import FakeAnalyst, FakeRecall  # noqa: E402

NO_SLEEP = {"sleep": lambda s: None, "log": lambda m: None}


@pytest.fixture(scope="module")
def graph():
    return v16.make_graph("synthetic")


@pytest.fixture
def flaky(monkeypatch):
    """FrozenState raises the provider's ValueError for symbols in ``state.bad``."""
    real = v16.FrozenState
    state = SimpleNamespace(bad=set())

    def fake(graph, sym, d, **kw):
        if sym in state.bad or (sym, d) in state.bad:
            raise ValueError(f"no Yahoo data for {sym}")
        return real(graph, sym, d, **kw)

    monkeypatch.setattr(v16, "FrozenState", fake)
    return state


def test_recall_skips_a_provider_miss_and_retries_it_on_resume(graph, tmp_path, flaky):
    items = v16.recall_items(3)
    flaky.bad = {items[0]}
    out = tmp_path / "recall.json"
    res = v16.run_recall(FakeRecall(), graph, out, limit=3, ablate=False, **NO_SLEEP)
    assert res["n"] == 2 and res["skipped"]["n"] == 1 and res["skipped"]["units"] == 3
    assert res["skipped"]["rows"][0]["reason"].startswith("no Yahoo data")
    flaky.bad = set()
    llm = FakeRecall()
    res2 = v16.run_recall(llm, graph, out, limit=3, ablate=False, **NO_SLEEP)
    assert res2["n"] == 3 and res2["skipped"]["n"] == 0 and len(llm.prompts) == 1


def test_calibration_skips_a_state_and_recovers_on_resume(graph, tmp_path, flaky):
    states = v16.calibration_states(2)
    flaky.bad = {states[0]}
    out = tmp_path / "cal.json"
    kw = {"limit": 2, "repeats": 1, "anchor_values": (30.0,), **NO_SLEEP}
    res = v16.run_calibration(FakeAnalyst(), graph, out, **kw)
    assert res["skipped"]["n"] == 1 and len(res["baseline"]) == 1
    flaky.bad = set()
    res2 = v16.run_calibration(FakeAnalyst(), graph, out, **kw)
    assert res2["skipped"]["n"] == 0 and len(res2["baseline"]) == 2


def test_fwd_retries_then_raises_provider_miss(graph):
    st = v16.FrozenState(graph, "AAPL", v16.design_dates(14)[3])
    calls = {"n": 0}
    real = graph.provider.history

    class Flaky:
        def history(self, *a, **k):
            calls["n"] += 1
            if calls["n"] < 2:
                raise ValueError("no Yahoo data")
            return real(*a, **k)

    g = SimpleNamespace(provider=Flaky())
    assert v16._fwd(g, st, 0, 5, sleep=lambda s: None) is not None and calls["n"] == 2

    class Dead:
        def history(self, *a, **k):
            raise ValueError("no Yahoo data")

    with pytest.raises(ProviderMiss):
        v16._fwd(SimpleNamespace(provider=Dead()), st, 0, 5, tries=2, sleep=lambda s: None)


@pytest.fixture
def fake_engine(monkeypatch):
    runs: list[str] = []
    trial = SimpleNamespace(
        name="t one", version="v0", overrides={"x": 1}, recorded_mean_sharpe=None, recorded_portfolio_sharpe=None
    )

    def fake_eval(syms, periods, cfg, every, provider=None, workers=1):
        runs.append("eval")
        return evaluation.EvaluationResult(pd.DataFrame([{"strategy": m08.AGENT, "period": "design", "Sharpe": 0.5}]), {})

    port = SimpleNamespace(metrics={m08.AGENT: SimpleNamespace(sharpe=0.4)})
    monkeypatch.setattr(evaluation, "TRIALS", [trial])
    monkeypatch.setattr(m08, "evaluate", fake_eval)
    monkeypatch.setattr(m08, "run_portfolio_backtest", lambda *a, **k: port)
    monkeypatch.setattr(m08, "base_config", lambda **o: o)
    monkeypatch.setattr(m08, "provider_for", lambda cfg, over, p: p)
    monkeypatch.setattr(m08, "log", lambda m: None)
    return SimpleNamespace(runs=runs, trial=trial)


def test_trials_atomic_fingerprinted_and_legacy_kept(tmp_path, fake_engine):
    m08.run_trials(tmp_path, provider=None)
    path = next(tmp_path.glob("trial_*.json"))
    meas = json.loads(path.read_text(encoding="utf-8"))["meta"]["measurement"]
    assert meas["fingerprint"] and not list(tmp_path.glob("*.tmp")) and fake_engine.runs == ["eval"]
    m08.run_trials(tmp_path, provider=None)  # same inputs: reused
    assert fake_engine.runs == ["eval"]
    fake_engine.trial.overrides = {"x": 2}  # other inputs: re-measured
    m08.run_trials(tmp_path, provider=None)
    assert fake_engine.runs == ["eval", "eval"]
    d = json.loads(path.read_text(encoding="utf-8"))  # legacy file (no fingerprint): kept
    del d["meta"]["measurement"]["fingerprint"]
    path.write_text(json.dumps(d), encoding="utf-8")
    fake_engine.trial.overrides = {"x": 3}
    m08.run_trials(tmp_path, provider=None)
    assert fake_engine.runs == ["eval", "eval"]
