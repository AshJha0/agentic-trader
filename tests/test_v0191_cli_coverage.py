"""v0.19.1: offline tests for the rarer branches of ``cli/evaluate`` and ``cli/decisions``.

Every collaborator (evaluation, calibration, graph, harness, replay) is replaced by a small fake,
so these tests check the command's own printing and exit codes, not the engines behind them."""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any

import pandas as pd
import pytest

from agentic_trader.cli import decisions as dec
from agentic_trader.cli import evaluate as ev


@pytest.fixture(autouse=True)
def _quiet_common(monkeypatch: pytest.MonkeyPatch) -> None:
    for mod in (ev, dec):
        monkeypatch.setattr(mod, "_config", lambda args: {"agentic": {"approval": "auto"}})
        monkeypatch.setattr(mod, "_header", lambda *a, **k: None)
        monkeypatch.setattr(mod, "_print_usage", lambda *a, **k: print("usage"))
    monkeypatch.setattr(dec, "_as_of", lambda args: "2024-01-05")
    monkeypatch.setattr(dec, "llm_usage", lambda llm: {})


def _fake_module(monkeypatch: pytest.MonkeyPatch, name: str, **attrs: Any) -> None:
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    monkeypatch.setitem(sys.modules, name, m)


class _Res:
    def __init__(self, tmp: Path, *, rich: bool) -> None:
        self.rich = rich
        self.rows = pd.DataFrame({"universe": ["core", "ext"] if rich else ["core", "core"]})
        self.meta: dict[str, Any] = {
            "errors": ["AAPL boom"] if rich else [],
            "timings": [1, 2] if rich else [],
        }

    def summary(self, universe: str | None = None) -> pd.DataFrame:
        return pd.DataFrame({"u": [universe or "all"]})

    def head_to_head(self) -> pd.DataFrame:
        return pd.DataFrame({"h": [1]})

    def paired_table(self) -> pd.DataFrame:
        return pd.DataFrame({"n": [3 if self.rich else 1]})

    def run_dispersion(self) -> pd.DataFrame:
        return pd.DataFrame({"sd": [0.1]}) if self.rich else pd.DataFrame()

    def slowest(self, k: int) -> pd.DataFrame:
        return pd.DataFrame({"job": ["x"]})

    def to_json(self, path: str) -> None:
        Path(path).write_text("{}")


@pytest.mark.parametrize("rich", [True, False])
def test_cmd_evaluate_branches(
    rich: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def evaluate(syms, periods, cfg, every, progress, workers, repeats):  # noqa: ANN001, ANN202
        progress("job 1")
        assert cfg["memory_path"] is None
        return _Res(tmp_path, rich=rich)

    _fake_module(
        monkeypatch,
        "agentic_trader.evaluation",
        PERIODS={"design": ("a", "b")},
        UNIVERSES={"core": ["AAPL"]},
        evaluate=evaluate,
    )
    out = tmp_path / "e.json"
    args = NS(
        periods="design",
        symbol="AAPL,MSFT" if rich else None,
        universe="core",
        every=5,
        workers=1,
        repeats=1,
        out=str(out) if rich else None,
    )
    assert ev.cmd_evaluate(args) == 0
    text = capsys.readouterr().out
    assert ("[ext universe]" in text) is rich
    assert ("time-block bootstrap" in text) is rich
    assert ("across-run dispersion" in text) is rich
    assert ("slowest jobs" in text) is rich
    assert ("1 failures" in text) is rich
    assert out.exists() is rich


@pytest.mark.parametrize("compare", [True, False])
def test_cmd_calibrate(
    compare: bool, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seen: dict[str, Any] = {}

    class Rep:
        samples = pd.DataFrame({"s": [1]})
        meta: dict[str, Any] = {}

        def summary(self) -> dict[str, Any]:
            return {"mean": 0.1}

        def compare(self, other: Any) -> dict[str, Any]:
            return {"drift": 0.0}

        def to_json(self, p: str) -> None:
            Path(p).write_text("{}")

        @classmethod
        def from_json(cls, p: str) -> Rep:
            return cls()

    def calibrate(graph, symbol, as_of, n, anchors, progress):  # noqa: ANN001, ANN202
        seen["anchors"], seen["as_of"] = anchors, as_of
        progress("run")
        return Rep()

    _fake_module(monkeypatch, "agentic_trader.calibration", CalibrationReport=Rep, calibrate=calibrate)
    _fake_module(monkeypatch, "agentic_trader.graph", TradingGraph=lambda cfg: object())
    out = tmp_path / "c.json"
    args = NS(
        anchors="none,0.5",
        date=None if compare else "2024-02-01",
        symbol="AAPL",
        n=2,
        compare="old.json" if compare else None,
        out=str(out) if compare else None,
    )
    assert ev.cmd_calibrate(args) == 0
    text = capsys.readouterr().out
    assert seen["anchors"] == (None, 0.5)
    assert ("drift vs old.json" in text) is compare
    assert out.exists() is compare
    if not compare:
        assert seen["as_of"] == "2024-02-01"


class _Dec:
    def to_dict(self) -> dict[str, Any]:
        return {"action": "BUY"}


class _Graph:
    llm = None

    def __init__(self, cfg: Any = None, on_event: Any = None) -> None:
        self.on_event = on_event

    def propagate(self, *a: Any) -> tuple[Any, _Dec]:
        return NS(to_markdown=lambda: "# report"), _Dec()

    def scan(self, syms: list[str], as_of: str, positions: dict[str, float]) -> pd.DataFrame:
        action = "ERROR" if syms == ["BAD"] else "BUY"
        return pd.DataFrame({"symbol": syms, "action": [action] * len(syms), "extra": [1] * len(syms)})


@pytest.mark.parametrize("as_json", [True, False])
def test_cmd_analyze(as_json: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(dec, "TradingGraph", _Graph)
    args = NS(save=False, symbol="AAPL", asset_class="equity", position=0.0, json=as_json)
    assert dec.cmd_analyze(args) == 0
    text = capsys.readouterr().out
    assert ('"action": "BUY"' in text) is as_json
    assert ("# report" in text) is not as_json


def test_cmd_scan_outputs_and_all_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(dec, "TradingGraph", _Graph)
    for out in ("s.json", "s.csv"):
        args = NS(symbol="AAPL,MSFT", positions='{"AAPL": 0.1}', out=str(tmp_path / out))
        assert dec.cmd_scan(args) == 0
        assert (tmp_path / out).exists()
    assert "extra" not in capsys.readouterr().out
    assert dec.cmd_scan(NS(symbol="BAD", positions=None, out=None)) == 1


class _Run:
    def __init__(self, state: str, *, plan: bool = True, report: bool = True) -> None:
        self.id = "run1"
        self.state = NS(value=state)
        self.plan = NS(source="llm", steps=[1], notes=["n1"]) if plan else None
        self.evidence: list[Any] = []
        self.findings: list[Any] = []
        self.errors = ["e1"]
        self.report = NS(to_markdown=lambda: "# task report") if report else None
        self.tracer = NS(summary=lambda: "3 spans")

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id}


def _harness(run: _Run) -> Any:
    class H:
        def __init__(self, graph: Any, positions: Any = None) -> None:
            self.positions = positions

        def run(self, task: Any) -> _Run:
            return run

        def pending_approvals(self, rid: str) -> list[Any]:
            return [NS(id="a1", request=NS(tool="place_order", arguments={}), reason="limit")]

    return H


@pytest.mark.parametrize(
    ("state", "plan", "report", "as_json", "code"),
    [
        ("COMPLETED", True, True, False, 0),
        ("COMPLETED", True, True, True, 0),
        ("FAILED", False, True, False, 1),
        ("FAILED", False, False, False, 1),
        ("AWAITING_APPROVAL", True, True, False, 3),
    ],
)
def test_cmd_task_exit_codes(
    state: str,
    plan: bool,
    report: bool,
    as_json: bool,
    code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import agentic_trader.agentic as agentic

    monkeypatch.setattr(agentic, "AgentHarness", _harness(_Run(state, plan=plan, report=report)))
    monkeypatch.setattr(dec, "TradingGraph", _Graph)
    args = NS(
        save=False,
        verbose=as_json,
        record=None,
        symbol="AAPL",
        position=0.1 if plan else None,
        role="analyst",
        question=None,
        json=as_json,
    )
    assert dec.cmd_task(args) == code
    text = capsys.readouterr().out
    assert "error: e1" in text
    if code == 3:
        assert "awaiting approval a1" in text
    if not plan:
        assert "plan: none" in text


def test_cmd_task_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import agentic_trader.agentic as agentic
    import agentic_trader.agentic.replay as replay

    class Recorder:
        def __init__(self, cfg: Any, on_event: Any) -> None:
            self.graph = _Graph()

        def recording(self, run: Any, positions: Any) -> Any:
            return NS(save=lambda p: p)

    monkeypatch.setattr(replay, "Recorder", Recorder)
    monkeypatch.setattr(replay, "recording_path", lambda rid, d: Path(d) / f"{rid}.pkl")
    monkeypatch.setattr(agentic, "AgentHarness", _harness(_Run("COMPLETED")))
    args = NS(
        save=False, verbose=False, record=str(tmp_path), symbol="AAPL", position=None, role="analyst", question="q", json=False
    )
    assert dec.cmd_task(args) == 0
    assert "recorded:" in capsys.readouterr().out


def test_cmd_replay_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import agentic_trader.agentic.replay as replay

    with pytest.raises(FileNotFoundError):
        dec.cmd_replay(NS(task_run_id=str(tmp_path / "none.pkl"), dir=None, json=False))
    pkl = tmp_path / "r.pkl"
    pkl.write_bytes(b"x")
    rec = NS(task_id="t1", state="COMPLETED", decision={"action": "BUY"})
    monkeypatch.setattr(replay, "load_recording", lambda p: rec)

    def missing(r: Any, check: bool) -> Any:
        raise replay.ReplayMissingPayload("no payload for tool x")

    monkeypatch.setattr(replay, "replay", missing)
    assert dec.cmd_replay(NS(task_run_id=str(pkl), dir=None, json=False)) == 2
    assert "no payload" in capsys.readouterr().err

    for matches in (True, False):
        res = NS(
            run=NS(to_dict=lambda: {"id": "t1"}),
            replayed_state="COMPLETED",
            replayed=None if matches else {"action": "SELL"},
            matches=matches,
            diff=lambda m=matches: {} if m else {"action": ("BUY", "SELL")},
        )
        monkeypatch.setattr(replay, "replay", lambda r, check, res=res: res)
        monkeypatch.setattr(replay, "recording_path", lambda ref, d: pkl)
        assert dec.cmd_replay(NS(task_run_id="t1", dir=str(tmp_path), json=True)) == (0 if matches else 1)
        text = capsys.readouterr().out
        assert ("DIVERGED" in text) is not matches
        assert json.loads(text.split("\nreplay")[0])["id"] == "t1"
