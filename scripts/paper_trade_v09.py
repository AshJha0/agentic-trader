"""The forward test: a daily paper-trading record of the frozen v0.9 candidates.

Every run recomputes, from the freeze date to the last complete session (New York's
yesterday), the fully costed walk-forward returns of each frozen book. The ledger is
append-only: a session already in ``ledger.csv`` is never rewritten, only sessions after
its last row are added from the recomputation. The full recomputation is written beside it
(``ledger_recomputed.csv``) and every difference between the two for a date already in the
ledger, and every session the recomputation no longer contains, goes to ``revisions.csv``
(date, column, old, new) and to the run's ``runs.jsonl`` line: a Yahoo restatement or a
changed headline snapshot is visible, never silently absorbed. A run whose recomputation
ends before the ledger does is refused (``--allow-shrink`` overrides) and a sleeve with too
few bars is an error, not a quiet "nothing to record".

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
MIN_SESSIONS_FOR_INTERVALS = 60      # descriptive intervals appear after this many sessions
DECISION_LOOK_SESSIONS = 3600         # the pre-registered single decision look (MDE 0.2 Sharpe at 95%)


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def recompute(as_of: date, cfg: dict, provider, freeze: date = FREEZE) -> pd.DataFrame:
    """The whole forward record, freeze -> as_of, one column per ``book/stream`` plus ``rf``."""
    cols, rf = {}, None
    for book, (syms, weighting, streams, _) in BOOKS.items():
        rep = run_portfolio_backtest(syms, freeze, as_of, cfg, rebalance_every=5, provider=provider,
                                     weighting=weighting, cov_window=120)
        # a sleeve whose bars stop early would silently contribute 0 from then on (mixed-calendar
        # fill); a gap of more than a week before the book's last session is a data failure
        last = pd.Timestamp(rep.dates[-1])
        for sym, sleeve in rep.sleeves.items():
            if (last - pd.Timestamp(sleeve.dates[-1])).days > 7:
                raise ValueError(f"{sym}: history stops at {sleeve.dates[-1].date()} while the book runs to "
                                 f"{last.date()}; refusing to record a sleeve with missing sessions")
        for s in streams:
            cols[f"{book}/{s}"] = rep.returns[s]
        r = pd.Series(rep.rf if isinstance(rep.rf, np.ndarray) else float(rep.rf or 0.0), index=rep.dates)
        rf = r if rf is None else pd.concat([rf, r], axis=1, sort=True).max(axis=1)
    frame = pd.DataFrame(cols).sort_index().fillna(0.0)
    frame["rf"] = rf.reindex(frame.index).ffill()
    return frame


def revisions(old: pd.DataFrame | None, new: pd.DataFrame) -> dict:
    """What the recomputation changed about sessions already in the ledger: per column the
    largest absolute change and its date (``changed``), the dated cells that moved (``cells``),
    and the ledger sessions the recomputation no longer contains up to its last date
    (``dropped``). Empty when the record is stable."""
    if old is None:
        return {"changed": {}, "cells": [], "dropped": []}
    common = old.index.intersection(new.index)
    changed, cells = {}, []
    for c in old.columns:
        if c in new.columns and len(common):
            diff = (old.loc[common, c] - new.loc[common, c]).abs()
            if float(diff.max()) > 1e-12:
                when = diff.idxmax()
                changed[c] = {"max_abs": float(diff.max()), "date": when.date().isoformat()}
                for d in diff.index[diff > 1e-12]:
                    cells.append({"date": d.date().isoformat(), "column": c, "old": float(old.loc[d, c]), "new": float(new.loc[d, c])})
    last = new.index[-1] if len(new) else None
    dropped = [d.date().isoformat() for d in old.index.difference(new.index) if last is not None and d <= last]
    return {"changed": changed, "cells": cells, "dropped": dropped}


def merge_append_only(old: pd.DataFrame | None, new: pd.DataFrame) -> pd.DataFrame:
    """The ledger after a run: the old rows verbatim plus the recomputed rows after the old last date."""
    if old is None or old.empty:
        return new
    added = new.loc[new.index > old.index[-1]]
    return pd.concat([old, added]) if len(added) else old.copy()


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
    lines.append(f"\nNo decision before session {DECISION_LOOK_SESSIONS} (pre-registered, docs/evaluation/v09_preregistration.md, "
                 f"amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: {len(frame)}.")
    lines.append("\nThe ledger is append-only: sessions are added from each run's recomputation and never rewritten; "
                 "differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--as-of", default=None, help="last session to include (default: New York's yesterday)")
    ap.add_argument("--out", default=str(ROOT / "results" / "paper"))
    ap.add_argument("--data", default="yahoo", choices=("yahoo", "synthetic"))
    ap.add_argument("--freeze", default=FREEZE.isoformat(), help="first session (tests only)")
    ap.add_argument("--allow-shrink", action="store_true", help="accept a recomputation that ends before the ledger does")
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
    # The freeze session is the first bar; a return needs a second. Until it is complete (the
    # run after the next close) there is nothing to record, and that is not a failure. Any
    # other shortfall (a sleeve whose history stops early) is an error and propagates.
    from agentic_trader.instruments import Instrument
    calendar = provider.history(Instrument.parse("SPY"), freeze, as_of)
    if len(calendar) < 2:
        log(f"fewer than 2 complete sessions since the freeze date {freeze} (as-of {as_of}): nothing to record yet")
        return 0
    log(f"recomputing {freeze} -> {as_of} on {a.data}")
    frame = recompute(as_of, cfg, provider, freeze)
    ledger = out / "ledger.csv"
    old = pd.read_csv(ledger, index_col=0, parse_dates=True) if ledger.exists() else None
    if old is not None and len(old) and frame.index[-1] < old.index[-1] and not a.allow_shrink:
        raise SystemExit(f"as-of {as_of} would shrink the record ({len(old)} -> {len(frame)} sessions); "
                         f"pass --allow-shrink to accept it")
    rev = revisions(old, frame)
    merged = merge_append_only(old, frame)
    frame.to_csv(out / "ledger_recomputed.csv")
    merged.to_csv(ledger)
    if rev["cells"] or rev["dropped"]:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        rows = [{"run_at": stamp, "as_of": as_of.isoformat(), **c} for c in rev["cells"]]
        rows += [{"run_at": stamp, "as_of": as_of.isoformat(), "date": d, "column": "(session)", "old": "present",
                  "new": "missing"} for d in rev["dropped"]]
        pd.DataFrame(rows).to_csv(out / "revisions.csv", mode="a", index=False,
                                  header=not (out / "revisions.csv").exists())
    (out / "summary.md").write_text(summary(merged, freeze), encoding="utf-8")
    with open(out / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "as_of": as_of.isoformat(),
                            "freeze": freeze.isoformat(), "sessions": int(len(merged)),
                            "sessions_recomputed": int(len(frame)), "appended": int(len(merged) - (len(old) if old is not None else 0)),
                            "data": a.data, "seconds": round(time.time() - t0, 1),
                            "revisions": rev["changed"], "dropped": rev["dropped"],
                            "last": {c: float(merged[c].iloc[-1]) for c in merged.columns},
                            "provenance": provenance()}, default=float) + "\n")
    if rev["changed"] or rev["dropped"]:
        log(f"WARNING: the recomputation differs from the ledger for {len(rev['cells'])} cell(s) and "
            f"{len(rev['dropped'])} dropped session(s); the ledger keeps its rows, see revisions.csv")
    log(f"{len(merged)} sessions in the ledger ({len(frame)} recomputed) in {time.time() - t0:.0f}s -> {ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
