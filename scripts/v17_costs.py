"""v0.17 lane L8: impact-coefficient calibration from free OHLC, and the decay-derived
rebalance table, both on the DESIGN period only (rules only, no model).

    python scripts/v17_costs.py validate              # estimator check on simulated OHLC (no network)
    python scripts/v17_costs.py calibrate --provider yahoo   # spread estimates and Y per core equity
    python scripts/v17_costs.py horizon --provider yahoo     # IC half-life -> rebalance, per alpha x name

Output goes to docs/results/v17_costs/ (markdown + json). ``validate`` is what the repository
ships; the two ``--provider yahoo`` runs need network and are queued for the maintainer
(see docs/review/v017_notes/L8_quant_rest.md). Nothing after the design end is requested.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from agentic_trader.config import DEFAULT_CONFIG
from agentic_trader.execution_realism import calibrate_impact, simulate_ohlc, spread_estimates
from agentic_trader.horizon import rebalance_from_decay

OUT = Path("docs/results/v17_costs")
WARMUP_DAYS = 400


def _write(name: str, frame: pd.DataFrame, header: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(frame.reset_index().to_json(orient="records", indent=1), encoding="utf-8")
    (OUT / f"{name}.md").write_text(header + "\n\n" + frame.to_markdown(floatfmt=".3f") + "\n", encoding="utf-8")


def validate(seeds: int = 5, days: int = 1500) -> pd.DataFrame:
    rows = []
    for spread_bp in (2.0, 5.0, 10.0, 20.0):
        for vol in (0.01, 0.02):
            cs, csf, ar = [], [], []
            for s in range(seeds):
                est = spread_estimates(simulate_ohlc(days, spread_bp / 1e4, vol, seed=s))
                cs.append(1e4 * est["corwin_schultz"])
                csf.append(1e4 * est["corwin_schultz_floored"])
                ar.append(1e4 * est["abdi_ranaldo"])
            rows.append(
                {
                    "true_spread_bp": spread_bp,
                    "daily_vol_pct": 100 * vol,
                    "cs_mean_bp": float(np.mean(cs)),
                    "cs_sd_bp": float(np.std(cs, ddof=1)),
                    "cs_floored_mean_bp": float(np.mean(csf)),
                    "ar_mean_bp": float(np.mean(ar)),
                    "ar_sd_bp": float(np.std(ar, ddof=1)),
                }
            )
    return pd.DataFrame(rows).set_index(["true_spread_bp", "daily_vol_pct"])


def _design_frames(provider_name: str) -> dict[str, pd.DataFrame]:
    from agentic_trader.data import get_provider
    from agentic_trader.evaluation import CORE_UNIVERSE, PERIODS
    from agentic_trader.instruments import Instrument

    start, end = (date.fromisoformat(x) for x in PERIODS["design"])
    provider = get_provider({**DEFAULT_CONFIG, "data_provider": provider_name})
    frames = {}
    for sym in CORE_UNIVERSE["equity"]:
        df = provider.history(Instrument.parse(sym, "equity"), start - timedelta(days=WARMUP_DAYS), end)
        frames[sym] = df[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
    return frames


def horizon(provider_name: str) -> pd.DataFrame:
    from agentic_trader.alpha import EQUITY_ALPHAS, compute_alphas
    from agentic_trader.instruments import Instrument

    rows = []
    for sym, df in _design_frames(provider_name).items():
        sig = compute_alphas(df, Instrument.parse(sym, "equity"), EQUITY_ALPHAS)
        for name in EQUITY_ALPHAS:
            ch = rebalance_from_decay(sig[name].to_numpy(float), df["Close"].to_numpy(float))
            rows.append(
                {
                    "symbol": sym,
                    "alpha": name,
                    "IC0": ch.ic0,
                    "t(IC0)": ch.t0,
                    "half_life": ch.half_life,
                    "rebalance_every": ch.rebalance_every,
                    "reason": ch.reason,
                }
            )
    return pd.DataFrame(rows).set_index(["alpha", "symbol"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["validate", "calibrate", "horizon"])
    ap.add_argument("--provider", default="yahoo")
    a = ap.parse_args()
    if a.what == "validate":
        _write(
            "estimator_validation",
            validate(),
            "### Spread estimators on simulated OHLC with a known spread (5 seeds x 1500 days, 100 trades a day)\n\n"
            "Evidence class: simulation. Produced by `python scripts/v17_costs.py validate`.",
        )
    elif a.what == "calibrate":
        t = calibrate_impact(_design_frames(a.provider))
        _write(
            f"impact_calibration_{a.provider}",
            t,
            f"### Spread-consistent impact coefficient Y, design period, provider {a.provider}\n\n"
            "Y = half spread / (daily vol * sqrt(0.01)). Evidence class: model-implied from public OHLC.",
        )
    else:
        t = horizon(a.provider)
        _write(
            f"horizon_{a.provider}",
            t,
            f"### Rebalance interval from lagged-IC half-life, design period, provider {a.provider}\n\n"
            "Default stays 5 bars; this table is an option, rules only. Evidence class: measured, design period.",
        )
    print(json.dumps({"wrote": str(OUT), "what": a.what}))


if __name__ == "__main__":
    main()
