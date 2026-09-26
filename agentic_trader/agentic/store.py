"""A persistent task store for the harness (SQLite, standard library only).

``AgentHarness.runs`` lives in the process that runs the tasks; without a store a
restart loses every record, which makes ``agentic-trader serve`` a toy. The store
keeps one JSON record per task (the full ``TaskRun.to_dict()``: plan, decision,
findings, critic, report, trace summary and spans, evidence rows) and is written
at every state transition, so a record is never more than one step behind.

On startup the harness reloads the records as an *archive*: they are served by
the API read routes exactly like live runs, but they are not resumable. A record
that was still in a non-terminal state when the previous process died is marked
FAILED with the reason ``process restarted`` -- an in-flight decision must never
silently disappear or appear to be still running.
"""
from __future__ import annotations

import json
import sqlite3
import threading
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
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS tasks_state ON tasks(state);
"""


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
        self._lock = threading.Lock()

    # ------------------------------------------------------------- writes
    def save_record(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO tasks(task_id, symbol, as_of, role, state, record, updated_at) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET "
                "state=excluded.state, record=excluded.record, updated_at=excluded.updated_at",
                (record["task_id"], record["symbol"], record["as_of"], record["role"], record["state"],
                 json.dumps(record, default=str), _now()))
            self._conn.commit()

    def save(self, run) -> None:
        """Persist a ``TaskRun`` (the full record plus evidence rows and trace spans)."""
        self.save_record(record_of(run))

    def mark_interrupted(self, note: str = "process restarted") -> int:
        """Fail every record left in a non-terminal state by a previous process."""
        terminal = tuple(s.value for s in TERMINAL_STATES)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT task_id, record FROM tasks WHERE state NOT IN ({','.join('?' * len(terminal))})",
                terminal).fetchall()
            for task_id, raw in rows:
                rec = json.loads(raw)
                rec["state"] = TaskState.FAILED.value
                rec.setdefault("history", []).append([TaskState.FAILED.value, f"{_now()} {note}"])
                rec.setdefault("errors", []).append(note)
                rec["finished_at"] = _now()
                self._conn.execute("UPDATE tasks SET state=?, record=?, updated_at=? WHERE task_id=?",
                                   (rec["state"], json.dumps(rec, default=str), _now(), task_id))
            self._conn.commit()
        return len(rows)

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

    def __len__(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def record_of(run) -> dict[str, Any]:
    """Everything the API serves for a task, as one JSON-able dict."""
    rec = run.to_dict(include_report=True)
    rec["evidence_rows"] = run.evidence.summary_rows()
    rec["spans"] = run.tracer.to_list()
    rec["correlation_id"] = run.correlation_id
    return rec
