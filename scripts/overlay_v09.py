"""Change 1 of the post-v0.9 plan: the vol-targeted book as the core, the desk's tilt as a sized overlay.

The v0.8 attribution found the desk's daily return is the vol-target control's (beta about 0.9, R^2
about 0.87) plus a tilt with no alpha. This tests the obvious consequence: hold the control and add
only a fraction ``lam`` of the tilt,

    r(lam) = r_control + lam * (r_desk - r_control)        lam = 0 is the control, lam = 1 the desk

on the same 15 core sleeves, equal capital (``results/v08/portfolio_{design,holdout}.csv``). The
blend is done on the daily returns of two fully costed streams, so trades that would net between the
control and the desk are costed twice: the blend's costs are an upper bound, and its Sharpe a
conservative one. Sharpe is on excess returns over the credited bill (260 periods a year, rf[:-1]
paired with returns[1:], the portfolio tables' convention).

Protocol: ``lam`` is chosen on the design period only. The holdout is printed as a report and is not a
basis for the choice. Every difference carries a paired circular block-bootstrap interval over days
(block 10, 5000 resamples). The grid has 5 values and all count as trials.

Writes ``results/v09/overlay.{md,json}``.

    .venv\\Scripts\\python.exe scripts/overlay_v09.py [--in results/v08] [--out results/v09]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.backtest import AGENT  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402
from agentic_trader.stats import paired_sharpe_block_bootstrap, sharpe_stats  # noqa: E402

PPY = 260.0
CONTROL = "B&H vol-target"
GRID = (0.0, 0.25, 0.5, 0.75, 1.0)


def blend(desk: np.ndarray, control: np.ndarray, lam: float) -> np.ndarray:
    """``control + lam * (desk - control)``: lam 0 is the control, 1 the desk, in between a sized tilt."""
    return control + lam * (desk - control)


def excess(r: np.ndarray, rf: np.ndarray) -> np.ndarray:
    """Daily excess returns: bar 0 is the flat first day, the bill credited over (t-1, t] is rf[t-1]."""
    return np.asarray(r, dtype=float)[1:] - np.nan_to_num(np.asarray(rf, dtype=float)[:-1]) / PPY


def mdd_pct(returns: np.ndarray) -> float:
    eq = np.cumprod(1.0 + np.asarray(returns, dtype=float))
    return float((1.0 - eq / np.maximum.accumulate(eq)).max() * 100)


def run_period(frame: pd.DataFrame) -> dict:
    desk, ctl, rf = frame[AGENT].to_numpy(float), frame[CONTROL].to_numpy(float), frame["rf"].to_numpy(float)
    ctl_x, desk_x = excess(ctl, rf), excess(desk, rf)
    rows = {}
    for lam in GRID:
        r = blend(desk, ctl, lam)
        x = excess(r, rf)
        s = sharpe_stats(x, PPY)
        rows[str(lam)] = {"lam": lam, "sharpe": s.sharpe_annual, "vol_pct": float(x.std(ddof=1) * np.sqrt(PPY) * 100),
                          "cumulative_return_pct": float((np.prod(1.0 + r) - 1.0) * 100), "mdd_pct": mdd_pct(r),
                          "vs_control": asdict(paired_sharpe_block_bootstrap(x, ctl_x, PPY, block=10, n_boot=5000)),
                          "vs_desk": asdict(paired_sharpe_block_bootstrap(x, desk_x, PPY, block=10, n_boot=5000))}
    return {"n": int(ctl_x.size), "rows": rows}


def fmt(d: dict) -> str:
    return f"{d['diff']:+.2f} [{d['ci_low']:+.2f}, {d['ci_high']:+.2f}] p {d['p_value']:.3f}"


def render(res: dict) -> str:
    out = ["# Change 1: the vol-targeted book as the core, the desk's tilt at size lam (15 core sleeves, equal capital)\n",
           "r(lam) = control + lam * (desk - control); lam 0 is `B&H vol-target`, lam 1 the desk. Excess-return Sharpe, "
           "260 periods/year, paired block bootstrap over days. Chosen on the design period only.\n"]
    for period in ("design", "holdout"):
        p = res["periods"][period]
        label = "design (the choice basis)" if period == "design" else "holdout (a report, not a basis for the choice)"
        out += [f"## {period}: {label}, n = {p['n']} days\n",
                "| lam | Sharpe | vol %/yr | cumulative return % | MDD % | Sharpe - control [95% CI] p | Sharpe - desk [95% CI] p |",
                "|--:|--:|--:|--:|--:|:--|:--|"]
        for r in p["rows"].values():
            out.append(f"| {r['lam']:.2f} | {r['sharpe']:.2f} | {r['vol_pct']:.2f} | {r['cumulative_return_pct']:.2f} | "
                       f"{r['mdd_pct']:.2f} | {fmt(r['vs_control'])} | {fmt(r['vs_desk'])} |")
        out.append("")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v08"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v09"))
    a = ap.parse_args(argv)
    inp, out = Path(a.inp), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    res = {"grid": GRID, "ppy": PPY, "source": str(inp), "periods": {}, "provenance": provenance()}
    for period in ("design", "holdout"):
        res["periods"][period] = run_period(pd.read_csv(inp / f"portfolio_{period}.csv", index_col=0, parse_dates=True))
    (out / "overlay.json").write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    text = render(res)
    (out / "overlay.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
