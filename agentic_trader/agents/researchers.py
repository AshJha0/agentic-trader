"""Researcher team: bull vs bear debate moderated by a facilitator."""
from __future__ import annotations

from ..state import AnalystReport, DebateOutcome, DebateTurn, TradingState
from .base import Agent, clip


def consensus_score(state: TradingState, weights: dict[str, float],
                    skip_abstained: bool = False) -> tuple[float, float]:
    """Confidence- and role-weighted average analyst signal, and the mean confidence.

    With ``skip_abstained`` an analyst that had no data does not vote: counting it
    as a zero signal would pull every consensus towards "no view" just because a
    data source is missing.
    """
    num = den = 0.0
    confs = []
    for r in state.reports.values():
        if skip_abstained and r.abstained:
            continue
        w = weights.get(r.analyst, 0.5) * r.confidence
        num += w * r.signal
        den += w
        confs.append(r.confidence)
    score = num / den if den > 0 else 0.0
    return clip(score, -1, 1), (sum(confs) / len(confs) if confs else 0.0)


class Researcher(Agent):
    deep = True
    side = "bull"  # or "bear"

    @property
    def role(self) -> str:  # type: ignore[override]
        view = "bullish (argue FOR" if self.side == "bull" else "bearish (argue AGAINST"
        return (f"{self.side.title()} Researcher. You take the {view} a long position) and "
                "debate the opposing researcher. Use evidence from the analyst reports, rebut "
                "the other side's latest points directly, and stay concise (<= 150 words).")

    def _supporting(self, state: TradingState) -> list[AnalystReport]:
        sgn = 1 if self.side == "bull" else -1
        reps = [r for r in state.reports.values() if not r.abstained and sgn * r.signal > 0.02]
        return sorted(reps, key=lambda r: abs(r.signal) * r.confidence, reverse=True)

    def _opposing(self, state: TradingState) -> list[AnalystReport]:
        sgn = 1 if self.side == "bull" else -1
        reps = [r for r in state.reports.values() if not r.abstained and sgn * r.signal < -0.02]
        return sorted(reps, key=lambda r: abs(r.signal) * r.confidence, reverse=True)

    def rules_argument(self, state: TradingState, rnd: int, history: list[DebateTurn]) -> str:
        sup, opp = self._supporting(state), self._opposing(state)
        parts = []
        if not sup:
            parts.append(f"No analyst supports the {self.side} case outright; the {self.side} "
                         "view rests on the absence of strong opposing evidence.")
        else:
            pick = sup[(rnd - 1) % len(sup)]
            pts = "; ".join(pick.key_points[:3]) or pick.summary
            parts.append(f"The {pick.analyst} analyst ({pick.signal:+.2f}, conf "
                         f"{pick.confidence:.2f}) backs the {self.side} case: {pts}.")
            if len(sup) > 1:
                others = ", ".join(r.analyst for r in sup if r is not pick)
                parts.append(f"This is corroborated by {others}.")
        if history and opp:
            weakest = min(opp, key=lambda r: r.confidence)
            parts.append(f"The opposing case leans on {opp[0].analyst}, but the "
                         f"{weakest.analyst} evidence is only {weakest.confidence:.0%} "
                         "confident and should be discounted.")
        return " ".join(parts)

    def speak(self, state: TradingState, rnd: int, history: list[DebateTurn]) -> DebateTurn:
        prompt = (
            f"Instrument: {state.instrument.display}, as of {state.as_of.isoformat()}, last "
            f"close {state.last_price:.6g}.\n\nAnalyst reports:\n{state.reports_digest()}\n\n"
            + ("Debate so far:\n" + "\n".join(f"{t.speaker}: {t.argument}" for t in history)
               if history else "You open the debate.")
            + (f"\n\nLessons from past decisions:\n" + "\n".join(state.lessons)
               if state.lessons else "")
            + f"\n\nRound {rnd}: give your {self.side} argument."
        )
        text = self.ask_text(prompt) or self.rules_argument(state, rnd, history)
        return DebateTurn(self.side, rnd, text.strip())


class BullResearcher(Researcher):
    name = "bull_researcher"
    side = "bull"


class BearResearcher(Researcher):
    name = "bear_researcher"
    side = "bear"


class DebateFacilitator(Agent):
    name = "facilitator"
    deep = True
    role = ("Debate Facilitator. You review the bull/bear debate and the analyst reports, "
            "decide which side made the stronger evidence-based case, and record the "
            "prevailing view as a structured verdict for the trader.")

    def judge(self, state: TradingState, turns: list[DebateTurn]) -> DebateOutcome:
        weights = self.config["analyst_weights"]
        thr = self.config["decision_threshold"]
        skip = self.config.get("rules", {}).get("abstain_without_data", False)
        score, avg_conf = consensus_score(state, weights, skip)
        conviction = clip(abs(score) * (0.5 + avg_conf), 0, 1)
        winner = "bull" if score > thr else "bear" if score < -thr else "balanced"
        voting = [r for r in state.reports.values() if not r.abstained]
        n_bull = sum(r.signal > 0.02 for r in voting)
        n_bear = sum(r.signal < -0.02 for r in voting)
        n_abs = len(state.reports) - len(voting)
        outcome = DebateOutcome(
            winner, score, conviction,
            f"Weighted analyst consensus {score:+.2f} ({n_bull} bullish vs {n_bear} bearish "
            f"reports, mean confidence {avg_conf:.2f}"
            + (f", {n_abs} without data" if n_abs else "") + f"); prevailing view: {winner}.",
            turns)

        prompt = (
            f"Instrument: {state.instrument.display}, as of {state.as_of.isoformat()}.\n\n"
            f"Analyst reports:\n{state.reports_digest()}\n\nDebate transcript:\n"
            + "\n".join(f"{t.speaker} (round {t.round}): {t.argument}" for t in turns)
            + '\n\nJSON keys: "winner" ("bull", "bear" or "balanced"), "score" (number in '
              '[-1, 1]; the direction and strength of the prevailing view), "conviction" '
              '(number in [0, 1]), "summary" (2-4 sentences recording the decisive arguments).'
        )
        data = self.ask_json(prompt, ("winner", "score", "summary"))
        if data:
            w = str(data["winner"]).lower()
            outcome = DebateOutcome(
                w if w in ("bull", "bear", "balanced") else winner,
                clip(data["score"], -1, 1),
                clip(data.get("conviction"), 0, 1, conviction),
                str(data["summary"]), turns, source="llm")
        return outcome


def run_debate(state: TradingState, bull: BullResearcher, bear: BearResearcher,
               facilitator: DebateFacilitator, rounds: int) -> DebateOutcome:
    turns: list[DebateTurn] = []
    for rnd in range(1, max(1, rounds) + 1):
        turns.append(bull.speak(state, rnd, turns))
        turns.append(bear.speak(state, rnd, turns))
    state.debate = facilitator.judge(state, turns)
    return state.debate
