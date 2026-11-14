"""Risk-management team (aggressive / neutral / conservative) and Portfolio Manager."""

from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np

from .. import quant
from .. import contracts
from ..state import Book, FinalDecision, RiskView, TradingState
from .base import Agent, clip, fmt_facts
from ..validate import cap_short_notional
from .trader import action_for, allow_short, atr14, policy_passages, protective_levels, sane_levels

log = logging.getLogger(__name__)


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
        # Long and short sides are different tails: a long loses on the left tail (-q05 of r),
        # a short on the right (q95 of r = -q05 of -r). Sizing a short with the long-side
        # number under-caps it on right-skewed series and over-caps it on left-skewed ones.
        "var_95_1d": quant.historical_var(r, 0.95),
        "var_95_1d_short": quant.historical_var(-r, 0.95),
        "cvar_95_1d": quant.historical_cvar(r, 0.95),
        "cvar_95_1d_short": quant.historical_cvar(-r, 0.95),
        "drawdown_from_60d_high": float(1.0 - c[-1] / peak) if peak > 0 else 0.0,
        "atr14": atr14(state),
        "target_vol": config["risk"]["target_vol"],
        "max_position": config["risk"]["max_position"],
        "max_var_95": config["risk"]["max_var_95"],
        "rebalance_band": config["risk"].get("rebalance_band", 0.0),
        "short_selling_allowed": allow_short(state, config),
        "max_short_notional": config["risk"].get("max_short_notional"),
        "max_book_var_95": config["risk"].get("max_book_var_95"),
        "book_var_method": config["risk"].get("book_var_method", "ewma"),
        # Informational only (current book, no proposed change): the enforced check runs in
        # PortfolioManager.guardrails, which has state.book and can evaluate the proposed
        # weight's own effect on it -- a plain fact dict can only report a number, not act.
        "book_var_95_now": (
            _book_var_now(state, config["risk"].get("book_var_method", "ewma")) if state.book is not None else None
        ),
    }


def position_var(f: dict[str, Any], w: float) -> float:
    """1-day 95% VaR per unit of |weight| for a position of sign ``w``: the left tail of the
    instrument's returns for a long, the right tail (``var_95_1d_short``) for a short."""
    return f["var_95_1d_short"] if w < 0 else f["var_95_1d"]


def position_cvar(f: dict[str, Any], w: float) -> float:
    """1-day 95% CVaR on the same side as ``position_var``."""
    return f["cvar_95_1d_short"] if w < 0 else f["cvar_95_1d"]


def _book_var_now(state: TradingState, method: str) -> float | None:
    from ..portfolio import book_var_95

    assert state.book is not None  # the caller only asks when a book is attached
    sym = state.instrument.symbol
    positions = {**state.book.positions, sym: state.current_weight or 0.0}
    return book_var_95(positions, state.book.returns, method=method)


class RiskAnalyst(Agent):
    deep = True
    stance = "neutral"
    _roles = {
        "aggressive": "Aggressive (risk-seeking) Risk Analyst. You champion high-reward "
        "opportunities and argue against leaving returns on the table.",
        "neutral": "Neutral Risk Analyst. You balance reward and risk, favouring volatility-targeted sizing.",
        "conservative": "Conservative (risk-averse) Risk Analyst. You prioritise capital "
        "preservation, drawdown control and tail risk.",
    }

    def __init__(self, llm, config, stance: str):
        super().__init__(llm, config)
        self.stance = stance
        self.name = f"{stance}_risk"

    @property
    def role(self) -> str:  # type: ignore[override]
        return self._roles[self.stance] + " Debate the other risk analysts and recommend a position size."

    def rules_weight(self, f: dict[str, Any]) -> float:
        w0, mx = f["proposed_weight"], f["max_position"]
        vt = quant.vol_target_weight(w0, f["realized_vol_20d_annual"] or float("nan"), f["target_vol"], mx) if w0 else 0.0
        if self.stance == "aggressive":
            if self.config["risk"].get("aggressive_vol_scaled", True):
                # 1.25x the vol-targeted size: the aggressive view scales with volatility like the
                # others, so the blended book is a proportional vol target (0.9375 x vt before the
                # cap) instead of a fixed floor at the cap (the v0.8 rule, kept as a trial).
                w = float(np.sign(w0)) * 1.25 * abs(vt)
            else:
                w = float(np.sign(w0)) * max(abs(w0) * 1.25, abs(vt))
        elif self.stance == "neutral":
            w = vt
        else:
            w = float(np.sign(w0)) * min(abs(w0), abs(vt)) * 0.5
            var = position_var(f, w)
            # historical_var is always >= 0 (quant.historical_var returns max(0, -q)), so the
            # left side of this chained comparison is 0 or NaN only when there is no VaR to
            # scale by, and it then evaluates false: the division below is never reached with
            # a zero or NaN VaR, whatever max_var_95 is.
            if var * abs(w) > f["max_var_95"] > 0:
                w *= f["max_var_95"] / (var * abs(w))
        return clip(w, -mx, mx)

    def speak(self, state: TradingState, f: dict[str, Any], rnd: int, history: list[RiskView]) -> RiskView:
        w = self.rules_weight(f)
        if rnd > 1 and history:  # rule-based convergence towards the group's view
            others = [v.recommended_weight for v in history[-3:] if v.stance != self.stance]
            if others:
                w = 0.75 * w + 0.25 * float(np.mean(others))
        text = (
            f"{self.stance.title()} view: size {w:+.2f} (proposal {f['proposed_weight']:+.2f}); "
            f"20d vol {_pct(f['realized_vol_20d_annual'])}, 1-day VaR95 (position side) "
            f"{position_var(f, f['proposed_weight']):.2%}, "
            f"CVaR95 {position_cvar(f, f['proposed_weight']):.2%}, drawdown from 60d high "
            f"{f['drawdown_from_60d_high']:.1%}."
        )
        untrusted = (
            state.untrusted_inputs
            or (state.proposal is not None and state.proposal.untrusted)
            or any(v.untrusted for v in history)
        )
        view = RiskView(self.stance, w, text, rnd, untrusted=untrusted)

        prompt = (
            f"Instrument: {state.instrument.display}, as of {state.as_of.isoformat()}.\n"
            f"{state.proposal_block()}\n\n"
            f"Risk facts:\n{fmt_facts(state.prompt_facts(f))}\n"
            + ("\nDiscussion so far:\n" + state.risk_views_block(history) if history else "")
            + f'\n\nRound {rnd}. JSON keys: "recommended_weight" (signed fraction of capital), '
            '"argument" (<= 120 words, respond to the other analysts).'
        )
        data = self.ask_json(
            prompt, ("recommended_weight", "argument"), state=state, numeric=("recommended_weight",), schema=contracts.RISK_VIEW
        )
        if data:
            mx = f["max_position"]
            view = RiskView(
                self.stance,
                clip(data["recommended_weight"], -mx, mx),
                str(data["argument"]),
                rnd,
                source="llm",
                untrusted=untrusted,
            )
        return view


class PortfolioManager(Agent):
    name = "portfolio_manager"
    deep = True
    role = (
        "Portfolio Manager. You review the trader's proposal and the risk team's "
        "discussion, then approve, resize or reject the trade. Hard firm limits are "
        "enforced after your decision."
    )
    stance_weights = {"aggressive": 0.25, "neutral": 0.5, "conservative": 0.25}

    def guardrails(
        self, w: float, f: dict[str, Any], symbol: str | None = None, book: Book | None = None
    ) -> tuple[float, list[str]]:
        """``symbol`` and ``book`` are only needed for the book-level VaR check (both
        ``None`` -- the default -- leaves every other guardrail exactly as before that
        check existed)."""
        notes = []
        mx, lim = f["max_position"], f["max_var_95"]
        if w < 0 and not f["short_selling_allowed"]:
            notes.append("short selling not allowed -> flat")
            w = 0.0
        short_cap = f.get("max_short_notional")
        if short_cap is not None and w < -short_cap:
            notes.append(f"capped at max short notional {short_cap:.2f}")
            w = cap_short_notional(w, short_cap)
        if abs(w) > mx:
            notes.append(f"capped at max position {mx:.2f}")
            w = math.copysign(mx, w)
        var = position_var(f, w)
        if lim > 0 and var * abs(w) > lim:
            new = math.copysign(lim / var, w)
            notes.append(f"VaR limit {lim:.2%}: {w:+.2f} -> {new:+.2f}")
            w = new
        if book is not None and symbol is not None and f.get("max_book_var_95") and w != 0:
            from ..portfolio import book_var_scale

            w, _, note = book_var_scale(
                symbol, w, book.positions, book.returns, f["max_book_var_95"], method=f.get("book_var_method", "ewma")
            )
            if note:
                notes.append(note)
        if 0 < abs(w) < self.config["risk"]["min_trade_weight"]:
            notes.append("below minimum trade size -> flat")
            w = 0.0
        return w, notes

    def run(self, state: TradingState, f: dict[str, Any]) -> FinalDecision:
        p, thr = state.proposal, self.config["decision_threshold"]
        assert p is not None and state.debate is not None  # the trader and debate stages ran first
        latest: dict[str, RiskView] = {}
        for v in state.risk_views:
            latest[v.stance] = v
        tot = sum(self.stance_weights[s] for s in latest)
        w = sum(self.stance_weights[s] * v.recommended_weight for s, v in latest.items()) / tot if tot else p.target_weight
        conf = p.confidence
        rationale = (
            f"Blended risk-team sizing (25% aggressive / 50% neutral / 25% conservative) "
            f"gives {w:+.2f} against a proposal of {p.target_weight:+.2f}."
        )
        fc = state.forecast
        if fc is not None:
            # combination.method "ic": the trader's mean-variance weight already prices risk,
            # so the hand-set stance blend is not applied; with conformal sizing the tilt is
            # scaled by min(1, |mu| / interval half-width).
            scale = fc.size_scale()
            w = fc.neutral + (p.target_weight - fc.neutral) * scale
            rationale = (
                f"IC-combination weight {p.target_weight:+.2f} from {len(fc.active)} significant "
                f"signal(s)" + (f", interval sizing x{scale:.2f}" if fc.interval is not None else "") + f" -> {w:+.2f}."
            )
        source = "rules"
        rule_w, model_w = float(w), None

        prompt = (
            f"Instrument: {state.instrument.display}, as of {state.as_of.isoformat()}, last "
            f"close {state.fmt_px(state.last_price)}.\n\nAnalyst reports:\n{state.reports_digest()}\n\n"
            f"{state.verdict_block()}\n\n{state.proposal_block()}\n\nRisk discussion:\n"
            + state.risk_views_block(state.risk_views)
            + f"\n\nRisk facts and firm limits:\n{fmt_facts(state.prompt_facts(f))}\n"
            + state.lessons_block()
            + policy_passages(state)
            + '\nJSON keys: "target_weight" (final signed fraction of capital), "confidence" '
            '([0, 1]), "rationale" (2-4 sentences explaining approval/resizing/rejection).'
        )
        data = self.ask_json(
            prompt,
            ("target_weight", "rationale"),
            state=state,
            numeric=("target_weight", "confidence"),
            schema=contracts.PORTFOLIO_MANAGER,
        )
        override_notes: list[str] = []
        if data:
            model_w = clip(data["target_weight"], -1, 1)
            w, override_notes = self.bound_model_weight(model_w, rule_w, state)
            conf = clip(data.get("confidence"), 0, 1, conf)
            rationale, source = str(data["rationale"]), "llm"

        sym = state.instrument.symbol
        w, notes = self.guardrails(w, f, sym, state.book)
        notes = override_notes + notes
        w, band_note = self.no_trade_band(w, state.current_weight, f, sym, state.book)
        if band_note:
            notes.append(band_note)
        approved = np.sign(w) == np.sign(p.target_weight)

        # Protective levels must match the final direction: keep the trader's when
        # the direction is unchanged (and they are sane), rebuild them otherwise.
        direction = float(np.sign(w))
        fallback = protective_levels(direction, state.last_price, f["atr14"], self.config["risk"])
        if direction == np.sign(p.target_weight):
            stop, take = sane_levels(direction, state.last_price, p.stop_loss, p.take_profit, fallback)
        else:
            stop, take = fallback
        d = FinalDecision(
            state.instrument.symbol,
            state.as_of,
            action_for(w, state.debate.score, thr),
            round(w, 4),
            conf,
            stop,
            take,
            rationale,
            bool(approved),
            notes,
            source,
            kept=band_note is not None,
            models_served=tuple(sorted({c["model_served"] for c in state.llm_calls if c.get("model_served")})),
            rule_weight=round(rule_w, 6),
            model_weight=None if model_w is None else round(model_w, 6),
        )
        state.decision = d
        return d

    def bound_model_weight(self, model_w: float, rule_w: float, state: TradingState | None = None) -> tuple[float, list[str]]:
        """Round 1 (A3, owner decision D4): the model PM may move the weight at most
        ``risk.pm_model_band`` (default 0.25) away from the rules weight computed on the same
        inputs, and every gap above ``risk.pm_model_flag`` (default 0.10) is logged and noted on
        the decision. Returns ``(bounded weight, notes)``; the guardrails run afterwards."""
        rcfg = self.config.get("risk", {})
        band = float(rcfg.get("pm_model_band", 0.25))
        flag = float(rcfg.get("pm_model_flag", 0.10))
        if not (math.isfinite(band) and band >= 0) or not (math.isfinite(flag) and flag >= 0):
            raise ValueError(f"risk.pm_model_band {band} and risk.pm_model_flag {flag} must be finite and >= 0")
        gap = model_w - rule_w
        bounded = min(rule_w + band, max(rule_w - band, model_w))
        notes: list[str] = []
        if abs(gap) > flag + 1e-12:
            where = f"{state.instrument.symbol} {state.as_of}" if state is not None else "decision"
            note = f"PM model weight {model_w:+.2f} vs rules {rule_w:+.2f} (gap {abs(gap):.2f} > flag {flag:.2f})" + (
                f"; bounded to {bounded:+.2f} (band {band:.2f})" if abs(bounded - model_w) > 1e-12 else ""
            )
            log.warning("%s: %s", where, note)
            notes.append(note)
        return bounded, notes

    def no_trade_band(
        self, w: float, current: float | None, f: dict[str, Any], symbol: str | None = None, book: Book | None = None
    ) -> tuple[float, str | None]:
        """Keep the current position when the new target is within ``rebalance_band`` of it.

        Small target changes cost spread and commission without changing the risk
        materially. The current position is kept only if it would itself pass every
        firm limit today, so the band can never hold a position the limits forbid. A
        note is returned exactly when the position is kept (``FinalDecision.kept``); any
        other outcome is a target the backtester trades, cap included.
        """
        band = f.get("rebalance_band", 0.0)
        if current is None or band <= 0 or w == current or abs(w - current) >= band:
            return w, None
        kept, fixes = self.guardrails(current, f, symbol, book)
        if fixes or kept != current:
            return w, None
        return current, f"within no-trade band ({abs(w - current):.2f} < {band:.2f}): keep {current:+.2f}"


def run_risk_team(state: TradingState, analysts: list[RiskAnalyst], pm: PortfolioManager, rounds: int) -> FinalDecision:
    f = risk_facts(state, pm.config)
    views: list[RiskView] = []
    for rnd in range(1, max(1, rounds) + 1):
        for a in analysts:
            views.append(a.speak(state, f, rnd, views))
    state.risk_views = views
    return pm.run(state, f)


def _pct(x) -> str:
    return "n/a" if x is None else f"{x:.1%}"
