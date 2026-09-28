"""v0.9 phases 1-3 on the design period: multi-asset base, trend and carry streams, combination.

Every run is a ``run_portfolio_backtest`` on the 2016-2021 design period only (the holdout and
reserve are spent; the next unseen data is the forward paper-trading record). Each run writes
the per-strategy daily portfolio returns (``<name>.csv``, with ``rf``) and a JSON with the
strategy table, block-bootstrap Sharpe differences against ``B&H vol-target`` and provenance,
so that ``scripts/combine_v09.py`` can combine the streams at the return level with risk
budgets and ``scripts/render_v09_tables.py`` can print everything the documents quote.

Runs (all risk parity across sleeves, 120-day covariance window, unless named otherwise):

* ``etf11_rp``      the multi-asset ETF universe: SPY EFA EEM IWM TLT IEF LQD HYG GLD DBC VNQ.
                    Its ``B&H vol-target`` row is the phase-1 base; ``TSMOM(12-1)`` the trend stream.
* ``etf11_equal``   the same with 1/N capital, to separate the scheme from the universe.
* ``fx15_rp``       the 15 FX pairs (core 5 + 10 crosses): ``Carry`` and ``TSMOM(12-1)`` streams.
* ``core15_rp``     the v0.8 core universe with risk parity, for the v0.8 comparison (1/N there).
* ``all26_rp``      ETF universe + 15 FX pairs with class budgets equity 0.6 / fx 0.4.

    .venv\\Scripts\\python.exe scripts/measure_v09.py [--period design|holdout] [--only etf11_rp,fx15_rp] [--out results/v09]

``--period holdout`` (2022-01-03 -> 2026-06-30) is the pre-registered one-off report of
docs/evaluation/v09_preregistration.md; write it to its own directory (``--out results/v09/holdout``).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader import quant  # noqa: E402
from agentic_trader.backtest import AGENT, run_portfolio_backtest  # noqa: E402
from agentic_trader.cli.common import load_dotenv  # noqa: E402
from agentic_trader.config import make_config  # noqa: E402
from agentic_trader.data import get_provider  # noqa: E402
from agentic_trader.evaluation import CORE_UNIVERSE, EXTENDED_UNIVERSE, PERIODS, UNIVERSES  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402

ETF11 = ["SPY", "EFA", "EEM", "IWM", "TLT", "IEF", "LQD", "HYG", "GLD", "DBC", "VNQ"]
FX15 = CORE_UNIVERSE["fx"] + EXTENDED_UNIVERSE["fx"]
CORE15 = UNIVERSES["core"]
EVERY = 5
COV_WINDOW = 120

# name -> (symbols, weighting, class_budgets)
RUNS: dict[str, tuple[list[str], str, dict | None]] = {
    "etf11_rp": (ETF11, "risk_parity", None),
    "etf11_equal": (ETF11, "equal", None),
    "fx15_rp": (FX15, "risk_parity", None),
    "core15_rp": (CORE15, "risk_parity", None),
    "all26_rp": (ETF11 + FX15, "risk_parity", {"equity": 0.6, "fx": 0.4}),
}

STREAMS = (AGENT, "Buy&Hold", "B&H vol-target", "TSMOM(12-1)", "Carry", "SMA(20/50)", "MACD", "KDJ+RSI", "ZMR")


def base_config() -> dict:
    return make_config(data_provider="yahoo", memory_path=None,
                       edgar_cache_dir=str(ROOT / "build" / "edgar_cache"),
                       fred_cache_dir=str(ROOT / "build" / "fred_cache"))


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _jsonable(x):
    if is_dataclass(x):
        return {k: _jsonable(v) for k, v in asdict(x).items()}
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, (np.floating, np.integer)):
        return x.item()
    if isinstance(x, float) and not np.isfinite(x):
        return None
    return x


def run(name: str, out: Path, provider, period: str) -> None:
    path = out / f"{name}.json"
    if path.exists():
        log(f"{name}: exists, skipped")
        return
    syms, weighting, budgets = RUNS[name]
    start, end = PERIODS[period]
    log(f"{name}: {len(syms)} sleeves, {weighting}, budgets {budgets}, {start} -> {end} ...")
    t0 = time.time()
    rep = run_portfolio_backtest(syms, start, end, base_config(), rebalance_every=EVERY, provider=provider,
                                 weighting=weighting, cov_window=COV_WINDOW, class_budgets=budgets)
    frame = rep.returns.copy()
    frame["rf"] = rep.rf if isinstance(rep.rf, np.ndarray) else float(rep.rf if rep.rf is not None else 0.0)
    frame.to_csv(out / f"{name}.csv")
    if rep.allocations is not None:
        rep.allocations.to_csv(out / f"{name}_allocations.csv")
    diffs = {s: rep.sharpe_difference(s, "B&H vol-target") for s in STREAMS if s in rep.metrics and s != "B&H vol-target"}
    sleeves = {s: {k: {"sharpe": r.results[k].metrics.sharpe, "cumulative_return": r.results[k].metrics.cumulative_return,
                       "max_drawdown": r.results[k].metrics.max_drawdown, "num_trades": r.results[k].metrics.num_trades}
                   for k in r.results} for s, r in rep.sleeves.items()}
    json.dump(_jsonable({"name": name, "period": period, "start": start, "end": end, "symbols": syms,
                         "weighting": weighting, "class_budgets": budgets, "cov_window": COV_WINDOW,
                         "rebalance_every": EVERY, "seconds": round(time.time() - t0, 1),
                         "table": rep.table().to_dict(orient="index"),
                         "metrics": {k: m for k, m in rep.metrics.items()},
                         "sharpe_vs_vol_target": diffs, "sleeves": sleeves, "provenance": provenance()}),
              open(path, "w", encoding="utf-8"), indent=1)
    log(f"{name}: done in {time.time() - t0:.0f}s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "results" / "v09"))
    ap.add_argument("--only", default=None, help="comma list of run names (default: every run)")
    ap.add_argument("--period", default="design", choices=("design", "holdout"))
    a = ap.parse_args(argv)
    load_dotenv(str(ROOT / ".env"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    log(f"quant backend {quant.BACKEND}; period {a.period} {PERIODS[a.period]}; output {out}")
    provider = get_provider(base_config())
    t0 = time.time()
    for name in RUNS:
        if only is None or name in only:
            run(name, out, provider, a.period)
    json.dump({"finished": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0),
               "files": sorted(p.name for p in out.iterdir()), "provenance": provenance()},
              open(out / "manifest.json", "w", encoding="utf-8"), indent=1)
    log(f"all done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
