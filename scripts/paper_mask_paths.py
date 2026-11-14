"""Mask the local Python path in the newest line of results/paper/runs.jsonl before the publish.

Only the last line is touched (round 2, review D6): earlier lines are already published and
the append-only check (``paper_ledger_check.py``) requires them byte for byte.
"""

import pathlib
import re
import sys


def mask_last_line(text: str) -> str:
    lines = text.split("\n")
    for k in range(len(lines) - 1, -1, -1):
        if lines[k].strip():
            lines[k] = re.sub(r'("executable": ")[^"]*', r"\1<local python>", lines[k])
            break
    return "\n".join(lines)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    p = pathlib.Path(args[0]) if args else (pathlib.Path(__file__).resolve().parent.parent / "results" / "paper" / "runs.jsonl")
    text = p.read_text(encoding="utf-8").replace("\r\n", "\n")
    p.write_text(mask_last_line(text), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
