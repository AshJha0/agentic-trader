"""v0.14 plan item 5.4: VaR calibration of three forecasters on the DESIGN period only.

For each of the 15 core names (``evaluation.CORE_UNIVERSE``) the 1-day 95% VaR is forecast
by the trailing 250-day historical quantile (the rule that failed in PLAN.md section 2:
Kupiec 2/15, independence 6/15), by RiskMetrics EWMA and by filtered historical simulation
(``agentic_trader.risk_model``), and each forecast series is judged by ``stats.var_backtest``
on the design days (``evaluation.PERIODS["design"]``). History before the design start is
fetched only to warm the forecasters up; nothing after the design end is requested, so the
holdout is never read. A name passes a test when its p-value is at least ``--level``.

    .venv\\Scripts\\python.exe scripts/v14_var_design.py [--level 0.05] [--out results/v14/var_design.json]

Uses the Yahoo provider (network); the test suite never runs this script.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_trader.config import DEFAULT_CONFIG
from agentic_trader.data.yahoo import YahooProvider
from agentic_trader.evaluation import CORE_UNIVERSE, PERIODS
from agentic_trader.instruments import Instrument
from agentic_trader.risk_model import VAR_METHODS, var_forecast
from agentic_trader.stats import var_backtest

WARMUP_DAYS = 550   # calendar days before the design start: > 250 trading days of window


def evaluate(level: float) -> dict:
    start, end = (date.fromisoformat(x) for x in PERIODS["design"])
    provider = YahooProvider(DEFAULT_CONFIG)
    symbols = CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]
    rows, counts = [], {m: {"kupiec": 0, "independence": 0, "both": 0} for m in VAR_METHODS}
    for sym in symbols:
        h = provider.history(Instrument.parse(sym), start - timedelta(days=WARMUP_DAYS), end)
        r = h["Close"].pct_change()
        r = r[r.index <= pd.Timestamp(end)]
        in_design = np.asarray(r.index >= pd.Timestamp(start))
        for m in VAR_METHODS:
            f = var_forecast(r.to_numpy(float), m)
            bt = var_backtest(r.to_numpy(float)[in_design], f[in_design])
            kup = bool(bt.kupiec_p >= level)
            ind = bt.christoffersen_p is not None and bool(bt.christoffersen_p >= level)
            counts[m]["kupiec"] += kup
            counts[m]["independence"] += ind
            counts[m]["both"] += kup and ind
            rows.append({"symbol": sym, "method": m, "n": bt.n, "breaches": bt.breaches,
                         "breach_rate": round(bt.breach_rate, 4), "kupiec_p": bt.kupiec_p,
                         "christoffersen_p": (None if bt.christoffersen_p is None
                                              else round(float(bt.christoffersen_p), 4))})
    return {"period": PERIODS["design"], "level": level, "n_symbols": len(symbols),
            "pass_counts": counts, "rows": rows,
            "mean_breach_rate": {m: float(np.mean([x["breach_rate"] for x in rows if x["method"] == m]))
                                 for m in VAR_METHODS}}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--level", type=float, default=0.05)
    ap.add_argument("--out", type=Path, default=Path("results/v14/var_design.json"))
    a = ap.parse_args()
    res = evaluate(a.level)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    for m, c in res["pass_counts"].items():
        print(f"{m:>10}: Kupiec {c['kupiec']}/{res['n_symbols']}, independence "
              f"{c['independence']}/{res['n_symbols']}, both {c['both']}/{res['n_symbols']}")


if __name__ == "__main__":
    main()
