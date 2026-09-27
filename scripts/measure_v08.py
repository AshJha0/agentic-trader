"""Re-measure every published number on real data for v0.8, into ``results/v08/``.

Every backtest-derived table in docs/evaluation/evaluation.md, README.md and docs/index.html
is regenerated from the files this script writes (see "Reproducing" in the evaluation). Each
run is skipped when its output already exists, so the script can be re-run to fill gaps.

Data: Yahoo (prices, split-adjusted with as-traded closes for EDGAR ratios), FRED (policy
rates, 3-month bills for the cash leg) and SEC EDGAR (needs ``EDGAR_USER_AGENT`` in ``.env``).
About an hour on the C++ backend.

    .venv\\Scripts\\python.exe scripts/measure_v08.py [--only eval_main,portfolio_holdout] [--out results/v08]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, is_dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader import quant  # noqa: E402
from agentic_trader.backtest import AGENT, run_portfolio_backtest  # noqa: E402
from agentic_trader.cli.common import load_dotenv  # noqa: E402
from agentic_trader.config import RULES_V02, RULES_V03, make_config  # noqa: E402
from agentic_trader.data import get_provider  # noqa: E402
from agentic_trader.evaluation import PERIODS, UNIVERSES, evaluate  # noqa: E402
from agentic_trader.instruments import Instrument  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402
from agentic_trader.stats import rolling_var_forecast, var_backtest  # noqa: E402

CORE, ALL = UNIVERSES["core"], UNIVERSES["all"]
FOUR = {k: PERIODS[k] for k in ("design", "holdout", "q1_2024", "reserve")}
TWO = {k: PERIODS[k] for k in ("design", "holdout")}
EVERY = 5

# name -> (symbols, periods, config overrides)
EVALS: dict[str, tuple[list[str], dict, dict]] = {
    "eval_main": (ALL, FOUR, {}),
    "eval_noedgar": (ALL, FOUR, {"edgar": False}),
    "eval_rules_v03": (ALL, FOUR, RULES_V03),
    "eval_rules_v02": (CORE, FOUR, RULES_V02),
    "eval_xalpha": (ALL, FOUR, {"analysts": ["technical", "fundamentals", "news", "sentiment", "xalpha"],
                                "xalpha_universe": ALL}),
    "eval_alpha": (CORE, FOUR, {"analysts": ["technical", "sentiment", "macro", "fundamentals", "news", "alpha"]}),
    "eval_no_trackrecord_cut": (ALL, FOUR, {"rules": {"track_record_cut": False}}),
    "eval_cash_leg_off": (ALL, FOUR, {"cash_leg": "off"}),
    "eval_impact_1e5": (CORE, TWO, {"costs": {"impact_coeff": 1.0}, "initial_capital": 1e5}),
    "eval_impact_1e7": (CORE, TWO, {"costs": {"impact_coeff": 1.0}, "initial_capital": 1e7}),
    "eval_impact_1e9": (CORE, TWO, {"costs": {"impact_coeff": 1.0}, "initial_capital": 1e9}),
}

# name -> (symbols, period, config overrides)
PORTFOLIOS: dict[str, tuple[list[str], str, dict]] = {
    "portfolio_design": (CORE, "design", {}),
    "portfolio_holdout": (CORE, "holdout", {}),
    "portfolio_design_cash_leg_off": (CORE, "design", {"cash_leg": "off"}),
    "portfolio_holdout_cash_leg_off": (CORE, "holdout", {"cash_leg": "off"}),
    "portfolio_holdout_impact_1e9_vwap": (CORE, "holdout", {"costs": {"impact_coeff": 1.0}, "initial_capital": 1e9}),
    "portfolio_holdout_impact_1e9_twap": (CORE, "holdout", {"costs": {"impact_coeff": 1.0, "execution_algo": "twap"},
                                                            "initial_capital": 1e9}),
    "portfolio_holdout_impact_1e9_ac": (CORE, "holdout", {"costs": {"impact_coeff": 1.0, "execution_algo": "ac",
                                                                    "ac_kappa": 5.0}, "initial_capital": 1e9}),
}

VAR_WINDOWS = (120, 250)
DESK_VAR_WINDOW = 250   # agents/risk.py risk_facts: historical VaR of the last 250 daily returns


def base_config(**over) -> dict:
    cfg = make_config(data_provider="yahoo", memory_path=None,
                      edgar_cache_dir=str(ROOT / "build" / "edgar_cache"),
                      fred_cache_dir=str(ROOT / "build" / "fred_cache"))
    return make_config(cfg, **over)


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


def run_eval(name: str, out: Path, provider) -> None:
    path = out / f"{name}.json"
    if path.exists():
        log(f"{name}: exists, skipped")
        return
    syms, periods, over = EVALS[name]
    cfg = base_config(**over)
    log(f"{name}: {len(syms)} symbols x {list(periods)} ...")
    t0 = time.time()
    res = evaluate(syms, periods, cfg, EVERY, provider=provider, workers=4,
                   progress=lambda m: log(f"  {name}: {m}"))
    res.meta["measurement"] = {"name": name, "overrides": _jsonable(over), "rebalance_every": EVERY,
                               "seconds": round(time.time() - t0, 1),
                               "macro_sources": _jsonable(getattr(provider, "macro_sources", None))}
    res.to_json(path)
    log(f"{name}: done in {time.time() - t0:.0f}s ({len(res.rows)} rows, {len(res.meta.get('errors', []))} errors)")


def run_portfolio(name: str, out: Path, provider) -> None:
    path = out / f"{name}.json"
    if path.exists():
        log(f"{name}: exists, skipped")
        return
    syms, period, over = PORTFOLIOS[name]
    start, end = PERIODS[period]
    cfg = base_config(**over)
    log(f"{name}: {len(syms)} sleeves {start} -> {end} ...")
    t0 = time.time()
    rep = run_portfolio_backtest(syms, start, end, cfg, rebalance_every=EVERY, provider=provider)
    rep.returns.to_csv(out / f"{name}.csv")
    sleeves = {s: {k: {"impact_paid": r.results[k].impact_paid, "sharpe": r.results[k].metrics.sharpe,
                       "cumulative_return": r.results[k].metrics.cumulative_return}
                   for k in r.results} for s, r in rep.sleeves.items()}
    json.dump(_jsonable({"name": name, "period": period, "start": start, "end": end, "symbols": syms,
                         "overrides": over, "rebalance_every": EVERY, "seconds": round(time.time() - t0, 1),
                         "table": rep.table().to_dict(orient="index"),
                         "metrics": {k: m for k, m in rep.metrics.items()},
                         "sleeves": sleeves, "provenance": provenance()}),
              open(path, "w", encoding="utf-8"), indent=1)
    log(f"{name}: done in {time.time() - t0:.0f}s")


def run_var_coverage(out: Path, provider) -> None:
    """Kupiec / Christoffersen coverage of (a) a rolling historical VaR of the holdout portfolio's
    own returns and (b) the desk's actual per-instrument forecast: the 95% historical VaR of the
    last 250 daily returns (agents/risk.py risk_facts), against each core instrument's next-day
    return over the holdout. (a) and (b) are different quantities; the docs must say which."""
    path = out / "var_coverage.json"
    if path.exists():
        log("var_coverage: exists, skipped")
        return
    csv = out / "portfolio_holdout.csv"
    if not csv.exists():
        log("var_coverage: needs portfolio_holdout.csv first, skipped")
        return
    log("var_coverage ...")
    port = pd.read_csv(csv, index_col=0, parse_dates=True)[AGENT].dropna().to_numpy(float)
    result = {"portfolio": {}, "instruments": {}, "desk_window": DESK_VAR_WINDOW}
    for w in VAR_WINDOWS:
        result["portfolio"][str(w)] = var_backtest(port, rolling_var_forecast(port, window=w, alpha=0.95), alpha=0.95)
    start, end = (date.fromisoformat(d) for d in PERIODS["holdout"])
    for s in CORE:
        ins = Instrument.parse(s)
        hist = provider.history(ins, start - timedelta(days=600), end)
        r = hist["Close"].pct_change().to_numpy(float)
        fc = rolling_var_forecast(r, window=DESK_VAR_WINDOW, alpha=0.95)
        mask = (hist.index >= pd.Timestamp(start)) & np.isfinite(r) & np.isfinite(fc)
        result["instruments"][s] = var_backtest(r[mask], fc[mask], alpha=0.95)
    json.dump(_jsonable({**result, "provenance": provenance()}), open(path, "w", encoding="utf-8"), indent=1)
    log("var_coverage: done")


def run_trials(out: Path, provider) -> None:
    """Every variant ever judged on the design period (evaluation.TRIALS), re-measured on the core
    universe under the current engine, so the selection statistics count all of them."""
    from agentic_trader.evaluation import TRIALS, trial_slug
    design = {"design": PERIODS["design"]}
    for t in TRIALS:
        path = out / f"trial_{trial_slug(t.name)}.json"
        if t.overrides is None or path.exists():
            continue
        log(f"trial {t.name!r} ...")
        t0 = time.time()
        res = evaluate(CORE, design, base_config(**t.overrides), EVERY, provider=provider, workers=4)
        res.meta["measurement"] = {"trial": t.name, "version": t.version, "overrides": _jsonable(t.overrides),
                                   "rebalance_every": EVERY, "seconds": round(time.time() - t0, 1)}
        res.to_json(path)
        log(f"trial {t.name!r}: done in {time.time() - t0:.0f}s")
    rows = []
    for t in TRIALS:
        path = out / f"trial_{trial_slug(t.name)}.json"
        mean = None
        if path.exists():
            data = json.load(open(path, encoding="utf-8"))
            vals = [r["Sharpe"] for r in data["rows"]
                    if r.get("strategy") == AGENT and r.get("period") == "design" and r.get("Sharpe") is not None]
            mean = float(np.mean(vals)) if vals else None
        rows.append({"name": t.name, "version": t.version, "reproducible": t.overrides is not None,
                     "recorded_mean_sharpe_v03_engine": t.recorded_mean_sharpe, "mean_sharpe": mean})
    json.dump({"trials": rows, "provenance": provenance()}, open(out / "trials.json", "w", encoding="utf-8"), indent=1)
    log(f"trials: {sum(r['mean_sharpe'] is not None for r in rows)} of {len(rows)} measured")


def run_phase_sweep(out: Path, provider) -> None:
    """The 5-bar cadence's five phases on the core holdout portfolio: the spread of the
    portfolio Sharpe across offsets 0..4 is the cadence noise floor (finding 65)."""
    path = out / "phase_sweep_holdout.json"
    if path.exists():
        log("phase_sweep: exists, skipped")
        return
    start, end = PERIODS["holdout"]
    rows = {}
    for offset in range(EVERY):
        log(f"phase_sweep: offset {offset} ...")
        t0 = time.time()
        rep = run_portfolio_backtest(CORE, start, end, base_config(), rebalance_every=EVERY, provider=provider,
                                     rebalance_offset=offset)
        rows[str(offset)] = {"table": rep.table().to_dict(orient="index"),
                             "sharpe_vs_vol_target": rep.sharpe_difference(AGENT, "B&H vol-target"),
                             "sharpe_vs_buy_hold": rep.sharpe_difference(AGENT, "Buy&Hold"),
                             "seconds": round(time.time() - t0, 1)}
    json.dump(_jsonable({"period": "holdout", "rebalance_every": EVERY, "offsets": rows, "provenance": provenance()}),
              open(path, "w", encoding="utf-8"), indent=1)
    log("phase_sweep: done")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(ROOT / "results" / "v08"))
    ap.add_argument("--only", default=None,
                    help="comma list of run names, or the stages var_coverage / trials / phase_sweep (default: everything)")
    args = ap.parse_args(argv)
    load_dotenv(str(ROOT / ".env"))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    only = set(args.only.split(",")) if args.only else None
    log(f"quant backend {quant.BACKEND}; output {out}")
    if quant.BACKEND != "cpp":
        log("WARNING: numpy backend; the published numbers are measured on the C++ backend")
    provider = get_provider(base_config())
    t0 = time.time()
    for name in EVALS:
        if only is None or name in only:
            run_eval(name, out, provider)
    for name in PORTFOLIOS:
        if only is None or name in only:
            run_portfolio(name, out, provider)
    if only is None or "var_coverage" in only:
        run_var_coverage(out, provider)
    if only is None or "phase_sweep" in only:
        run_phase_sweep(out, provider)
    if only is None or "trials" in only:
        run_trials(out, provider)
    manifest = {"finished": time.strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0),
                "files": sorted(p.name for p in out.iterdir()), "provenance": provenance()}
    json.dump(manifest, open(out / "manifest.json", "w", encoding="utf-8"), indent=1)
    log(f"all done in {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
