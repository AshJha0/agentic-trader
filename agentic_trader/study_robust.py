"""Keep long study runs alive across transient data-provider misses (v0.19 lane B).

A provider miss (``ValueError("no Yahoo data for GOOGL between ...")``) on one item used to
abort a multi-hour run. ``retry_provider`` retries the item a few times; if it still fails the
caller records a *skipped* row with the reason, and the pre-registered summary reports the
skip count and the skipped ids. Nothing is dropped silently, and a skipped item is retried
on the next resume (it is not counted as done).
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

PROVIDER_TRIES = 3
PROVIDER_DELAY_S = 5.0


class ProviderMiss(Exception):
    """The data provider failed for one item on every try; ``reason`` is the last error."""

    def __init__(self, reason: str, tries: int):
        super().__init__(reason)
        self.reason, self.tries = reason, tries


def retry_provider(
    fn: Callable[[], T],
    *,
    label: str = "",
    tries: int = PROVIDER_TRIES,
    delay_s: float = PROVIDER_DELAY_S,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """``fn()``, retried on ``ValueError`` (the provider's "no data" signal) up to ``tries``
    times with ``delay_s`` between tries; raises ``ProviderMiss`` when every try failed.
    Other exceptions propagate at once (they are bugs or a dead model server, not a miss)."""
    if tries < 1:
        raise ValueError("tries must be >= 1")
    last: ValueError | None = None
    for attempt in range(1, tries + 1):
        try:
            return fn()
        except ValueError as e:
            last = e
            log.warning("provider miss for %s (try %d/%d): %s", label or "item", attempt, tries, e)
            if attempt < tries:
                sleep(delay_s)
    raise ProviderMiss(str(last), tries)


def skip_row(row_id: str, reason: str, tries: int, **extra: object) -> dict[str, object]:
    """The checkpoint row recorded for an item skipped after ``tries`` provider misses."""
    return {"id": row_id, "skipped": True, "skip_reason": reason, "skip_tries": tries, **extra}
