"""Phase 0 of the v0.9 plan: where does the desk's portfolio Sharpe come from?

Reads the v0.8 portfolio return files (``results/v08/portfolio_{design,holdout}.csv``: one
daily return per strategy plus the credited ``rf``) and decomposes the desk against the two
controls on excess returns:

* the active tilt ``desk - vol-target`` (what the signals add on top of a mechanical
  volatility-targeted holding of the same sleeves), with its own annualised Sharpe and a
  circular block-bootstrap interval;
* a regression of the desk's excess return on the control's: annualised alpha, beta, the
  information ratio of the residual and R^2;
* the same against plain buy & hold;
* trades and exposure per sleeve from ``eval_main.json`` (the desk's turnover).

Writes ``results/v09/attribution.{md,json}``. Annualisation uses 260 periods per year, the
portfolio tables' convention (the largest periods-per-year among the sleeves; FX is present).

    .venv\\Scripts\\python.exe scripts/attribution_v09.py [--in results/v08] [--out results/v09]
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
from agentic_trader.evaluation import EvaluationResult  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402
from agentic_trader.stats import paired_sharpe_block_bootstrap, sharpe_stats  # noqa: E402

PPY = 260.0
CONTROLS = ("B&H vol-target", "Buy&Hold")


def excess(frame: pd.DataFrame, col: str) -> np.ndarray:
    r = frame[col].to_numpy(float)[1:]                     # bar 0 is the flat first day
    rf = frame["rf"].to_numpy(float)[:-1]                  # the rate credited over (t-1, t]
    return r - np.where(np.isfinite(rf), rf, 0.0) / PPY


def regress(y: np.ndarray, x: np.ndarray) -> dict:
    x1 = np.column_stack([np.ones_like(x), x])
    coef, *_ = np.linalg.lstsq(x1, y, rcond=None)
    resid = y - x1 @ coef
    n, k = y.size, 2
    ss_res, ss_tot = float(resid @ resid), float(((y - y.mean()) ** 2).sum())
    sigma = np.sqrt(ss_res / (n - k))                                   # residual std, OLS dof
    se_alpha = sigma * np.sqrt(np.linalg.inv(x1.T @ x1)[0, 0])
    # information ratio: the alpha per unit of residual risk (the OLS residual itself has mean 0)
    ir = float(coef[0] / sigma * np.sqrt(PPY)) if sigma > 0 else float("nan")
    return {"alpha_annual_pct": float(coef[0] * PPY * 100), "alpha_t": float(coef[0] / se_alpha) if se_alpha > 0 else float("nan"),
            "beta": float(coef[1]), "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan"),
            "information_ratio": ir, "residual_vol_pct": float(sigma * np.sqrt(PPY) * 100), "n": int(n)}


def decompose(frame: pd.DataFrame) -> dict:
    d = excess(frame, AGENT)
    out = {"n": int(d.size), "desk_sharpe": sharpe_stats(d, PPY).sharpe_annual,
           "desk_vol_pct": float(d.std(ddof=1) * np.sqrt(PPY) * 100)}
    for c in CONTROLS:
        v = excess(frame, c)
        tilt = d - v
        # the tilt's own Sharpe with a block-bootstrap interval: Sharpe(tilt) - Sharpe(0) over the same days
        boot = paired_sharpe_block_bootstrap(tilt, np.zeros_like(tilt), PPY, block=10, n_boot=5000)
        out[c] = {"control_sharpe": sharpe_stats(v, PPY).sharpe_annual,
                  "control_vol_pct": float(v.std(ddof=1) * np.sqrt(PPY) * 100),
                  "sharpe_difference": asdict(paired_sharpe_block_bootstrap(d, v, PPY, block=10, n_boot=5000)),
                  "correlation": float(np.corrcoef(d, v)[0, 1]),
                  "tilt": {"mean_annual_pct": float(tilt.mean() * PPY * 100),
                           "vol_annual_pct": float(tilt.std(ddof=1) * np.sqrt(PPY) * 100),
                           "sharpe": boot.sharpe_a, "ci_low": boot.ci_low, "ci_high": boot.ci_high,
                           "p_value": boot.p_value},
                  "regression": regress(d, v)}
    return out


def turnover(res: EvaluationResult, period: str) -> dict:
    rows = res.rows[(res.rows["period"] == period) & (res.rows["universe"] == "core")]
    g = rows.groupby("strategy")[["Trades", "Exp%"]].mean()
    return {s: {"trades_mean": float(g.loc[s, "Trades"]), "exposure_mean_pct": float(g.loc[s, "Exp%"])}
            for s in g.index}


def fmt(x: float, nd: int = 2) -> str:
    return "" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def render(results: dict) -> str:
    out = ["# v0.9 phase 0: attribution of the desk's portfolio Sharpe (v0.8 files, 15 core sleeves, 260 periods/year)\n"]
    for period, r in results["periods"].items():
        out.append(f"## {period} (n = {r['n']} days)\n")
        out.append("| series | Sharpe (excess) | vol % | corr with desk |\n|:--|--:|--:|--:|")
        out.append(f"| desk | {fmt(r['desk_sharpe'])} | {fmt(r['desk_vol_pct'])} | 1.00 |")
        for c in CONTROLS:
            out.append(f"| {c} | {fmt(r[c]['control_sharpe'])} | {fmt(r[c]['control_vol_pct'])} | {fmt(r[c]['correlation'])} |")
        out.append("")
        out.append("| against | desk − control Sharpe [95% CI] p | tilt mean %/yr | tilt vol %/yr | tilt Sharpe [95% CI] p | alpha %/yr (t) | beta | R² | IR | residual vol %/yr |")
        out.append("|:--|:--|--:|--:|:--|:--|--:|--:|--:|--:|")
        for c in CONTROLS:
            x, t, g = r[c], r[c]["tilt"], r[c]["regression"]
            sd = x["sharpe_difference"]
            out.append(f"| {c} | {sd['diff']:+.2f} [{sd['ci_low']:+.2f}, {sd['ci_high']:+.2f}] p {sd['p_value']:.3f} "
                       f"| {t['mean_annual_pct']:+.2f} | {fmt(t['vol_annual_pct'])} "
                       f"| {t['sharpe']:+.2f} [{t['ci_low']:+.2f}, {t['ci_high']:+.2f}] p {t['p_value']:.3f} "
                       f"| {g['alpha_annual_pct']:+.2f} ({g['alpha_t']:+.2f}) | {fmt(g['beta'])} | {fmt(g['r2'])} | {g['information_ratio']:+.2f} | {fmt(g['residual_vol_pct'])} |")
        out.append("")
        tv = results["turnover"].get(period, {})
        if tv:
            out.append("| strategy | mean trades per sleeve | mean exposure % |\n|:--|--:|--:|")
            for s, v in tv.items():
                out.append(f"| {s} | {fmt(v['trades_mean'], 1)} | {fmt(v['exposure_mean_pct'], 1)} |")
            out.append("")
    out.append("Reading: the tilt is the desk's daily excess return minus the control's on the same day; its "
               "Sharpe is what the signals add on top of holding the same sleeves mechanically. The regression "
               "gives the same thing as alpha (annualised intercept, with its t) and beta on the control; the "
               "information ratio is alpha per unit of residual risk. Intervals: circular block bootstrap over days (block 10, 5000 resamples).")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--in", dest="inp", default=str(ROOT / "results" / "v08"))
    ap.add_argument("--out", default=str(ROOT / "results" / "v09"))
    a = ap.parse_args(argv)
    inp, out = Path(a.inp), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    results = {"periods": {}, "turnover": {}, "ppy": PPY, "source": str(inp), "provenance": provenance()}
    for period in ("design", "holdout"):
        frame = pd.read_csv(inp / f"portfolio_{period}.csv", index_col=0, parse_dates=True)
        results["periods"][period] = decompose(frame)
    main_res = EvaluationResult.from_json(inp / "eval_main.json")
    for period in ("design", "holdout"):
        results["turnover"][period] = turnover(main_res, period)
    (out / "attribution.json").write_text(json.dumps(results, indent=1, default=float), encoding="utf-8")
    (out / "attribution.md").write_text(render(results), encoding="utf-8")
    print(render(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
