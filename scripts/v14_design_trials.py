"""v0.14 plan items 5.1-5.3: the three registered trials on the DESIGN period only.

Runs the offline desk (rules, no model) on the 15 core names over ``evaluation.PERIODS
["design"]`` four times: the current rules desk for reference, then each v0.14 trial in
``evaluation.TRIALS`` (IC-weighted combination; plus HMM regime conditioning; plus
conformal interval sizing), and writes one JSON per run to ``results/v14/``. Each run
reports the desk's design Sharpe per name next to the vol-targeted buy-and-hold control,
the mean difference and a cross-instrument bootstrap of it.

A second diagnostic measures the pre-registered expectation directly: for every name and
every fifth design bar, ``combine.desk_forecast`` on the point-in-time history, recording
how often no signal survives the shrinkage and the mean absolute tilt
(``results/v14/ic_tilt_design.json``).

History before the design start is fetched only for warm-up; nothing after the design end
is requested, so the holdout is never read. Each output is skipped when it already exists.

    .venv\\Scripts\\python.exe scripts/v14_design_trials.py [--out results/v14]

Uses the Yahoo provider (network); the test suite never runs this script.

Status (2026-11-08): every output has run (``results/v14/``). The regime-conditioned and
conformal-sized trials ran after follow-up 5.2b cached the per-series research inputs.
Re-running this script fills only missing files.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.backtest import AGENT  # noqa: E402
from agentic_trader.combine import desk_forecast  # noqa: E402
from agentic_trader.config import make_config  # noqa: E402
from agentic_trader.data import get_provider  # noqa: E402
from agentic_trader.evaluation import PERIODS, TRIALS, UNIVERSES, evaluate, trial_slug  # noqa: E402
from agentic_trader.instruments import Instrument  # noqa: E402

CONTROL = "B&H vol-target"
V14 = [t for t in TRIALS if t.version == "v0.14"]


def _jsonable(x):
    if is_dataclass(x) and not isinstance(x, type):
        return _jsonable(asdict(x))
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return None if not math.isfinite(float(x)) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    return x


def run_eval(name: str, overrides: dict, provider) -> dict:
    t0 = time.perf_counter()
    res = evaluate(UNIVERSES["core"], {"design": PERIODS["design"]}, overrides, provider=provider)
    rows = res.rows
    piv = rows.pivot_table(index="symbol", columns="strategy", values="Sharpe", aggfunc="mean")
    both = piv[[AGENT, CONTROL]].dropna()
    diff = both[AGENT] - both[CONTROL]
    try:
        boot = _jsonable(res.paired(baseline=CONTROL, period="design"))
    except ValueError as exc:
        boot = {"error": str(exc)}
    return {"trial": name, "overrides": overrides, "period": PERIODS["design"],
            "n_symbols": int(len(both)), "meta_failures": _jsonable(res.meta.get("failures")),
            "sharpe": {s: {"agent": float(r[AGENT]), "control": float(r[CONTROL])} for s, r in both.iterrows()},
            "mean_sharpe_agent": float(both[AGENT].mean()), "mean_sharpe_control": float(both[CONTROL].mean()),
            "mean_diff_vs_control": float(diff.mean()), "beats_control": int((diff > 0).sum()),
            "paired_bootstrap_vs_control": boot,
            "summary": _jsonable(res.summary("design").reset_index().to_dict(orient="records")),
            "seconds": round(time.perf_counter() - t0, 1)}


def tilt_diagnostic(provider, step: int = 5) -> dict:
    cfg = make_config({"combination": {"method": "ic", "window": 504}})
    comb = {**cfg["combination"], "conformal": cfg["conformal"]}
    start, end = (date.fromisoformat(x) for x in PERIODS["design"])
    out = {}
    for sym in UNIVERSES["core"]:
        ins = Instrument.parse(sym)
        h = provider.history(ins, start - timedelta(days=1400), end)
        h = h[h.index <= pd.Timestamp(end)]
        carry = provider.carry_series(ins, h.index) if ins.is_fx else None
        pos = np.flatnonzero(h.index >= pd.Timestamp(start))[::step]
        tilts, active = [], []
        for i in pos:
            f = desk_forecast(h.iloc[: i + 1], ins, comb, None if carry is None else carry[: i + 1])
            tilts.append(f.tilt if math.isfinite(f.tilt) else 0.0)
            active.append(len(f.active))
        t, a = np.array(tilts), np.array(active)
        out[sym] = {"dates": int(t.size), "share_no_signal": float((a == 0).mean()),
                    "mean_abs_tilt": float(np.abs(t).mean()), "median_abs_tilt": float(np.median(np.abs(t))),
                    "mean_active_signals": float(a.mean())}
    vals = list(out.values())
    return {"period": PERIODS["design"], "window": 504, "step": step, "per_symbol": out,
            "share_no_signal": float(np.mean([v["share_no_signal"] for v in vals])),
            "mean_abs_tilt": float(np.mean([v["mean_abs_tilt"] for v in vals]))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("results/v14"))
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    provider = get_provider(make_config({"data_provider": "yahoo"}))
    path = a.out / "ic_tilt_design.json"
    if not path.exists():
        path.write_text(json.dumps(tilt_diagnostic(provider), indent=2), encoding="utf-8")
    d = json.loads(path.read_text(encoding="utf-8"))
    print(f"tilt diagnostic: no surviving signal on {d['share_no_signal']:.1%} of design dates, "
          f"mean |tilt| {d['mean_abs_tilt']:.3f}")
    runs = [("rules desk (current default)", {})] + [(t.name, t.overrides) for t in V14]
    for name, ov in runs:
        path = a.out / f"design_{trial_slug(name)}.json"
        if not path.exists():
            path.write_text(json.dumps(run_eval(name, ov, provider), indent=2), encoding="utf-8")
        r = json.loads(path.read_text(encoding="utf-8"))
        print(f"{name}: mean Sharpe {r['mean_sharpe_agent']:+.3f} vs control {r['mean_sharpe_control']:+.3f} "
              f"(diff {r['mean_diff_vs_control']:+.3f}, beats control on {r['beats_control']}/{r['n_symbols']})")


if __name__ == "__main__":
    main()
