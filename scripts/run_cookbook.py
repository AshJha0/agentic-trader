"""Execute every ```python block in COOKBOOK.md, each in a fresh process and temp dir.

    python scripts/run_cookbook.py [--offline] [--only TEXT]

``--offline`` skips recipes that need the network (Yahoo, FRED, EDGAR, an LLM key),
which is what CI runs. Exit status is the number of failures.
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NETWORK_MARKERS = ("yahoo", "FredClient", "fred", "edgar", "ANTHROPIC_API_KEY", "anthropic", "urlopen")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip recipes that touch the network")
    ap.add_argument("--only", default=None, help="run only sections whose title contains this text")
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()
    md = (ROOT / "COOKBOOK.md").read_text(encoding="utf-8")
    sections = re.split(r"^### ", md, flags=re.M)[1:]
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)}
    fails = ran = skipped = 0
    for sec in sections:
        title = sec.splitlines()[0]
        if args.only and args.only.lower() not in title.lower():
            continue
        for block in re.findall(r"```python\n(.*?)```", sec, flags=re.S):
            if args.offline and any(m.lower() in block.lower() for m in NETWORK_MARKERS):
                skipped += 1
                print(f"SKIP {title} (network)")
                continue
            with tempfile.TemporaryDirectory() as tmp:
                p = subprocess.run([sys.executable, "-c", block], cwd=tmp, capture_output=True, text=True,
                                   timeout=args.timeout, encoding="utf-8", errors="replace", env=env)
            ran += 1
            ok = p.returncode == 0
            fails += not ok
            print(f"{'OK  ' if ok else 'FAIL'} {title}")
            for line in (p.stdout.strip().splitlines() or [""])[-3:]:
                print(f"      {line[:150]}")
            if not ok:
                print("      " + "\n      ".join(p.stderr.strip().splitlines()[-8:]))
    print(f"\n{len(sections)} sections: {ran} run, {skipped} skipped, {fails} failures")
    return fails


if __name__ == "__main__":
    sys.exit(main())
