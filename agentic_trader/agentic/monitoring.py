"""Model-output monitoring on stored decision rows (review C4 and C5).

Both functions read the JSON lines written by ``scripts/llm_study.py`` (and the paper runner
when it records model calls): one row per decision with ``cell``, ``seed``, ``symbol``,
``as_of``, ``target_weight``, ``close`` and ``calls`` (each call: ``status``, ``schema``,
``reply``). Nothing here calls a model.

**Drift (C4).** Plain idea: a model that starts refusing, parsing badly or pinning every signal
at +1 has changed, whatever the P&L says. Per day: decisions, model calls, rejection rate
(share of calls whose status is not ``ok``), signal mean / std / extreme share (``|s| >= 0.99``)
of the analyst replies, divergence rate (share of decisions whose target-weight sign differs
from the control cell on the same symbol, date and seed), and the population stability index
(PSI) of the day's signals against a baseline (the first ``baseline_days`` days, or a given
list). A day breaching a threshold produces an alert record; ``append_alerts`` writes them as
JSON lines. Thresholds are conventions, not fitted: PSI 0.25 is the usual "significant shift"
line in credit-model monitoring; the others are set at levels that would already be a desk
incident. Evidence class: method plus fixture tests; no live model rows at v0.17.

**Calibration (C5).** Plain idea: when the analyst says confidence 0.8, is its direction right
about 80% of the time? For each analyst reply with a non-zero signal, the outcome is 1 when
``sign(signal)`` equals the sign of the forward return, else 0. Formal: Brier score
``mean((confidence - outcome)^2)`` and a reliability table (bins of confidence: mean
confidence vs hit rate, count) with the expected calibration error. The forward return is
``fwd_return`` on the row when present (e.g. a 20-day return), else the close-to-close return
to the same symbol's next row in that cell and seed. Worked example: replies (0.9, right),
(0.9, wrong) give Brier (0.01 + 0.81) / 2 = 0.41 and a 0.9 bin with hit rate 0.5.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

DEFAULT_THRESHOLDS = {"rejection_rate": 0.10, "divergence_rate": 0.50, "psi": 0.25, "extreme_share": 0.50}
_EDGES = [-1.0001, -0.6, -0.2, 0.2, 0.6, 1.0001]


def _reply_json(reply: Any) -> dict[str, Any] | None:
    if isinstance(reply, dict):
        return reply
    if not isinstance(reply, str):
        return None
    from ..llm import extract_json

    return extract_json(reply)


def analyst_outputs(row: dict[str, Any]) -> list[tuple[float, float | None]]:
    """(signal, confidence) of every ok schema call in the row whose reply carries a signal."""
    out = []
    for c in row.get("calls") or []:
        if c.get("status") != "ok":
            continue
        d = _reply_json(c.get("reply"))
        if not d or "signal" not in d:
            continue
        try:
            s = float(d["signal"])
        except (TypeError, ValueError):
            continue
        conf = d.get("confidence")
        try:
            cf = float(conf) if conf is not None else None
        except (TypeError, ValueError):
            cf = None
        if math.isfinite(s):
            out.append((max(-1.0, min(1.0, s)), cf if cf is not None and math.isfinite(cf) else None))
    return out


def _psi(base: list[float], cur: list[float]) -> float:
    def hist(xs: list[float]) -> list[float]:
        n = [0] * (len(_EDGES) - 1)
        for x in xs:
            for i in range(len(n)):
                if _EDGES[i] <= x < _EDGES[i + 1]:
                    n[i] += 1
                    break
        tot = max(1, len(xs))
        return [max(k / tot, 1e-4) for k in n]

    b, c = hist(base), hist(cur)
    return float(sum((ci - bi) * math.log(ci / bi) for bi, ci in zip(b, c)))


def _sign(x: float) -> int:
    return (x > 1e-12) - (x < -1e-12)


def daily_drift(
    rows: Iterable[dict[str, Any]],
    cell: str,
    control_cell: str | None = None,
    baseline_days: int = 5,
    baseline_signals: list[float] | None = None,
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Per-day output statistics for ``cell`` and the alerts they raise."""
    th = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    rows = list(rows)
    control = {
        (r["symbol"], r["as_of"], int(r.get("seed", 0))): float(r["target_weight"])
        for r in rows
        if control_cell is not None and r.get("cell") == control_cell
    }
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        if r.get("cell") == cell:
            by_day[str(r["as_of"])].append(r)
    days = sorted(by_day)
    sigs = {d: [s for r in by_day[d] for s, _ in analyst_outputs(r)] for d in days}
    base = list(baseline_signals) if baseline_signals is not None else [s for d in days[:baseline_days] for s in sigs[d]]
    stats, alerts = [], []
    for i, d in enumerate(days):
        rs = by_day[d]
        calls = [c for r in rs for c in (r.get("calls") or [])]
        rej = sum(c.get("status") != "ok" for c in calls) / len(calls) if calls else None
        s = sigs[d]
        mean = sum(s) / len(s) if s else None
        std = math.sqrt(sum((x - mean) ** 2 for x in s) / (len(s) - 1)) if mean is not None and len(s) > 1 else None
        ext = sum(abs(x) >= 0.99 for x in s) / len(s) if s else None
        pairs = [
            (float(r["target_weight"]), control[k])
            for r in rs
            if (k := (r["symbol"], r["as_of"], int(r.get("seed", 0)))) in control
        ]
        div = sum(_sign(a) != _sign(b) for a, b in pairs) / len(pairs) if pairs else None
        in_base = baseline_signals is None and i < baseline_days
        psi = _psi(base, s) if s and base and not in_base else None
        st: dict[str, Any] = {
            "day": d,
            "decisions": len(rs),
            "calls": len(calls),
            "rejection_rate": rej,
            "signal_mean": mean,
            "signal_std": std,
            "extreme_share": ext,
            "divergence_rate": div,
            "psi": psi,
        }
        stats.append(st)
        for m, lim in th.items():
            v = st.get(m)
            if v is not None and v > lim:
                alerts.append(
                    {
                        "kind": "model_output_drift",
                        "cell": cell,
                        "day": d,
                        "metric": m,
                        "value": round(float(v), 6),
                        "threshold": lim,
                    }
                )
    return {"cell": cell, "control_cell": control_cell, "thresholds": th, "days": stats, "alerts": alerts}


def append_alerts(path: str | Path, alerts: list[dict[str, Any]]) -> int:
    """Append alert records as JSON lines; returns how many were written."""
    if not alerts:
        return 0
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for a in alerts:
            fh.write(json.dumps(a, sort_keys=True) + "\n")
    return len(alerts)


def confidence_calibration(rows: Iterable[dict[str, Any]], cell: str | None = None, bins: int = 5) -> dict[str, Any]:
    """Brier score and reliability table of analyst ``confidence`` vs realised direction."""
    rows = [r for r in rows if cell is None or r.get("cell") == cell]
    series: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        series[(r.get("cell"), int(r.get("seed", 0)), r["symbol"])].append(r)
    pairs: list[tuple[float, int]] = []
    for rs in series.values():
        rs.sort(key=lambda r: str(r["as_of"]))
        for j, r in enumerate(rs):
            fwd = r.get("fwd_return")
            if fwd is None and j + 1 < len(rs) and r.get("close") and rs[j + 1].get("close"):
                fwd = float(rs[j + 1]["close"]) / float(r["close"]) - 1.0
            if fwd is None or not math.isfinite(float(fwd)) or _sign(float(fwd)) == 0:
                continue
            for s, cf in analyst_outputs(r):
                if cf is None or _sign(s) == 0:
                    continue
                pairs.append((max(0.0, min(1.0, cf)), int(_sign(s) == _sign(float(fwd)))))
    n = len(pairs)
    if n == 0:
        return {"n": 0, "brier": None, "ece": None, "hit_rate": None, "bins": []}
    brier = sum((c - o) ** 2 for c, o in pairs) / n
    table, ece = [], 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        sel = [(c, o) for c, o in pairs if lo <= c < hi or (b == bins - 1 and c == 1.0)]
        if not sel:
            continue
        mc, hr = sum(c for c, _ in sel) / len(sel), sum(o for _, o in sel) / len(sel)
        ece += len(sel) / n * abs(mc - hr)
        table.append({"lo": lo, "hi": hi, "n": len(sel), "mean_confidence": mc, "hit_rate": hr})
    return {"n": n, "brier": brier, "ece": ece, "hit_rate": sum(o for _, o in pairs) / n, "bins": table}
