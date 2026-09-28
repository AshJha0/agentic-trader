"""Render the v0.9 design-period runs (``scripts/measure_v09.py``) as markdown tables.

For every run JSON under ``results/v09``: the strategy table (the same columns as
``agentic-trader portfolio``), the paired block-bootstrap Sharpe difference of every stream
against ``B&H vol-target`` on that run, and the mean capital share per sleeve. Then the
attribution and combination reports are appended verbatim when present. Writes
``results/v09/tables.md``.

    .venv\\Scripts\\python.exe scripts/render_v09_tables.py [--in results/v09]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RUN_ORDER = ("etf11_rp", "etf11_equal", "fx15_rp", "core15_rp", "all26_rp")
OUT: list[str] = []


def emit(title: str, body: str) -> None:
    OUT.append(f"### {title}\n\n{body.strip()}\n")


def md(df: pd.DataFrame, index: bool = True, floatfmt: str = ".2f") -> str:
    df = df.copy()
    if index:
        df = df.reset_index()
    cols = list(df.columns)
    lines = ["| " + " | ".join(str(c) for c in cols) + " |",
             "|" + "|".join("--:" if pd.api.types.is_numeric_dtype(df[c]) else ":--" for c in cols) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, (float, np.floating)):
                cells.append("" if not np.isfinite(v) else format(v, floatfmt))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def diff_line(d: dict) -> str:
    return f"{d['diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}] p={d['p_value']:.3f}"


def section_run(name: str, p: dict, d: Path) -> None:
    label = (f"{name}: {len(p['symbols'])} sleeves, {p['weighting']}"
             + (f", class budgets {p['class_budgets']}" if p.get("class_budgets") else "")
             + f", {p['start']} -> {p['end']}, provenance {p['provenance']['git_commit'][:7]}"
             + (" dirty" if p['provenance'].get('git_dirty') else " clean"))
    emit(f"portfolio table, {label}", md(pd.DataFrame(p["table"]).T))
    rows = [{"stream": s, "Sharpe": p["metrics"][s]["sharpe"], "Sharpe - B&H vol-target [95% CI] p": diff_line(v)}
            for s, v in p["sharpe_vs_vol_target"].items()]
    emit(f"Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): {name}",
         md(pd.DataFrame(rows), index=False))
    alloc = d / f"{name}_allocations.csv"
    if alloc.exists():
        a = pd.read_csv(alloc, index_col=0, parse_dates=True)
        emit(f"mean capital share per sleeve: {name}", md(a.mean().rename("mean share").to_frame().T, floatfmt=".3f"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v09"))
    a = ap.parse_args(argv)
    d = Path(a.inp)
    for name in RUN_ORDER:
        f = d / f"{name}.json"
        if f.exists():
            section_run(name, json.load(open(f, encoding="utf-8")), d)
        else:
            OUT.append(f"_{name}.json missing_\n")
    for extra in ("attribution.md", "combine.md"):
        f = d / extra
        if f.exists():
            OUT.append(f.read_text(encoding="utf-8"))
    text = "\n".join(OUT)
    (d / "tables.md").write_text(text, encoding="utf-8")
    print(f"wrote {d / 'tables.md'}: {sum(1 for line in text.splitlines() if line.startswith('#'))} sections")
    return 0


if __name__ == "__main__":
    sys.exit(main())
