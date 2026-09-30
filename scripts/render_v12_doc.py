"""Write docs/evaluation/v012_trend_core.md from the v0.12 result files (no number is typed).

Copies, verbatim, the tables ``scripts/render_v09_tables.py --in results/v12`` rendered from
the ``scripts/measure_v09.py --period design_long --out results/v12`` runs, the stream
combination ``scripts/combine_v09.py --in results/v12 --trend "TSMOM(L/S)" --tag _ls`` wrote
and the overlay report of ``scripts/overlay_v09.py --out results/v12 --files ...``. The prose
around them is fixed text. The three source files are also copied to ``docs/results/v12``.

    .venv\\Scripts\\python.exe scripts/render_v12_doc.py [--in results/v12]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS = ("etf11_rp", "etf11_equal", "fx15_rp", "all26_rp")
SOURCES = ("tables.md", "combine_ls.md", "overlay.md")

INTRO = """# v0.12: a longer design period, long/short trend across asset classes, and the vol-target core

Follows [v09_research.md](v09_research.md), [v010_overlay.md](v010_overlay.md) and
[v011_review.md](v011_review.md). This page is written by `scripts/render_v12_doc.py`; every
table is copied from `results/v12/` (kept under [docs/results/v12](../results/v12)). No number
on this page is typed.

**Outcome, stated first: nothing is adopted.** On the longer design period the long/short
multi-horizon trend stream does not beat the vol-target control on any run, no book built
from the streams beats the multi-asset base, and no size of the desk's tilt over the
vol-target core can be told apart from the control. For each of these candidates the
interval against the control includes zero. The tables are below so the reader can check that sentence.

## What was asked, and the rule set before measuring

The tier-2 review approved three steps, to be run in this order, on design data only:

1. **A longer design period.** `design_long` runs from 2008-07-01 to 2021-12-31, the earliest
   date at which the eleven ETFs of the multi-asset universe have a year of history. It ends
   where the old design period ends, so it contains no holdout or reserve day. It includes
   2008 and 2011, which the 2016 to 2021 period does not.
2. **Trend as the literature defines it.** `TSMOM(L/S)` is the average sign of the trailing
   1, 3 and 12 month return, long and short, at the vol-target size (Moskowitz, Ooi and
   Pedersen 2012). The v0.9 stream `TSMOM(12-1)` was long-only on equities and used one
   horizon. The signal is `quant.strat_tsmom`, in the C++ core with a numpy twin.
3. **The vol-target book as the core.** The desk's tilt is added at size `lam` over the
   control, `r(lam) = control + lam * (desk - control)`, on the longer period.

The adoption rule is the one the project has used since v0.9: a change is adopted only if
its design-period Sharpe difference against the run's own `B&H vol-target` control has a 95%
block-bootstrap interval above zero. The holdout and the reserve are spent and were not
consulted. Every variant printed here is registered in `evaluation.TRIALS` (version `v0.12`).

Two limits of this round. The 15-instrument core universe cannot be run from 2008 (one of
its stocks listed in 2012), so the overlay is measured on the ETF, FX and combined runs and
not on the core 15. And the desk's analysts see less before 2016: filings coverage is
thinner, so the desk's own rows on this period are not the v0.11 desk on its usual footing.

Conventions are those of [v09_research.md](v09_research.md): Sharpe on excess returns over
the credited bill, risk parity across sleeves from a 120-day covariance window with no
look-ahead, the paired circular block bootstrap over days (block 10, 5000 resamples). On the
ETF runs the `Carry` row is idle cash, not a carry measurement.

"""

READING = """
## Reading

* **Trend.** Read the `TSMOM(L/S)` row of each difference table against the run's control,
  and beside the long-only `TSMOM(12-1)` row of the same table. Allowing shorts did not help
  on the ETF runs; on FX both trend rows sit near the control with wide intervals.
* **Books.** Adding the trend and carry streams to the base lowers volatility and drawdown
  and lowers the Sharpe ratio with them; no book's interval against the base is above zero.
* **Overlay.** Where the control earns something (the ETF run) the Sharpe falls as `lam`
  rises; on FX nothing earns. No size is distinguishable from the control.
* **One row that looks significant.** `KDJ+RSI` on the FX run has an interval above zero. It
  is an old baseline, not a candidate of this round, one of 36 difference rows on this page,
  and the same rule is below the control on the ETF runs. It is not adopted.
* **What this does not say.** It does not say trend following does not work. It says that
  these costed streams, on these 26 instruments and this period, did not beat a vol-targeted
  holding of the same instruments by more than the noise. A futures universe across more
  asset classes is the setting the literature reports, and the project does not have it.

The test that remains is the forward paper-trading record
([v09_preregistration.md](v09_preregistration.md)), which is the only unseen data.
"""


def section(text: str, start: str) -> str:
    i = text.index(start)
    j = text.find("\n### ", i + 1)
    return text[i:j if j != -1 else len(text)].rstrip().replace("### ", "#### ", 1) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v12"))
    a = ap.parse_args(argv)
    d = Path(a.inp)
    tables = (d / "tables.md").read_text(encoding="utf-8")
    out = [INTRO]
    provs = {r: json.load(open(d / f"{r}.json", encoding="utf-8"))["provenance"] for r in RUNS}
    out.append("Provenance: " + "; ".join(f"`{r}` at commit `{p['git_commit'][:7]}` ({'dirty' if p['git_dirty'] else 'clean'} tree), "
                                           f"{p['quant_backend']} backend" for r, p in provs.items()) + ".\n")
    out.append("\n## Step 1 and 2: the runs on the longer design period\n")
    for r in RUNS:
        out.append(section(tables, f"### portfolio table, {r}:"))
        out.append(section(tables, f"### Sharpe difference against the run's B&H vol-target (paired block bootstrap over days): {r}\n"))
    out.append("\n## Step 2: books built with the long/short trend stream\n")
    out.append((d / "combine_ls.md").read_text(encoding="utf-8").split("\n", 1)[1].replace("\n## ", "\n#### ").strip() + "\n")
    out.append("\n## Step 3: the vol-target core with the desk's tilt at size lam\n")
    out.append((d / "overlay.md").read_text(encoding="utf-8").split("\n", 1)[1].replace("\n## ", "\n#### ").strip() + "\n")
    out.append(READING)
    path = ROOT / "docs" / "evaluation" / "v012_trend_core.md"
    path.write_text("\n".join(out), encoding="utf-8")
    keep = ROOT / "docs" / "results" / "v12"
    keep.mkdir(parents=True, exist_ok=True)
    for name in SOURCES:
        shutil.copyfile(d / name, keep / name)
    print(f"wrote {path} and {len(SOURCES)} files under {keep}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
