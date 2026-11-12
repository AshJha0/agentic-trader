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
its control), ``runs.jsonl`` (one line per run: as-of date, rows, provenance, revisions and
``price_vintage``, the SHA-256 of every price frame the run read; see ``paper_ops.py``).

Nothing here changes a rule, a universe or a weight after the freeze date. To adopt a
candidate later, the forward record has to clear the pre-registered bar on its own.

    .venv\\Scripts\\python.exe scripts/paper_trade_v09.py [--as-of YYYY-MM-DD] [--out results/paper] [--data yahoo|synthetic]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.backtest import AGENT, run_portfolio_backtest  # noqa: E402
from agentic_trader.cli.common import default_as_of, exchange_today, load_dotenv  # noqa: E402
from agentic_trader.config import make_config  # noqa: E402
from agentic_trader.data import get_provider  # noqa: E402
from agentic_trader.evaluation import CORE_UNIVERSE, EXTENDED_UNIVERSE, UNIVERSES  # noqa: E402
from agentic_trader.provenance import provenance  # noqa: E402
from agentic_trader.stats import paired_sharpe_block_bootstrap, sharpe_stats  # noqa: E402
from agentic_trader.validate import read_ledger_csv, write_ledger_csv  # noqa: E402
from agentic_trader.nyse_calendar import last_session_on_or_before  # noqa: E402
from scripts.paper_ops import (VintageRecorder, engine_fingerprint, engine_patterns, ledger_chain,  # noqa: E402
                               store_session_bars, vintage_hash)

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


def recompute(as_of: date, cfg: dict, provider, freeze: date = FREEZE, exposure: dict | None = None,
              coverage: dict | None = None) -> pd.DataFrame:
    """The whole forward record, freeze -> as_of, one column per ``book/stream`` plus ``rf``.

    When ``exposure`` is a dict it receives one frame with, per ``book/stream``, the gross
    exposure held over each bar (sum of |weight| x allocation), the turnover traded on it and
    the trading cost charged for it (turnover x (cost_bps + slippage_bps) of each sleeve), all
    as fractions of book capital.

    Only complete sessions are returned (round 2, review D2): the frame stops at the earliest
    last bar of any sleeve of any book. Before, a sleeve whose provider lagged by a day (Yahoo
    serving AAPL through T-1 while the rest ran to T) was filled with a 0 return on T, and that
    0 went into the append-only ledger for good. The held-back sessions are listed in
    ``coverage["skipped"]`` (date and reason) and recorded by the next run once complete; a
    sleeve more than 7 days behind is still an error. ``coverage["last_bar"]`` is the last
    complete session."""
    cols, rf = {}, None
    exp_cols = {}
    last_bars: dict[str, pd.Timestamp] = {}
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
            last_bars[f"{book}:{sym}"] = pd.Timestamp(sleeve.dates[-1])
        for s in streams:
            cols[f"{book}/{s}"] = rep.returns[s]
            if exposure is not None:
                alloc = rep.allocations.reindex(rep.dates) if rep.allocations is not None else None
                gross = turn = cost = 0.0
                for sym, sleeve in rep.sleeves.items():
                    res = sleeve.results[s]
                    share = alloc[sym] if alloc is not None else 1.0 / len(rep.sleeves)
                    bc = sleeve.backtest_config
                    unit = 0.0 if bc is None else (bc.cost_bps + bc.slippage_bps) / 1e4
                    pos = pd.Series(np.abs(res.positions), index=sleeve.dates).reindex(rep.dates).fillna(0.0)
                    trd = pd.Series(np.abs(res.traded), index=sleeve.dates).reindex(rep.dates).fillna(0.0)
                    gross = gross + pos * share
                    turn = turn + trd * share
                    cost = cost + trd * unit * share
                exp_cols[f"{book}/{s}/gross"] = gross
                exp_cols[f"{book}/{s}/turnover"] = turn
                exp_cols[f"{book}/{s}/cost"] = cost
        r = pd.Series(rep.rf if isinstance(rep.rf, np.ndarray) else float(rep.rf or 0.0), index=rep.dates)
        rf = r if rf is None else pd.concat([rf, r], axis=1, sort=True).max(axis=1)
    frame = pd.DataFrame(cols).sort_index().fillna(0.0)
    frame["rf"] = rf.reindex(frame.index).ffill()
    complete = min(last_bars.values()) if last_bars else (frame.index[-1] if len(frame) else None)
    skipped = []
    if complete is not None:
        for d in frame.index[frame.index > complete]:
            behind = sorted(k for k, v in last_bars.items() if v < d)
            skipped.append({"date": d.date().isoformat(),
                            "reason": f"incomplete session: no bar yet for {', '.join(behind)}"})
        frame = frame.loc[frame.index <= complete]
    if coverage is not None:
        coverage["skipped"] = skipped
        coverage["last_bar"] = None if complete is None else complete.date().isoformat()
    if exposure is not None:
        exposure["frame"] = pd.DataFrame(exp_cols).reindex(frame.index).fillna(0.0)
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


FREEZE_FILE = ROOT / "docs" / "evaluation" / "paper_freeze.json"


def check_freeze(freeze_file: Path, cfg: dict) -> str:
    """The vintage id of the frozen engine, after checking that the engine about to run is it.

    ``freeze_file`` names the engine files (globs; since round 2 always widened by
    ``paper_ops.REQUIRED_ENGINE_FILES``: the whole package, cpp/ and the lock), the config blocks and a SHA-256 of both
    plus ``BOOKS`` (``paper_ops.engine_fingerprint``). A different hash means the code or
    config that computes the frozen books has changed since the freeze, and the run is
    refused: recording it would mix two engines in one append-only ledger. A deliberate
    change is a re-freeze (``--refreeze NEW_ID --reason ...``), which starts a new vintage
    id carried by every row recorded after it (``ledger_vintage.csv``); it is never silent."""
    spec = json.loads(freeze_file.read_text(encoding="utf-8"))
    have = engine_fingerprint(ROOT, engine_patterns(spec["engine_files"]), cfg, spec["config_keys"], BOOKS)
    if have != spec["engine_hash"]:
        raise SystemExit(f"engine changed since freeze vintage {spec['vintage_id']} ({freeze_file.name}: "
                         f"{spec['engine_hash'][:12]}, now {have[:12]}); refusing to record. A deliberate change "
                         f"needs a re-freeze: --refreeze NEW_ID --reason TEXT (see docs/evaluation/paper_freeze.md)")
    return str(spec["vintage_id"])


def refreeze(freeze_file: Path, cfg: dict, vintage_id: str, reason: str, today: date) -> dict:
    """Record the current engine as a new vintage in ``freeze_file``; the old one moves to
    ``history``. Refuses an id already used and an empty reason."""
    spec = json.loads(freeze_file.read_text(encoding="utf-8"))
    used = {spec["vintage_id"], *(h["vintage_id"] for h in spec.get("history", []))}
    if vintage_id in used or not reason.strip():
        raise SystemExit(f"re-freeze needs a new vintage id (used: {sorted(used)}) and a reason")
    old = {k: spec[k] for k in ("vintage_id", "engine_hash", "frozen_on", "reason") if k in spec}
    patterns = engine_patterns(spec["engine_files"])
    spec.update(history=[*spec.get("history", []), old], vintage_id=vintage_id, frozen_on=today.isoformat(),
                reason=reason, engine_files=patterns,
                engine_hash=engine_fingerprint(ROOT, patterns, cfg, spec["config_keys"], BOOKS))
    freeze_file.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8")
    return spec


def resolve_as_of(ny_yesterday: date) -> date:
    """The last NYSE session on or before New York's yesterday: a Monday run records Friday,
    a run the day after a holiday records the session before it."""
    return last_session_on_or_before(ny_yesterday)


def assert_final(as_of: date, today: date) -> None:
    """Refuse to record a session that may not be final: a daily bar dated D is complete only
    once the New York date is after D, so ``as_of`` must be strictly before ``today`` (New
    York's date at run time). A provisional close written into the append-only ledger could
    never be corrected there."""
    if as_of >= today:
        raise SystemExit(f"as-of {as_of} is not before New York's date {today}: the session may not be final; "
                         f"refusing to record it (the default as-of is New York's yesterday)")


def same_day_revisions(old: pd.DataFrame | None, cells: list[dict]) -> list[dict]:
    """Revised cells on the ledger's last session before this run: the session recorded by
    the previous run moved one day later, the sign of a bar fetched before it was final."""
    if old is None or old.empty:
        return []
    last = old.index[-1].date().isoformat()
    return [c for c in cells if c["date"] == last]


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
    ap.add_argument("--oms", action="store_true",
                    help="also run the paper OMS shadow record (separate label, under <out>/oms; off by default: "
                         "the frozen record is unchanged, and turning it on starts a new, separately labelled record)")
    ap.add_argument("--oms-corporate-actions", action="store_true",
                    help="with --oms: apply corporate actions with ex-date in the session window to held "
                         "quantities (C3 hook; off by default; needs a provider with action tables)")
    ap.add_argument("--freeze-file", default=str(FREEZE_FILE), help="engine freeze record (tests only)")
    ap.add_argument("--refreeze", default=None, metavar="NEW_ID",
                    help="record the current engine as a new vintage in the freeze file and exit (deliberate change)")
    ap.add_argument("--reason", default="", help="why the engine was re-frozen (required with --refreeze)")
    a = ap.parse_args(argv)
    load_dotenv(str(ROOT / ".env"))
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    as_of = date.fromisoformat(a.as_of) if a.as_of else resolve_as_of(default_as_of())
    freeze = date.fromisoformat(a.freeze)
    assert_final(as_of, exchange_today())
    if as_of < freeze:
        log(f"as-of {as_of} is before the freeze date {freeze}: nothing to record yet")
        return 0
    cfg = make_config(data_provider=a.data, memory_path=None,
                      edgar_cache_dir=str(ROOT / "build" / "edgar_cache"),
                      fred_cache_dir=str(ROOT / "build" / "fred_cache"))
    if a.refreeze:
        spec = refreeze(Path(a.freeze_file), cfg, a.refreeze, a.reason, exchange_today())
        log(f"re-frozen as vintage {spec['vintage_id']} ({spec['engine_hash'][:12]}): {a.reason}")
        return 0
    vintage_id = check_freeze(Path(a.freeze_file), cfg)
    provider = VintageRecorder(get_provider(cfg))
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
    exp: dict = {}
    cov: dict = {}
    frame = recompute(as_of, cfg, provider, freeze, exposure=exp, coverage=cov)
    for s in cov.get("skipped", []):
        log(f"WARNING: session {s['date']} not recorded: {s['reason']}; the next run records it once complete")
    if cov.get("last_bar") and date.fromisoformat(cov["last_bar"]) < as_of:
        log(f"WARNING: the last complete session is {cov['last_bar']}, before the as-of {as_of}: "
            f"the provider has not served every bar yet (review D7)")
    ledger = out / "ledger.csv"
    old = read_ledger_csv(ledger) if ledger.exists() else None
    if old is not None and len(old) and frame.index[-1] < old.index[-1] and not a.allow_shrink:
        raise SystemExit(f"as-of {as_of} would shrink the record ({len(old)} -> {len(frame)} sessions); "
                         f"pass --allow-shrink to accept it")
    rev = revisions(old, frame)
    merged = merge_append_only(old, frame)
    write_ledger_csv(frame, out / "ledger_recomputed.csv")
    write_ledger_csv(merged, ledger)
    # ledger_vintage.csv: the engine vintage of every ledger row, appended with the rows
    added = merged.index[len(old):] if old is not None else merged.index
    if len(added):
        vfile = out / "ledger_vintage.csv"
        pd.DataFrame({"date": added.strftime("%Y-%m-%d"), "vintage_id": vintage_id}).to_csv(
            vfile, mode="a", index=False, header=not vfile.exists())
    # exposure.csv: gross exposure, turnover and trading cost per book/stream per session,
    # kept append-only like the ledger (sessions already written are never rewritten)
    exp_file = out / "exposure.csv"
    if "frame" in exp:
        old_exp = pd.read_csv(exp_file, index_col=0, parse_dates=True) if exp_file.exists() else None
        merge_append_only(old_exp, exp["frame"]).to_csv(exp_file)
    if rev["cells"] or rev["dropped"]:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        rows = [{"run_at": stamp, "as_of": as_of.isoformat(), **c} for c in rev["cells"]]
        rows += [{"run_at": stamp, "as_of": as_of.isoformat(), "date": d, "column": "(session)", "old": "present",
                  "new": "missing"} for d in rev["dropped"]]
        pd.DataFrame(rows).to_csv(out / "revisions.csv", mode="a", index=False,
                                  header=not (out / "revisions.csv").exists())
    same_day = same_day_revisions(old, rev["cells"])
    text = summary(merged, freeze)
    if same_day:
        text += (f"\n**Same-day revision:** {len(same_day)} cell(s) of {same_day[0]['date']}, the session the previous "
                 f"run recorded, moved in this run (columns: {', '.join(sorted({c['column'] for c in same_day}))}). "
                 f"The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.\n")
    (out / "summary.md").write_text(text, encoding="utf-8")
    bars = store_session_bars(provider, out / "bars", as_of)
    heads = ledger_chain(ledger.read_text(encoding="utf-8"))
    with open(out / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"run_at": time.strftime("%Y-%m-%d %H:%M:%S"), "as_of": as_of.isoformat(),
                            "fetched_at_utc": pd.Timestamp.now("UTC").strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "same_day_revisions": len(same_day), "bars": bars, "vintage_id": vintage_id,
                            "freeze": freeze.isoformat(), "sessions": int(len(merged)),
                            "sessions_recomputed": int(len(frame)), "appended": int(len(merged) - (len(old) if old is not None else 0)),
                            "data": a.data, "seconds": round(time.time() - t0, 1),
                            "price_vintage": vintage_hash(provider.frames),
                            "revisions": rev["changed"], "dropped": rev["dropped"],
                            # round 2: the last complete session the recomputation reached (D7),
                            # sessions held back as incomplete (D2), the ledger's hash chain (D6)
                            "last_bar": cov.get("last_bar"), "skipped": cov.get("skipped", []),
                            "ledger_rows": len(heads) - 1, "ledger_chain": heads[-1] if heads else None,
                            "last": {c: float(merged[c].iloc[-1]) for c in merged.columns},
                            "provenance": provenance()}, default=float) + "\n")
    if a.oms:   # plan item 4.7; never reads or writes the frozen ledger
        from agentic_trader.oms import paper_session
        log(f"OMS shadow record: {paper_session(as_of, cfg, provider, BOOKS, out / 'oms', freeze, corporate_actions=a.oms_corporate_actions)}")
    if same_day:
        log(f"WARNING: same-day revision of {same_day[0]['date']} ({len(same_day)} cell(s)); see summary.md")
    if rev["changed"] or rev["dropped"]:
        log(f"WARNING: the recomputation differs from the ledger for {len(rev['cells'])} cell(s) and "
            f"{len(rev['dropped'])} dropped session(s); the ledger keeps its rows, see revisions.csv")
    log(f"{len(merged)} sessions in the ledger ({len(frame)} recomputed) in {time.time() - t0:.0f}s -> {ledger}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
