"""Mask the local Python path in results/paper/runs.jsonl before the daily publish."""
import pathlib
import re

p = pathlib.Path(__file__).resolve().parent.parent / "results" / "paper" / "runs.jsonl"
text = p.read_text(encoding="utf-8")
p.write_text(re.sub(r'("executable": ")[^"]*', r"\1<local python>", text), encoding="utf-8", newline="\n")
