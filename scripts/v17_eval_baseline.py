"""v0.17 R3.3: check or deliberately re-record the eval-regression baseline. No model calls.

    python scripts/v17_eval_baseline.py                 # check; exit 1 on drift
    python scripts/v17_eval_baseline.py --update --reason "trader prompt v3; eval run results/v17_eval/run.jsonl"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentic_trader.agentic import eval_gate as eg  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--reason", default="")
    a = ap.parse_args(argv)
    if a.update:
        if not a.reason.strip():
            ap.error("--update needs --reason")
        print(json.dumps(eg.write_baseline(a.reason), indent=1))
        return 0
    fails = eg.gate_failures(eg.current_record(), eg.load_baseline())
    for f in fails:
        print(f)
    if fails:
        print("re-run the eval on the new prompts, then: " + eg.UPDATE_HINT)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
