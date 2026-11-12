"""Protocol amendment (v0.17, review Q1/B2): the registered rules trials at exec_lag 0, 1 and next open.

For every reproducible trial in ``evaluation.TRIALS`` (rules only: ``llm_provider`` stays
"offline", no model is called) this runs the trial's own statistic -- the 15-sleeve core
design-period portfolio, equal capital, rebalanced every 5 bars, the same call as
``scripts/measure_v08.py run_trials`` -- once with the same-close fill (lag 0), once with
the decision executed one bar later (lag 1) and (round 2, review C7/D1) once filled at the
next bar's open (``backtest.fill = "next_open"``, lag 0), and reports the portfolio Sharpe,
the paired Sharpe difference against the B&H vol-target control and its block-bootstrap p.

Every published Sharpe so far is the lag-0 same-close fill: the decision reads close[t] and
trades at close[t]. This table bounds how optimistic that is. It is meant to be run after the
round-2 keep fix (review D4: a PM keep is an engine flag), which removed phantom keep trades
at lag 1 that would have biased the comparison against the desk. The timing options are
explicit config (``backtest.exec_lag``, ``backtest.fill``); their defaults (0, "close") are
unchanged, so the published numbers still reproduce.

It is an amendment to the registered trials, not a new trial family: no rule is chosen on
these numbers and ``TRIALS`` is unchanged.

    python scripts/v17_exec_lag.py --provider yahoo [--trials "name a,name b"] [--lags 0,1,next_open]
        [--out docs/results/v17_exec_lag] [--resume | --fresh]

``--lags`` takes integers (exec_lag k, filled at the close) and ``next_open`` (lag 0, filled at
the next open); the default is ``0,1,next_open``.

Each finished (trial, lag) is appended to ``checkpoint_<provider>.jsonl`` in --out (fsync per
line, header fingerprint of code/config/data); a rerun resumes from it, and the final tables are
built from it, so an interrupted-then-resumed run writes the same bytes as an uninterrupted one.
Per-unit timings are no longer in the rows (they made the files irreproducible).

``--provider synthetic`` runs offline on the synthetic generator (a smoke test of the pipeline;
its numbers are not evidence about markets). ``--provider yahoo`` downloads daily bars.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.backtest import AGENT, run_portfolio_backtest  # noqa: E402
from agentic_trader.checkpoint import Checkpoint, CheckpointMismatch, file_sha256  # noqa: E402
from agentic_trader.config import make_config  # noqa: E402
from agentic_trader.data import get_provider  # noqa: E402
from agentic_trader.evaluation import PERIODS, TRIALS, UNIVERSES  # noqa: E402
from agentic_trader.provenance import package_version, provenance  # noqa: E402

CONTROL = "B&H vol-target"
EVERY = 5
NL = "\n"
NEXT_OPEN = "next_open"


def variant_timing(variant) -> tuple[int, str]:
    """(exec_lag, fill) of a variant: an integer k is lag k filled at the close; ``next_open``
    is lag 0 filled at the next bar's open."""
    if str(variant) == NEXT_OPEN:
        return 0, NEXT_OPEN
    k = int(variant)
    if k < 0:
        raise ValueError(f"exec lag must be >= 0, got {k}")
    return k, "close"


def parse_variants(text: str) -> list:
    """``"0,1,next_open"`` -> ``[0, 1, "next_open"]``; duplicates and unknown tokens are errors."""
    out: list = []
    for tok in (t.strip() for t in text.split(",") if t.strip()):
        v = NEXT_OPEN if tok == NEXT_OPEN else int(tok)
        variant_timing(v)
        out.append(v)
    if not out or len({str(v) for v in out}) != len(out):
        raise ValueError(f"--lags needs distinct variants, got {text!r}")
    return out


def label(variant) -> str:
    return "next open" if str(variant) == NEXT_OPEN else f"lag{variant}"


def trial_config(provider_name: str, overrides: dict, lag) -> dict:
    cfg = make_config(data_provider=provider_name, memory_path=None, llm_provider="offline",
                      edgar_cache_dir=str(ROOT / "build" / "edgar_cache"),
                      fred_cache_dir=str(ROOT / "build" / "fred_cache"))
    cfg = make_config(cfg, **overrides)
    k, fill = variant_timing(lag)
    cfg["backtest"] = {**cfg.get("backtest", {}), "exec_lag": k, "fill": fill}
    return cfg


def run_unit(provider, provider_name: str, trial, lag, start: str, end: str) -> dict:
    """One (trial, variant) backtest -> its result row (no timing: rows must be reproducible)."""
    cfg = trial_config(provider_name, trial.overrides, lag)
    prov = provider if not set(trial.overrides) & {"edgar", "data_provider", "fred_vintages"}         else provider.reconfigured(cfg)
    rep = run_portfolio_backtest(UNIVERSES["core"], start, end, cfg, rebalance_every=EVERY, provider=prov)
    d = rep.sharpe_difference(AGENT, CONTROL)
    k, fill = variant_timing(lag)
    return {"trial": trial.name, "version": trial.version, "exec_lag": lag, "lag_bars": k, "fill": fill,
            "sharpe": float(rep.metrics[AGENT].sharpe), "control_sharpe": float(rep.metrics[CONTROL].sharpe),
            "delta_vs_control": float(d.diff), "ci_low": float(d.ci_low), "ci_high": float(d.ci_high),
            "p_value": float(d.p_value), "days": int(d.n)}


def run_header(provider_name: str, period: str, start: str, end: str, trials, lags) -> dict:
    """What a checkpoint must agree on before it can be resumed: code, config, data."""
    code = file_sha256(Path(__file__), ROOT / "agentic_trader" / "backtest.py")
    return {"script": "v17_exec_lag", "code_sha256": code, "package_version": package_version(),
            "provider": provider_name, "period": [period, start, end], "universe": list(UNIVERSES["core"]),
            "rebalance_every": EVERY, "control": CONTROL, "lags": list(lags),
            "trials": [[t.name, t.version, t.overrides] for t in trials]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--provider", default="yahoo", choices=["yahoo", "synthetic"])
    ap.add_argument("--trials", default=None, help="comma-separated trial names (default: every reproducible one)")
    ap.add_argument("--lags", default=f"0,1,{NEXT_OPEN}",
                    help="comma-separated variants: integers (exec lag, close fill) and next_open")
    ap.add_argument("--period", default="design")
    ap.add_argument("--out", default=str(ROOT / "docs" / "results" / "v17_exec_lag"))
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--resume", dest="resume", action="store_true", default=True,
                   help="skip (trial, lag) units already in the checkpoint (default)")
    g.add_argument("--fresh", dest="resume", action="store_false", help="discard the checkpoint and start over")
    a = ap.parse_args(argv)
    try:
        lags = parse_variants(a.lags)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    want = None if a.trials is None else {s.strip() for s in a.trials.split(",")}
    trials = [t for t in TRIALS if t.overrides is not None and (want is None or t.name in want)]
    if want is not None and len(trials) != len(want):
        raise SystemExit(f"unknown or non-reproducible trials: {sorted(want - {t.name for t in trials})}")
    start, end = PERIODS[a.period]
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tag = a.provider
    try:
        ck = Checkpoint(out / f"checkpoint_{tag}.jsonl", run_header(a.provider, a.period, start, end, trials, lags),
                        fresh=not a.resume)
    except CheckpointMismatch as e:
        raise SystemExit(str(e)) from None
    units = [(t, lag) for t in trials for lag in lags]
    n_units = len(units)
    provider = None
    t_all = time.time()
    for k, (t, lag) in enumerate(units, 1):
        key = f"{t.name}|{lag}"
        if ck.done(key):
            print(f"{k}/{n_units} {t.name!r} {label(lag)}: done (checkpoint)", flush=True)
            continue
        if provider is None:
            provider = get_provider(trial_config(a.provider, {}, 0))
        t0 = time.time()
        row = run_unit(provider, a.provider, t, lag, start, end)
        ck.add(key, row)
        print(f"{k}/{n_units} {t.name!r} {label(lag)}: SR {row['sharpe']:.3f} delta {row['delta_vs_control']:+.3f} "
              f"p {row['p_value']:.3f} ({time.time() - t0:.0f}s)", flush=True)
    write_outputs(out, tag, a.period, lags, trials, ck)
    meta = {"amendment": "v0.17 R1.1 / review Q1-B2, round 2 C7/D1: execution timing sensitivity of registered trials",
            "provider": a.provider, "period": [start, end], "universe": "core", "rebalance_every": EVERY,
            "lags": lags, "fills": {str(v): variant_timing(v)[1] for v in lags},
            "control": CONTROL, "statistic": "design-period equal-capital portfolio Sharpe",
            "p_value": "paired circular block bootstrap (block 10, 5000 resamples, seed 0)",
            "llm_provider": "offline (rules only)", "trials": [t.name for t in trials],
            "checkpoint": ck.path.name, "checkpoint_fingerprint": ck.fp,
            "seconds_this_session": round(time.time() - t_all, 1), "provenance": provenance()}
    json.dump(meta, open(out / f"meta_{tag}.json", "w", encoding="utf-8"), indent=1, default=str)
    return 0


def table_lines(rows: list[dict], tag: str, period: str, lags, trials) -> list[str]:
    """The markdown table, one row per trial, three columns per timing variant."""
    by = {(r["trial"], str(r["exec_lag"])): r for r in rows}
    lines = [f"# Registered rules trials: {' vs '.join(label(k) for k in lags)} ({tag}, {period})", "",
             "lagK: the decision taken on the close of bar t is filled at the close of bar t+K (lag0 is the "
             "same-close fill behind every number published before round 2). next open: filled at the open "
             f"of bar t+1. delta: the portfolio Sharpe minus the {CONTROL} control's at the same timing; "
             "p: paired circular block bootstrap.", "",
             "| trial | " + " | ".join(f"SR {label(k)} | delta {label(k)} | p {label(k)}" for k in lags) + " |",
             "|---|" + "---|" * (3 * len(lags))]
    for t in trials:
        cells = []
        for k in lags:
            r = by[(t.name, str(k))]
            cells += [f"{r['sharpe']:.3f}", f"{r['delta_vs_control']:+.3f}", f"{r['p_value']:.3f}"]
        lines.append(f"| {t.name} | " + " | ".join(cells) + " |")
    return lines


def write_outputs(out: Path, tag: str, period: str, lags, trials, ck: Checkpoint) -> None:
    """Final files from the checkpoint alone, in fixed unit order: resumed == uninterrupted."""
    rows = [ck.get(f"{t.name}|{k}") for t in trials for k in lags]
    with open(out / f"trials_lag_{tag}.json", "w", encoding="utf-8", newline=NL) as f:
        json.dump(rows, f, indent=1)
    with open(out / f"trials_lag_{tag}.md", "w", encoding="utf-8", newline=NL) as f:
        f.write(NL.join(table_lines(rows, tag, period, lags, trials)) + NL)


if __name__ == "__main__":
    raise SystemExit(main())
