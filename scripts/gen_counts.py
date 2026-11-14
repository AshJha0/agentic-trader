"""Keep the counts quoted in README.md and the docs site in step with the repository.

Each quoted count sits between marker comments, for example::

    <!-- count:threats -->43<!-- /count -->

Running the script recomputes every count and rewrites the text between the markers.
``--check`` rewrites nothing and exits 1 if any marked value differs from the computed one.

Counts and their sources:

* ``learn_concepts``: numbered ``## N.`` headings in LEARN.md.
* ``threats``: distinct threat ids (``| T12 |`` table rows) in docs/threat-model/threat-model.md.
* ``cookbook_recipes``: ``### `` headings in COOKBOOK.md.
* ``diagrams``: mermaid blocks in docs/DIAGRAMS.md.
* ``tests_approx``: ``pytest --collect-only -q`` on the default (not slow) selection,
  rounded to the nearest hundred, because the pages say "about".
* ``coverage_pct``, ``coverage_pct2``, ``coverage_statements``, ``coverage_branches``,
  ``coverage_missed_lines``, ``coverage_missed_branches``: from coverage.xml.

Collecting the tests needs the full dev install and coverage needs a test run, so
both families are skipped (with a note) unless ``--with-tests`` is given or a
--coverage-xml names a file. Code size by language is not quoted anywhere, so it is not counted.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ("README.md", "docs/index.html", "docs/INDEX.md")
MARKER = re.compile(r"(<!-- count:(?P<name>[a-z0-9_]+) -->)(?P<value>.*?)(<!-- /count -->)")
COVERAGE_KEYS = (
    "coverage_pct",
    "coverage_pct2",
    "coverage_statements",
    "coverage_branches",
    "coverage_missed_lines",
    "coverage_missed_branches",
)


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def count_learn_concepts(root: Path) -> str:
    return str(len(re.findall(r"^## \d+\.", _read(root, "LEARN.md"), re.MULTILINE)))


def count_threats(root: Path) -> str:
    text = _read(root, "docs/threat-model/threat-model.md")
    return str(len(set(re.findall(r"^\| *(T\d+)\b", text, re.MULTILINE))))


def count_cookbook_recipes(root: Path) -> str:
    return str(len(re.findall(r"^### ", _read(root, "COOKBOOK.md"), re.MULTILINE)))


def count_diagrams(root: Path) -> str:
    return str(_read(root, "docs/DIAGRAMS.md").count("```mermaid"))


def count_tests_approx(root: Path) -> str:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", "not slow"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    match = re.search(r"(\d+)(?:/\d+)? tests? (?:collected|selected)", out)
    if match is None:
        raise RuntimeError("could not read the collected test count from pytest")
    return f"{round(int(match.group(1)), -2):,}"


def coverage_counts(xml_path: Path) -> dict[str, str]:
    attrs = ET.parse(xml_path).getroot().attrib
    lines_valid, lines_cov = int(attrs["lines-valid"]), int(attrs["lines-covered"])
    br_valid, br_cov = int(attrs.get("branches-valid", 0)), int(attrs.get("branches-covered", 0))
    total = lines_valid + br_valid
    pct = 100.0 * (lines_cov + br_cov) / total if total else 0.0
    return {
        "coverage_pct": f"{pct:.1f}",
        "coverage_pct2": f"{pct:.2f}",
        "coverage_statements": f"{lines_valid:,}",
        "coverage_branches": f"{br_valid:,}",
        "coverage_missed_lines": f"{lines_valid - lines_cov:,}",
        "coverage_missed_branches": f"{br_valid - br_cov:,}",
    }


CHEAP: dict[str, Callable[[Path], str]] = {
    "learn_concepts": count_learn_concepts,
    "threats": count_threats,
    "cookbook_recipes": count_cookbook_recipes,
    "diagrams": count_diagrams,
}


def compute(root: Path, *, with_tests: bool, coverage_xml: Path | None = None) -> tuple[dict[str, str], list[str]]:
    """Return the computed counts and notes on any family that was skipped."""
    counts = {name: fn(root) for name, fn in CHEAP.items()}
    notes: list[str] = []
    if with_tests:
        counts["tests_approx"] = count_tests_approx(root)
    else:
        notes.append("tests_approx skipped: needs a full pytest collection (use --with-tests)")
    xml_path = coverage_xml
    if xml_path is not None and xml_path.is_file():
        counts.update(coverage_counts(xml_path))
    else:
        notes.append("coverage_* skipped: pass --coverage-xml PATH (a full-suite coverage.xml with branch data)")
    return counts, notes


def apply(text: str, counts: dict[str, str]) -> tuple[str, list[tuple[str, str, str]]]:
    """Rewrite known markers; return the new text and (name, old, new) for each drift."""
    drift: list[tuple[str, str, str]] = []

    def repl(m: re.Match[str]) -> str:
        name, old = m.group("name"), m.group("value")
        new = counts.get(name)
        if new is None:
            return m.group(0)
        if new != old:
            drift.append((name, old, new))
        return f"{m.group(1)}{new}{m.group(4)}"

    return MARKER.sub(repl, text), drift


def main(argv: list[str] | None = None, root: Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    parser.add_argument("--with-tests", action="store_true", help="also collect the tests")
    parser.add_argument(
        "--coverage-xml",
        type=Path,
        default=None,
        help="coverage.xml of a full run with --cov-branch (an old or partial file gives false drift)",
    )
    args = parser.parse_args(argv)
    counts, notes = compute(root, with_tests=args.with_tests, coverage_xml=args.coverage_xml)
    for note in notes:
        print(f"note: {note}")
    unknown: set[str] = set()
    any_drift = False
    for rel in TARGETS:
        path = root / rel
        if not path.is_file():
            continue
        raw = path.read_bytes().decode("utf-8")
        unknown |= {m.group("name") for m in MARKER.finditer(raw)} - set(counts)
        new, drift = apply(raw, counts)
        for name, old, value in drift:
            any_drift = True
            print(f"{rel}: {name} {old!r} -> {value!r}")
        if drift and not args.check:
            path.write_bytes(new.encode("utf-8"))
    skipped = unknown & ({"tests_approx"} | set(COVERAGE_KEYS))
    if unknown - skipped:
        print(f"error: unknown count markers: {sorted(unknown - skipped)}")
        return 1
    if args.check and any_drift:
        print("counts drifted: run python scripts/gen_counts.py and commit the result")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
