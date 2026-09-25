"""Trader: turns the debate verdict into a concrete, sized trade proposal."""
from __future__ import annotations

import math

import numpy as np

from .. import quant
from ..state import Action, TradeProposal, TradingState
from .base import Agent, clip, fmt_facts


def allow_short(state: TradingState, config: dict) -> bool:
    r = config["risk"]
    return r["allow_short_fx"] if state.instrument.is_fx else r["allow_short_equity"]


def action_for(weight: float, score: float, thr: float) -> Action:
    if weight > 0:
        return Action.BUY
    if weight < 0 or score < -thr:
        return Action.SELL
    return Action.HOLD


class Trader(Agent):
    name = "trader"
    deep = True
    role = ("Trader. You synthesise the analyst reports and the researchers' debate verdict "
            "into a concrete trade: direction, position size (as a fraction of capital), "
            "stop-loss, take-profit and holding horizon.")

    def run(self, state: TradingState) -> TradeProposal:
        cfg, risk = self.config, self.config["risk"]
        thr = cfg["decision_threshold"]
        debate = state.debate
        assert debate is not None, "trader runs after the research debate"
        h = state.history
        price = state.last_price
        a = quant.atr(h["High"].to_numpy(), h["Low"].to_numpy(), h["Close"].to_numpy(), 14)
        atr = float(a[-1]) if len(a) and not math.isnan(a[-1]) else price * 0.02
        shorts = allow_short(state, cfg)

        score = debate.score
        w = clip(2.0 * score, -1, 1) if abs(score) > thr else 0.0
        if not shorts:
            w = max(w, 0.0)
        hit = state.track_record.get("hit_rate")
        if hit is not None and state.track_record.get("n", 0) >= 5 and hit < 0.4:
            w *= 0.75  # recent calls on this instrument have been poor: trade smaller
        d = float(np.sign(w))
        stop = price - d * risk["stop_atr_mult"] * atr if d else None
        tp = price + d * risk["take_profit_atr_mult"] * atr if d else None
        rationale = (f"Debate verdict {debate.winner} (score {score:+.2f}, conviction "
                     f"{debate.conviction:.2f}) -> target weight {w:+.2f}. Stops at "
                     f"{risk['stop_atr_mult']}x ATR ({atr:.5g}).")
        if hit is not None:
            rationale += f" Track record hit rate {hit:.0%} over {int(state.track_record['n'])} calls."
        proposal = TradeProposal(action_for(w, score, thr), w, debate.conviction, price, stop, tp,
                                 10, rationale)

        facts = {"last_close": price, "atr14": atr, "short_selling_allowed": shorts,
                 "max_position": risk["max_position"], "debate_winner": debate.winner,
                 "debate_score": score, "debate_conviction": debate.conviction,
                 **{f"track_{k}": v for k, v in state.track_record.items()}}
        prompt = (
            f"Instrument: {state.instrument.display} ({state.instrument.asset_class}), as of "
            f"{state.as_of.isoformat()}.\n\nAnalyst reports:\n{state.reports_digest()}\n\n"
            f"Debate verdict: {debate.summary}\n\nTrading facts:\n{fmt_facts(facts)}\n"
            + ("\nLessons from past decisions:\n" + "\n".join(state.lessons) + "\n"
               if state.lessons else "")
            + '\nJSON keys: "action" ("BUY", "SELL" or "HOLD"), "target_weight" (signed '
              'fraction of capital in [-1, 1]; negative = short), "confidence" ([0, 1]), '
              '"stop_loss" (price or null), "take_profit" (price or null), "horizon_days" '
              '(int), "rationale" (2-4 sentences).'
        )
        data = self.ask_json(prompt, ("action", "target_weight", "rationale"))
        if data:
            w = clip(data["target_weight"], -1, 1)
            if not shorts:
                w = max(w, 0.0)
            act = str(data["action"]).upper()
            proposal = TradeProposal(
                Action(act) if act in Action.__members__ else action_for(w, score, thr),
                w, clip(data.get("confidence"), 0, 1, debate.conviction), price,
                _price_or_none(data.get("stop_loss")), _price_or_none(data.get("take_profit")),
                int(clip(data.get("horizon_days"), 1, 90, 10)), str(data["rationale"]),
                source="llm")
        state.proposal = proposal
        return proposal


def _price_or_none(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and not math.isnan(v) else None
