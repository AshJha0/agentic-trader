"""Outcome-aware governance (plan items 4.1-4.3).

* :func:`join_outcomes` joins each recorded ``TaskRun`` (the dict the task store keeps) to the
  realised P&L ``DecisionMemory`` settled for the same symbol, decision day and provider.
* :func:`governance_report` turns the joined rows into per-role hit rates, the correlation
  between each critic check failing and the decision losing money, and each check's
  false-positive rate (flagged, yet the decision made money). :func:`weekly_rollup` groups the
  same numbers by ISO week. Every figure carries its sample size; nothing is reported for a
  cell with no observations.
* :func:`planner_survival` measures how much of a plan survives the validator.
* :class:`MemoryTool` is the governed, fenced, append-only tool surface over decision memory.

Hit rate counts only resolved, non-flat decisions (``weight != 0`` and ``pnl`` set): a flat
decision has no sign to be right about and an expired entry has no verdict.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable

from ..memory import DecisionMemory, MemoryEntry
from ..state import untrusted_block

# --------------------------------------------------------------------------- 4.1 join


@dataclass
class OutcomeRow:
    task_id: str
    symbol: str
    as_of: str
    role: str
    weight: float | None
    pnl: float | None          # realised, from DecisionMemory; None while unresolved / expired
    resolved: bool
    expired: bool
    failed_checks: tuple[str, ...] = ()
    critic_passed: bool | None = None

    @property
    def scored(self) -> bool:
        return self.pnl is not None and bool(self.weight)

    @property
    def hit(self) -> bool:
        return bool(self.pnl is not None and self.pnl > 0)


def _memory_index(memory: DecisionMemory | Iterable[MemoryEntry]) -> dict[tuple[str, str], list[MemoryEntry]]:
    entries = memory.entries if isinstance(memory, DecisionMemory) else list(memory)
    idx: dict[tuple[str, str], list[MemoryEntry]] = defaultdict(list)
    for e in entries:
        idx[(e.symbol.upper(), e.as_of)].append(e)
    return idx


def join_outcomes(records: Iterable[dict[str, Any]], memory: DecisionMemory | Iterable[MemoryEntry],
                  provider: str | None = None) -> list[OutcomeRow]:
    """One row per finished run with a decision. ``provider`` restricts the memory side (a
    synthetic session's outcome is not a live run's); with several matching entries the
    resolved one wins."""
    idx = _memory_index(memory)
    rows: list[OutcomeRow] = []
    for r in records:
        dec = r.get("decision")
        if not dec:
            continue
        sym = str(r.get("symbol", dec.get("symbol", ""))).upper()
        as_of = str(r.get("as_of", dec.get("as_of", "")))
        cands = [e for e in idx.get((sym, as_of), []) if provider is None or e.provider == provider]
        e = next((c for c in cands if c.pnl is not None), cands[0] if cands else None)
        critic = r.get("critic") or {}
        failed = tuple(sorted({c["name"] for c in critic.get("checks", []) if not c.get("passed", True)}))
        rows.append(OutcomeRow(
            task_id=str(r.get("task_id", "")), symbol=sym, as_of=as_of, role=str(r.get("role", "")),
            weight=(e.weight if e is not None else dec.get("target_weight")),
            pnl=e.pnl if e is not None else None,
            resolved=bool(e is not None and e.resolved_on is not None and not e.expired),
            expired=bool(e is not None and e.expired), failed_checks=failed,
            critic_passed=critic.get("passed") if critic else None))
    return rows


def _rate(k: int, n: int) -> float | None:
    return k / n if n else None


def _phi(flag: list[bool], loss: list[bool]) -> float | None:
    """Pearson correlation of two binary series (the phi coefficient); None when either
    series is constant or empty."""
    n = len(flag)
    if n == 0:
        return None
    a = sum(f and l for f, l in zip(flag, loss))
    b = sum(f and not l for f, l in zip(flag, loss))
    c = sum((not f) and l for f, l in zip(flag, loss))
    d = n - a - b - c
    den = math.sqrt((a + b) * (c + d) * (a + c) * (b + d))
    return (a * d - b * c) / den if den else None


def governance_report(rows: list[OutcomeRow], checks: Iterable[str] | None = None) -> dict[str, Any]:
    scored = [r for r in rows if r.scored]
    by_role: dict[str, dict[str, Any]] = {}
    for role in sorted({r.role for r in rows}):
        rs = [r for r in scored if r.role == role]
        hits = sum(r.hit for r in rs)
        by_role[role] = {"runs": sum(r.role == role for r in rows), "scored": len(rs), "hits": hits,
                         "hit_rate": _rate(hits, len(rs)),
                         "avg_pnl": (sum(r.pnl for r in rs) / len(rs)) if rs else None}  # type: ignore[misc]
    names = sorted(set(checks or ()) | {c for r in rows for c in r.failed_checks})
    by_check: dict[str, dict[str, Any]] = {}
    for name in names:
        flag = [name in r.failed_checks for r in scored]
        loss = [not r.hit for r in scored]
        flagged = sum(flag)
        fp = sum(f and not l for f, l in zip(flag, loss))
        by_check[name] = {"flagged_runs": sum(name in r.failed_checks for r in rows),
                          "flagged_scored": flagged, "false_positives": fp,
                          "false_positive_rate": _rate(fp, flagged),
                          "flag_loss_phi": _phi(flag, loss), "n_scored": len(scored)}
    return {"runs": len(rows), "resolved": sum(r.resolved for r in rows),
            "expired": sum(r.expired for r in rows), "unresolved": sum(r.pnl is None and not r.expired for r in rows),
            "scored": len(scored), "by_role": by_role, "by_check": by_check}


def iso_week(day: str) -> str:
    y, w, _ = date.fromisoformat(day).isocalendar()
    return f"{y}-W{w:02d}"


def weekly_rollup(rows: list[OutcomeRow]) -> list[dict[str, Any]]:
    weeks: dict[str, list[OutcomeRow]] = defaultdict(list)
    for r in rows:
        weeks[iso_week(r.as_of)].append(r)
    out = []
    for wk in sorted(weeks):
        rs = weeks[wk]
        sc = [r for r in rs if r.scored]
        hits = sum(r.hit for r in sc)
        out.append({"week": wk, "runs": len(rs), "scored": len(sc), "hits": hits, "hit_rate": _rate(hits, len(sc)),
                    "pnl_sum": sum(r.pnl for r in sc) if sc else None,  # type: ignore[misc]
                    "critic_flagged": sum(bool(r.failed_checks) for r in rs)})
    return out


def _fmt(x: Any, pct: bool = False) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, float):
        return f"{x:.1%}" if pct else f"{x:+.4f}"
    return str(x)


def render_report(rep: dict[str, Any], weeks: list[dict[str, Any]]) -> str:
    lines = [f"Runs with a decision: {rep['runs']} (resolved {rep['resolved']}, expired {rep['expired']}, "
             f"unresolved {rep['unresolved']}; scored non-flat {rep['scored']})", "",
             "| Role | Runs | Scored | Hits | Hit rate | Avg P&L |", "|---|---|---|---|---|---|"]
    for role, v in rep["by_role"].items():
        lines.append(f"| {role} | {v['runs']} | {v['scored']} | {v['hits']} | {_fmt(v['hit_rate'], True)} "
                     f"| {_fmt(v['avg_pnl'])} |")
    lines += ["", "| Critic check | Flagged (all) | Flagged (scored) | False positives | FP rate | phi(flag, loss) |",
              "|---|---|---|---|---|---|"]
    for name, v in rep["by_check"].items():
        lines.append(f"| {name} | {v['flagged_runs']} | {v['flagged_scored']} | {v['false_positives']} "
                     f"| {_fmt(v['false_positive_rate'], True)} | {_fmt(v['flag_loss_phi'])} |")
    lines += ["", "| Week | Runs | Scored | Hits | Hit rate | P&L sum | Critic flagged |", "|---|---|---|---|---|---|---|"]
    for w in weeks:
        lines.append(f"| {w['week']} | {w['runs']} | {w['scored']} | {w['hits']} | {_fmt(w['hit_rate'], True)} "
                     f"| {_fmt(w['pnl_sum'])} | {w['critic_flagged']} |")
    return "\n".join(lines)


# --------------------------------------------------------------------------- 4.2 survival


def planner_survival(raw_steps: list[Any] | None, plan: Any) -> dict[str, Any]:
    """How a raw plan fared through ``validate_plan``. ``raw_steps`` None means the model
    reply was unusable (the canonical fallback ran). Survival counts proposed tool/agent
    steps that appear (by type and name) in the validated plan; additions are validated
    non-governance steps that were not proposed; budget hits are data-budget drops."""
    from .domain import GOVERNANCE_STEPS
    gov = {t.value for t in GOVERNANCE_STEPS} | {"critic", "validate", "finalise"}
    final = [(s.type.value, s.name) for s in plan.steps if s.type.value not in gov]
    if raw_steps is None:
        return {"proposed": 0, "survived": 0, "added": len(final), "budget_hits": 0, "unusable": True,
                "repaired": True}
    proposed = [(str(r.get("type", "")).lower(), str(r.get("name", "")).strip()) for r in raw_steps
                if isinstance(r, dict) and str(r.get("type", "")).lower() in {"tool", "agent"}]
    remaining = list(final)
    survived = 0
    for p in proposed:
        if p in remaining:
            remaining.remove(p)
            survived += 1
    proposed_set = set(proposed)
    added = sum(1 for f in final if f not in proposed_set)
    budget = sum("max_plan_lookback_bars" in n for n in plan.notes)
    return {"proposed": len(raw_steps), "survived": survived, "added": added, "budget_hits": budget,
            "unusable": False, "repaired": bool(plan.notes)}


def survival_table(results: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for source, rs in results.items():
        prop = sum(r["proposed"] for r in rs)
        surv = sum(r["survived"] for r in rs)
        rows.append({"source": source, "tasks": len(rs), "steps_proposed": prop, "steps_survived": surv,
                     "step_survival": _rate(surv, prop), "steps_added": sum(r["added"] for r in rs),
                     "plans_repaired": sum(r["repaired"] for r in rs),
                     "plans_unusable": sum(r["unusable"] for r in rs),
                     "budget_hits": sum(r["budget_hits"] for r in rs),
                     "plans_with_budget_hit": sum(r["budget_hits"] > 0 for r in rs)})
    return rows


# --------------------------------------------------------------------------- 4.3 memory tool


class MemoryToolError(PermissionError):
    pass


@dataclass
class MemoryTool:
    """Governed tool backend over :class:`DecisionMemory`.

    * reads return lessons resolved on or before the task's ``as_of`` only (no look-ahead),
      always inside an ``untrusted_block`` (the lessons quote earlier model-written reasoning);
    * writes are append-only: ``remember`` records a new decision and refuses a key already
      present (``DecisionMemory.record`` would replace it); there is no update or delete;
    * symbols must be in ``universe`` (when given), the write date must equal the bound
      ``as_of``, summaries are clipped, and each run has a write budget;
    * every call, allowed or refused, is appended to ``audit``.
    """
    memory: DecisionMemory
    as_of: date
    provider: str = ""
    universe: tuple[str, ...] | None = None
    max_writes: int = 5
    max_summary_chars: int = 400
    audit: list[dict[str, Any]] = field(default_factory=list)
    _writes: int = 0

    def _check_symbol(self, symbol: str) -> str:
        sym = str(symbol).strip().upper()
        if not sym or (self.universe is not None and sym not in {u.upper() for u in self.universe}):
            raise MemoryToolError(f"symbol {sym!r} outside the configured universe")
        return sym

    def _log(self, op: str, ok: bool, detail: str) -> None:
        self.audit.append({"op": op, "allowed": ok, "detail": detail, "as_of": self.as_of.isoformat()})

    def recall(self, symbol: str, k: int = 3) -> str:
        try:
            sym = self._check_symbol(symbol)
        except MemoryToolError as e:
            self._log("recall", False, str(e))
            raise
        k = max(0, min(int(k), 10))
        lessons = self.memory.lessons(sym, self.as_of, k=k, provider=self.provider or None)
        rec = self.memory.track_record(sym, self.as_of, provider=self.provider or None)
        self._log("recall", True, f"{sym}: {len(lessons)} lessons")
        head = (f"track record {sym}: n={int(rec['n'])}, hit rate {rec['hit_rate']:.0%}" if rec
                else f"track record {sym}: none resolved by {self.as_of.isoformat()}")
        return head + "\n" + untrusted_block("decision memory (earlier model-written reasoning)", lessons)

    def remember(self, symbol: str, action: str, weight: float, price: float, summary: str,
                 horizon_days: int = 10, as_of: date | None = None, price_basis: str = "") -> str:
        try:
            sym = self._check_symbol(symbol)
            day = as_of or self.as_of
            if day != self.as_of:
                raise MemoryToolError(f"write dated {day} but the task is bound to {self.as_of}")
            if self._writes >= self.max_writes:
                raise MemoryToolError(f"write budget of {self.max_writes} per run spent")
            for v, nm in ((weight, "weight"), (price, "price")):
                if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
                    raise MemoryToolError(f"{nm} must be a finite number")
            if price <= 0 or not 1 <= int(horizon_days) <= 260:
                raise MemoryToolError("price must be positive and horizon_days in 1..260")
            key = f"{sym}|{day.isoformat()}|{self.provider}"
            self.memory._catch_up()
            if key in self.memory._by_key:
                raise MemoryToolError(f"{key} already recorded; memory is append-only")
        except MemoryToolError as e:
            self._log("remember", False, str(e))
            raise
        self.memory.record(sym, day, str(action)[:16], float(weight), float(price),
                           str(summary)[:self.max_summary_chars], horizon_days=int(horizon_days),
                           provider=self.provider, price_basis=price_basis)
        self._writes += 1
        self._log("remember", True, key)
        return key
