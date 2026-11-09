"""Deferred tool loading behind a tool-search tool (plan item 4.6).

A client that sees every tool's description and schema up front pays for all of them in its
context, and a large catalogue makes the wrong tool easier to pick. With deferral only the
tool **names** are visible; a client calls the search tool with a query, gets the full
descriptors of the best matches, and only those become callable. Policy, approval and
evidence are unchanged: a loaded tool still runs through the governed executor.

Ranking is plain and deterministic: query terms are matched against each tool's name, server
and description (name hits weigh 3, server 2, description 1); ties break on the name. An exact
tool name always ranks first. No model and no embedding is involved.
"""
from __future__ import annotations

import re
import threading
from typing import Any

from .tools import ToolRegistry

_TERM = re.compile(r"[a-z0-9]+")


def _terms(text: str) -> list[str]:
    return _TERM.findall(text.lower())


class DeferredToolCatalog:
    """Names visible, descriptors on search. ``loaded`` is the set a caller may invoke."""

    def __init__(self, registry: ToolRegistry, preloaded: tuple[str, ...] = ()) -> None:
        self.registry = registry
        self._lock = threading.Lock()
        self._loaded: set[str] = set()
        for name in preloaded:
            self.registry.get(name)        # KeyError for an unknown tool
            self._loaded.add(name)

    def names(self) -> list[str]:
        return sorted(d.name for d in self.registry.descriptors())

    @property
    def loaded(self) -> set[str]:
        with self._lock:
            return set(self._loaded)

    def is_loaded(self, name: str) -> bool:
        with self._lock:
            return name in self._loaded

    def _entry(self, name: str) -> dict[str, Any]:
        return next(e for e in self.registry.catalogue() if e["name"] == name)

    def search(self, query: str, limit: int = 5, load: bool = True) -> list[dict[str, Any]]:
        """Full descriptors of the best ``limit`` matches; they are loaded unless ``load`` is False."""
        limit = max(1, min(int(limit), 20))
        q = query.strip()
        terms = set(_terms(q))
        scored = []
        for d in self.registry.descriptors():
            if q == d.name or q.replace("__", ".") == d.name:
                scored.append((1e9, d.name))
                continue
            name_t, server_t, desc_t = set(_terms(d.name)), set(_terms(d.server)), set(_terms(d.description))
            s = sum(3 * (t in name_t) + 2 * (t in server_t) + (t in desc_t) for t in terms)
            if s > 0:
                scored.append((s, d.name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        hits = [n for _, n in scored[:limit]]
        if load:
            with self._lock:
                self._loaded.update(hits)
        return [self._entry(n) for n in hits]

    def load(self, name: str) -> dict[str, Any]:
        self.registry.get(name)
        with self._lock:
            self._loaded.add(name)
        return self._entry(name)

    def require_loaded(self, name: str) -> None:
        if name not in self.registry:
            raise KeyError(f"unknown tool {name!r}")
        if not self.is_loaded(name):
            raise PermissionError(f"tool {name} is deferred: call tool_search first")


def _chars_tokens(text: str) -> int:
    """Deterministic token estimate: ceil(chars / 4), no request overhead or margin, so the
    ratio between two payloads is not flattered by a fixed constant."""
    return -(-len(text) // 4)


def token_saving(registry: ToolRegistry, queries: tuple[str, ...] = ("price history", "submit order"),
                 limit: int = 5) -> dict[str, Any]:
    """Measured context cost of up-front vs deferred tool listing on ``registry``.

    ``full`` is the JSON of every descriptor (what an eager client holds); ``deferred`` is the
    names list plus the descriptors a client loads after one search per query (top ``limit``
    each, deduplicated). Same estimator on both sides: ``ceil(chars / 4)``.
    """
    import json
    full = _chars_tokens(json.dumps(registry.catalogue(), sort_keys=True))
    cat = DeferredToolCatalog(registry)
    names = _chars_tokens(json.dumps(cat.names()))
    loaded: dict[str, dict[str, Any]] = {}
    for q in queries:
        for e in cat.search(q, limit, load=False):
            loaded[e["name"]] = e
    after = names + _chars_tokens(json.dumps(sorted(loaded.values(), key=lambda e: e["name"]), sort_keys=True))
    return {"tools": len(registry), "full_tokens": full, "names_tokens": names,
            "deferred_tokens_after_search": after, "loaded_tools": len(loaded),
            "saving_tokens": full - after, "saving_share": (full - after) / full if full else 0.0}
