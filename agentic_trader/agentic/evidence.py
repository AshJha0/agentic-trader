"""Evidence store: every record an agent may cite, resolvable by id.

The store is append-only. ``resolve`` answers "does this id exist and does its
digest still match its payload", which is what the validator and the reporter's
audit need. It is thread-safe so parallel steps can add evidence.
"""
from __future__ import annotations

import threading
from typing import Any, Iterable

from .domain import Evidence, EvidenceType, digest


class EvidenceStore:
    def __init__(self) -> None:
        self._items: dict[str, Evidence] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()

    def add(self, ev: Evidence) -> Evidence:
        with self._lock:
            if ev.id in self._items:
                raise ValueError(f"duplicate evidence id {ev.id}")
            self._items[ev.id] = ev
            self._order.append(ev.id)
        return ev

    def record(self, type_: EvidenceType, source: str, summary: str, payload: Any,
               correlation_id: str, arguments: dict[str, Any] | None = None) -> Evidence:
        return self.add(Evidence.build(type_, source, summary, payload, correlation_id, arguments))

    def get(self, ev_id: str) -> Evidence | None:
        return self._items.get(ev_id)

    def resolve(self, ev_id: str) -> bool:
        """True when the id exists and the stored payload still hashes to its digest."""
        ev = self._items.get(ev_id)
        return ev is not None and digest(ev.payload) == ev.digest

    def unresolved(self, ids: Iterable[str]) -> list[str]:
        return [i for i in ids if not self.resolve(i)]

    def by_type(self, type_: EvidenceType) -> list[Evidence]:
        return [self._items[i] for i in self._order if self._items[i].type is type_]

    def by_source(self, source: str) -> list[Evidence]:
        return [self._items[i] for i in self._order if self._items[i].source == source]

    def ids_since(self, n: int) -> list[str]:
        """Ids of everything added after the first ``n`` records (for attribution)."""
        return list(self._order[n:])

    def __len__(self) -> int:
        return len(self._order)

    def __iter__(self):
        return (self._items[i] for i in list(self._order))

    def summary_rows(self) -> list[dict[str, Any]]:
        return [{"id": e.id, "type": e.type.value, "source": e.source, "summary": e.summary,
                 "digest": e.digest[:12], "correlation_id": e.correlation_id,
                 "created_at": e.created_at.isoformat()} for e in self]
