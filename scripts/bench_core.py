"""v0.17 D1: time the quant core on a realistic daily panel, C++ against numpy.

    python scripts/bench_core.py [--names 15] [--years 10] [--repeat 5]

A panel of ``names`` daily series of ``years * 252`` bars (synthetic GBM, seed 0), each run
through ``strat_tsmom`` signal generation and ``run_backtest`` with stops off, as the
evaluation does per sleeve. Times are the best of ``repeat`` wall-clock runs per backend.
The C++ row is reported only when the compiled ``_atcore`` imports (build with
scripts/build_cpp.ps1); otherwise it says so. Prints a markdown table and a json line.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np

from agentic_trader.quant import pycore


def panel(names: int, bars: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return 100.0 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, (names, bars)), axis=1))


def run(core, prices: np.ndarray) -> float:
    cfg = pycore.BacktestConfig(cost_bps=1.0, slippage_bps=1.0, allow_short=True)
    t0 = time.perf_counter()
    for p in prices:
        w = np.asarray(core.strat_tsmom(p, [252], 21), float)
        core.run_backtest(p, w, cfg)
    return time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=15)
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--repeat", type=int, default=5)
    a = ap.parse_args()
    prices = panel(a.names, a.years * 252)
    rows = {"numpy": min(run(pycore, prices) for _ in range(a.repeat))}
    try:
        from agentic_trader.quant import _atcore  # type: ignore[attr-defined]
        from agentic_trader import quant

        rows["cpp"] = min(run(quant, prices) for _ in range(a.repeat)) if quant.BACKEND == "cpp" else None
        del _atcore
    except ImportError:
        rows["cpp"] = None
    print(f"| backend | seconds ({a.names} names x {a.years * 252} bars, best of {a.repeat}) |")
    print("|:--|--:|")
    for k, v in rows.items():
        print(f"| {k} | {'not built' if v is None else f'{v:.4f}'} |")
    if rows["cpp"]:
        print(f"\nspeed-up numpy/cpp: {rows['numpy'] / rows['cpp']:.1f}x")
    print(json.dumps({"names": a.names, "bars": a.years * 252, **rows}))


if __name__ == "__main__":
    main()
