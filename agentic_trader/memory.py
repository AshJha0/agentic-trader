"""Decision memory and reflection.

Every final decision is logged. Once its horizon has elapsed the realised
outcome is attached together with a short lesson, and later decisions on the
same instrument receive those lessons plus a hit-rate track record. Outcomes
are only resolved with prices available at the *current* as-of date, so a
backtest never sees the future through memory.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path


@dataclass
class MemoryEntry:
    symbol: str
    as_of: str
    action: str
    weight: float
    price: float
    horizon_days: int
    summary: str
    resolved_on: str | None = None
    exit_price: float | None = None
    pnl: float | None = None      # weight * price return over the horizon
    lesson: str | None = None


class DecisionMemory:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.entries: list[MemoryEntry] = []
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.entries.append(MemoryEntry(**json.loads(line)))

    def _save(self) -> None:
        if not self.path:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("".join(json.dumps(asdict(e)) + "\n" for e in self.entries),
                             encoding="utf-8")

    def record(self, symbol: str, as_of: date, action: str, weight: float, price: float,
               summary: str, horizon_days: int = 10) -> None:
        self.entries.append(MemoryEntry(symbol, as_of.isoformat(), action, weight, price,
                                        horizon_days, summary[:400]))
        self._save()

    def resolve(self, symbol: str, as_of: date, price: float) -> int:
        """Attach outcomes to entries whose horizon has passed by ``as_of``."""
        n = 0
        for e in self.entries:
            if e.symbol != symbol or e.resolved_on is not None:
                continue
            if (as_of - date.fromisoformat(e.as_of)).days < e.horizon_days:
                continue
            ret = price / e.price - 1.0
            e.resolved_on, e.exit_price, e.pnl = as_of.isoformat(), price, e.weight * ret
            if e.weight == 0:
                verdict = ("stayed flat while price moved "
                           f"{ret:+.1%}" + (" (missed opportunity)" if abs(ret) > 0.03 else ""))
            elif e.pnl > 0:
                verdict = f"was right: position {e.weight:+.2f} earned {e.pnl:+.2%}"
            else:
                verdict = f"was wrong: position {e.weight:+.2f} lost {e.pnl:+.2%}"
            e.lesson = (f"{e.as_of} {e.action} {symbol} at {e.price:.5g} {verdict} by "
                        f"{e.resolved_on}. Reasoning then: {e.summary[:160]}")
            n += 1
        if n:
            self._save()
        return n

    def lessons(self, symbol: str, as_of: date, k: int = 3) -> list[str]:
        done = [e for e in self.entries if e.symbol == symbol and e.lesson
                and e.resolved_on and date.fromisoformat(e.resolved_on) <= as_of]
        return [e.lesson for e in done[-k:]]

    def track_record(self, symbol: str, as_of: date, k: int = 20) -> dict[str, float]:
        done = [e for e in self.entries if e.symbol == symbol and e.pnl is not None
                and e.weight != 0 and date.fromisoformat(e.resolved_on) <= as_of][-k:]
        if not done:
            return {}
        return {"n": float(len(done)),
                "hit_rate": sum(e.pnl > 0 for e in done) / len(done),
                "avg_pnl": sum(e.pnl for e in done) / len(done)}
