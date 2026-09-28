"""Structured global state shared by all agents.

Agents communicate through concise structured documents (reports, proposals,
decisions) held in one state object rather than a long free-text chat history,
which avoids the "telephone effect" of details degrading at every hop.
Natural-language dialogue is only used inside the two debates (bull/bear
researchers and the risk team), and even those are stored as structured turns.

Every document carries ``evidence_ids``: the evidence records (tool outputs,
calculations, documents) it was built from, filled in by the agentic harness so
that findings and reports can be audited.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import pandas as pd

from .instruments import Instrument

_TAG = "untrusted_data"


def untrusted_block(label: str, lines: list[str]) -> str:
    """Wrap third-party (or previously model-written) text so the model can tell data
    from instructions.

    Any attempt inside the text to open or close the tag is neutralised, so a
    crafted headline cannot end the block early and smuggle instructions out.
    """
    # Neutralised on the joined body, and without requiring a closing ">": a tag split
    # over two lines, or left unterminated for the model to complete, is caught too.
    body = re.sub(rf"<\s*/?\s*{_TAG}\b[^>]*>?", "[removed tag]", "\n".join(str(line) for line in lines), flags=re.I)
    return f'<{_TAG} source="{label}">\n{body}\n</{_TAG}>'


class Action(str, Enum):
    BUY = "BUY"    # hold a long position (FX: long base currency)
    SELL = "SELL"  # hold a short position, or exit to flat when shorting is not allowed
    HOLD = "HOLD"  # no directional view -> flat


@dataclass
class AnalystReport:
    analyst: str
    signal: float          # -1 (strongly bearish) .. +1 (strongly bullish)
    confidence: float      # 0 .. 1
    summary: str
    key_points: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    source: str = "rules"  # "rules" | "llm"
    # True when the analyst had no data at all (e.g. no news in the window). An
    # abstaining analyst is shown in the audit trail but does not vote in the
    # consensus when rules.abstain_without_data is on: missing evidence is not
    # neutral evidence.
    abstained: bool = False
    # The rule-based signal when a model reply replaced it (None otherwise). The
    # critic flags a model view that diverges too far from the rules on the same facts.
    rule_signal: float | None = None
    # True when the analyst read third-party text (headlines, social posts): its summary
    # and key points may quote that text, so downstream prompts show them fenced.
    untrusted: bool = False
    evidence_ids: tuple[str, ...] = ()


def fenced(label: str, lines: list[str], untrusted: bool) -> str:
    """``lines`` for a prompt: inside an ``untrusted_block`` when they descend from
    third-party text, plain otherwise."""
    return untrusted_block(label, lines) if untrusted else "\n".join(lines)


# ``untrusted`` on the documents below: the text was written (by a model or a rule) from a
# prompt that carried fenced third-party material, so it may quote that material and is shown
# inside an ``<untrusted_data>`` block in every later prompt, whoever wrote it.
@dataclass
class DebateTurn:
    speaker: str
    round: int
    argument: str
    untrusted: bool = False


@dataclass
class DebateOutcome:
    winner: str            # "bull" | "bear" | "balanced"
    score: float           # -1 .. +1 consensus direction
    conviction: float      # 0 .. 1
    summary: str
    turns: list[DebateTurn] = field(default_factory=list)
    source: str = "rules"
    evidence_ids: tuple[str, ...] = ()
    untrusted: bool = False


@dataclass
class TradeProposal:
    action: Action
    target_weight: float
    confidence: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    horizon_days: int      # holding horizon in trading days (bars), not calendar days
    rationale: str
    source: str = "rules"
    evidence_ids: tuple[str, ...] = ()
    untrusted: bool = False


@dataclass
class RiskView:
    stance: str            # "aggressive" | "neutral" | "conservative"
    recommended_weight: float
    argument: str
    round: int = 1
    source: str = "rules"
    evidence_ids: tuple[str, ...] = ()
    untrusted: bool = False


@dataclass
class FinalDecision:
    symbol: str
    as_of: date
    action: Action
    target_weight: float
    confidence: float
    stop_loss: float | None
    take_profit: float | None
    rationale: str
    approved: bool = True
    adjustments: list[str] = field(default_factory=list)
    source: str = "rules"
    evidence_ids: tuple[str, ...] = ()
    kept: bool = False   # the desk held its current position (the no-trade band): not a target

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        d["action"] = self.action.value
        d["evidence_ids"] = list(self.evidence_ids)
        return d


@dataclass
class Book:
    """Other current positions and their return history, for a book-level risk check.

    ``positions`` maps symbol -> current weight for every sleeve *other than* the instrument
    under decision (its own weight is what is being decided, so it is never a key here).
    ``returns`` is an aligned (T, N) daily-return frame covering every symbol in ``positions``
    plus the instrument itself, through the decision date with no look-ahead. Built by
    ``TradingGraph.scan()`` when ``config["risk"]["max_book_var_95"]`` is set; ``None`` on
    ``TradingState`` for a standalone ``propagate()`` call, which leaves book-level risk
    checks off exactly as before this existed.
    """
    positions: dict[str, float]
    returns: pd.DataFrame


@dataclass
class TradingState:
    instrument: Instrument
    as_of: date
    history: pd.DataFrame                     # OHLCV strictly <= as_of
    current_weight: float | None = None       # position held going into this decision
    reports: dict[str, AnalystReport] = field(default_factory=dict)
    debate: DebateOutcome | None = None
    proposal: TradeProposal | None = None
    risk_views: list[RiskView] = field(default_factory=list)
    decision: FinalDecision | None = None
    lessons: list[str] = field(default_factory=list)  # reflections from past decisions
    track_record: dict[str, float] = field(default_factory=dict)  # hit rate etc. from memory
    log: list[str] = field(default_factory=list)
    anon: Any = None  # anonymize.Anonymizer when config["llm_anonymize"] is on
    # Filled by the agentic harness: retrieved policy passages shown to the trader
    # and PM, and the alpha snapshot when the quant.alpha tool ran.
    knowledge: list[dict[str, Any]] = field(default_factory=list)
    alpha: dict[str, Any] = field(default_factory=dict)
    book: "Book | None" = None  # other current positions + returns, for a book-level VaR check
    # Which provider priced ``history`` and on what basis: stamped on the memory record so
    # an outcome is only ever valued on the same kind of series.
    provider_name: str = ""
    price_basis: str = ""

    @property
    def last_price(self) -> float:
        return float(self.history["Close"].iloc[-1])

    # Price presentation for prompts: rebased to last close = 100 when anonymised.
    def px(self, v: float | None) -> float | None:
        return self.anon.px(v) if self.anon is not None and v is not None else v

    def unpx(self, v: float | None) -> float | None:
        return self.anon.unpx(v) if self.anon is not None and v is not None else v

    def fmt_px(self, v: float | None) -> str:
        return "n/a" if v is None else f"{self.px(v):.5g}"

    def prompt_facts(self, facts: dict[str, Any]) -> dict[str, Any]:
        return self.anon.facts(facts) if self.anon is not None else facts

    def reports_digest(self) -> str:
        """Compact text of all analyst reports, used in downstream prompts.

        A report built from third-party text (``untrusted``) keeps its numbers in the
        open but its summary and key points inside an ``<untrusted_data>`` block: the
        news analyst's key points quote headlines verbatim, and a model-written summary
        may too, so the fence has to travel with the text into every later prompt.
        """
        lines = []
        if self.current_weight is not None:
            lines.append(f"[portfolio] current position weight {self.current_weight:+.2f}")
        for r in self.reports.values():
            if r.abstained:
                lines.append(f"[{r.analyst}] no data - abstains: {r.summary}")
                continue
            head = f"[{r.analyst}] signal={r.signal:+.2f} conf={r.confidence:.2f}"
            if r.untrusted:
                lines.append(f"{head}: report text (written from third-party material) follows")
                lines.append(untrusted_block(f"{r.analyst} report (from third-party text)",
                                             [r.summary, *(f"- {p}" for p in r.key_points[:6])]))
            else:
                lines.append(f"{head}: {r.summary}")
                lines.extend(f"  - {p}" for p in r.key_points[:6])
        return "\n".join(lines)

    def lessons_block(self) -> str:
        """The memory lessons for a prompt, fenced: a lesson quotes an earlier decision's
        rationale, which may itself have been model-written from third-party text."""
        if not self.lessons:
            return ""
        return ("\nLessons from past decisions:\n"
                + untrusted_block("memory lessons (earlier decisions on this instrument)", self.lessons)
                + "\n")

    @property
    def untrusted_inputs(self) -> bool:
        """True when a prompt built from this state carries fenced text: a report written from
        third-party material, or memory lessons (earlier model-written text). Whatever is then
        written from that prompt -- a debate turn, the verdict, the proposal's rationale, a
        risk argument -- may quote it, so the document is marked ``untrusted`` and every later
        prompt shows it fenced too."""
        return bool(self.lessons) or any(r.untrusted and not r.abstained for r in self.reports.values())

    def debate_block(self, turns: list[DebateTurn], rounds: bool = False) -> str:
        """The debate turns for a prompt, fenced as one block when any of them is untrusted."""
        lines = [f"{t.speaker} (round {t.round}): {t.argument}" if rounds else f"{t.speaker}: {t.argument}"
                 for t in turns]
        return fenced("debate turns (written from third-party material)", lines, any(t.untrusted for t in turns))

    def verdict_block(self) -> str:
        d = self.debate
        return "Debate verdict: " + fenced("debate verdict (written from third-party material)", [d.summary],
                                           d.untrusted)

    def proposal_block(self) -> str:
        """The trader's proposal for a prompt: its numbers in the open, its rationale fenced
        when it descends from third-party text."""
        p = self.proposal
        return (f"Trader proposal: {p.action.value} weight {p.target_weight:+.2f}; "
                + fenced("trader rationale (written from third-party material)", [p.rationale], p.untrusted))

    def risk_views_block(self, views: list[RiskView]) -> str:
        """The risk team's views for a prompt: when any argument is untrusted the recommended
        sizes stay in the open and the arguments go inside one fenced block."""
        if not any(v.untrusted for v in views):
            return "\n".join(f"{v.stance} (round {v.round}, {v.recommended_weight:+.2f}): {v.argument}" for v in views)
        sizes = "\n".join(f"{v.stance} (round {v.round}) recommends {v.recommended_weight:+.2f}" for v in views)
        return sizes + "\n" + untrusted_block("risk analysts' arguments (written from third-party material)",
                                              [f"{v.stance} (round {v.round}): {v.argument}" for v in views])

    def to_markdown(self) -> str:
        ins = self.instrument
        out = [f"# {ins.display} ({ins.asset_class}) — {self.as_of.isoformat()}",
               f"Last close: {self.last_price:.5g}"]
        if self.current_weight is not None:
            out.append(f"Current position: {self.current_weight:+.2f}")
        out.append("")
        out.append("## Analyst team")
        for r in self.reports.values():
            tag = "abstained (no data)" if r.abstained else (
                f"signal {r.signal:+.2f}, confidence {r.confidence:.2f}")
            out.append(f"### {r.analyst.title()} ({r.source}) — {tag}")
            out.append(r.summary)
            out.extend(f"- {p}" for p in r.key_points)
            out.append("")
        if self.debate:
            d = self.debate
            out.append(f"## Research debate — winner: {d.winner} (score {d.score:+.2f}, "
                       f"conviction {d.conviction:.2f})")
            for t in d.turns:
                out.append(f"**{t.speaker} (round {t.round})**: {t.argument}")
                out.append("")
            out.append(f"_Facilitator_: {d.summary}")
            out.append("")
        if self.proposal:
            p = self.proposal
            out.append("## Trader proposal")
            out.append(f"{p.action.value} target weight {p.target_weight:+.2f}, confidence "
                       f"{p.confidence:.2f}, stop {_fmt(p.stop_loss)}, target {_fmt(p.take_profit)}, "
                       f"horizon {p.horizon_days}d")
            out.append(p.rationale)
            out.append("")
        if self.risk_views:
            out.append("## Risk management team")
            for v in self.risk_views:
                out.append(f"- **{v.stance}** (round {v.round}) -> {v.recommended_weight:+.2f}: "
                           f"{v.argument}")
            out.append("")
        if self.decision:
            d = self.decision
            out.append("## Portfolio manager decision")
            out.append(f"**{d.action.value}** target weight {d.target_weight:+.2f} "
                       f"(approved={d.approved}, confidence {d.confidence:.2f})")
            out.append(d.rationale)
            out.extend(f"- adjustment: {a}" for a in d.adjustments)
        if self.lessons:
            out.append("\n## Lessons from memory")
            out.extend(f"- {l}" for l in self.lessons)
        return "\n".join(out)


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.5g}"
