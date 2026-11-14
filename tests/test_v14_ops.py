"""v0.14 ops (PLAN 4.10/4.11): price-vintage hash, freshness rule, idempotent publish, workflow files."""

import importlib.util
import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _ops():
    spec = importlib.util.spec_from_file_location("paper_ops", ROOT / "scripts" / "paper_ops.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _frame(close=(100.0, 101.5, 99.25)):
    idx = pd.DatetimeIndex(["2026-11-03", "2026-11-04", "2026-11-05"])
    return pd.DataFrame({"close": list(close), "volume": [1e6, 2e6, 1.5e6]}, index=idx)


def test_vintage_hash_is_stable_and_moves_with_any_price():
    ops = _ops()
    key = ("SPY", "2026-11-01", "2026-11-06")
    base = ops.vintage_hash({key: _frame()})
    assert base == ops.vintage_hash({key: _frame()}) and len(base) == 64
    other = ("TLT", "2026-11-01", "2026-11-06")
    assert ops.vintage_hash({key: _frame(), other: _frame()}) == ops.vintage_hash({other: _frame(), key: _frame()})
    assert ops.vintage_hash({key: _frame((100.0, 101.5, 99.25 + 1e-9))}) != base  # a restated close
    assert ops.vintage_hash({("SPY", "2026-11-01", "2026-11-07"): _frame()}) != base  # a different request


def test_vintage_recorder_passes_calls_through_and_keeps_each_frame():
    ops = _ops()

    class Fake:
        name = "fake"

        def history(self, instrument, start, end):
            return _frame()

    rec = ops.VintageRecorder(Fake())
    rec.history("SPY", date(2026, 11, 1), date(2026, 11, 6))
    assert rec.name == "fake" and list(rec.frames) == [("SPY", "2026-11-01", "2026-11-06")]


@pytest.mark.parametrize(
    "last, today, stale",
    [
        ("2026-11-05", "2026-11-06", 1),  # Thu -> Fri
        ("2026-11-06", "2026-11-07", 0),  # Fri -> Sat: the weekend adds nothing
        ("2026-11-06", "2026-11-09", 1),  # Fri -> Mon
        ("2026-11-05", "2026-11-09", 2),  # Thu -> Mon: still within the limit
        ("2026-11-04", "2026-11-09", 3),  # Wed -> Mon: stale
        ("2026-11-06", "2026-11-06", 0),
    ],
)
def test_business_day_arithmetic(last, today, stale):
    assert _ops().business_days_stale(date.fromisoformat(last), date.fromisoformat(today)) == stale


def test_freshness_rule_skips_without_a_record_and_fails_past_two_business_days(tmp_path):
    ops = _ops()
    runs = tmp_path / "runs.jsonl"
    assert ops.freshness(runs, date(2026, 11, 9))[0]  # first run: no file
    runs.write_text("", encoding="utf-8")
    assert ops.freshness(runs, date(2026, 11, 9))[0]  # empty file
    runs.write_text("\n".join(json.dumps({"as_of": d}) for d in ("2026-11-05", "2026-11-04")) + "\n", encoding="utf-8")
    ok, msg = ops.freshness(runs, date(2026, 11, 9))
    assert ok and "2026-11-05" in msg
    ok, msg = ops.freshness(runs, date(2026, 11, 10))
    assert not ok and msg.startswith("STALE")
    assert ops.main(["freshness", "--runs", str(runs), "--today", "2026-11-10"]) == 1
    assert ops.main(["freshness", "--runs", str(runs), "--today", "2026-11-09"]) == 0


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_commit_helper_is_idempotent(tmp_path):
    ops = _ops()

    def git(*args):
        return subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True).stdout

    git("init", "-q")
    git("config", "user.email", "bot@example.invalid")
    git("config", "user.name", "bot")
    (tmp_path / "runs.jsonl").write_text('{"as_of": "2026-11-06"}\n', encoding="utf-8")
    assert ops.commit_if_changed(tmp_path, ["runs.jsonl", "missing.csv"], "paper: daily record") is True
    assert ops.commit_if_changed(tmp_path, ["runs.jsonl", "missing.csv"], "paper: daily record") is False
    assert git("rev-list", "--count", "HEAD").strip() == "1"


def test_every_slow_marked_test_still_exists():
    from tests.conftest import SLOW

    for node in SLOW:
        path, name = node.split("::")
        assert f"def {name}(" in (ROOT / path).read_text(encoding="utf-8"), node


def test_workflows_parse_and_pin_every_action_by_sha():
    yaml = pytest.importorskip("yaml")
    files = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    assert {f.name for f in files} >= {"ci.yml", "paper.yml", "nightly.yml"}
    for f in files:
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        assert doc["jobs"], f.name
        for job in doc["jobs"].values():
            for step in job.get("steps", []):
                if "uses" in step:
                    ref = step["uses"].split("@", 1)[1]
                    assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), (f.name, step["uses"])
