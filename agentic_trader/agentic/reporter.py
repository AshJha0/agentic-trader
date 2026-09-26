"""Audited reports.

The reporter builds a structured report from the task's state and findings,
then a narrative (a deterministic template, or a model given only the
structured facts). Afterwards two audits run:

* **number audit** - every number in the narrative must match a value in the
  structured facts, tolerant of rounding, sign and percentage forms;
* **evidence audit** - every evidence id mentioned in the narrative or cited by
  a finding must resolve in the store.

Discrepancies are attached as warnings, never silently accepted, and the
markdown rendering lists them.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..llm import LLM
from ..state import TradingState
from .critic import CriticReport
from .domain import Finding, Task
from .evidence import EvidenceStore

_NUMBER = re.compile(r"(?<![A-Za-z0-9_\-])[+-]?\d+(?:[.,]\d+)?%?")
_EVIDENCE_ID = re.compile(r"\b(?:DATA|CALC|DOC|MODEL|DEC|APPR)-[0-9a-f]{8}\b")
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


@dataclass
class Report:
    task_id: str
    symbol: str
    as_of: str
    facts: dict[str, float]                 # every figure the narrative may use
    sections: dict[str, Any]
    narrative: str
    warnings: list[str] = field(default_factory=list)
    narrative_source: str = "template"

    def to_dict(self) -> dict[str, Any]:
        return {"task_id": self.task_id, "symbol": self.symbol, "as_of": self.as_of, "facts": self.facts,
                "sections": self.sections, "narrative": self.narrative, "warnings": self.warnings,
                "narrative_source": self.narrative_source}

    def to_markdown(self) -> str:
        s = self.sections
        out = [f"# {self.symbol} decision — {self.as_of}", "", "## Executive summary", self.narrative, ""]
        out.append("## Decision")
        d = s["decision"]
        out.append(f"**{d['action']}** target weight {d['target_weight']:+.2f} (confidence "
                   f"{d['confidence']:.2f}, critic multiplier {d['critic_multiplier']:.2f}); "
                   f"stop {d['stop_loss']}, target {d['take_profit']}")
        out.extend(f"- adjustment: {a}" for a in d["adjustments"])
        out.append("")
        out.append("## Findings")
        for f in s["findings"]:
            out.append(f"- **{f['agent']}** ({f['confidence']:.2f}): {f['claim']} "
                       f"[{', '.join(f['evidence_ids'])}]")
        out.append("")
        out.append("## Critic")
        for c in s["critic"]["checks"]:
            out.append(f"- {'PASS' if c['passed'] else 'FAIL'} {c['name']}: {c['detail']}")
        for c in s["critic"].get("llm_concerns", []):
            out.append(f"- model concern: {c}")
        out.append("")
        if s.get("knowledge"):
            out.append("## Policy passages applied")
            out.extend(f"- {k['title']} / {k['heading']} ({k['id']})" for k in s["knowledge"])
            out.append("")
        out.append("## Evidence")
        out.extend(f"- {e['id']} {e['type']} {e['source']}: {e['summary']}" for e in s["evidence"])
        if self.warnings:
            out.append("")
            out.append("## Audit warnings")
            out.extend(f"- {w}" for w in self.warnings)
        return "\n".join(out)


# ---------------------------------------------------------------- audits
def _number_variants(v: float) -> set[float]:
    out = set()
    for x in (v, v * 100.0, abs(v), abs(v) * 100.0):
        if math.isfinite(x):
            out.add(x)
    return out


def number_audit(narrative: str, facts: dict[str, float], rel_tol: float = 1e-6) -> list[str]:
    """Numbers in the narrative that match no fact (with rounding and % forms).

    A token matches a fact when the fact, rounded to the token's displayed
    precision, equals the token ("0.54" matches 0.5354, "223" matches 223.219,
    "53.5%" matches 0.5354). The relative tolerance only absorbs float noise.
    """
    values: list[float] = []
    for v in facts.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            values.extend(_number_variants(float(v)))
    text = _ISO_DATE.sub(" ", narrative)   # dates are not figures
    text = _EVIDENCE_ID.sub(" ", text)
    unmatched = []
    for m in _NUMBER.finditer(text):
        token = m.group(0)
        raw = token.rstrip("%").replace(",", "")
        try:
            num = float(raw)
        except ValueError:
            continue
        shown = len(raw.split(".")[1]) if "." in raw else 0
        half_ulp = 0.5 * 10 ** -shown                      # rounding tolerance in the token's units
        # (candidate value, tolerance in the candidate's units)
        cands = [(abs(num), half_ulp)]
        if token.endswith("%"):
            cands.append((abs(num) / 100.0, half_ulp / 100.0))
        ok = False
        for c, tol in cands:
            for v in values:
                if abs(v - c) <= max(abs(v) * rel_tol, tol + 1e-12):
                    ok = True
                    break
            if ok:
                break
        if not ok:
            unmatched.append(token)
    return unmatched


def evidence_audit(narrative: str, findings: list[Finding], evidence: EvidenceStore) -> list[str]:
    ids = set(_EVIDENCE_ID.findall(narrative))
    for f in findings:
        ids.update(f.evidence_ids)
    return sorted(i for i in ids if not evidence.resolve(i))


# --------------------------------------------------------------- builder
def collect_facts(state: TradingState, critic: CriticReport) -> dict[str, float]:
    d = state.decision
    facts: dict[str, float] = {"last_close": state.last_price}
    if state.current_weight is not None:
        facts["current_weight"] = state.current_weight
    votes = [r for r in state.reports.values() if not r.abstained]
    facts["n_analysts"] = float(len(state.reports))
    facts["n_voting"] = float(len(votes))
    facts["n_bullish"] = float(sum(r.signal > 0.1 for r in votes))
    facts["n_bearish"] = float(sum(r.signal < -0.1 for r in votes))
    facts["n_abstained"] = float(len(state.reports) - len(votes))
    for r in votes:
        facts[f"{r.analyst}_signal"] = r.signal
        facts[f"{r.analyst}_confidence"] = r.confidence
    if state.debate:
        facts["n_debate_turns"] = float(len(state.debate.turns))
    facts["n_risk_views"] = float(len(state.risk_views))
    if state.debate:
        facts["debate_score"], facts["debate_conviction"] = state.debate.score, state.debate.conviction
    if state.proposal:
        facts["proposed_weight"] = state.proposal.target_weight
        facts["horizon_days"] = float(state.proposal.horizon_days)
    for v in state.risk_views:
        facts[f"risk_{v.stance}_weight"] = v.recommended_weight
    if d:
        facts.update(target_weight=d.target_weight, confidence=d.confidence * critic.multiplier,
                     raw_confidence=d.confidence, critic_multiplier=critic.multiplier)
        if d.stop_loss is not None:
            facts["stop_loss"] = d.stop_loss
        if d.take_profit is not None:
            facts["take_profit"] = d.take_profit
    return facts


def template_narrative(state: TradingState, facts: dict[str, float], findings: list[Finding],
                       critic: CriticReport) -> str:
    d = state.decision
    ins = state.instrument
    votes = [r for r in state.reports.values() if not r.abstained]
    bulls = [r.analyst for r in votes if r.signal > 0.1]
    bears = [r.analyst for r in votes if r.signal < -0.1]
    parts = [f"{ins.display}: {d.action.value} with a target weight of {d.target_weight:+.2f} "
             f"(confidence {facts['confidence']:.2f})."]
    if state.debate:
        parts.append(f"The debate verdict was {state.debate.winner} with a score of {state.debate.score:+.2f}; "
                     f"{len(bulls)} analysts leaned bullish and {len(bears)} bearish.")
    if state.proposal:
        parts.append(f"The trader proposed {state.proposal.target_weight:+.2f}; the risk team's views were "
                     + ", ".join(f"{v.stance} {v.recommended_weight:+.2f}" for v in state.risk_views[-3:]) + ".")
    if d.adjustments:
        parts.append("Adjustments: " + "; ".join(d.adjustments) + ".")
    if d.stop_loss is not None and d.take_profit is not None:
        parts.append(f"Protective stop {d.stop_loss:.5g}, target {d.take_profit:.5g}.")
    failed = [c.name for c in critic.failed]
    if failed:
        parts.append("The critic flagged: " + ", ".join(failed) + f"; confidence was scaled by {critic.multiplier:.2f}.")
    else:
        parts.append("The critic's checks all passed.")
    return " ".join(parts)


def llm_narrative(llm: LLM, state: TradingState, facts: dict[str, float], findings: list[Finding]) -> str | None:
    prompt = (
        f"Write a 4-6 sentence executive summary of this decision for a portfolio manager.\n\n"
        f"Structured facts (use these figures and no others; quote them as given):\n"
        + "\n".join(f"- {k}: {v:.4g}" for k, v in facts.items())
        + "\n\nFindings:\n" + "\n".join(f"- {f.agent}: {f.claim}" for f in findings)
        + "\n\nDo not invent numbers, dates or evidence ids. Plain prose, no headings."
    )
    return llm.complete("You are the reporting analyst of a trading desk.", prompt, deep=True)


def build_report(task: Task, state: TradingState, findings: list[Finding], critic: CriticReport,
                 evidence: EvidenceStore, llm: LLM | None = None) -> Report:
    if state.decision is None:
        raise ValueError("cannot report without a decision")
    facts = collect_facts(state, critic)
    narrative, source = None, "template"
    if llm is not None:
        narrative = llm_narrative(llm, state, facts, findings)
        source = "llm" if narrative else "template"
    if not narrative:
        narrative = template_narrative(state, facts, findings, critic)
    d = state.decision
    sections = {
        "decision": {"action": d.action.value, "target_weight": d.target_weight,
                     "confidence": facts["confidence"], "critic_multiplier": critic.multiplier,
                     "stop_loss": None if d.stop_loss is None else round(d.stop_loss, 6),
                     "take_profit": None if d.take_profit is None else round(d.take_profit, 6),
                     "adjustments": list(d.adjustments), "approved": d.approved, "source": d.source},
        "findings": [{"agent": f.agent, "claim": f.claim, "confidence": round(f.confidence, 3),
                      "evidence_ids": list(f.evidence_ids)} for f in findings],
        "critic": critic.to_dict(),
        "knowledge": list(state.knowledge),
        "evidence": evidence.summary_rows(),
    }
    warnings = [f"number not traceable to the facts: {t}" for t in number_audit(narrative, facts)]
    warnings += [f"evidence id does not resolve: {i}" for i in evidence_audit(narrative, findings, evidence)]
    return Report(task.id, state.instrument.symbol, state.as_of.isoformat(), facts, sections, narrative,
                  warnings, source)
