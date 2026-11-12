"""Refuse a paper publish that rewrites the record (round 2, review D6).

The forward record is append-only. Before the publish job commits ``results/paper``, this
checks the files it is about to commit against the committed ones (``git show BASE:path``):

* each append-only file (``ledger.csv``, ``ledger_vintage.csv``, ``revisions.csv``,
  ``runs.jsonl``) must start with every line of the committed file, in order: the new file
  extends the old one, or is the same (a run that appended nothing). A file absent at BASE
  passes. A file present at BASE and missing now fails.
* the hash chain: every ``runs.jsonl`` line that carries ``ledger_rows`` and ``ledger_chain``
  must match ``paper_ops.ledger_chain`` over the first ``ledger_rows`` rows of the new
  ``ledger.csv``. A rewritten row breaks every head recorded after it.

Worked example: the committed ledger ends 2026-11-11; a stale artifact built before a laptop
commit that added 2026-11-12 is downloaded over it. The new ledger.csv then lacks the
2026-11-12 line the committed file has, the prefix check fails, and nothing is committed.

    python scripts/paper_ledger_check.py [--base HEAD] [--dir results/paper]

Standard library only (the publish job installs nothing). Exit 0 when every check passes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPEND_ONLY = ("ledger.csv", "ledger_vintage.csv", "revisions.csv", "runs.jsonl")


def _paper_ops():
    spec = importlib.util.spec_from_file_location("_paper_ops", ROOT / "scripts" / "paper_ops.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _lines(text: str) -> list[str]:
    return [ln for ln in text.replace("\r\n", "\n").split("\n") if ln.strip()]


def check_extends(old: str | None, new: str | None, name: str) -> list[str]:
    """Errors when ``new`` does not keep every line of ``old`` in order at its start."""
    if old is None:
        return []
    if new is None:
        return [f"{name}: committed file is missing from the publish"]
    a, b = _lines(old), _lines(new)
    if len(b) < len(a):
        return [f"{name}: {len(a)} committed line(s), only {len(b)} now (the record shrank)"]
    for k, (x, y) in enumerate(zip(a, b), 1):
        if x != y:
            return [f"{name}: line {k} differs from the committed one (append-only file rewritten)"]
    return []


def check_chain(ledger: str | None, runs: str | None) -> list[str]:
    """Errors when a runs.jsonl chain head does not match the ledger's rows."""
    if ledger is None or runs is None:
        return []
    heads = _paper_ops().ledger_chain(ledger)
    errors = []
    for k, line in enumerate(_lines(runs), 1):
        rec = json.loads(line)
        if "ledger_chain" not in rec:
            continue   # lines written before round 2 carry no chain
        n = int(rec.get("ledger_rows", -1))
        if not 0 <= n < len(heads):
            errors.append(f"runs.jsonl line {k}: ledger_rows {n} but the ledger has {len(heads) - 1} row(s)")
        elif heads[n] != rec["ledger_chain"]:
            errors.append(f"runs.jsonl line {k}: chain head after {n} row(s) does not match the ledger "
                          f"(a recorded row was rewritten)")
    return errors


def _git_show(base: str, rel: str) -> str | None:
    r = subprocess.run(["git", "show", f"{base}:{rel}"], cwd=ROOT, capture_output=True)
    return r.stdout.decode("utf-8") if r.returncode == 0 else None


def run_checks(old: dict[str, str | None], new: dict[str, str | None]) -> list[str]:
    errors: list[str] = []
    for name in APPEND_ONLY:
        errors += check_extends(old.get(name), new.get(name), name)
    errors += check_chain(new.get("ledger.csv"), new.get("runs.jsonl"))
    return errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="HEAD", help="git revision holding the committed record")
    ap.add_argument("--dir", default="results/paper", help="record directory, relative to the repo root")
    a = ap.parse_args(argv)
    d = ROOT / a.dir
    old = {n: _git_show(a.base, f"{a.dir}/{n}") for n in APPEND_ONLY}
    new = {n: ((d / n).read_text(encoding="utf-8") if (d / n).exists() else None) for n in APPEND_ONLY}
    errors = run_checks(old, new)
    for e in errors:
        print(f"FAIL {e}")
    if not errors:
        print(f"ok: {', '.join(APPEND_ONLY)} extend {a.base}; ledger chain heads match")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
