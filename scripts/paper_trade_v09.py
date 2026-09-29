"""The forward test: a daily paper-trading record of the frozen v0.9 candidates.

Every run recomputes, from the freeze date to the last complete session (New York's
yesterday), the fully costed walk-forward returns of each frozen book and appends nothing
by hand: the ledger is the recomputation. Recomputing the whole record every day (a few
minutes) keeps it self-consistent and makes data revisions visible: when today's history
differs from yesterday's ledger for a date before today, the largest difference is logged
(``runs.jsonl``) instead of silently replacing the record.

Frozen books (docs/evaluation/v09_preregistration.md), all with the released v0.8.0 rules:

* ``core15``  the v0.8 desk on the 15 core instruments, equal capital (the incumbent), with
              its ``B&H vol-target`` and ``Buy&Hold`` controls;
* ``etf11``   the multi-asset base: 11 ETFs, risk parity, ``B&H vol-target`` and ``Buy&Hold``,
              plus the ``TSMOM(12-1)`` trend stream;
* ``fx15``    the 15 FX pairs, risk parity: ``Carry`` and ``TSMOM(12-1)`` with their control.

Outputs under ``results/paper``: ``ledger.csv`` (one daily return per book/stream plus the
credited ``rf``), ``summary.md`` (cumulative return, Sharpe on excess returns and, once 60
sessions exist, the paired block-bootstrap Sharpe difference of every candidate against
its control), ``runs.jsonl`` (one line per run: as-of date, rows, provenance, revisions).

Nothing here changes a rule, a universe or a weight after the freeze date. To adopt a
candidate later, the forward record has to clear the pre-registered bar on its own.

    .venv\\Scripts\\python.exe scripts/paper_trade_v09.py [--as-of YYYY-MM-DD] [--out results/paper] [--data yahoo|synthetic]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.backtest import AGENT, run_portfolio_backtest  # noqa: E402
from agentic_trader.cli.common import default_as_of, load_dotenv  # noqa: E402
from agentic_trader.config import make_config  # noqa: E402
from agentic_trader.data import get_provider  # noqa: E402
from agentic_trader.evaluation import CORE_UNIVERSE, EXTENDED_UNIVERSE, UNIVERSES  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402
from agentic_trader.stats import paired_sharpe_block_bootstrap, sharpe_stats  # noqa: E402

FREEZE = date(2026, 9, 29)          # the first session of the forward record (v0.9 pre-registration)
PPY = 260.0
ETF11 = ["SPY", "EFA", "EEM", "IWM", "TLT", "IEF", "LQD", "HYG", "GLD", "DBC", "VNQ"]
FX15 = CORE_UNIVERSE["fx"] + EXTENDED_UNIVERSE["fx"]

# book -> (symbols, weighting, streams recorded, control of each candidate)
BOOKS: dict[str, tuple[list[str], str, tuple[str, ...], dict[str, str]]] = {
    "core15": (UNIVERSES["core"], "equal", (AGENT, "B&H vol-target", "Buy&Hold"), {AGENT: "B&H vol-target"}),
    "etf11": (ETF11, "risk_parity", ("B&H vol-target", "Buy&Hold", "TSMOM(12-1)"), {"TSMOM(12-1)": "B&H vol-target"}),
    "fx15": (FX15, "risk_parity", ("B&H vol-target", "Carry", "TSMOM(12-1)"),
             {"Carry": "B&H vol-target", "TSMOM(12-1)": "B&H vol-target"}),
}
MIN_SESSIONS_FOR_INTERVALS = 60


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def recompute(as_of: date, cfg: dict, provider, freeze: date = FREEZE) -> pd.DataFrame:
    """The whole forward record, freeze -> as_of, one column per ``book/stream`` plus ``rf``."""
    cols, rf = {}, None
    for book, (syms, weighting, streams, _) in BOOKS.items():
        rep = run_portfolio_backtest(syms, freeze, as_of, cfg, rebalance_every=5, provider=provider,
                                     weighting=weighting, cov_window=120)
        for s in streams:
            cols[f"{book}/{s}"] = rep.returns[s]
        r = pd.Series(rep.rf if isinstance(rep.rf, np.ndarray) else float(rep.rf or 0.0), index=rep.dates)
        rf = r if rf is None else pd.concat([rf, r], axis=1, sort=True).max(axis=1)
    frame = pd.DataFrame(cols).sort_index().fillna(0.0)
    frame["rf"] = rf.reindex(frame.index).ffill()
    return frame


def revisions(old: pd.DataFrame | None, new: pd.DataFrame) -> dict:
    """Largest absolute change of a return already in the ledger (a data revision), per column."""
    if old is None:
        return {}
    common = old.index.intersection(new.index)
    out = {}
    for c in old.columns:
        if c in new.columns and len(common):
            d = float((old.loc[common, c] - new.loc[common, c]).abs().max())
            if d > 1e-12:
                out[c] = d
    return out


def summary(frame: pd.DataFrame, freeze: date = FREEZE) -> str:
    lines = [f"# Forward paper-trading record: {frame.index[0].date()} -> {frame.index[-1].date()} "
             f"({len(frame)} sessions, frozen {freeze}, rules v0.8.0)\n",
             "| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |",
             "|:--|--:|--:|:--|"]
    rf = frame["rf"].to_numpy(float)
    def ex(col):
        r = frame[col].to_numpy(float)[1:]
        return r - np.nan_to_num(rf[:-1]) / PPY
    for book, (_, _, streams, controls) in BOOKS.items():
        for s in streams:
            col = f"{book}/{s}"
            r = frame[col].to_numpy(float)
            cr = float(np.prod(1.0 + r) - 1.0) * 100
            e = ex(col)
            sh = sharpe_stats(e, PPY).sharpe_annual if len(e) >= 3 else float("nan")
            vs = ""
            if s in controls and len(frame) >= MIN_SESSIONS_FOR_INTERVALS:
                d = paired_sharpe_block_bootstrap(e, ex(f"{book}/{controls[s]}"), PPY, block=10, n_boot=5000)
                vs = f"{d.diff:+.2f} [{d.ci_low:+.2f}, {d.ci_high:+.2f}] p {d.p_value:.3f}"
            elif s in controls:
                vs = f"(interval after {MIN_SESSIONS_FOR_INTERVALS} sessions)"
            lines.append(f"| {col} | {cr:+.2f} | {sh:.2f} | {vs} |")
    lines.append("\nEvery number is recomputed from the freeze date on each run; revisions of earlier returns are logged in runs.jsonl.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", default=None, help="last session to include (default: New York's yesterday)")
    ap.add_argument("--out", default=str(ROOT / "results" / "paper"))
    ap.add_argument("--data", default="yahoo", choices=("yahoo", "synthetic"))
    ap.add_argument("--freeze", default=FREEZE.isoformat(), help="first session (tests only)")
    a = ap.parse_args(argv)
    load_dotenv(str(ROOT / ".env"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    as_of = date.fromisoformat(a.as_of) if a.as_of else default_as_of()
    freeze = date.fromisoformat(a.freeze)
    if as_of < freeze:
        log(f"as-of {as_of} is before the freeze date {freeze}: nothing to record yet")
        return 0
    cfg = make_config(data_provider=a.data, memory_path=None,
                      edgar_cache_dir=str(ROOT / "build" / "edgar_cache"),
                      fred_cache_dir=str(ROOT / "build" / "fred_cache"))
    provider = get_provider(cfg)
    t0 = time.time()
    log(f"recomputing {freeze} -> {as_of} on {a.data}")
    try:
        frame = recompute(as_of, cfg, provider, freeze)
    except ValueError as e:
        if "fewer than 2 bars" not in str(e):
            raise
        # The freeze session is the first bar; a return needs a second. Until it is complete
        # (the run after the next close) there is nothing to record, and that is not a failure.
        log(f"fewer than 2 complete sessions since the freeze date {freeze} (as-of {as_of}): nothing to record yet")
        return 0
    ledger = out / "ledger.csv"
    old = pd.read_csv(ledger, index_col=0, parse_dates=True) if ledger.exists() else None
    rev = revisions(old, frame)
    frame.to_csv(ledger)
    (out / "summary.md").write_text(summary(frame, freeze), encoding="utf-8")
    with open(out / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "as_of": as_of.isoformat(),
                            "freeze": freeze.isoformat(), "sessions": int(len(frame)), "data": a.data,
                            "seconds": round(time.time() - t0, 1), "revisions": rev,
                            "last": {c: float(frame[c].iloc[-1]) for c in frame.columns},
                            "provenance": provenance()}, default=float) + "\n")
    if rev:
        log(f"WARNING: {len(rev)} column(s) revised for dates already in the ledger: {rev}")
    log(f"{len(frame)} sessions recorded in {time.time() - t0:.0f}s -> {ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
