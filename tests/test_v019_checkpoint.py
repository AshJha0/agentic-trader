"""Resumable v17_exec_lag: checkpoint resume, header refusal, torn last line, progress."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from agentic_trader.checkpoint import Checkpoint, CheckpointMismatch
from agentic_trader.evaluation import TRIALS

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("v17_exec_lag", ROOT / "scripts" / "v17_exec_lag.py")
assert _spec and _spec.loader
lag_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(lag_mod)

NAMES = [t.name for t in TRIALS if t.overrides is not None][:3]
ARGS = ["--provider", "synthetic", "--trials", ",".join(NAMES), "--lags", "0,1"]


class Boom(Exception):
    pass


@pytest.fixture
def fake(monkeypatch):
    calls: list = []
    stop = {"after": None}

    def unit(provider, name, trial, lag, start, end):
        if stop["after"] is not None and len(calls) >= stop["after"]:
            raise Boom
        calls.append((trial.name, lag))
        x = (len(trial.name) * 0.137 + lag * 0.05) % 1
        return {"trial": trial.name, "version": trial.version, "exec_lag": lag, "sharpe": x,
                "control_sharpe": 0.4, "delta_vs_control": x - 0.4, "ci_low": -1.0, "ci_high": 1.0,
                "p_value": 0.5, "days": 100}

    monkeypatch.setattr(lag_mod, "run_unit", unit)
    monkeypatch.setattr(lag_mod, "get_provider", lambda cfg: object())
    return calls, stop


def _finals(d: Path) -> dict:
    return {n: (d / n).read_bytes() for n in ("trials_lag_synthetic.json", "trials_lag_synthetic.md")}


def test_resume_equals_full_run(tmp_path, fake, capsys):
    calls, stop = fake
    full = tmp_path / "full"
    assert lag_mod.main(ARGS + ["--out", str(full)]) == 0
    assert len(calls) == 6
    calls.clear()
    part = tmp_path / "part"
    stop["after"] = 4
    with pytest.raises(Boom):
        lag_mod.main(ARGS + ["--out", str(part)])
    stop["after"] = None
    calls.clear()
    capsys.readouterr()
    assert lag_mod.main(ARGS + ["--out", str(part)]) == 0
    assert len(calls) == 2                      # only the unfinished units ran
    assert _finals(part) == _finals(full)
    out = capsys.readouterr().out.splitlines()
    assert [ln.split()[0] for ln in out] == [f"{k}/6" for k in range(1, 7)]
    assert sum("done (checkpoint)" in ln for ln in out) == 4


def test_fresh_reruns_everything(tmp_path, fake):
    calls, _ = fake
    lag_mod.main(ARGS + ["--out", str(tmp_path)])
    calls.clear()
    lag_mod.main(ARGS + ["--out", str(tmp_path), "--fresh"])
    assert len(calls) == 6


def test_mismatched_header_refused(tmp_path, fake):
    lag_mod.main(ARGS + ["--out", str(tmp_path)])
    with pytest.raises(SystemExit, match="different inputs"):
        lag_mod.main(["--provider", "synthetic", "--trials", NAMES[0], "--lags", "0,1", "--out", str(tmp_path)])
    with pytest.raises(CheckpointMismatch):
        Checkpoint(tmp_path / "checkpoint_synthetic.jsonl", {"other": 1})


def test_half_written_last_line_tolerated(tmp_path):
    p = tmp_path / "ck.jsonl"
    ck = Checkpoint(p, {"a": 1})
    ck.add("u1", {"v": 1})
    ck.add("u2", {"v": 2})
    good = p.read_bytes()
    p.write_bytes(good + b'{"key": "u3", "row": {"v"')
    ck2 = Checkpoint(p, {"a": 1})
    assert len(ck2) == 2 and ck2.done("u2") and not ck2.done("u3")
    assert p.read_bytes() == good               # torn tail truncated
    ck2.add("u3", {"v": 3})
    assert Checkpoint(p, {"a": 1}).get("u3") == {"v": 3}
    assert all(json.loads(x) for x in p.read_text(encoding="utf-8").splitlines())
