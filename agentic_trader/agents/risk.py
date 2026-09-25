"""Risk-management team (aggressive / neutral / conservative) and Portfolio Manager."""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .. import quant
from ..state import FinalDecision, RiskView, TradingState
from .base import Agent, clip, fmt_facts
from .trader import action_for, allow_short, atr14, protective_levels, sane_levels


def risk_facts(state: TradingState, config: dict) -> dict[str, Any]:
    c = state.history["Close"].to_numpy()
    ppy = state.instrument.periods_per_year
    r = quant.pct_change(c)[-250:]
    rv = quant.realized_vol(c, 20, ppy)
    peak = float(np.max(c[-60:]))
    p = state.proposal
    return {
        "proposed_weight": p.target_weight if p else 0.0,
        "current_position": state.current_weight,
        "realized_vol_20d_annual": float(rv[-1]) if len(rv) and not math.isnan(rv[-1]) else None,
        "var_95_1d": quant.historical_var(r, 0.95),
        "cvar_95_1d": quant.historical_cvar(r, 0.95),
        "drawdown_from_60d_high": float(1.0 - c[-1] / peak) if peak > 0 else 0.0,
        "atr14": atr14(state),
        "target_vol": config["risk"]["target_vol"],
        "max_position": config["risk"]["max_position"],
        "max_var_95": config["risk"]["max_var_95"],
        "rebalance_band": config["risk"].get("rebalance_band", 0.0),
        "short_selling_allowed": allow_short(state, config),
    }


class RiskAnalyst(Agent):
    deep = True
    stance = "neutral"
    _roles = {
        "aggressive": "Aggressive (risk-seeking) Risk Analyst. You champion high-reward "
                      "opportunities and argue against leaving returns on the table.",
        "neutral": "Neutral Risk Analyst. You balance reward and risk, favouring volatility-"
                   "targeted sizing.",
        "conservative": "Conservative (risk-averse) Risk Analyst. You prioritise capital "
                        "preservation, drawdown control and tail risk.",
    }

    def __init__(self, llm, config, stance: str):
        super().__init__(llm, config)
        self.stance = stance
        self.name = f"{stance}_risk"

    @property
    def role(self) -> str:  # type: ignore[override]
        return self._roles[self.stance] + " Debate the other risk analysts and recommend a " \
            "position size."

    def rules_weight(self, f: dict[str, Any]) -> float:
        w0, mx = f["proposed_weight"], f["max_position"]
        vt = quant.vol_target_weight(w0, f["realized_vol_20d_annual"] or float("nan"),
                                     f["target_vol"], mx) if w0 else 0.0
        if self.stance == "aggressive":
            w = float(np.sign(w0)) * max(abs(w0) * 1.25, abs(vt))
        elif self.stance == "neutral":
            w = vt
        else:
            w = float(np.sign(w0)) * min(abs(w0), abs(vt)) * 0.5
            if f["var_95_1d"] * abs(w) > f["max_var_95"] > 0:
                w *= f["max_var_95"] / (f["var_95_1d"] * abs(w))
        return clip(w, -mx, mx)

    def speak(self, state: TradingState, f: dict[str, Any], rnd: int,
              history: list[RiskView]) -> RiskView:
        w = self.rules_weight(f)
        if rnd > 1 and history:  # rule-based convergence towards the group's view
            others = [v.recommended_weight for v in history[-3:] if v.stance != self.stance]
            if others:
                w = 0.75 * w + 0.25 * float(np.mean(others))
        text = (f"{self.stance.title()} view: size {w:+.2f} (proposal {f['proposed_weight']:+.2f}); "
                f"20d vol {_pct(f['realized_vol_20d_annual'])}, 1-day VaR95 {f['var_95_1d']:.2%}, "
                f"CVaR95 {f['cvar_95_1d']:.2%}, drawdown from 60d high "
                f"{f['drawdown_from_60d_high']:.1%}.")
        view = RiskView(self.stance, w, text, rnd)

        p = state.proposal
        prompt = (
            f"Instrument: {state.instrument.display}, as of {state.as_of.isoformat()}.\n"
            f"Trader proposal: {p.action.value} weight {p.target_weight:+.2f}; {p.rationale}\n\n"
            f"Risk facts:\n{fmt_facts(f)}\n"
            + ("\nDiscussion so far:\n" + "\n".join(
                f"{v.stance} (round {v.round}, {v.recommended_weight:+.2f}): {v.argument}"
                for v in history) if history else "")
            + f'\n\nRound {rnd}. JSON keys: "recommended_weight" (signed fraction of capital), '
              '"argument" (<= 120 words, respond to the other analysts).'
        )
        data = self.ask_json(prompt, ("recommended_weight", "argument"))
        if data:
            mx = f["max_position"]
            view = RiskView(self.stance, clip(data["recommended_weight"], -mx, mx),
                            str(data["argument"]), rnd, source="llm")
        return view


class PortfolioManager(Agent):
    name = "portfolio_manager"
    deep = True
    role = ("Portfolio Manager. You review the trader's proposal and the risk team's "
            "discussion, then approve, resize or reject the trade. Hard firm limits are "
            "enforced after your decision.")
    stance_weights = {"aggressive": 0.25, "neutral": 0.5, "conservative": 0.25}

    def guardrails(self, w: float, f: dict[str, Any]) -> tuple[float, list[str]]:
        notes = []
        mx, lim = f["max_position"], f["max_var_95"]
        if w < 0 and not f["short_selling_allowed"]:
            notes.append("short selling not allowed -> flat")
            w = 0.0
        if abs(w) > mx:
            notes.append(f"capped at max position {mx:.2f}")
            w = math.copysign(mx, w)
        if lim > 0 and f["var_95_1d"] * abs(w) > lim:
            new = math.copysign(lim / f["var_95_1d"], w)
            notes.append(f"VaR limit {lim:.2%}: {w:+.2f} -> {new:+.2f}")
            w = new
        if 0 < abs(w) < self.config["risk"]["min_trade_weight"]:
            notes.append("below minimum trade size -> flat")
            w = 0.0
        return w, notes

    def run(self, state: TradingState, f: dict[str, Any]) -> FinalDecision:
        p, thr = state.proposal, self.config["decision_threshold"]
        latest: dict[str, RiskView] = {}
        for v in state.risk_views:
            latest[v.stance] = v
        tot = sum(self.stance_weights[s] for s in latest)
        w = (sum(self.stance_weights[s] * v.recommended_weight for s, v in latest.items()) / tot
             if tot else p.target_weight)
        conf = p.confidence
        rationale = (f"Blended risk-team sizing (25% aggressive / 50% neutral / 25% conservative) "
                     f"gives {w:+.2f} against a proposal of {p.target_weight:+.2f}.")
        source = "rules"

        prompt = (
            f"Instrument: {state.instrument.display}, as of {state.as_of.isoformat()}, last "
            f"close {state.last_price:.6g}.\n\nAnalyst reports:\n{state.reports_digest()}\n\n"
            f"Debate verdict: {state.debate.summary}\n\nTrader proposal: {p.action.value} "
            f"{p.target_weight:+.2f}. {p.rationale}\n\nRisk discussion:\n"
            + "\n".join(f"{v.stance} (round {v.round}, {v.recommended_weight:+.2f}): {v.argument}"
                        for v in state.risk_views)
            + f"\n\nRisk facts and firm limits:\n{fmt_facts(f)}\n"
            + ("\nLessons from past decisions:\n" + "\n".join(state.lessons) + "\n"
               if state.lessons else "")
            + '\nJSON keys: "target_weight" (final signed fraction of capital), "confidence" '
              '([0, 1]), "rationale" (2-4 sentences explaining approval/resizing/rejection).'
        )
        data = self.ask_json(prompt, ("target_weight", "rationale"))
        if data:
            w = clip(data["target_weight"], -1, 1)
            conf = clip(data.get("confidence"), 0, 1, conf)
            rationale, source = str(data["rationale"]), "llm"

        w, notes = self.guardrails(w, f)
        w, band_note = self.no_trade_band(w, state.current_weight, f)
        if band_note:
            notes.append(band_note)
        approved = (np.sign(w) == np.sign(p.target_weight))

        # Protective levels must match the final direction: keep the trader's when
        # the direction is unchanged (and they are sane), rebuild them otherwise.
        direction = float(np.sign(w))
        fallback = protective_levels(direction, state.last_price, f["atr14"], self.config["risk"])
        if direction == np.sign(p.target_weight):
            stop, take = sane_levels(direction, state.last_price, p.stop_loss, p.take_profit,
                                     fallback)
        else:
            stop, take = fallback
        d = FinalDecision(state.instrument.symbol, state.as_of,
                          action_for(w, state.debate.score, thr), round(w, 4), conf,
                          stop, take, rationale, bool(approved), notes, source)
        state.decision = d
        return d

    def no_trade_band(self, w: float, current: float | None,
                      f: dict[str, Any]) -> tuple[float, str | None]:
        """Keep the current position when the new target is within ``rebalance_band`` of it.

        Small target changes cost spread and commission without changing the risk
        materially. The current position is kept only if it would itself pass every
        firm limit today, so the band can never hold a position the limits forbid.
        """
        band = f.get("rebalance_band", 0.0)
        if current is None or band <= 0 or w == current or abs(w - current) >= band:
            return w, None
        kept, fixes = self.guardrails(current, f)
        if fixes or kept != current:
            return w, None
        return current, f"within no-trade band ({abs(w - current):.2f} < {band:.2f}): keep {current:+.2f}"


def run_risk_team(state: TradingState, analysts: list[RiskAnalyst], pm: PortfolioManager,
                  rounds: int) -> FinalDecision:
    f = risk_facts(state, pm.config)
    views: list[RiskView] = []
    for rnd in range(1, max(1, rounds) + 1):
        for a in analysts:
            views.append(a.speak(state, f, rnd, views))
    state.risk_views = views
    return pm.run(state, f)


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.1%}"
