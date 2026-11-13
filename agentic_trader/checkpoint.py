"""Append-only JSON-lines checkpoint for long scripts that loop over independent units.

A script that runs hundreds of slow units and writes its results only at the end loses
everything when the machine shuts down. :class:`Checkpoint` records one JSON line per
finished unit, appended and fsync'd, so a rerun skips what is already done.

The first line is a header holding a fingerprint of the inputs (code, configuration,
data). Resuming against a header with a different fingerprint is refused: rows produced
by different code or data must never be mixed in one result file. A half-written last
line (the process died mid-write) is ignored and dropped on open, so that unit simply
runs again. A corrupt line in the middle is skipped on its own; valid rows after it are kept
and the count of skipped lines is reported (``Checkpoint.skipped_lines``).

Final outputs should be rebuilt from :meth:`Checkpoint.rows` in a fixed unit order, so a
resumed run writes byte-identical files to an uninterrupted one.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NL = b"\n"


class CheckpointMismatch(RuntimeError):
    """The checkpoint on disk was written for different inputs."""


def fingerprint(obj: Any) -> str:
    """sha256 of the canonical JSON of ``obj`` (sorted keys, ``str`` for unknown types)."""
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_sha256(*paths: str | Path) -> str:
    """sha256 over the bytes of the given files, in order (code fingerprint)."""
    h = hashlib.sha256()
    for p in paths:
        h.update(Path(p).read_bytes())
    return h.hexdigest()


class Checkpoint:
    """One JSON object per line; line 1 is ``{"header": {...}, "fingerprint": ...}``,
    every other line is ``{"key": <str>, "row": {...}}``."""

    def __init__(self, path: str | Path, header: dict, *, fresh: bool = False) -> None:
        self.path = Path(path)
        self.header = header
        self.fp = fingerprint(header)
        self._rows: dict[str, dict] = {}
        self.skipped_lines = 0       # corrupt lines skipped by the last open (review D11)
        if fresh and self.path.exists():
            self.path.unlink()
        if self.path.exists():
            self._load()
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._append({"header": header, "fingerprint": self.fp})

    def _load(self) -> None:
        """Read the file, skipping corrupt lines one by one (review D11).

        Before 2026-11-13 the first corrupt line ended the read and the file was truncated
        there, so valid rows written after it were lost and those units ran again. Now each
        corrupt or malformed line is skipped on its own, every later valid row is kept, and the
        number skipped is in :attr:`skipped_lines` (a warning is also logged). The file is then
        rewritten with only the valid lines, so the next open is clean. A corrupt header
        cannot be checked against the fingerprint, so the rows behind it cannot be trusted:
        the file is restarted, as before."""
        raw = self.path.read_bytes()
        lines = raw.split(NL)
        complete = lines[:-1]         # anything after the final newline is a partial write
        partial = bool(lines[-1].strip())
        kept: list[bytes] = []
        skipped = 0
        for i, line in enumerate(complete):
            try:
                obj = json.loads(line)
                if not isinstance(obj, dict):
                    raise ValueError("not a JSON object")
                if i > 0:
                    key, row = str(obj["key"]), obj["row"]
            except (ValueError, KeyError):
                if i == 0:
                    break             # no readable header: restart below
                skipped += 1
                continue
            if i == 0:
                if obj.get("fingerprint") != self.fp:
                    raise CheckpointMismatch(
                        f"{self.path} was written for different inputs "
                        f"(fingerprint {obj.get('fingerprint')!r} != {self.fp!r}); "
                        "rerun with --fresh or point --out elsewhere")
            else:
                self._rows[key] = row
            kept.append(line)
        self.skipped_lines = skipped
        if not kept:                  # not even a header survived
            self._rows.clear()
            self.path.unlink()
            self._append({"header": self.header, "fingerprint": self.fp})
            return
        if skipped:
            log.warning("%s: skipped %d corrupt line(s); kept %d row(s)", self.path, skipped, len(kept) - 1)
        if skipped or partial:
            tmp = self.path.with_name(self.path.name + ".tmp")
            with open(tmp, "wb") as f:
                f.write(b"".join(x + NL for x in kept))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)

    def _append(self, obj: dict) -> None:
        data = (json.dumps(obj, default=str) + "\n").encode("utf-8")
        with open(self.path, "ab") as f:  # one write call per line, then fsync
            f.write(data)
            f.flush()
            os.fsync(f.fileno())

    def done(self, key: str) -> bool:
        return key in self._rows

    def add(self, key: str, row: dict) -> None:
        line = {"key": key, "row": row}
        self._append(line)
        # keep exactly what a resumed run would read back (key order, JSON types)
        self._rows[key] = json.loads(json.dumps(line, default=str))["row"]

    def get(self, key: str) -> dict:
        return self._rows[key]

    def __len__(self) -> int:
        return len(self._rows)
