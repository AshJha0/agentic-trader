"""The critic: deterministic checks first, then an optional model critique that
can only lower confidence.

Checks on a completed decision:

1. every evidence id cited by a finding resolves in the store;
2. a model-sourced analyst signal does not diverge from the rule-based signal
   on the same facts by more than the threshold;
3. analysts do not contradict each other beyond the tolerance without the
   facilitator recording a balanced verdict;
4. the final decision respects the firm limits (size, VaR, shorting);
5. protective levels sit on the correct side of the entry;
6. the decision's direction is consistent with the debate verdict unless an
   adjustment explains the difference;
7. findings backed by a single piece of evidence are capped at 0.6 confidence.

A failed check lowers the confidence of the affected findings and of the
decision; nothing here can raise a confidence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..agents.base import clip
from ..llm import LLM, extract_json
from ..state import TradingState
from .domain import Finding
from .evidence import EvidenceStore


@dataclass
class Check:
    name: str
    passed: bool
    detail: str
    severity: str = "warning"  # "warning" lowers confidence; "error" fails the review


@dataclass
class CriticReport:
    checks: list[Check] = field(default_factory=list)
    multiplier: float = 1.0          # applied to the decision confidence (<= 1)
    llm_concerns: list[str] = field(default_factory=list)
    llm_multiplier: float | None = None

    @property
    def passed(self) -> bool:
        return not any(c.severity == "error" and not c.passed for c in self.checks)

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def to_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "multiplier": round(self.multiplier, 3),
                "checks": [c.__dict__ for c in self.checks], "llm_concerns": self.llm_concerns,
                "llm_multiplier": self.llm_multiplier}


class Critic:
    def __init__(self, config: dict[str, Any], llm: LLM | None = None):
        self.config = config
        self.llm = llm if config.get("agentic", {}).get("llm_critic", True) else None
        self.divergence = float(config.get("agentic", {}).get("critic_divergence", 0.6))

    def review(self, state: TradingState, findings: list[Finding], evidence: EvidenceStore,
               risk_facts: dict[str, Any] | None = None) -> CriticReport:
        rep = CriticReport()
        mult = 1.0

        # 1. evidence resolves
        for f in findings:
            bad = evidence.unresolved(f.evidence_ids)
            if bad:
                rep.checks.append(Check("evidence_resolves", False,
                                        f"{f.agent}: unresolved evidence {bad}", "error"))
                f.confidence = 0.0
        if not rep.failed:
            rep.checks.append(Check("evidence_resolves", True, f"{len(findings)} findings, all evidence resolves"))

        # 2. model vs rules divergence
        for r in state.reports.values():
            if r.source == "llm" and r.rule_signal is not None and not r.abstained:
                gap = abs(r.signal - r.rule_signal)
                if gap > self.divergence:
                    rep.checks.append(Check("model_rule_divergence", False,
                                            f"{r.analyst}: model {r.signal:+.2f} vs rules {r.rule_signal:+.2f}"))
                    mult = min(mult, 0.7)
                    for f in findings:
                        if f.agent == r.analyst:
                            f.confidence *= 0.5
        if not any(c.name == "model_rule_divergence" for c in rep.checks):
            rep.checks.append(Check("model_rule_divergence", True, "no model view diverges from its rules"))

        # 3. contradictions among analysts
        votes = [r for r in state.reports.values() if not r.abstained]
        if len(votes) >= 2:
            strong_bull = [r.analyst for r in votes if r.signal > 0.5]
            strong_bear = [r.analyst for r in votes if r.signal < -0.5]
            if strong_bull and strong_bear and state.debate and state.debate.winner != "balanced":
                rep.checks.append(Check("analyst_contradiction", False,
                                        f"{strong_bull} strongly bullish vs {strong_bear} strongly bearish, "
                                        f"verdict {state.debate.winner}"))
                mult = min(mult, 0.8)
            else:
                rep.checks.append(Check("analyst_contradiction", True, "no unresolved strong contradiction"))

        d = state.decision
        if d is not None:
            risk_cfg = self.config["risk"]
            # 4. firm limits
            problems = []
            if abs(d.target_weight) > risk_cfg["max_position"] + 1e-9:
                problems.append(f"|weight| {abs(d.target_weight):.2f} > max {risk_cfg['max_position']}")
            allow_short = risk_cfg["allow_short_fx"] if state.instrument.is_fx else risk_cfg["allow_short_equity"]
            if d.target_weight < 0 and not allow_short:
                problems.append("short position under a long-only policy")
            var = (risk_facts or {}).get("var_95_1d")
            if var and risk_cfg["max_var_95"] > 0 and var * abs(d.target_weight) > risk_cfg["max_var_95"] + 1e-9:
                problems.append(f"VaR {var * abs(d.target_weight):.2%} > cap {risk_cfg['max_var_95']:.2%}")
            rep.checks.append(Check("firm_limits", not problems,
                                    "; ".join(problems) or "size, shorting and VaR within limits",
                                    "error"))
            # 5. protective levels
            px, ok = state.last_price, True
            if d.target_weight > 0:
                ok = (d.stop_loss is None or d.stop_loss < px) and (d.take_profit is None or d.take_profit > px)
            elif d.target_weight < 0:
                ok = (d.stop_loss is None or d.stop_loss > px) and (d.take_profit is None or d.take_profit < px)
            rep.checks.append(Check("protective_levels", ok, "stop and target on the correct side"
                                    if ok else "a protective level sits on the wrong side of the entry", "error"))
            # 6. direction: the trader's tilt must agree with the verdict, and the PM must
            #    not flip the proposal's direction without recording an adjustment. Sizing
            #    below the strategic weight by the risk team is not a directional change.
            if state.debate is not None and state.proposal is not None:
                neutral = risk_cfg.get("neutral_weight", {}).get(state.instrument.asset_class, 0.0)
                tilt = int(np.sign(round(state.proposal.target_weight - neutral, 6)))
                verdict = {"bull": 1, "bear": -1, "balanced": 0}[state.debate.winner]
                tilt_ok = verdict == 0 or tilt == 0 or tilt == verdict
                flip_ok = d.approved or bool(d.adjustments)
                detail = []
                if not tilt_ok:
                    detail.append(f"verdict {state.debate.winner} but the trader tilted {tilt:+d}")
                if not flip_ok:
                    detail.append("the PM reversed the proposal's direction without an adjustment")
                rep.checks.append(Check("direction_vs_verdict", tilt_ok and flip_ok,
                                        "; ".join(detail) or "proposal tilt agrees with the verdict and the "
                                        "decision keeps its direction"))
                if not (tilt_ok and flip_ok):
                    mult = min(mult, 0.8)

        # 7. single-evidence cap
        for f in findings:
            if len(set(f.evidence_ids)) <= 1 and f.confidence > 0.6:
                f.confidence = 0.6
                rep.checks.append(Check("single_evidence_cap", True, f"{f.agent}: capped at 0.6"))

        # optional model critique: only ever lowers
        if self.llm is not None and d is not None:
            concerns, m = self._llm_critique(state, findings)
            rep.llm_concerns, rep.llm_multiplier = concerns, m
            if m is not None:
                mult = min(mult, m)
        rep.multiplier = mult
        return rep

    def _llm_critique(self, state: TradingState, findings: list[Finding]) -> tuple[list[str], float | None]:
        prompt = (
            f"Review this trading decision for {state.instrument.display} as of {state.as_of.isoformat()}.\n\n"
            f"Analyst reports:\n{state.reports_digest()}\n\nFindings:\n"
            + "\n".join(f"- {f.agent}: {f.claim} (confidence {f.confidence:.2f})" for f in findings)
            + f"\n\nDecision: {state.decision.action.value} {state.decision.target_weight:+.2f}. "
              f"{state.decision.rationale}\n\n"
            'JSON keys: "concerns" (list of short strings; empty if none), "confidence_multiplier" '
            "(number in [0, 1]: 1 = no concern, lower = less confident). You may only lower confidence."
        )
        text = self.llm.complete(
            "You are the independent critic of a trading desk. Find weaknesses, contradictions and "
            "unsupported claims. Be specific and brief.", prompt, deep=True)
        data = extract_json(text)
        if not data:
            return [], None
        concerns = [str(c)[:200] for c in data.get("concerns", []) if isinstance(data.get("concerns"), list)][:8]
        m = clip(data.get("confidence_multiplier"), 0.0, 1.0, 1.0)
        return concerns, min(m, 1.0)
