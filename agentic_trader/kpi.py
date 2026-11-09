"""KPI table for the model against its rules control (PLAN 6.4).

Plain idea: every desk decision can be logged with what the model said, what the rules
control said for the same name and date, what it cost, and what the price did next. From
those rows a reviewer wants five numbers: does the model call direction more often than the
rules (hit rate vs control), are its probabilities honest (Brier score and calibration bins),
what would trading only the difference have earned (model-delta book), what did each decision
cost, and the Sharpe of the model's book as one row among the others, not the headline.

Formal: a record is one JSON object per (as_of, symbol) with

- ``model_signal``: the model path's signed view in [-1, 1] (or a target weight);
- ``rule_signal``: the rules control's signed view for the same state (``AgentState.rule_signal``);
- ``outcome_return``: the realised forward return over the holding horizon;
- optional ``prob_up`` in [0, 1]: the model's probability that ``outcome_return > 0``;
- optional ``model_weight`` / ``control_weight``: book weights (default: the signals);
- optional ``cost_usd``: model spend for the decision (0 for rules or local models);
- optional ``agent_sources``: the per-decision source counts that ``evaluate()`` already keeps.

hit rate = share of records with a non-zero view whose sign matches the outcome's sign;
Brier = mean((prob_up - 1[outcome > 0])^2); the delta book's return on a date is
sum over names of (model_weight - control_weight) * outcome_return; Sharpe is annualised
with ``ppy`` periods per year on the per-date book returns.

Worked example: two records on one date, model +1 / rules -1 on a +2% outcome and model +1 /
rules +1 on a -1% outcome. Model hit rate 1/2, rules hit rate 0/2; the delta book is
(1 - (-1)) * 0.02 + 0 * (-0.01) = +0.04 on that date.

The library computes; it does not judge. A KPI table built from fixtures says nothing about
any model; P2 results feed the same function later.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class KPIRecord:
    as_of: str
    symbol: str
    model_signal: float
    rule_signal: float
    outcome_return: float
    prob_up: float | None = None
    model_weight: float | None = None
    control_weight: float | None = None
    cost_usd: float = 0.0
    agent_sources: dict[str, int] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "KPIRecord":
        missing = [k for k in ("as_of", "symbol", "model_signal", "rule_signal", "outcome_return")
                   if d.get(k) is None]
        if missing:
            raise ValueError(f"KPI record missing {missing}: {d}")
        p = d.get("prob_up")
        if p is not None and not 0.0 <= float(p) <= 1.0:
            raise ValueError(f"prob_up must lie in [0, 1], got {p}")
        return cls(
            as_of=str(d["as_of"]), symbol=str(d["symbol"]),
            model_signal=float(d["model_signal"]), rule_signal=float(d["rule_signal"]),
            outcome_return=float(d["outcome_return"]),
            prob_up=None if p is None else float(p),
            model_weight=None if d.get("model_weight") is None else float(d["model_weight"]),
            control_weight=None if d.get("control_weight") is None else float(d["control_weight"]),
            cost_usd=float(d.get("cost_usd") or 0.0),
            agent_sources={str(k): int(v) for k, v in (d.get("agent_sources") or {}).items()},
        )


def load_records(path: str | Path) -> list[KPIRecord]:
    """Read a JSONL file (one record per line; blank lines skipped)."""
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(KPIRecord.from_dict(json.loads(line)))
    return out


def _sign(x: float) -> int:
    return (x > 0) - (x < 0)


def hit_rate(views: Iterable[float], outcomes: Iterable[float]) -> tuple[float | None, int]:
    """Share of non-zero views whose sign matches a non-zero outcome; (rate, n used)."""
    pairs = [(_sign(v), _sign(o)) for v, o in zip(views, outcomes) if _sign(v) and _sign(o)]
    if not pairs:
        return None, 0
    return sum(a == b for a, b in pairs) / len(pairs), len(pairs)


def brier(probs: Iterable[float], outcomes: Iterable[float]) -> float | None:
    sq = [(p - (1.0 if o > 0 else 0.0)) ** 2 for p, o in zip(probs, outcomes)]
    return sum(sq) / len(sq) if sq else None


def calibration_bins(probs: list[float], outcomes: list[float], bins: int = 10) -> list[dict[str, Any]]:
    """Equal-width bins on [0, 1]: mean forecast, observed up-frequency, count (empty bins dropped)."""
    if bins < 1:
        raise ValueError("bins must be >= 1")
    acc: dict[int, list[tuple[float, float]]] = defaultdict(list)
    for p, o in zip(probs, outcomes):
        acc[min(int(p * bins), bins - 1)].append((p, 1.0 if o > 0 else 0.0))
    rows = []
    for b in sorted(acc):
        xs = acc[b]
        rows.append({"lo": b / bins, "hi": (b + 1) / bins, "n": len(xs),
                     "mean_prob": sum(p for p, _ in xs) / len(xs),
                     "freq_up": sum(y for _, y in xs) / len(xs)})
    return rows


def sharpe(returns: list[float], ppy: float = 252.0) -> float | None:
    if len(returns) < 2:
        return None
    m = sum(returns) / len(returns)
    var = sum((r - m) ** 2 for r in returns) / (len(returns) - 1)
    return None if var <= 0 else m / math.sqrt(var) * math.sqrt(ppy)


def _book(records: list[KPIRecord], weight) -> list[float]:
    by_date: dict[str, float] = defaultdict(float)
    for r in records:
        by_date[r.as_of] += weight(r) * r.outcome_return
    return [by_date[d] for d in sorted(by_date)]


def kpi_table(records: list[KPIRecord], *, bins: int = 10, ppy: float = 252.0) -> dict[str, Any]:
    """All KPIs in one dict; ``rows`` is the flat table the CLI prints."""
    if not records:
        raise ValueError("no KPI records")
    outs = [r.outcome_return for r in records]
    m_hit, m_n = hit_rate([r.model_signal for r in records], outs)
    c_hit, c_n = hit_rate([r.rule_signal for r in records], outs)
    prob = [r for r in records if r.prob_up is not None]
    probs = [r.prob_up for r in prob if r.prob_up is not None]
    pouts = [r.outcome_return for r in prob]

    def mw(r: KPIRecord) -> float:
        return r.model_signal if r.model_weight is None else r.model_weight

    def cw(r: KPIRecord) -> float:
        return r.rule_signal if r.control_weight is None else r.control_weight

    delta = _book(records, lambda r: mw(r) - cw(r))
    model_book = _book(records, mw)
    control_book = _book(records, cw)
    total_cost = sum(r.cost_usd for r in records)
    sources: dict[str, int] = defaultdict(int)
    for r in records:
        for k, v in r.agent_sources.items():
            sources[k] += v
    out: dict[str, Any] = {
        "n_records": len(records),
        "n_dates": len(delta),
        "hit_rate_model": m_hit, "hit_n_model": m_n,
        "hit_rate_control": c_hit, "hit_n_control": c_n,
        "hit_rate_delta": None if m_hit is None or c_hit is None else m_hit - c_hit,
        "brier": brier(probs, pouts), "brier_n": len(probs),
        "calibration": calibration_bins(probs, pouts, bins) if probs else [],
        "delta_book_total": sum(delta),
        "delta_book_mean": sum(delta) / len(delta),
        "delta_book_sharpe": sharpe(delta, ppy),
        "cost_total_usd": total_cost,
        "cost_per_decision_usd": total_cost / len(records),
        "sharpe_model": sharpe(model_book, ppy),
        "sharpe_control": sharpe(control_book, ppy),
        "agent_sources": dict(sources),
    }
    out["rows"] = [
        ("hit rate, model", out["hit_rate_model"], m_n),
        ("hit rate, rules control", out["hit_rate_control"], c_n),
        ("hit rate, model minus control", out["hit_rate_delta"], None),
        ("Brier score (model prob_up)", out["brier"], len(probs)),
        ("model-delta book, total return", out["delta_book_total"], len(delta)),
        ("model-delta book, Sharpe", out["delta_book_sharpe"], len(delta)),
        ("cost per decision, USD", out["cost_per_decision_usd"], len(records)),
        ("Sharpe, model book", out["sharpe_model"], len(model_book)),
        ("Sharpe, rules control book", out["sharpe_control"], len(control_book)),
    ]
    return out


def format_table(t: dict[str, Any]) -> str:
    def f(v: Any) -> str:
        return "n/a" if v is None else f"{v:.4f}"
    lines = ["| KPI | value | n |", "|---|---:|---:|"]
    lines += [f"| {name} | {f(v)} | {'' if n is None else n} |" for name, v, n in t["rows"]]
    if t["calibration"]:
        lines += ["", "| bin | n | mean prob | observed up |", "|---|---:|---:|---:|"]
        lines += [f"| [{b['lo']:.1f}, {b['hi']:.1f}) | {b['n']} | {b['mean_prob']:.3f} | "
                  f"{b['freq_up']:.3f} |" for b in t["calibration"]]
    return "\n".join(lines)
