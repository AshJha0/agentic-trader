"""Operations around the forward paper record: price-vintage hash, freshness rule, publish step.

* ``VintageRecorder`` wraps a market-data provider and keeps every price frame the run reads;
  ``vintage_hash`` turns them into one SHA-256 that ``paper_trade_v09.py`` writes into the
  run's ``runs.jsonl`` line. Two runs with the same hash saw byte-identical bars; a Yahoo
  restatement or a back-filled session changes it.
* ``freshness`` fails when the last recorded session is more than ``--max-business-days``
  business days (Monday to Friday, exchange holidays not modelled) older than today. A file
  with no record yet passes: the first run has nothing to be late against.
* ``commit`` stages the published files and commits only when they changed, so a re-run of
  the same session, or a run that appended nothing, leaves the history untouched.

    python scripts/paper_ops.py freshness [--runs results/paper/runs.jsonl] [--today YYYY-MM-DD]
    python scripts/paper_ops.py commit [--message "paper: daily record [skip ci]"]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "paper" / "runs.jsonl"
# the files the daily publish commits (the same set the laptop's paper_daily.cmd adds)
PUBLISHED = ("ledger.csv", "ledger_recomputed.csv", "revisions.csv", "runs.jsonl", "summary.md", "exposure.csv")
MAX_STALE_BUSINESS_DAYS = 2


class VintageRecorder:
    """A provider that answers like the one it wraps and remembers each price frame it served."""

    def __init__(self, provider):
        self._provider = provider
        self.frames: dict[tuple[str, str, str], pd.DataFrame] = {}

    def history(self, instrument, start: date, end: date) -> pd.DataFrame:
        frame = self._provider.history(instrument, start, end)
        self.frames[(str(instrument), start.isoformat(), end.isoformat())] = frame
        return frame

    def __getattr__(self, name):
        return getattr(self._provider, name)


def vintage_hash(frames: dict[tuple[str, str, str], pd.DataFrame]) -> str:
    """SHA-256 over every (request, frame) pair, taken in sorted request order.

    Each frame is serialised as CSV with full float precision (``repr`` round-trip), so a
    change in any price, volume, date or column name changes the hash, and nothing else
    (dict order, pandas internals) does."""
    h = hashlib.sha256()
    for key in sorted(frames):
        h.update("|".join(key).encode())
        h.update(b"\n")
        h.update(frames[key].to_csv(float_format="%.17g", lineterminator="\n").encode())
    return h.hexdigest()


def last_recorded_session(runs: Path) -> date | None:
    """The latest ``as_of`` in a runs.jsonl file, or None when there is no record yet."""
    if not runs.exists():
        return None
    as_of = [json.loads(line)["as_of"] for line in runs.read_text(encoding="utf-8").splitlines() if line.strip()]
    return max(date.fromisoformat(d) for d in as_of) if as_of else None


def business_days_stale(last: date, today: date) -> int:
    """Business days after ``last`` up to and including ``today`` (Monday to Friday)."""
    day = np.timedelta64(1, "D")
    return int(np.busday_count(np.datetime64(last, "D") + day, np.datetime64(today, "D") + day))


def freshness(runs: Path, today: date, max_business_days: int = MAX_STALE_BUSINESS_DAYS) -> tuple[bool, str]:
    last = last_recorded_session(runs)
    if last is None:
        return True, f"{runs.name}: no recorded session yet, nothing to check"
    stale = business_days_stale(last, today)
    verdict = "ok" if stale <= max_business_days else "STALE"
    return stale <= max_business_days, (f"{verdict}: last recorded session {last}, {stale} business day(s) "
                                        f"before {today} (limit {max_business_days})")


def commit_if_changed(repo: Path, paths: list[str], message: str) -> bool:
    """Stage ``paths`` and commit them if the index differs from HEAD. Returns True on a commit."""
    existing = [p for p in paths if (repo / p).exists()]
    if existing:
        subprocess.run(["git", "add", "--", *existing], cwd=repo, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=repo).returncode == 0:
        return False
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=repo, check=True)
    return True


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freshness", help="fail when the last recorded session is too old")
    f.add_argument("--runs", default=str(RUNS))
    f.add_argument("--today", default=None, help="reference date (default: today, UTC)")
    f.add_argument("--max-business-days", type=int, default=MAX_STALE_BUSINESS_DAYS)
    c = sub.add_parser("commit", help="commit the published paper files if they changed")
    c.add_argument("--message", default="paper: daily record [skip ci]")
    a = ap.parse_args(argv)
    if a.cmd == "freshness":
        today = date.fromisoformat(a.today) if a.today else pd.Timestamp.now("UTC").date()
        ok, msg = freshness(Path(a.runs), today, a.max_business_days)
        print(msg)
        return 0 if ok else 1
    committed = commit_if_changed(ROOT, [f"results/paper/{p}" for p in PUBLISHED], a.message)
    print("committed" if committed else "nothing changed, no commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
