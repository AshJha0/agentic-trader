"""Tests for scripts/gen_counts.py: the counting rules, the rewrite and --check."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "gen_counts", Path(__file__).resolve().parent.parent / "scripts" / "gen_counts.py"
)
assert _SPEC is not None and _SPEC.loader is not None
gc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gc)


def _repo(tmp: Path, readme: str) -> Path:
    (tmp / "docs" / "threat-model").mkdir(parents=True)
    (tmp / "LEARN.md").write_text("# L\n## 1. a\n## 2. b\n## Not numbered\n", encoding="utf-8")
    (tmp / "COOKBOOK.md").write_text("### r1\n### r2\n### r3\n", encoding="utf-8")
    (tmp / "docs" / "DIAGRAMS.md").write_text("```mermaid\n```\n", encoding="utf-8")
    (tmp / "docs" / "threat-model" / "threat-model.md").write_text(
        "| T1 | x |\n| T2 | y |\n| T2 | again |\n", encoding="utf-8"
    )
    (tmp / "README.md").write_bytes(readme.encode("utf-8"))
    return tmp


def test_cheap_counts(tmp_path: Path) -> None:
    root = _repo(tmp_path, "")
    counts, notes = gc.compute(root, with_tests=False)
    assert counts == {"learn_concepts": "2", "threats": "2", "cookbook_recipes": "3", "diagrams": "1"}
    assert len(notes) == 2  # tests and coverage both skipped, each with a note


def test_coverage_from_xml(tmp_path: Path) -> None:
    xml = tmp_path / "coverage.xml"
    xml.write_text(
        '<coverage lines-valid="1000" lines-covered="950" branches-valid="200"'
        ' branches-covered="180"/>',
        encoding="utf-8",
    )
    got = gc.coverage_counts(xml)
    assert got["coverage_pct2"] == "94.17"
    assert got["coverage_pct"] == "94.2"
    assert got["coverage_statements"] == "1,000"
    assert got["coverage_missed_lines"] == "50"
    assert got["coverage_missed_branches"] == "20"


def test_apply_reports_drift_and_leaves_unknown() -> None:
    text = "a <!-- count:threats -->40<!-- /count --> b <!-- count:other -->7<!-- /count -->"
    new, drift = gc.apply(text, {"threats": "43"})
    assert drift == [("threats", "40", "43")]
    assert "<!-- count:threats -->43<!-- /count -->" in new
    assert "<!-- count:other -->7<!-- /count -->" in new


def test_check_then_write_keeps_crlf(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, "x\r\n<!-- count:threats -->40<!-- /count -->\r\n")
    assert gc.main(["--check"], root=root) == 1
    assert "'40' -> '2'" in capsys.readouterr().out
    assert gc.main([], root=root) == 0
    assert (root / "README.md").read_bytes() == b"x\r\n<!-- count:threats -->2<!-- /count -->\r\n"
    assert gc.main(["--check"], root=root) == 0


def test_check_skips_expensive_markers(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _repo(tmp_path, "<!-- count:tests_approx -->2,100<!-- /count -->")
    assert gc.main(["--check"], root=root) == 0
    assert "tests_approx skipped" in capsys.readouterr().out


def test_unknown_marker_fails(tmp_path: Path) -> None:
    root = _repo(tmp_path, "<!-- count:nonsense -->1<!-- /count -->")
    assert gc.main(["--check"], root=root) == 1
