"""Write docs/evaluation/v011_review.md from the v0.11 result files (no number is typed).

Assembles, from ``results/v11/tables.md`` (rendered by ``scripts/render_v08_tables.py --in
results/v11``) and ``results/v11/manifest.json``, the sections the v0.11 page quotes: the
headline summaries and paired tables for the core and extended slices, the drawdown tables
against the controls, the portfolio tables with their block-bootstrap differences, the
cash-leg and re-check tables, VaR coverage, the trials registry with the deflated Sharpe on
one statistic, and the rebalance-phase sweep. The prose around them is fixed text; every
table is copied verbatim.

    .venv\\Scripts\\python.exe scripts/render_v11_doc.py [--in results/v11]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SECTIONS = [
    ("Headline, core (15)", ["summary: core (15), design", "summary: core (15), holdout", "head to head: core (15)"]),
    ("Headline, extended (45)", ["summary: extended (45), design", "summary: extended (45), holdout", "head to head: extended (45)"]),
    ("Paired Sharpe against every baseline", ["paired Sharpe, agent minus baseline: core (15)", "paired Sharpe, agent minus baseline: extended (45)",
                                              "paired Sharpe, agent minus baseline: all 60"]),
    ("Drawdown and Calmar against the two controls", ["paired MDD%, agent minus control: core (15)", "paired MDD%, agent minus control: extended (45)",
                                                        "paired Calmar, agent minus control: core (15)", "paired Calmar, agent minus control: extended (45)",
                                                        "summary by asset class: core (15) equity (10), holdout", "paired MDD% by asset class, agent minus control: core (15) equity (10)"]),
    ("The 15-sleeve portfolio", ["portfolio: design", "portfolio Sharpe difference (paired block bootstrap over days): design",
                                 "portfolio: holdout", "portfolio Sharpe difference (paired block bootstrap over days): holdout",
                                 "cash leg on vs off: holdout"]),
    ("Re-checks under the v0.11 engine", ["EDGAR on (a) vs off (b)", "FX carry rule on (a) vs off (b)", "with the cross-sectional analyst (a) vs default (b)",
                                          "with the alpha analyst, corrected gate (a) vs default (b)", "track-record size cut off (a) vs on (b)",
                                          "cash leg off (a) vs on (b)", "v0.3+ rules (a) vs v0.2 rules (b), core"]),
    ("Execution and impact", ["execution algorithm, $1B holdout portfolio", "impact sweep, core universe"]),
    ("VaR coverage", ["VaR coverage: rolling historical VaR", "VaR coverage: the desk's own per-instrument forecast"]),
    ("Selection statistics on one statistic", ["trials registry:", "selection statistics for the frozen rules"]),
    ("Rebalance-phase sweep", ["rebalance-phase sweep"]),
]

INTRO = """# v0.11 review measurement: every published table under the corrected engine

This page is written by `scripts/render_v11_doc.py` from `results/v11/tables.md`, which
`scripts/render_v08_tables.py --in results/v11` renders from the files
`scripts/measure_v08.py --out results/v11` wrote. No number on this page is typed. It is the
re-measurement after the tier-2 review ([CHANGELOG](../../CHANGELOG.md), "Unreleased —
v0.11"): EDGAR visible from the session whose close could know a filing, market impact priced
on the as-traded close, the aggressive risk analyst sized at 1.25× the vol-targeted weight,
the news analyst's confidence by the tone its headlines carry, evaluation rows at full
precision, Benjamini–Hochberg over the printed rows, and the deflated Sharpe on every
trial's portfolio Sharpe.

Conventions are those of the v0.8 section of [evaluation.md](evaluation.md): summary tables
report the median Sharpe across instruments; paired tables the mean difference with a 95%
bootstrap interval (`instruments` on core and extended, `clusters` on all 60), two-sided p
and the BH flag over the table's rows; on/off tables print p and no BH flag; Sharpe and
Sortino are on excess returns over the credited bill; `wins` counts the instruments where
the desk's value is the larger, whatever the metric. The two rule changes of v0.11 were
chosen on the 2016–2021 design period against their v0.8 counterparts, which are registered
trials in the table below; the holdout is reported, not chosen on.

"""


def section(text: str, title_start: str) -> str | None:
    m = re.search(r"^### " + re.escape(title_start) + r".*?(?=^### |\Z)", text, re.S | re.M)
    return None if m is None else m.group(0).rstrip().replace("### ", "#### ", 1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v11"))
    a = ap.parse_args(argv)
    d = Path(a.inp)
    tables = (d / "tables.md").read_text(encoding="utf-8")
    manifest = json.load(open(d / "manifest.json", encoding="utf-8"))
    prov = manifest["provenance"]
    out = [INTRO, f"Measured {manifest['finished']} at commit `{prov['git_commit'][:7]}` "
           f"({'dirty' if prov['git_dirty'] else 'clean'} tree), {prov['quant_backend']} backend, {manifest['seconds']} s.\n"]
    missing = []
    for title, keys in SECTIONS:
        out.append(f"\n## {title}\n")
        for k in keys:
            s = section(tables, k)
            if s is None:
                missing.append(k)
            else:
                out.append(s)
    if missing:
        out.append("\n_Sections not rendered in this measurement: " + "; ".join(missing) + "_\n")
    path = ROOT / "docs" / "evaluation" / "v011_review.md"
    path.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {path}: {sum(1 for l in out if l.startswith('####'))} tables, missing {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
