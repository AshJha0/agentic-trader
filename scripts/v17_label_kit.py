"""v0.17 R3.1 owner labelling kit for the analyst eval judge (review finding B2). No model calls.

    # 1. build the blind sheet from a real run (>= 100 replies, stratified by checker verdict)
    python scripts/v17_label_kit.py sheet --replies results/v16_eval/run.jsonl --out results/v17_labels
    # 2. the owner fills results/v17_labels/labels.csv (read sheet.html, follow INSTRUCTIONS.txt)
    # 3. import: calibration rows + kappa per criterion (checker vs human; judge vs human if given)
    python scripts/v17_label_kit.py import --sheet results/v17_labels --labeller owner \
        --judged results/v17_eval/judge_llama.jsonl --out results/v17_labels/agreement.json \
        --calibration-out results/v17_labels/calibration_real.json

``--replies`` is a ``scripts/v16_eval.py run`` JSONL. Without one, ``--fixture`` builds the sheet
from a JSONL you name (tests use synthetic replies); a fixture sheet is marked as such in key.json.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.agentic import eval_set as ev  # noqa: E402
from agentic_trader.agentic import judge_kit as jk  # noqa: E402


def _read_jsonl(path: Path) -> dict[str, dict]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            rows[r["id"]] = r
    return rows


def cmd_sheet(a: argparse.Namespace) -> int:
    src = Path(a.replies or a.fixture)
    replies = _read_jsonl(src)
    rows = jk.sample_replies(ev.load_items(), replies, n=a.n, seed=a.seed)
    if len(rows) < a.n and not a.fixture:
        print(f"only {len(rows)} replies available, fewer than {a.n}", file=sys.stderr)
        return 1
    label = ("fixture:" if a.fixture else "run:") + str(src)
    paths = jk.write_sheet(rows, Path(a.out), source=label)
    print(json.dumps({"rows": len(rows), **{k: str(v) for k, v in paths.items()}}))
    return 0


def cmd_import(a: argparse.Namespace) -> int:
    d = Path(a.sheet)
    rows = jk.import_sheet(d / "labels.csv", d / "key.json")
    judged = _read_jsonl(Path(a.judged)) if a.judged else None
    rep = jk.agreement_report(rows, judged, n_boot=a.n_boot)
    rep["source"] = json.loads((d / "key.json").read_text(encoding="utf-8"))["source"]
    rep["labeller"] = a.labeller
    if a.calibration_out:
        jk.write_calibration(rows, Path(a.calibration_out), labeller=a.labeller, source=rep["source"])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=1, default=str), encoding="utf-8")
    print(json.dumps(rep, indent=1, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sheet")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--replies", help="v16_eval.py run JSONL (real model replies)")
    g.add_argument("--fixture", help="a replies JSONL used as a fixture (marked in key.json)")
    s.add_argument("--out", required=True)
    s.add_argument("--n", type=int, default=100)
    s.add_argument("--seed", type=int, default=20261109)
    i = sub.add_parser("import")
    i.add_argument("--sheet", required=True, help="directory with labels.csv and key.json")
    i.add_argument("--labeller", required=True)
    i.add_argument("--judged", default=None, help="v16_eval.py judge JSONL over the same replies")
    i.add_argument("--out", required=True)
    i.add_argument("--calibration-out", default=None)
    i.add_argument("--n-boot", type=int, default=2000)
    a = p.parse_args(argv)
    return cmd_sheet(a) if a.cmd == "sheet" else cmd_import(a)


if __name__ == "__main__":
    raise SystemExit(main())
