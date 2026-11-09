"""Operations around the forward paper record: price-vintage hash, freshness rule, publish step.

* ``VintageRecorder`` wraps a market-data provider and keeps every price frame the run reads;
  ``vintage_hash`` turns them into one SHA-256 that ``paper_trade_v09.py`` writes into the
  run's ``runs.jsonl`` line. Two runs with the same hash saw byte-identical bars; a Yahoo
  restatement or a back-filled session changes it.
* ``freshness`` fails when the last recorded session is more than ``--max-business-days``
  NYSE sessions older than today (``agentic_trader/nyse_calendar.py``: weekends, holidays
  and one-off closures are not counted, so a Monday or post-holiday run is not stale). A file
  with no record yet passes: the first run has nothing to be late against.
* ``commit`` stages the published files and commits only when they changed, so a re-run of
  the same session, or a run that appended nothing, leaves the history untouched.

    python scripts/paper_ops.py freshness [--runs results/paper/runs.jsonl] [--today YYYY-MM-DD]
    python scripts/paper_ops.py commit [--message "paper: daily record [skip ci]"]
    python scripts/paper_ops.py push [--attempts 5] [--backoff 5]

* ``store_session_bars`` writes the bars the run read (as served, i.e. adjusted) and, where
  the provider has them, the raw closes and corporate actions (splits, dividends) to
  ``results/paper/bars/<as-of>/`` as deterministic gzip CSV, so a revision flagged by the hash
  can be attributed and a past session recomputed after Yahoo re-adjusts its history. That
  directory is git-ignored and never published (Yahoo data may not be redistributed, see
  DATA_LICENSING.md): the workflow keeps it as a private Actions artifact and only the files'
  SHA-256 go into ``runs.jsonl``.
* ``engine_fingerprint`` hashes the engine files and config blocks of the frozen record; the
  paper script refuses to run when it differs from ``docs/evaluation/paper_freeze.json``.

The ``commit``, ``push`` and ``freshness`` commands need only the standard library (the
publish and freshness jobs install nothing); numpy and pandas are imported where frames are
handled.
* ``push`` pushes HEAD to main and, when the push loses a race with another commit, rebases
  and retries with exponential backoff (``--attempts`` pushes in all).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import subprocess
import sys
import time
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "results" / "paper" / "runs.jsonl"
# the files the daily publish commits (the same set the laptop's paper_daily.cmd adds)
PUBLISHED = ("ledger.csv", "ledger_recomputed.csv", "revisions.csv", "runs.jsonl", "summary.md", "exposure.csv",
             "ledger_vintage.csv")
# raw session bars (results/paper/bars/) are NOT published: Yahoo data may not be redistributed
# (DATA_LICENSING.md). They stay git-ignored on the runner, go to a private Actions artifact,
# and only their SHA-256 is published in runs.jsonl.
MAX_STALE_BUSINESS_DAYS = 2


class VintageRecorder:
    """A provider that answers like the one it wraps and remembers each price frame it served."""

    def __init__(self, provider):
        self._provider = provider
        self.frames: dict[tuple[str, str, str], pd.DataFrame] = {}
        self.instruments: dict[str, object] = {}   # str(instrument) -> instrument, for the bar store

    def history(self, instrument, start: date, end: date) -> pd.DataFrame:
        frame = self._provider.history(instrument, start, end)
        self.frames[(str(instrument), start.isoformat(), end.isoformat())] = frame
        self.instruments[str(instrument)] = instrument
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


def engine_fingerprint(root: Path, patterns: list[str], config: dict, config_keys: list[str],
                       books: object) -> str:
    """SHA-256 over the engine that computes the frozen record: the bytes of every file the
    ``patterns`` (globs relative to ``root``) match, in sorted path order with CRLF taken as
    LF (a Windows checkout hashes like a Linux one), the ``config_keys`` subset of the run's
    config (the numbers-driving blocks, not paths or LLM settings) and ``repr(books)``."""
    h = hashlib.sha256()
    files = sorted({p for pat in patterns for p in root.glob(pat) if p.is_file()})
    for p in files:
        h.update(p.relative_to(root).as_posix().encode() + b"\n")
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    h.update(json.dumps({k: config.get(k) for k in sorted(config_keys)}, sort_keys=True, default=str).encode())
    h.update(repr(books).encode())
    return h.hexdigest()


def _gzip_csv(frame: pd.DataFrame) -> bytes:
    """``frame`` as CSV in a gzip stream with a zero timestamp and no file name, so the same
    frame always gives the same bytes (a re-run of a session leaves git nothing to commit)."""
    text = frame.to_csv(float_format="%.17g", lineterminator="\n").encode()
    buf = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buf, mtime=0, compresslevel=9) as g:
        g.write(text)
    return buf.getvalue()


def _long(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    import pandas as pd
    parts = []
    for name in sorted(frames):
        f = frames[name].copy()
        f.index = pd.Index(pd.DatetimeIndex(f.index).strftime("%Y-%m-%d"), name="date")
        f.insert(0, "symbol", name)
        parts.append(f)
    return pd.concat(parts)


def store_session_bars(provider, out: Path, as_of: date) -> dict:
    """Write the session's price vintage under ``out/<as_of>/`` and return what was written.

    ``prices.csv.gz``: per symbol the widest frame the run read, exactly as served (adjusted
    when the provider adjusts). ``actions.csv.gz``: per symbol the raw close (Yahoo's ``Close``
    with ``auto_adjust=False``: split-adjusted, not dividend-adjusted), the split ratio and the
    cash dividend on each ex-date, cut to the window of the prices, from the provider's
    ``corporate_actions`` when it has one (Yahoo does; the synthetic provider and FX do not).
    The unadjusted close on day t is ``RawClose_t x prod(Split_s for s > t)``.

    Append-only like the ledger: a file already present is never overwritten. A second run of
    the same session that read different bars writes ``prices.<hash12>.csv.gz`` beside it, so a
    same-day restatement is kept, not lost."""
    widest: dict[str, pd.DataFrame] = {}
    insts: dict[str, object] = {}
    for (key, _start, _end), frame in provider.frames.items():
        ins = provider.instruments.get(key)
        name = str(getattr(ins, "symbol", key))
        if frame is not None and len(frame) and (name not in widest or len(frame) > len(widest[name])):
            widest[name], insts[name] = frame, ins
    actions: dict[str, pd.DataFrame] = {}
    fetch = getattr(provider, "corporate_actions", None)
    if callable(fetch):
        for name, f in widest.items():
            try:
                a = fetch(insts[name])
            except Exception as e:   # an action outage must not lose the price vintage
                print(f"corporate actions unavailable for {name}: {e}", file=sys.stderr)
                continue
            if a is not None and len(a):
                import pandas as pd
                lo, hi = pd.Timestamp(f.index.min()), pd.Timestamp(as_of)
                actions[name] = a.loc[(a.index >= lo) & (a.index <= hi)]
    day = out / as_of.isoformat()
    day.mkdir(parents=True, exist_ok=True)
    files: dict[str, str] = {}
    size = 0
    for stem, table in (("prices", widest), ("actions", actions)):
        if not table:
            continue
        blob = _gzip_csv(_long(table))
        target = day / f"{stem}.csv.gz"
        if target.exists() and target.read_bytes() != blob:
            target = day / f"{stem}.{hashlib.sha256(blob).hexdigest()[:12]}.csv.gz"
        if not target.exists():
            target.write_bytes(blob)
        files[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        size += len(blob)
    return {"dir": day.name, "symbols": len(widest), "files": files, "bytes": size}


def read_session_bars(path: Path) -> dict[str, pd.DataFrame]:
    """Inverse of the writer: symbol -> frame indexed by date, columns as stored."""
    import pandas as pd
    long = pd.read_csv(path, index_col=0, parse_dates=True)
    return {str(sym): g.drop(columns="symbol") for sym, g in long.groupby("symbol", sort=True)}


def push_with_retry(attempts: int = 5, backoff: float = 5.0,
                    run: Callable[[list[str]], int] | None = None,
                    sleep: Callable[[float], None] = time.sleep) -> bool:
    """``git push origin HEAD:main``; when it fails (usually a lost race with another commit
    to main), wait ``backoff x 2^k`` seconds, ``git pull --rebase`` and push again, ``attempts``
    pushes in all. A rebase conflict aborts and returns False at once: a real conflict on the
    append-only files needs a person, not a loop."""
    runner = run or (lambda cmd: subprocess.run(cmd, cwd=ROOT).returncode)
    for k in range(attempts):
        if runner(["git", "push", "-q", "origin", "HEAD:main"]) == 0:
            return True
        if k == attempts - 1:
            break
        sleep(backoff * 2 ** k)
        if runner(["git", "pull", "-q", "--rebase", "origin", "main"]) != 0:
            runner(["git", "rebase", "--abort"])
            return False
    return False


def last_recorded_session(runs: Path) -> date | None:
    """The latest ``as_of`` in a runs.jsonl file, or None when there is no record yet."""
    if not runs.exists():
        return None
    as_of = [json.loads(line)["as_of"] for line in runs.read_text(encoding="utf-8").splitlines() if line.strip()]
    return max(date.fromisoformat(d) for d in as_of) if as_of else None


def _calendar():
    """``agentic_trader/nyse_calendar.py`` loaded by path: stdlib only, no package import."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("_nyse_calendar", ROOT / "agentic_trader" / "nyse_calendar.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def business_days_stale(last: date, today: date) -> int:
    """NYSE sessions after ``last`` up to and including ``today`` (weekends and NYSE
    closures are not counted)."""
    return int(_calendar().sessions_after(last, today))


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
    p = sub.add_parser("push", help="push HEAD to main; on a lost race rebase and retry with backoff")
    p.add_argument("--attempts", type=int, default=5)
    p.add_argument("--backoff", type=float, default=5.0, help="first wait in seconds; doubles on each retry")
    a = ap.parse_args(argv)
    if a.cmd == "push":
        ok = push_with_retry(a.attempts, a.backoff)
        print("pushed" if ok else f"push failed after up to {a.attempts} attempt(s)")
        return 0 if ok else 1
    if a.cmd == "freshness":
        today = date.fromisoformat(a.today) if a.today else datetime.now(timezone.utc).date()
        ok, msg = freshness(Path(a.runs), today, a.max_business_days)
        print(msg)
        return 0 if ok else 1
    committed = commit_if_changed(ROOT, [f"results/paper/{p}" for p in PUBLISHED], a.message)
    print("committed" if committed else "nothing changed, no commit")
    return 0


if __name__ == "__main__":
    sys.exit(main())
