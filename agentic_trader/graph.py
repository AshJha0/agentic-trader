"""The trading-firm workflow.

    Analyst team  ->  Bull/Bear debate + facilitator  ->  Trader
        ->  Risk team discussion  ->  Portfolio Manager  ->  decision (+ memory)

``TradingGraph.propagate(symbol, as_of)`` runs one pass and returns the full
structured state together with the final decision.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from .agents import (ANALYSTS, BearResearcher, BullResearcher, DebateFacilitator,
                     PortfolioManager, RiskAnalyst, Trader, run_debate, run_risk_team)
from .config import make_config
from .data import MarketDataProvider, get_provider
from .instruments import Instrument
from .llm import LLM, get_llm
from .memory import DecisionMemory
from .state import FinalDecision, TradingState

log = logging.getLogger(__name__)

DEFAULT_ANALYSTS = {
    "equity": ["technical", "fundamentals", "news", "sentiment"],
    "fx": ["technical", "macro", "news", "sentiment"],
}

Event = Callable[[str, str], None]  # (stage, message)


class TradingGraph:
    def __init__(self, config: dict | None = None, provider: MarketDataProvider | None = None,
                 llm: LLM | None = None, memory: DecisionMemory | None = None,
                 on_event: Event | None = None):
        self.config = make_config(config)
        self.provider = provider or get_provider(self.config)
        self.llm = llm if llm is not None else get_llm(self.config)
        self.memory = memory if memory is not None else DecisionMemory(self.config.get("memory_path"))
        self.on_event = on_event or (lambda stage, msg: log.info("[%s] %s", stage, msg))

        c, m = self.config, self.llm
        self.bull, self.bear = BullResearcher(m, c), BearResearcher(m, c)
        self.facilitator = DebateFacilitator(m, c)
        self.trader = Trader(m, c)
        self.risk_team = [RiskAnalyst(m, c, s) for s in ("aggressive", "neutral", "conservative")]
        self.pm = PortfolioManager(m, c)

    def _analysts(self, instrument: Instrument):
        names = self.config.get("analysts") or DEFAULT_ANALYSTS[instrument.asset_class]
        out = []
        for n in names:
            if n == "fundamentals" and instrument.is_fx:
                n = "macro"  # FX has no company fundamentals
            if n not in ANALYSTS:
                raise ValueError(f"unknown analyst {n!r}; choose from {sorted(ANALYSTS)}")
            out.append(ANALYSTS[n](self.llm, self.config))
        return out

    def propagate(self, symbol: str | Instrument, as_of: date | str,
                  asset_class: str | None = None) -> tuple[TradingState, FinalDecision]:
        ins = symbol if isinstance(symbol, Instrument) else Instrument.parse(symbol, asset_class)
        as_of = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
        emit = self.on_event

        start = as_of - timedelta(days=self.config["lookback_days"])
        hist = self.provider.history(ins, start, as_of)
        hist = hist[hist.index <= pd.Timestamp(as_of)]  # point-in-time guard, whatever the provider does
        if len(hist) < 30:
            raise ValueError(f"not enough history for {ins.display} up to {as_of} "
                             f"({len(hist)} bars)")
        state = TradingState(ins, as_of, hist)
        # Decisions are for the last available bar (as_of may be a weekend/holiday).
        bar_date = hist.index[-1].date()

        self.memory.resolve(ins.symbol, as_of, state.last_price)
        state.lessons = self.memory.lessons(ins.symbol, as_of)
        state.track_record = self.memory.track_record(ins.symbol, as_of)

        emit("data", f"{ins.display} {ins.asset_class}: {len(hist)} bars to {bar_date}, "
                     f"last {state.last_price:.6g}")
        for a in self._analysts(ins):
            r = a.run(state, self.provider)
            emit("analyst", f"{r.analyst:<12} signal {r.signal:+.2f} conf {r.confidence:.2f} "
                            f"[{r.source}] {r.summary}")

        d = run_debate(state, self.bull, self.bear, self.facilitator,
                       self.config["max_debate_rounds"])
        emit("debate", f"{len(d.turns)} turns -> winner {d.winner}, score {d.score:+.2f} "
                       f"[{d.source}]")

        p = self.trader.run(state)
        emit("trader", f"{p.action.value} {p.target_weight:+.2f} [{p.source}]")

        dec = run_risk_team(state, self.risk_team, self.pm, self.config["max_risk_discuss_rounds"])
        views = ", ".join(f"{v.stance[:4]} {v.recommended_weight:+.2f}"
                          for v in state.risk_views[-len(self.risk_team):])
        emit("risk", views)
        emit("decision", f"{dec.action.value} target weight {dec.target_weight:+.2f} "
                         f"(approved={dec.approved}) [{dec.source}]"
                         + (f" | {'; '.join(dec.adjustments)}" if dec.adjustments else ""))

        self.memory.record(ins.symbol, as_of, dec.action.value, dec.target_weight,
                           state.last_price, dec.rationale,
                           horizon_days=state.proposal.horizon_days if state.proposal else 10)
        if self.config.get("save_reports"):
            path = self.save_report(state)
            emit("report", f"saved {path}")
        return state, dec

    def save_report(self, state: TradingState) -> Path:
        out = Path(self.config["results_dir"]) / state.instrument.symbol / state.as_of.isoformat()
        out.mkdir(parents=True, exist_ok=True)
        path = out / "report.md"
        path.write_text(state.to_markdown(), encoding="utf-8")
        return path
