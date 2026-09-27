"""A persistent task store for the harness (SQLite, standard library only).

``AgentHarness.runs`` lives in the process that runs the tasks; without a store a
restart loses every record, which makes ``agentic-trader serve`` a toy. The store
keeps one JSON record per task (the full ``TaskRun.to_dict()``: plan, decision,
findings, critic, report, trace summary and spans, evidence rows) and is written
at every state transition, so a record is never more than one step behind.

Every record carries the **owner** (the harness instance that drives the run) and
a **heartbeat** (epoch seconds, refreshed by the owner while the run is live).
A record left in a non-terminal state is only marked FAILED (``process
restarted``) by the interrupted-run sweep when its heartbeat has expired past the
lease (or it predates leases): a second instance sharing the store cannot fail a
live sibling's runs, even one configured with the same instance id. The sweep is a
compare-and-swap on the state it selected, so a record another process finished
in the meantime is left alone.

On startup the harness reloads the terminal records as an *archive*: they are
served by the API read routes exactly like live runs, but they are not resumable.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain import TERMINAL_STATES, TaskState

_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    as_of TEXT NOT NULL,
    role TEXT NOT NULL,
    state TEXT NOT NULL,
    record TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    owner TEXT,
    heartbeat REAL
);
CREATE INDEX IF NOT EXISTS tasks_state ON tasks(state);
"""
_TERMINAL = tuple(s.value for s in TERMINAL_STATES)
_NOT_TERMINAL = f"state NOT IN ({','.join('?' * len(_TERMINAL))})"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TaskStore:
    """SQLite-backed record store. Thread-safe; one connection per store."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._lock = threading.Lock()
        self.closed = False

    def _migrate(self) -> None:
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(tasks)").fetchall()}
        for col, typ in (("owner", "TEXT"), ("heartbeat", "REAL")):
            if col not in cols:
                self._conn.execute(f"ALTER TABLE tasks ADD COLUMN {col} {typ}")
        self._conn.commit()

    # ------------------------------------------------------------- writes
    def save_record(self, record: dict[str, Any], owner: str | None = None) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO tasks(task_id, symbol, as_of, role, state, record, updated_at, owner, heartbeat) "
                "VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET "
                "state=excluded.state, record=excluded.record, updated_at=excluded.updated_at, "
                "owner=excluded.owner, heartbeat=excluded.heartbeat",
                (record["task_id"], record["symbol"], record["as_of"], record["role"], record["state"],
                 json.dumps(record, default=str), _now(), owner, time.time()))
            self._conn.commit()

    def save(self, run, owner: str | None = None) -> None:
        """Persist a ``TaskRun`` (the full record plus evidence rows and trace spans)."""
        self.save_record(record_of(run), owner)

    def heartbeat(self, owner: str, task_ids: list[str] | tuple[str, ...] | None = None) -> int:
        """Refresh the lease on the live records this owner drives: the given ``task_ids``
        (what the instance actually holds; a predecessor's orphans under the same configured
        owner id are not kept alive), or every non-terminal record of the owner when omitted."""
        now = time.time()
        with self._lock:
            if task_ids is None:
                cur = self._conn.execute(f"UPDATE tasks SET heartbeat=? WHERE owner=? AND {_NOT_TERMINAL}",
                                         (now, owner, *_TERMINAL))
                n = cur.rowcount
            else:
                n = 0
                ids = list(task_ids)
                for i in range(0, len(ids), 500):
                    chunk = ids[i:i + 500]
                    marks = ",".join("?" * len(chunk))
                    cur = self._conn.execute(
                        f"UPDATE tasks SET heartbeat=? WHERE owner=? AND task_id IN ({marks}) AND {_NOT_TERMINAL}",
                        (now, owner, *chunk, *_TERMINAL))
                    n += cur.rowcount
            self._conn.commit()
            return n

    def mark_interrupted(self, note: str = "process restarted", owner: str | None = None,
                         lease_s: float | None = None) -> int:
        """Fail records left in a non-terminal state by a process that is gone.

        With neither ``owner`` nor ``lease_s`` every non-terminal record is failed (an
        explicit, ungated sweep for a single-process restart). With ``lease_s`` only records
        that are provably orphaned are touched: those whose heartbeat is older than
        ``lease_s`` seconds, and those with no owner or heartbeat at all (written before
        leases existed). The owner never widens the sweep: a live sibling sharing a
        configured instance id keeps heartbeating its runs and they survive. ``owner``
        without ``lease_s`` is refused rather than silently sweeping everything.

        Returns the number of records this call failed. Each update is conditioned on the
        state and version it selected, so a record finished by its owner between the select
        and the update keeps its terminal state.
        """
        if lease_s is None:
            if owner is not None:
                raise ValueError("mark_interrupted(owner=...) needs lease_s: without a lease the sweep would fail "
                                 "every live record")
            cutoff = None
        else:
            lease = float(lease_s)
            if not lease > 0:
                raise ValueError(f"lease_s must be a positive number of seconds, got {lease_s!r}")
            cutoff = time.time() - lease
        with self._lock:
            if cutoff is None:
                rows = self._conn.execute(
                    f"SELECT task_id, record, state, updated_at FROM tasks WHERE {_NOT_TERMINAL}",
                    _TERMINAL).fetchall()
            else:
                rows = self._conn.execute(
                    f"SELECT task_id, record, state, updated_at FROM tasks WHERE {_NOT_TERMINAL} AND "
                    "(owner IS NULL OR heartbeat IS NULL OR heartbeat < ?)",
                    (*_TERMINAL, cutoff)).fetchall()
            failed = 0
            for task_id, raw, state, updated_at in rows:
                rec = json.loads(raw)
                rec["state"] = TaskState.FAILED.value
                rec.setdefault("history", []).append([TaskState.FAILED.value, f"{_now()} {note}"])
                rec.setdefault("errors", []).append(note)
                rec["finished_at"] = _now()
                cur = self._conn.execute(
                    "UPDATE tasks SET state=?, record=?, updated_at=? WHERE task_id=? AND state=? AND updated_at=?",
                    (rec["state"], json.dumps(rec, default=str), _now(), task_id, state, updated_at))
                failed += cur.rowcount
            self._conn.commit()
        return failed

    def delete(self, task_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute("DELETE FROM tasks WHERE task_id=?", (task_id,))
            self._conn.commit()
            return cur.rowcount > 0

    # -------------------------------------------------------------- reads
    def load(self, task_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT record FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def load_all(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT record FROM tasks ORDER BY updated_at").fetchall()
        return [json.loads(r[0]) for r in rows]

    def summaries(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_id, symbol, as_of, role, state, updated_at FROM tasks ORDER BY updated_at").fetchall()
        return [dict(zip(("task_id", "symbol", "as_of", "role", "state", "updated_at"), r)) for r in rows]

    def ownership(self, task_id: str) -> tuple[str | None, float | None] | None:
        """(owner, heartbeat) of a record, or ``None`` when unknown."""
        with self._lock:
            row = self._conn.execute("SELECT owner, heartbeat FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        return (row[0], row[1]) if row else None

    def __len__(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self.closed = True
            self._conn.close()


def record_of(run) -> dict[str, Any]:
    """Everything the API serves for a task, as one JSON-able dict."""
    rec = run.to_dict(include_report=True)
    rec["evidence_rows"] = run.evidence.summary_rows()
    rec["spans"] = run.tracer.to_list()
    rec["correlation_id"] = run.correlation_id
    return rec
