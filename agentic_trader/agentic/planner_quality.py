"""Planner quality beyond validator survival (review B7).

Survival (``governance.planner_survival``) counts how many proposed steps the validator kept.
It says nothing about whether the plan was a good one: a validator that repairs everything
makes any plan "survive". This module compares a model plan with the canonical plan for the
same task, before any repair:

* **step-set precision** -- share of the model's distinct (type, name) steps that the canonical
  plan also has; **recall** -- share of the canonical steps the model proposed; F1 of the two;
* **order agreement** -- over pairs of steps both plans contain, the share ordered the same
  way (1.0 = same order, 0.5 = unrelated, 0.0 = reversed); ``None`` when fewer than two
  common steps;
* **zero repair** -- the validator returned the proposed steps unchanged (same names, same
  order, no notes);
* **exact canonical** -- the proposed step names equal the canonical ones in order.

Governance steps (critic, validate, finalise) are excluded on both sides: the model is never
asked for them and the validator always appends them. Pure functions, no model.
"""

from __future__ import annotations

from typing import Any, Iterable

_GOV = {"critic", "validate", "validate_evidence", "finalise"}


def _keys(steps: Iterable[Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for s in steps:
        if isinstance(s, dict):
            t, n = str(s.get("type", "")).lower(), str(s.get("name", "")).strip()
        else:  # PlanStep
            t, n = s.type.value, s.name
        if t in {"tool", "agent"} and n not in _GOV:
            out.append((t, n))
    return out


def order_agreement(a: list[tuple[str, str]], b: list[tuple[str, str]]) -> float | None:
    """Share of concordant pairs among steps present in both sequences (first occurrence)."""
    pos_a = {k: i for i, k in reversed(list(enumerate(a)))}
    pos_b = {k: i for i, k in reversed(list(enumerate(b)))}
    common = [k for k in pos_a if k in pos_b]
    pairs = conc = 0
    for i in range(len(common)):
        for j in range(i + 1, len(common)):
            x, y = common[i], common[j]
            pairs += 1
            conc += (pos_a[x] < pos_a[y]) == (pos_b[x] < pos_b[y])
    return conc / pairs if pairs else None


def plan_quality(raw_steps: list[Any] | None, canonical_steps: Iterable[Any], validated: Any | None = None) -> dict[str, Any]:
    """Quality of one raw model plan against the canonical plan. ``validated`` is the
    ``Plan`` returned by ``validate_plan`` for ``raw_steps`` (for the zero-repair flag)."""
    canon = _keys(canonical_steps)
    if raw_steps is None:
        return {
            "usable": False,
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "order": None,
            "zero_repair": False,
            "exact_canonical": False,
            "n_proposed": 0,
            "n_canonical": len(canon),
        }
    prop = _keys(raw_steps)
    ps, cs = set(prop), set(canon)
    inter = len(ps & cs)
    precision = inter / len(ps) if ps else 0.0
    recall = inter / len(cs) if cs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    zero = False
    if validated is not None:
        zero = _keys(validated.steps) == prop and not tuple(getattr(validated, "notes", ()) or ())
    return {
        "usable": True,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "order": order_agreement(prop, canon),
        "zero_repair": zero,
        "exact_canonical": prop == canon,
        "n_proposed": len(prop),
        "n_canonical": len(canon),
    }


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Means over plans; usable-only means for precision/recall/order as well as all-plan."""
    n = len(rows)
    use = [r for r in rows if r["usable"]]
    ords = [r["order"] for r in use if r["order"] is not None]

    def mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else float("nan")

    return {
        "plans": n,
        "usable": len(use),
        "precision_mean": mean([r["precision"] for r in use]),
        "recall_mean": mean([r["recall"] for r in use]),
        "f1_mean": mean([r["f1"] for r in use]),
        "f1_mean_all_plans": mean([r["f1"] for r in rows]),
        "order_agreement_mean": mean(ords),
        "zero_repair_share": sum(r["zero_repair"] for r in rows) / n if n else float("nan"),
        "exact_canonical_share": sum(r["exact_canonical"] for r in rows) / n if n else float("nan"),
    }
