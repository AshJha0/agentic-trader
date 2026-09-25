"""Structured global state shared by all agents.

Following the TradingAgents paper, agents communicate through concise structured
documents (reports, proposals, decisions) held in one state object rather than a
long free-text chat history. Natural-language dialogue is only used inside the
two debates (bull/bear researchers and the risk team), and even those are stored
as structured turns.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from enum import Enum
from typing import Any

import pandas as pd

from .instruments import Instrument


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


@dataclass
class DebateTurn:
    speaker: str
    round: int
    argument: str


@dataclass
class DebateOutcome:
    winner: str            # "bull" | "bear" | "balanced"
    score: float           # -1 .. +1 consensus direction
    conviction: float      # 0 .. 1
    summary: str
    turns: list[DebateTurn] = field(default_factory=list)
    source: str = "rules"


@dataclass
class TradeProposal:
    action: Action
    target_weight: float
    confidence: float
    entry_price: float
    stop_loss: float | None
    take_profit: float | None
    horizon_days: int
    rationale: str
    source: str = "rules"


@dataclass
class RiskView:
    stance: str            # "aggressive" | "neutral" | "conservative"
    recommended_weight: float
    argument: str
    round: int = 1
    source: str = "rules"


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

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        d["action"] = self.action.value
        return d


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

    @property
    def last_price(self) -> float:
        return float(self.history["Close"].iloc[-1])

    def reports_digest(self) -> str:
        """Compact text of all analyst reports, used in downstream prompts."""
        lines = []
        if self.current_weight is not None:
            lines.append(f"[portfolio] current position weight {self.current_weight:+.2f}")
        for r in self.reports.values():
            if r.abstained:
                lines.append(f"[{r.analyst}] no data - abstains: {r.summary}")
                continue
            lines.append(f"[{r.analyst}] signal={r.signal:+.2f} conf={r.confidence:.2f}: {r.summary}")
            lines.extend(f"  - {p}" for p in r.key_points[:6])
        return "\n".join(lines)

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
