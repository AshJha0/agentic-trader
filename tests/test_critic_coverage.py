"""Branch coverage for ``agentic/critic.py``: every check in pass and fail, the divergence
threshold edge, the three weight rules and their config errors, and a property test that the
post-rule weight always sits inside the guardrail limits. Offline, no model."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st_

from agentic_trader import make_config
from agentic_trader.agentic.critic import (Critic, CriticReport, apply_weight_rule, decision_untrusted,
                                           findings_block)
from agentic_trader.agentic.domain import Finding
from agentic_trader.agentic.evidence import EvidenceStore, EvidenceType
from agentic_trader.agents.risk import position_var, risk_facts
from agentic_trader.instruments import Instrument
from agentic_trader.state import (Action, AnalystReport, DebateOutcome, FinalDecision, RiskView,
                                  TradeProposal, TradingState)

AS_OF = date(2024, 3, 1)
BASE = make_config(memory_path=None)


def _history(n=60, wiggle=True):
    idx = pd.bdate_range(end=AS_OF, periods=n)
    c = 100 + np.arange(float(n))
    if wiggle:
        c = c + 3 * np.sin(np.arange(float(n)))      # a non-zero loss tail, so the VaR cap can bind
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)


def _state(weight=0.3, model=0.9, rules=-0.1, symbol="AAPL", stop=None, take=None, action=None):
    st = TradingState(Instrument.parse(symbol), AS_OF, _history())
    if model is not None:
        st.reports["news"] = AnalystReport("news", model, 0.6, "s", source="llm", rule_signal=rules)
    act = action or (Action.BUY if weight > 0 else Action.SELL if weight < 0 else Action.HOLD)
    st.decision = FinalDecision(symbol, AS_OF, act, weight, 0.7, stop, take, "r")
    return st


def _cfg(rule="scale", scale=0.5, equity=1.0, fx=0.0, **risk):
    return make_config(BASE, agentic={"critic_weight_rule": rule, "critic_weight_scale": scale, "llm_critic": False},
                       risk={"neutral_weight": {"equity": equity, "fx": fx}, **risk})


def _review(st, cfg, findings=None, evidence=None, facts=None, llm=None):
    return Critic(cfg, llm).review(st, findings or [], evidence or EvidenceStore(), facts)


def _check(rep, name):
    return [c for c in rep.checks if c.name == name]


# ---------------------------------------------------------------- check 2: divergence threshold edge
@pytest.mark.parametrize("model,flagged", [(0.6, False), (0.6001, True), (0.5999, False)])
def test_divergence_threshold_edge(model, flagged):
    st = _state(model=model, rules=0.0)
    rep = _review(st, _cfg())
    assert rep.divergence_flagged is flagged
    assert rep.multiplier == (pytest.approx(0.7) if flagged else 1.0)


def test_divergence_halves_the_analyst_findings_and_ignores_abstained_or_rules_reports():
    st = _state(model=0.9, rules=-0.1)
    st.reports["tech"] = AnalystReport("tech", 0.9, 0.6, "s", source="rules", rule_signal=-0.9)
    st.reports["fund"] = AnalystReport("fund", 0.9, 0.6, "s", source="llm", rule_signal=-0.9, abstained=True)
    ev = EvidenceStore()
    e1, e2 = (ev.record(EvidenceType.DECISION, "t", "s", {}, "c").id for _ in range(2))
    f_news = Finding.make("news", "c", 0.8, [e1, e2])
    f_tech = Finding.make("tech", "c", 0.8, [e1, e2])
    rep = _review(st, _cfg(), [f_news, f_tech], ev)
    assert len([c for c in _check(rep, "model_rule_divergence") if not c.passed]) == 1
    assert f_news.confidence == pytest.approx(0.4) and f_tech.confidence == pytest.approx(0.8)


# ---------------------------------------------------------------- checks 1 and 7: evidence, single-evidence cap
def test_unresolved_evidence_fails_the_review_and_zeroes_the_finding():
    st = _state(model=None)
    f = Finding.make("news", "c", 0.8, ["EV-missing"])
    rep = _review(st, _cfg(), [f])
    (c,) = _check(rep, "evidence_resolves")
    assert not c.passed and c.severity == "error" and not rep.passed and f.confidence == 0.0
    assert rep.failed and rep.to_dict()["passed"] is False


def test_resolved_evidence_passes_and_single_evidence_is_capped():
    st = _state(model=None)
    ev = EvidenceStore()
    e = ev.record(EvidenceType.DECISION, "t", "s", {}, "c").id
    f = Finding.make("news", "c", 0.9, [e, e])          # duplicates count once
    rep = _review(st, _cfg(), [f], ev)
    assert _check(rep, "evidence_resolves")[0].passed and f.confidence == 0.6
    assert _check(rep, "single_evidence_cap")


# ---------------------------------------------------------------- check 3: contradictions
def test_analyst_contradiction_pass_and_fail():
    st = _state(model=None)
    st.reports["bull"] = AnalystReport("bull", 0.8, 0.6, "s")
    st.reports["bear"] = AnalystReport("bear", -0.8, 0.6, "s")
    st.debate = DebateOutcome("bull", 0.5, 0.5, "s")
    rep = _review(st, _cfg())
    assert not _check(rep, "analyst_contradiction")[0].passed and rep.multiplier == pytest.approx(0.8)
    st.debate = DebateOutcome("balanced", 0.0, 0.5, "s")
    assert _check(_review(st, _cfg()), "analyst_contradiction")[0].passed
    st.reports.pop("bear")
    st.reports["x"] = AnalystReport("x", 0.1, 0.6, "s")
    assert _check(_review(st, _cfg()), "analyst_contradiction")[0].passed


def test_single_vote_skips_the_contradiction_check():
    st = _state(model=None)
    st.reports["only"] = AnalystReport("only", 0.8, 0.6, "s")
    assert not _check(_review(st, _cfg()), "analyst_contradiction")


# ---------------------------------------------------------------- check 4: firm limits
def test_firm_limits_pass():
    st = _state(weight=0.3, model=None)
    assert _check(_review(st, _cfg(), facts={"var_95_1d": 0.01}), "firm_limits")[0].passed


def test_firm_limits_fail_on_size_short_and_var():
    st = _state(weight=-1.5, model=None, symbol="AAPL")
    (c,) = _check(_review(st, _cfg(), facts={"var_95_1d": 0.01, "var_95_1d_short": 0.05}), "firm_limits")
    assert not c.passed and "max" in c.detail and "long-only" in c.detail and "VaR" in c.detail


def test_firm_limits_short_var_falls_back_to_long_tail_when_missing():
    st = _state(weight=-0.5, model=None, symbol="EURUSD")
    (c,) = _check(_review(st, _cfg(), facts={"var_95_1d": 0.1}), "firm_limits")
    assert not c.passed and "VaR" in c.detail


# ---------------------------------------------------------------- check 5: protective levels
@pytest.mark.parametrize("w,stop,take,ok", [
    (0.3, 150.0, 200.0, True), (0.3, 170.0, None, False), (0.3, None, 150.0, False),
    (-0.3, 200.0, 150.0, True), (-0.3, 150.0, None, False), (-0.3, None, 200.0, False),
    (0.0, 1.0, 1.0, True)])
def test_protective_levels(w, stop, take, ok):
    st = _state(weight=w, model=None, symbol="EURUSD", stop=stop, take=take)
    assert _check(_review(st, _cfg()), "protective_levels")[0].passed is ok


# ---------------------------------------------------------------- check 6: direction vs verdict
def _with_proposal(st, w, winner, approved=True, adjustments=()):
    st.proposal = TradeProposal(Action.BUY, w, 0.6, 100.0, None, None, 5, "r")
    st.debate = DebateOutcome(winner, 0.0, 0.5, "s")
    st.decision.approved = approved
    st.decision.adjustments = list(adjustments)
    return st


@pytest.mark.parametrize("w,winner,approved,adj,ok", [
    (0.5, "bull", True, (), True), (0.5, "balanced", True, (), True), (0.0, "bear", True, (), True),
    (0.5, "bear", True, (), False), (0.5, "bull", False, (), False), (0.5, "bull", False, ("x",), True)])
def test_direction_vs_verdict(w, winner, approved, adj, ok):
    st = _with_proposal(_state(weight=0.3, model=None, symbol="EURUSD"), w, winner, approved, adj)
    rep = _review(st, _cfg())
    assert _check(rep, "direction_vs_verdict")[0].passed is ok
    assert (rep.multiplier < 1) is (not ok)


def test_no_decision_skips_decision_checks():
    st = _state(model=None)
    st.decision = None
    rep = _review(st, _cfg())
    assert not _check(rep, "firm_limits") and apply_weight_rule(st, rep, _cfg()) is None


# ---------------------------------------------------------------- optional model critique
class _LLM:
    def __init__(self, reply):
        self.reply = reply

    def complete(self, system, prompt, deep=True):
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


@pytest.mark.parametrize("reply,mult,problem", [
    ('{"concerns": ["thin"], "confidence_multiplier": 0.5}', 0.5, None),
    ('{"concerns": "thin", "confidence_multiplier": 0.9}', 0.9, "not a list"),
    ('{"confidence_multiplier": true}', None, "concerns missing"),
    ('{"concerns": [], "confidence_multiplier": "abc"}', None, "not a number"),
    ("no json here", None, "not a JSON object"),
    (RuntimeError("down"), None, "RuntimeError"),
])
def test_llm_critique_outcomes(reply, mult, problem):
    st = _state(weight=0.3, model=None)
    cfg = make_config(_cfg(), agentic={"llm_critic": True})
    rep = _review(st, cfg, llm=_LLM(reply))
    assert rep.llm_multiplier == mult
    bad = _check(rep, "llm_critique_wellformed")
    assert (problem is None and not bad) or (problem in bad[0].detail)
    if mult is not None:
        assert rep.multiplier == pytest.approx(mult)


def test_llm_critique_fences_an_untrusted_rationale():
    st = _state(weight=0.3, model=None)
    st.reports["news"] = AnalystReport("news", 0.1, 0.6, "s", untrusted=True)
    seen = {}

    class Rec(_LLM):
        def complete(self, system, prompt, deep=True):
            seen["p"] = prompt
            return '{"concerns": [], "confidence_multiplier": 1}'
    _review(st, make_config(_cfg(), agentic={"llm_critic": True}), llm=Rec(None))
    assert "untrusted_data" in seen["p"] and decision_untrusted(st)


def test_llm_critic_off_in_config_drops_the_model():
    assert Critic(_cfg(), _LLM("{}")).llm is None


def test_findings_block_fences_untrusted_claims():
    fs = [Finding.make("a", "plain", 0.5, []), Finding.make("b", "quoted", 0.5, [], untrusted=True)]
    out = findings_block(fs)
    assert "plain (confidence 0.50)" in out and "untrusted_data" in out
    assert "confidence" not in findings_block(fs[:1], confidence=False)
    risky = _state(model=None)
    risky.risk_views = [RiskView("neutral", 0.1, "x", untrusted=True)]
    assert decision_untrusted(risky)


# ---------------------------------------------------------------- weight rules
def test_invalid_rule_and_scale_raise():
    st = _state()
    rep = _review(st, _cfg())
    with pytest.raises(ValueError, match="critic_weight_rule"):
        apply_weight_rule(st, rep, _cfg("bogus"))
    for bad in (-0.01, 1.01):
        with pytest.raises(ValueError, match="critic_weight_scale"):
            apply_weight_rule(st, rep, _cfg("scale", bad))


def test_rule_off_does_nothing():
    st = _state()
    assert apply_weight_rule(st, _review(st, _cfg()), _cfg("off")) is None and st.decision.target_weight == 0.3


def test_scale_zero_moves_to_neutral_and_scale_one_keeps_the_weight():
    st = _state(symbol="EURUSD")
    act = apply_weight_rule(st, _review(st, _cfg()), _cfg("scale", 0.0))
    assert act["to"] == 0.0 and st.decision.action is Action.HOLD and st.decision.stop_loss is None
    st = _state(symbol="EURUSD")
    act = apply_weight_rule(st, _review(st, _cfg()), _cfg("scale", 1.0))
    assert not act["changed"] and not act["guardrail_clipped"] and st.decision.adjustments == []
    assert act["scale"] == 1.0


def test_veto_records_no_scale_and_short_neutral_sets_sell():
    st = _state(weight=0.3, symbol="EURUSD")
    act = apply_weight_rule(st, _review(st, _cfg()), _cfg("veto", fx=-0.2))
    assert act["scale"] is None and act["to"] == pytest.approx(-0.2) and st.decision.action is Action.SELL


def test_sign_flip_follows_new_sign_and_clears_wrong_side_levels():
    # FX short -0.4, strategic +0.5, scale 0.2: 0.5 + 0.2 * (-0.9) = +0.32, now a long;
    # the short's stop (above) and target (below) are both on the wrong side for a long.
    st = _state(weight=-0.4, symbol="EURUSD", stop=200.0, take=120.0)
    act = apply_weight_rule(st, _review(st, _cfg()), _cfg("scale", 0.2, fx=0.5, max_var_95=0.0))
    d = st.decision
    assert act["to"] == pytest.approx(0.32) and d.action is Action.BUY
    assert d.stop_loss is None and d.take_profit is None and d.kept is False


def test_long_to_short_clears_long_levels_and_right_side_levels_survive():
    st = _state(weight=0.3, symbol="EURUSD", stop=150.0, take=170.0)
    apply_weight_rule(st, _review(st, _cfg()), _cfg("veto", fx=-0.3, max_var_95=0.0))
    assert st.decision.action is Action.SELL and st.decision.stop_loss is None and st.decision.take_profit is None
    st = _state(weight=0.6, symbol="EURUSD", stop=150.0, take=170.0)
    apply_weight_rule(st, _review(st, _cfg()), _cfg("scale", 0.5, max_var_95=0.0))
    assert st.decision.stop_loss == 150.0 and st.decision.take_profit == 170.0


def test_flat_from_sell_keeps_sell_action_label():
    st = _state(weight=-0.3, symbol="EURUSD", stop=200.0, take=120.0)
    apply_weight_rule(st, _review(st, _cfg()), _cfg("veto"))
    assert st.decision.target_weight == 0.0 and st.decision.stop_loss is None and st.decision.take_profit is None


def test_fx_neutral_zero_vs_equity_neutral_one_on_default_neutrals():
    cfg = make_config(BASE, agentic={"llm_critic": False}, risk={"max_var_95": 0.0})
    fx = _state(weight=0.3, symbol="EURUSD")
    eq = _state(weight=0.3, symbol="AAPL")
    a_fx = apply_weight_rule(fx, _review(fx, cfg), cfg)
    a_eq = apply_weight_rule(eq, _review(eq, cfg), cfg)
    assert a_fx["neutral"] == 0.0 and a_fx["to"] == pytest.approx(0.15)
    assert a_eq["neutral"] == 1.0 and a_eq["to"] == pytest.approx(0.65)


def test_var_cap_clips_an_equity_long_and_uses_given_facts():
    cfg = _cfg("veto", max_var_95=0.01)
    st = _state(weight=0.3)
    f = risk_facts(st, cfg)
    act = apply_weight_rule(st, _review(st, cfg), cfg, f)
    assert act["guardrail_clipped"] and any("VaR" in n for n in act["guardrail_notes"])
    assert position_var(f, act["to"]) * abs(act["to"]) <= 0.01 + 1e-9


def test_report_to_dict_carries_the_action():
    rep = CriticReport()
    assert rep.passed and rep.to_dict()["weight_action"] is None and not rep.divergence_flagged


# ---------------------------------------------------------------- property: post-rule weight is admissible
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(w=st_.floats(-1.0, 1.0), neutral=st_.floats(-1.0, 1.5), scale=st_.floats(0.0, 1.0),
       rule=st_.sampled_from(["scale", "veto"]), symbol=st_.sampled_from(["AAPL", "EURUSD"]),
       mx=st_.floats(0.1, 1.0), var_cap=st_.sampled_from([0.0, 0.005, 0.02]))
def test_post_rule_weight_respects_the_guardrails(w, neutral, scale, rule, symbol, mx, var_cap):
    cfg = _cfg(rule, scale, equity=neutral, fx=neutral, max_position=mx, max_var_95=var_cap)
    st = _state(weight=w, symbol=symbol)
    act = apply_weight_rule(st, _review(st, cfg), cfg)
    if not act["changed"]:
        return                                  # the rule left the PM's (already guarded) weight alone
    to = st.decision.target_weight
    f = risk_facts(st, cfg)
    assert abs(to) <= mx + 1e-6
    if not f["short_selling_allowed"]:
        assert to >= 0
    if var_cap > 0 and to != 0:
        assert position_var(f, to) * abs(to) <= var_cap + 1e-6
    assert to == 0 or abs(to) >= cfg["risk"]["min_trade_weight"] - 1e-9
