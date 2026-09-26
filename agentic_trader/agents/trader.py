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


def atr14(state: TradingState) -> float:
    """Latest ATR(14); 2% of price when history is too short to compute it."""
    h = state.history
    a = quant.atr(h["High"].to_numpy(), h["Low"].to_numpy(), h["Close"].to_numpy(), 14)
    v = float(a[-1]) if len(a) else float("nan")
    return v if v > 0 and not math.isnan(v) else state.last_price * 0.02


def protective_levels(direction: float, entry: float, atr: float,
                      risk: dict) -> tuple[float | None, float | None]:
    """ATR-based stop and target for a direction (+1 long, -1 short, 0 flat)."""
    if direction == 0:
        return None, None
    stop = entry - direction * risk["stop_atr_mult"] * atr
    take = entry + direction * risk["take_profit_atr_mult"] * atr
    return (stop if stop > 0 else None), (take if take > 0 else None)


def sane_levels(direction: float, entry: float, stop: float | None, take: float | None,
                fallback: tuple[float | None, float | None]) -> tuple[float | None, float | None]:
    """Keep model-supplied levels only when they sit on the correct side of the entry.

    A long needs stop < entry < take; a short needs take < entry < stop. Anything
    else (a stop above a long's entry, a target of 0, a level that is not a number)
    is replaced by the ATR-based fallback so a bad model reply cannot produce a
    stop that fires instantly or never.
    """
    if direction == 0:
        return None, None
    fs, ft = fallback
    ok_stop = stop is not None and (stop < entry if direction > 0 else stop > entry)
    ok_take = take is not None and (take > entry if direction > 0 else take < entry)
    return (stop if ok_stop else fs), (take if ok_take else ft)


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
        price = state.last_price
        atr = atr14(state)
        shorts = allow_short(state, cfg)

        score = debate.score
        # Strategic weight + tactical tilt: with no view hold the benchmark weight
        # (0 = flat); conviction moves the position above or below it.
        neutral = risk.get("neutral_weight", {}).get(state.instrument.asset_class, 0.0)
        w = clip(neutral + 2.0 * score, -1, 1) if abs(score) > thr else neutral
        if not shorts:
            w = max(w, 0.0)
        hit = state.track_record.get("hit_rate")
        if hit is not None and state.track_record.get("n", 0) >= 5 and hit < 0.4:
            w *= 0.75  # recent calls on this instrument have been poor: trade smaller
        d = float(np.sign(w))
        stop, tp = protective_levels(d, price, atr, risk)
        rationale = (f"Debate verdict {debate.winner} (score {score:+.2f}, conviction "
                     f"{debate.conviction:.2f}) -> target weight {w:+.2f}"
                     + (f" (strategic weight {neutral:+.2f} plus tilt)" if neutral else "")
                     + f". Stops at {risk['stop_atr_mult']}x ATR (ATR = {atr / price:.2%} of price).")
        if hit is not None:
            rationale += f" Track record hit rate {hit:.0%} over {int(state.track_record['n'])} calls."
        proposal = TradeProposal(action_for(w, score, thr), w, debate.conviction, price, stop, tp,
                                 10, rationale)

        facts = {"last_close": state.px(price), "atr14": state.px(atr), "short_selling_allowed": shorts,
                 "max_position": risk["max_position"], "debate_winner": debate.winner,
                 "debate_score": score, "debate_conviction": debate.conviction,
                 "current_position": state.current_weight,
                 "strategic_weight_when_neutral": neutral,
                 **{f"track_{k}": v for k, v in state.track_record.items()}}
        prompt = (
            f"Instrument: {state.instrument.display} ({state.instrument.asset_class}), as of "
            f"{state.as_of.isoformat()}.\n\nAnalyst reports:\n{state.reports_digest()}\n\n"
            f"Debate verdict: {debate.summary}\n\nTrading facts:\n{fmt_facts(facts)}\n"
            + ("\nLessons from past decisions:\n" + "\n".join(state.lessons) + "\n"
               if state.lessons else "")
            + policy_passages(state)
            + '\nJSON keys: "action" ("BUY", "SELL" or "HOLD"), "target_weight" (signed '
              'fraction of capital in [-1, 1]; negative = short), "confidence" ([0, 1]), '
              '"stop_loss" (price or null), "take_profit" (price or null), "horizon_days" '
              '(int), "rationale" (2-4 sentences).'
        )
        data = self.ask_json(prompt, ("action", "target_weight", "rationale"), state=state)
        if data:
            w = clip(data["target_weight"], -1, 1)
            if not shorts:
                w = max(w, 0.0)
            d = float(np.sign(w))
            # The model saw (possibly rebased) prices: map its levels back to real ones.
            stop, tp = sane_levels(d, price, state.unpx(_price_or_none(data.get("stop_loss"))),
                                   state.unpx(_price_or_none(data.get("take_profit"))),
                                   protective_levels(d, price, atr, risk))
            act = str(data["action"]).upper()
            proposal = TradeProposal(
                Action(act) if act in Action.__members__ else action_for(w, score, thr),
                w, clip(data.get("confidence"), 0, 1, debate.conviction), price, stop, tp,
                int(clip(data.get("horizon_days"), 1, 90, 10)), str(data["rationale"]),
                source="llm")
        state.proposal = proposal
        return proposal


def policy_passages(state: TradingState) -> str:
    """Firm policy passages retrieved by the agentic harness (knowledge.search), if any."""
    if not state.knowledge:
        return ""
    lines = [f"- {k.get('title', '')} / {k.get('heading', '')}: {str(k.get('text', ''))[:400]}"
             for k in state.knowledge[:3]]
    return "\nFirm policy (retrieved passages, follow them):\n" + "\n".join(lines) + "\n"


def _price_or_none(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v > 0 and not math.isnan(v) and not math.isinf(v) else None
