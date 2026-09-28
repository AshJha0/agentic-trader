"""Write docs/evaluation/v09_research.md from the v0.9 result files (no number is typed).

Assembles the design-period runs (``results/v09``) and the pre-registered holdout report
(``results/v09/holdout``): for each run the portfolio table and the paired block-bootstrap
Sharpe differences against the run's ``B&H vol-target``, then the stream combination
tables, with the fixed prose around them. Every table is copied from ``tables.md`` /
``combine.md`` as rendered by ``scripts/render_v09_tables.py`` and ``scripts/combine_v09.py``.

    .venv\\Scripts\\python.exe scripts/render_v09_doc.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ("etf11_rp", "etf11_equal", "fx15_rp", "core15_rp", "all26_rp")


def section(text: str, title_start: str) -> str:
    """The '### <title_start>...' section of a tables.md, heading included."""
    m = re.search(r"^### " + re.escape(title_start) + r".*?(?=^### |\Z)", text, re.S | re.M)
    if not m:
        raise SystemExit(f"section starting {title_start!r} not found")
    return m.group(0).rstrip() + "\n"


def combine_tables(text: str) -> str:
    body = text.split("\n", 1)[1]                       # drop the H1
    return body.replace("\n## ", "\n#### ").strip() + "\n"


def provenance_line(d: Path) -> str:
    m = json.load(open(d / "manifest.json", encoding="utf-8"))
    p = m["provenance"]
    return (f"Measured {m['finished']} at commit `{p['git_commit'][:7]}` "
            f"({'dirty' if p['git_dirty'] else 'clean'} tree), {p['quant_backend']} backend, {m['seconds']} s.")


def block(d: Path, label: str) -> str:
    tables = (d / "tables.md").read_text(encoding="utf-8")
    out = [provenance_line(d), ""]
    for run in RUNS:
        out.append(section(tables, f"portfolio table, {run}").replace("### ", "#### ", 1))
        out.append(section(tables, "Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): " + run)
                   .replace("### ", "#### ", 1))
    out.append(f"#### Stream combination ({label})\n")
    out.append(combine_tables((d / "combine.md").read_text(encoding="utf-8")))
    return "\n".join(out)


INTRO = """# v0.9 research: a multi-asset base, trend and carry, and the forward test

This is the record of the v0.9 plan (chosen after the v0.8 attribution showed the desk's
active tilts add nothing over the vol-targeted control) and its outcome. Every number
below is copied from `results/v09/tables.md`, `results/v09/combine.md` and
`results/v09/holdout/*` by `scripts/render_v09_doc.py`; the pre-registration written
before the holdout run is [v09_preregistration.md](v09_preregistration.md).

**Outcome in one sentence: on the 2016–2021 design period none of the three candidate
streams beats its control and no combination beats the multi-asset base, so nothing is
adopted; the holdout report below is a report, not a choice; the forward paper-trading
record (`scripts/paper_trade_v09.py`, frozen 2026-09-29) is the test.**

Conventions: Sharpe on excess returns over the credited bill; `B&H vol-target` is the
mechanical control of every run; the paired block bootstrap over days (block 10, 5000
resamples) gives every difference its interval and two-sided p; risk parity re-estimates
capital shares every 5 bars from a 120-day covariance window with no look-ahead. The two
new streams are baselines in every sleeve since this branch: `TSMOM(12-1)` (sign of the
trailing 12-month return skipping the last month, at the vol-target size, long-only where
shorts are not allowed) and `Carry` (the FX carry premium at the desk's strategic size;
flat on equities, so its row is 0 in the ETF runs).

## Phase 0: attribution of the v0.8 desk (`scripts/attribution_v09.py`)

"""

DESIGN = """
## Phases 1–3 on the design period (2016-01-04 → 2021-12-31)

Runs: `etf11_rp` (SPY EFA EEM IWM TLT IEF LQD HYG GLD DBC VNQ, risk parity), `etf11_equal`
(1/N), `fx15_rp` (the 15 FX pairs), `core15_rp` (the v0.8 core universe under risk
parity; v0.8 used 1/N) and `all26_rp` (ETFs + FX with class budgets equity 0.6 / fx 0.4).

"""

HOLDOUT = """
## The pre-registered holdout report (2022-01-03 → 2026-06-30)

Reported once, after the design-period verdict and the pre-registration; not a basis for
any choice (see [v09_preregistration.md](v09_preregistration.md)).

"""

FORWARD = """
## The forward test

`scripts/paper_trade_v09.py` recomputes, from 2026-09-29 to the last complete session,
the fully costed returns of the frozen books — the v0.8 desk on the core 15 (equal
capital) with its `B&H vol-target` and `Buy&Hold` controls; the 11-ETF risk-parity base
with `TSMOM(12-1)`; the 15 FX pairs with `Carry` and `TSMOM(12-1)` — and writes
`results/paper/ledger.csv`, `summary.md` (intervals after 60 sessions) and `runs.jsonl`
(provenance and any revision of an earlier return). A candidate is adopted only when its
forward Sharpe minus its control's clears a block-bootstrap interval that excludes zero.
"""


def main() -> int:
    design, holdout = ROOT / "results" / "v09", ROOT / "results" / "v09" / "holdout"
    attribution = (design / "attribution.md").read_text(encoding="utf-8").split("\n", 1)[1]
    doc = (INTRO + attribution.replace("\n## ", "\n### ").strip() + "\n" + DESIGN + block(design, "design")
           + HOLDOUT + block(holdout, "holdout") + FORWARD)
    out = ROOT / "docs" / "evaluation" / "v09_research.md"
    out.write_text(doc, encoding="utf-8")
    print(f"wrote {out}: {len(doc.splitlines())} lines")
    return 0


if __name__ == "__main__":
    sys.exit(main())
