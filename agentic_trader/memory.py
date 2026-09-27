"""Decision memory and reflection.

Every final decision is logged. Once its horizon has elapsed the realised
outcome is attached together with a short lesson, and later decisions on the
same instrument receive those lessons plus a hit-rate track record.

Outcomes are valued on *one* price series -- the history handed to the desk at the
current as-of date, which stops at that date -- from the entry bar to the bar
``horizon_days`` trading days later. Nothing is compared against the absolute price
stored at decision time, so a split or dividend rebase between sessions, or a
different data provider, cannot turn a right call into a "was wrong" verdict; an
entry is only ever resolved by the provider that recorded it, and one whose exit bar
has fallen out of the window is expired without a verdict rather than booked with a
multi-year return. A backtest never sees the future through memory because the
series it resolves on ends at as-of.

The log on disk is append-only: one line per decision and one per resolution, each
written with a single ``write`` and ``fsync`` under an in-process lock and a file lock
(``msvcrt.locking`` on Windows, ``fcntl.flock`` elsewhere: the MSVC C runtime emulates
``O_APPEND`` as seek-then-write, so two handles appending at once would otherwise
overwrite each other). Several threads, or several processes (``serve --processes N``),
can share one file without one writer's records racing another's. A repeated decision
for the same instrument, date and provider replaces the earlier one on reload (the
latest line wins).
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

if os.name == "nt":
    import msvcrt

    _LOCK_AT = 1 << 60   # a byte far past any log: Windows locks are mandatory, and a reader
                         # (another process loading the file) must never hit a locked region

    def _lock_file(fd: int, timeout: float = 30.0) -> None:
        # LK_LOCK sleeps a whole second between its retries, so poll the non-blocking form.
        deadline = time.monotonic() + timeout
        os.lseek(fd, _LOCK_AT, os.SEEK_SET)
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.0005)

    def _unlock_file(fd: int) -> None:
        os.lseek(fd, _LOCK_AT, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(fd: int, timeout: float = 30.0) -> None:
        fcntl.flock(fd, fcntl.LOCK_EX)

    def _unlock_file(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


@dataclass
class MemoryEntry:
    symbol: str
    as_of: str
    action: str
    weight: float
    price: float           # last close at decision time, on the recording provider's basis
    horizon_days: int      # trading days (bars) to the outcome, matching the proposal's horizon
    summary: str
    provider: str = ""     # data provider that priced the decision; resolves only on the same one
    price_basis: str = ""  # what ``price`` is (adjusted close, as-traded close, ...)
    resolved_on: str | None = None
    exit_price: float | None = None
    pnl: float | None = None      # weight * price return over the horizon
    lesson: str | None = None
    expired: bool = False         # closed without a verdict: no consistent series covered it

    @property
    def key(self) -> str:
        return f"{self.symbol}|{self.as_of}|{self.provider}"


_FIELDS = {f.name for f in fields(MemoryEntry)}
_RESOLUTION_FIELDS = ("resolved_on", "exit_price", "pnl", "lesson", "expired")


def series_basis(provider: Any) -> str:
    """What a provider's ``Close`` column is, for the memory record."""
    basis = getattr(provider, "price_basis", None)
    if basis:
        return str(basis)
    return "adjusted_close" if getattr(provider, "name", "") == "yahoo" else "close"


def _closes(history: Any) -> pd.Series:
    s = history["Close"] if isinstance(history, pd.DataFrame) else pd.Series(history)
    return s.sort_index()


class DecisionMemory:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[MemoryEntry] = []
        self._by_key: dict[str, MemoryEntry] = {}
        self.skipped_lines = 0
        self._lock = threading.RLock()
        if self.path and self.path.exists():
            self._load()

    # ------------------------------------------------------------ persistence
    def _load(self) -> None:
        for n, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise TypeError("not an object")
                if "resolve" in obj:
                    e = self._by_key.get(str(obj["resolve"]))
                    if e is not None:
                        for k in _RESOLUTION_FIELDS:
                            setattr(e, k, obj.get(k, getattr(e, k)))
                    continue
                self._put(MemoryEntry(**{k: v for k, v in obj.items() if k in _FIELDS}))
            except (json.JSONDecodeError, TypeError, ValueError) as e:
                # A torn write or a hand edit must not make every later run crash.
                self.skipped_lines += 1
                log.warning("memory %s line %d unreadable, skipped: %s", self.path, n, e)

    def _put(self, e: MemoryEntry) -> None:
        old = self._by_key.get(e.key)
        if old is not None:
            self.entries.remove(old)
        self.entries.append(e)
        self._by_key[e.key] = e

    def _append(self, obj: dict[str, Any]) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = (json.dumps(obj) + "\n").encode("utf-8")
        fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            _lock_file(fd)
            try:
                os.lseek(fd, 0, os.SEEK_END)
                os.write(fd, data)
                os.fsync(fd)
            finally:
                _unlock_file(fd)
        finally:
            os.close(fd)

    def _append_resolution(self, e: MemoryEntry) -> None:
        self._append({"resolve": e.key, **{k: getattr(e, k) for k in _RESOLUTION_FIELDS}})

    # ---------------------------------------------------------------- writes
    def record(self, symbol: str, as_of: date, action: str, weight: float, price: float,
               summary: str, horizon_days: int = 10, provider: str = "", price_basis: str = "") -> None:
        e = MemoryEntry(symbol, as_of.isoformat(), action, weight, price, int(horizon_days),
                        summary[:400], provider, price_basis)
        with self._lock:
            self._put(e)
            self._append(asdict(e))

    def resolve(self, symbol: str, as_of: date, history: Any, provider: str = "",
                price_basis: str = "") -> int:
        """Attach outcomes to entries whose horizon bar lies within ``history``.

        ``history`` is the price series the desk sees at ``as_of`` (a frame with a ``Close``
        column, or a series), which must not extend past ``as_of``. An entry made on another
        provider or basis is never valued on this series; one that this series cannot value
        (its entry bar predates the window, or its exit bar never arrives) is expired once
        more than twice its horizon has elapsed. Returns the number of entries closed
        (resolved or expired).
        """
        closes = _closes(history)
        last_pos = len(closes) - 1
        n = 0
        with self._lock:
            for e in self.entries:
                if e.symbol != symbol or e.resolved_on is not None:
                    continue
                entry_day = date.fromisoformat(e.as_of)
                same_series = (e.provider, e.price_basis) == (provider, price_basis) and last_pos >= 0
                pos = int(closes.index.searchsorted(pd.Timestamp(entry_day), side="right")) - 1 if same_series else -1
                if pos >= 0 and (entry_day - closes.index[pos].date()).days <= 7:
                    exit_pos = pos + e.horizon_days
                    if exit_pos <= last_pos:
                        self._settle(e, float(closes.iloc[pos]), float(closes.iloc[exit_pos]),
                                     closes.index[exit_pos].date())
                        n += 1
                        continue
                # Horizon not reached, or not valuable on this series: expire once the entry is
                # older than twice its horizon, whether or not its exit bar ever arrives.
                if (as_of - entry_day).days > self.max_age_days(e.horizon_days):
                    e.resolved_on, e.expired = as_of.isoformat(), True
                    self._append_resolution(e)
                    n += 1
        return n

    @staticmethod
    def max_age_days(horizon_bars: int) -> int:
        """Calendar days after which an unvalued entry is expired: twice the horizon, in
        calendar time (5 bars per 7 days)."""
        return int(math.ceil(2 * horizon_bars * 7 / 5))

    def _settle(self, e: MemoryEntry, entry_px: float, exit_px: float, exit_day: date) -> None:
        ret = exit_px / entry_px - 1.0 if entry_px > 0 else 0.0
        e.resolved_on, e.exit_price, e.pnl = exit_day.isoformat(), exit_px, e.weight * ret
        if e.weight == 0:
            verdict = ("stayed flat while price moved "
                       f"{ret:+.1%}" + (" (missed opportunity)" if abs(ret) > 0.03 else ""))
        elif e.pnl > 0:
            verdict = f"was right: position {e.weight:+.2f} earned {e.pnl:+.2%}"
        else:
            verdict = f"was wrong: position {e.weight:+.2f} lost {e.pnl:+.2%}"
        # No raw price level in the lesson: it is fed back into prompts, which
        # may be anonymised; the return and dates carry the information.
        e.lesson = (f"{e.as_of} {e.action} {e.symbol} {verdict} over {e.horizon_days} trading days "
                    f"to {e.resolved_on}. Reasoning then: {e.summary[:160]}")
        self._append_resolution(e)

    # ----------------------------------------------------------------- reads
    # ``provider`` restricts the read to entries priced by that provider (``None``: any):
    # a synthetic session's outcomes are not a track record for a live one.
    def lessons(self, symbol: str, as_of: date, k: int = 3, provider: str | None = None) -> list[str]:
        with self._lock:
            done = [e for e in self.entries if e.symbol == symbol and e.lesson
                    and (provider is None or e.provider == provider)
                    and e.resolved_on and date.fromisoformat(e.resolved_on) <= as_of]
            return [e.lesson for e in done[-k:]]

    def track_record(self, symbol: str, as_of: date, k: int = 20,
                     provider: str | None = None) -> dict[str, float]:
        with self._lock:
            done = [e for e in self.entries if e.symbol == symbol and e.pnl is not None
                    and (provider is None or e.provider == provider)
                    and e.weight != 0 and date.fromisoformat(e.resolved_on) <= as_of][-k:]
        if not done:
            return {}
        return {"n": float(len(done)),
                "hit_rate": sum(e.pnl > 0 for e in done) / len(done),
                "avg_pnl": sum(e.pnl for e in done) / len(done)}
