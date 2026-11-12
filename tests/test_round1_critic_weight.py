"""Round 1, lane S2: the model-to-weight path (review findings A3-A8, A12, A17) and the critic
and guardrail boundaries that survived the mutation spot check (R3, C2, C3, C8).

Every test states, in its docstring, what the pre-Round-1 code did on the same input. Offline:
no model, no network, no Ollama (fake LLMs and a stubbed digest lookup only)."""
import json
import math
from datetime import date

import numpy as np
import pandas as pd
import pytest

from agentic_trader import TradingGraph, make_config
from agentic_trader.agentic.critic import Critic, apply_weight_rule
from agentic_trader.agentic.domain import Finding, Task
from agentic_trader.agentic.evidence import EvidenceStore
from agentic_trader.agentic.reporter import build_report, number_audit
from agentic_trader.agents.risk import PortfolioManager, risk_facts
from agentic_trader.instruments import Instrument
from agentic_trader.local_llm import LocalLLM, ModelDigestMismatch
from agentic_trader.memory import DecisionMemory
from agentic_trader.state import (Action, AnalystReport, DebateOutcome, FinalDecision, RiskView, TradeProposal,
                                  TradingState)
from agentic_trader.text_analysts import MAX_CLAIMS, FundamentalsTextAnalyst, MacroTextAnalyst, quote_problem

AS_OF = date(2024, 3, 1)
BASE = make_config(memory_path=None, agentic={"llm_critic": False})


def _history(n=60):
    idx = pd.bdate_range(end=AS_OF, periods=n)
    c = 100 + np.arange(float(n)) + 3 * np.sin(np.arange(float(n)))
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1e6}, index=idx)


def _state(weight=0.2, symbol="AAPL", diverge=True, stop=None, take=None, source="rules", rule_weight=None):
    st = TradingState(Instrument.parse(symbol), AS_OF, _history())
    if diverge:
        st.reports["news"] = AnalystReport("news", 0.9, 0.6, "s", source="llm", rule_signal=-0.1)
    act = Action.BUY if weight > 0 else Action.SELL if weight < 0 else Action.HOLD
    st.decision = FinalDecision(symbol, AS_OF, act, weight, 0.7, stop, take, "r", source=source,
                                rule_weight=weight if rule_weight is None else rule_weight,
                                model_weight=weight if source == "llm" else None)
    return st


def _cfg(rule="scale", scale=0.5, **risk):
    return make_config(BASE, agentic={"critic_weight_rule": rule, "critic_weight_scale": scale}, risk=risk)


def _review(st, cfg, facts=None, findings=None, evidence=None):
    return Critic(cfg).review(st, findings or [], evidence or EvidenceStore(), facts)


def _check(rep, name):
    (c,) = [c for c in rep.checks if c.name == name]
    return c


# ================================================================ A4: an alarm never adds exposure
def test_a4_flag_on_an_equity_long_shrinks_it_instead_of_scaling_toward_neutral_one():
    """Old code: neutral 1.0 + 0.5 * (0.2 - 1.0) = +0.60, three times the PM's +0.20."""
    cfg = _cfg(max_var_95=0.0)            # default equity neutral weight is 1.0
    assert cfg["risk"]["neutral_weight"]["equity"] == 1.0
    st = _state(0.2)
    act = apply_weight_rule(st, _review(st, cfg), cfg)
    assert st.decision.target_weight == pytest.approx(0.1) and act["anchor_source"] == "flat"


def test_a4_veto_on_a_flat_equity_decision_does_not_open_a_long():
    """Old code: veto set the weight to the neutral 1.0 (then the guardrails trimmed it), so an
    alarm on a flat decision opened a long."""
    cfg = _cfg("veto", max_var_95=0.0)
    st = _state(0.0)
    apply_weight_rule(st, _review(st, cfg), cfg)
    assert st.decision.target_weight == 0.0 and st.decision.action is Action.HOLD


def test_a4_model_pm_is_pulled_toward_its_rules_weight():
    """Old code: 1.0 + 0.5 * (0.8 - 1.0) = +0.90 (toward neutral); now 0.1 + 0.5 * 0.7 = +0.45."""
    cfg = _cfg(max_var_95=0.0)
    st = _state(0.8, source="llm", rule_weight=0.1)
    act = apply_weight_rule(st, _review(st, cfg), cfg)
    assert act["anchor_source"] == "rules" and act["anchor"] == pytest.approx(0.1)
    assert st.decision.target_weight == pytest.approx(0.45)
    assert "toward rules" in st.decision.adjustments[-1]


def test_a4_rules_weight_larger_than_the_decision_is_capped_at_the_decision_size():
    """Old code would move toward whatever anchor it had, larger or not; now |after| <= |before|."""
    cfg = _cfg("veto", max_var_95=0.0)
    st = _state(0.2, source="llm", rule_weight=0.9)
    apply_weight_rule(st, _review(st, cfg), cfg)
    assert st.decision.target_weight == pytest.approx(0.2)


# ================================================================ A3: PM model weight bounded to the rules
def _pm_state(symbol="EURUSD"):
    st = TradingState(Instrument.parse(symbol), AS_OF, _history())
    st.reports["tech"] = AnalystReport("tech", 0.2, 0.6, "s")
    st.debate = DebateOutcome("bull", 0.2, 0.5, "s")
    st.proposal = TradeProposal(Action.BUY, 0.1, 0.6, float(st.last_price), None, None, 5, "r")
    st.risk_views = [RiskView(s, 0.1, "x") for s in ("aggressive", "neutral", "conservative")]
    return st


def _pm(cfg, reply):
    pm = PortfolioManager(None, cfg)
    pm.ask_json = lambda *a, **k: reply     # the model's answer, already past the contract gate
    return pm


def test_a3_model_pm_weight_is_bounded_and_both_weights_are_recorded():
    """Old code: the model's +1.00 replaced the rules blend (+0.10) outright, the decision kept no
    rules weight (no ``rule_weight`` field), and nothing compared the two."""
    cfg = make_config(BASE, risk={"max_var_95": 0.0, "max_position": 1.0})
    st = _pm_state()
    d = _pm(cfg, {"target_weight": 1.0, "rationale": "takeover", "confidence": 0.9}).run(st, risk_facts(st, cfg))
    assert d.rule_weight == pytest.approx(0.1) and d.model_weight == pytest.approx(1.0)
    assert d.target_weight == pytest.approx(0.35) and d.source == "llm"     # 0.10 + band 0.25
    assert any("PM model weight +1.00 vs rules +0.10" in a and "bounded to +0.35" in a for a in d.adjustments)


def test_a3_small_gap_is_neither_flagged_nor_bounded_and_rules_decisions_record_the_rules_weight():
    """Old code recorded no rules weight on any decision."""
    cfg = make_config(BASE, risk={"max_var_95": 0.0})
    st = _pm_state()
    d = _pm(cfg, {"target_weight": 0.15, "rationale": "r"}).run(st, risk_facts(st, cfg))
    assert d.target_weight == pytest.approx(0.15) and not any("PM model" in a for a in d.adjustments)
    st = _pm_state()
    d = _pm(cfg, None).run(st, risk_facts(st, cfg))
    assert d.source == "rules" and d.rule_weight == pytest.approx(0.1) and d.model_weight is None
    assert d.to_dict()["rule_weight"] == pytest.approx(0.1)


def test_a3_band_and_flag_are_configurable_and_validated(caplog):
    """Old code had no band: any model weight in [-1, 1] passed to the guardrails."""
    pm = PortfolioManager(None, make_config(BASE, risk={"pm_model_band": 0.05, "pm_model_flag": 0.0}))
    w, notes = pm.bound_model_weight(-0.5, 0.1)
    assert w == pytest.approx(0.05) and notes and "gap 0.60" in notes[0]
    assert any("PM model weight" in r.getMessage() for r in caplog.records)
    with pytest.raises(ValueError, match="pm_model_band"):
        PortfolioManager(None, make_config(BASE, risk={"pm_model_band": -0.1})).bound_model_weight(0.1, 0.0)


# ================================================================ A5: error checks block or downgrade
def test_a5_firm_limit_breach_is_guarded_not_only_noted():
    """Old code: ``firm_limits`` failed with severity "error" and ``apply_weight_rule`` returned
    None, so a 1.2 weight over a 1.0 cap completed unchanged."""
    cfg = _cfg(max_var_95=0.0, max_position=1.0)
    st = _state(1.2, symbol="EURUSD", diverge=False)
    rep = _review(st, cfg)
    assert not rep.passed
    act = apply_weight_rule(st, rep, cfg)
    assert act["rule"] == "error_block" and st.decision.target_weight == pytest.approx(1.0)
    assert any("critic error block" in a for a in st.decision.adjustments)


def test_a5_short_under_long_only_goes_flat_and_rule_off_still_enforces_errors():
    """Old code: a -0.3 equity short under a long-only policy was flagged and kept, also with the
    weight rule switched off."""
    cfg = _cfg("off", max_var_95=0.0)
    st = _state(-0.3, diverge=False)
    act = apply_weight_rule(st, _review(st, cfg), cfg)
    assert act is not None and st.decision.target_weight == 0.0


def test_a5_wrong_side_stop_is_cleared():
    """Old code: a long with its stop above the entry failed ``protective_levels`` and shipped."""
    cfg = _cfg(max_var_95=0.0)
    st = _state(0.3, symbol="EURUSD", diverge=False)
    st.decision.stop_loss = st.last_price * 1.05
    act = apply_weight_rule(st, _review(st, cfg), cfg)
    assert st.decision.stop_loss is None and act["errors"]["cleared_levels"] == ["stop_loss"]
    assert st.decision.target_weight == pytest.approx(0.3)


def test_a5_unresolved_evidence_downgrades_confidence():
    """Old code: the review failed but the decision's confidence multiplier stayed at 1.0."""
    cfg = _cfg(max_var_95=0.0)
    st = _state(0.3, symbol="EURUSD", diverge=False)
    rep = _review(st, cfg, findings=[Finding.make("news", "c", 0.8, ["EV-missing"])])
    assert rep.multiplier == 1.0
    apply_weight_rule(st, rep, cfg)
    assert rep.multiplier == pytest.approx(0.5)


# ================================================================ A6: VaR checked or said to be unchecked
def test_a6_no_risk_facts_says_var_not_checked():
    """Old code: with no risk facts the detail read "size, shorting and VaR within limits"."""
    st = _state(0.3, symbol="EURUSD", diverge=False)
    c = _check(_review(st, _cfg()), "firm_limits")
    assert c.passed and "VaR not checked" in c.detail
    c = _check(_review(st, _cfg(), facts={"var_95_1d": 0.01}), "firm_limits")
    assert "VaR within limits" in c.detail and "not checked" not in c.detail


def test_a6_graph_critic_gets_risk_facts_and_catches_a_var_breach():
    """Old code: ``run_critic`` passed no risk facts, so a decision over the VaR cap passed."""
    cfg = make_config(BASE, risk={"max_var_95": 0.001})
    g = TradingGraph(cfg, memory=DecisionMemory(None), on_event=lambda *_: None)
    st = _state(0.9, symbol="EURUSD", diverge=False)
    rep = g.run_critic(st)
    c = _check(rep, "firm_limits")
    assert not c.passed and "VaR" in c.detail
    f = risk_facts(st, cfg)
    assert abs(st.decision.target_weight) * f["var_95_1d"] <= 0.001 + 1e-9    # and the block acted


# ================================================================ mutation survivors: exact limit values
def test_r3_short_notional_cap_binds_between_one_and_two_caps():
    """Mutant R3 (cap applied only below -2 x cap) kept -0.40 here; the cap is 0.30."""
    cfg = make_config(BASE, risk={"max_var_95": 0.0})
    st = _state(0.0, symbol="EURUSD", diverge=False)
    f = {**risk_facts(st, cfg), "max_short_notional": 0.3}
    w, notes = PortfolioManager(None, cfg).guardrails(-0.4, f)
    assert w == pytest.approx(-0.3) and any("max short notional 0.30" in n for n in notes)
    w, notes = PortfolioManager(None, cfg).guardrails(-0.3, f)
    assert w == pytest.approx(-0.3) and not notes


@pytest.mark.parametrize("w,ok", [(1.0, True), (1.0 + 1e-10, True), (1.049, False), (1.001, False)])
def test_c2_critic_size_limit_is_exact(w, ok):
    """Mutant C2 (tolerance 1e-9 -> 0.05) passed |w| = max + 0.049; only w = -1.5 was tested."""
    st = _state(w, symbol="EURUSD", diverge=False)
    assert _check(_review(st, _cfg(max_position=1.0, max_var_95=0.0)), "firm_limits").passed is ok


@pytest.mark.parametrize("w,ok", [(-0.04, False), (-0.001, False), (0.0, True)])
def test_c3_any_short_fails_under_long_only(w, ok):
    """Mutant C3 (long-only check only below -0.05) passed a -0.04 equity short."""
    st = _state(w, symbol="AAPL", diverge=False)
    c = _check(_review(st, _cfg(max_var_95=0.0)), "firm_limits")
    assert c.passed is ok and (ok or "long-only" in c.detail)


@pytest.mark.parametrize("w,level,ok", [
    (0.3, "stop_at", False), (0.3, "stop_below", True), (0.3, "take_at", False),
    (-0.3, "stop_at", False), (-0.3, "stop_above", True), (-0.3, "take_at", False)])
def test_c8_protective_level_exactly_at_entry_fails(w, level, ok):
    """Mutant C8 (long stop ``<`` -> ``<=``) passed a stop exactly at the entry price."""
    st = _state(w, symbol="EURUSD", diverge=False)
    px = st.last_price
    levels = {"stop_at": (px, None), "take_at": (None, px), "stop_below": (px * 0.99, None),
              "stop_above": (px * 1.01, None)}
    st.decision.stop_loss, st.decision.take_profit = levels[level]
    assert _check(_review(st, _cfg()), "protective_levels").passed is ok


# ================================================================ A7: quote rules
class _Reply:
    def __init__(self, reply):
        self.reply = reply

    def complete_json(self, system, prompt, *, deep, schema):
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


class _Section:
    def __init__(self, text):
        from datetime import datetime, timezone
        self.symbol, self.accession, self.form, self.section = "WID", "0001-24-000001", "10-K", "7"
        self.visible_date, self.text = datetime(2024, 2, 1, 21, tzinfo=timezone.utc), text


SECTION = _Section("The company reported that revenue increased 12% on strong demand. Margins compressed "
                   "due to input costs. The outlook remains uncertain.")


def _claim(quote, direction="positive"):
    return {"claim": "c", "direction": direction, "accession": SECTION.accession, "section": "7", "quote": quote}


def test_a7_twenty_claims_quoting_the_count_for_nothing():
    """Old code: all 20 passed the substring check, net +20, signal +1.0."""
    out = FundamentalsTextAnalyst(_Reply({"claims": [_claim("the")] * 20})).analyze("WID", [SECTION])
    assert out.result["claims"] == [] and out.result["net_direction"] == 0 and len(out.dropped) == 20


def test_a7_short_or_stopword_quotes_duplicates_and_the_cap():
    """Old code kept every substring quote, repeats included, with no cap."""
    good = "revenue increased 12% on strong demand"
    claims = [_claim(good), _claim(good), _claim("that revenue"), _claim("Margins compressed due to input costs")]
    out = FundamentalsTextAnalyst(_Reply({"claims": claims})).analyze("WID", [SECTION])
    reasons = sorted(d["reason"] for d in out.dropped)
    assert len(out.result["claims"]) == 2 and out.result["net_direction"] == 2
    assert any("duplicate" in r for r in reasons) and any("shorter" in r for r in reasons)
    assert quote_problem("and it was on the way") == "quote has no content word"
    assert quote_problem("revenue increased sharply") is None
    words = SECTION.text.split()
    many = [_claim(" ".join(words[i:i + 4])) for i in range(len(words) - 4)]
    out = FundamentalsTextAnalyst(_Reply({"claims": many})).analyze("WID", [SECTION])
    assert len(out.result["claims"]) <= MAX_CLAIMS


# ================================================================ A8: NaN and range rejected, not clipped
CUR = "Inflation remains elevated; further tightening may be appropriate."


@pytest.mark.parametrize("shift", ["NaN", "Infinity", "-Infinity", "7", "-1.5", "true", "\"0.5\""])
def test_a8_bad_shift_is_rejected(shift):
    """Old code: NaN became +1.0 (max(-1, min(1, nan)) is 1.0) and 7 was clipped to +1.0."""
    reply = '{"stance": "neutral", "shift": %s, "quotes": ["further tightening may be appropriate"]}' % shift
    out = MacroTextAnalyst(_Reply(reply)).analyze(CUR)
    assert not out.ok and "shift" not in out.result


def test_a8_valid_shift_and_repeated_quotes():
    reply = {"stance": "hawkish", "shift": 1, "quotes": ["further tightening may be appropriate"] * 3}
    out = MacroTextAnalyst(_Reply(reply)).analyze(CUR)
    assert out.ok and out.result["shift"] == 1.0 and len(out.result["quotes"]) == 1 and len(out.dropped) == 2
    assert math.isfinite(out.result["shift"])


# ================================================================ A12: signed audit that blocks
def test_a12_number_audit_compares_signs():
    """Old code: "+0.60" and "0.60" matched a fact of -0.60 (abs on both sides)."""
    facts = {"target_weight": -0.6, "confidence": 0.51}
    assert number_audit("SELL at -0.60, confidence 0.51", facts) == []
    assert number_audit("BUY at +0.60", facts) == ["+0.60"]
    assert number_audit("weight 0.60", facts) == ["0.60"]
    assert number_audit("confidence -0.51", facts) == ["-0.51"]
    assert number_audit("weight 60%", {"target_weight": 0.6}) == []


class _Narrator:
    def __init__(self, text):
        self.text = text

    def complete(self, system, prompt, *, deep):
        return self.text


def _report(text):
    st = _state(-0.6, symbol="EURUSD", diverge=False)
    rep = Critic(BASE).review(st, [], EvidenceStore())
    return build_report(Task("EURUSD", AS_OF), st, [], rep, EvidenceStore(), _Narrator(text))


@pytest.mark.parametrize("text,why", [
    ("Buy, target weight +0.60, approved by risk.", "+0.60"),
    ("Sell -0.60. Details at www.example.com today.", "output guard"),
    ("Sell -0.60 and buy TSLA as a hedge.", "output guard"),
])
def test_a12_failing_model_narrative_is_replaced_by_the_template(text, why):
    """Old code shipped each of these model narratives (narrative_source "llm") with at most a
    warning line; the URL and foreign ticker were not checked at all."""
    r = _report(text)
    assert r.narrative_source == "template" and r.rejected_narrative == text and text not in r.narrative
    assert any(why in w for w in r.warnings) and any("rejected" in w for w in r.warnings)
    assert r.to_dict()["rejected_narrative"] == text


def test_a12_clean_model_narrative_ships():
    r = _report("EUR/USD: SELL with a target weight of -0.60 after the desk review.")
    assert r.narrative_source == "llm" and r.rejected_narrative is None and r.warnings == []


# ================================================================ A17: pinned digest enforced
PIN = "a" * 64


def _local(pin, served):
    llm = LocalLLM({"llm_provider": "local", "local_llm_model": "qwen-test", "local_llm_digest": pin})
    seen = {"digest": 0, "post": 0}

    def digest(url, model):
        seen["digest"] += 1
        return None if served is None else {"name": model, "digest": served}

    def post(body):
        seen["post"] += 1
        return {"model": body["model"], "message": {"content": "ok"}, "done": True, "done_reason": "stop"}
    llm._digest_fn, llm._post = digest, post
    return llm, seen


def test_a17_digest_mismatch_or_unlisted_model_stops_before_any_call():
    """Old code stored ``local_llm_digest`` and never compared it: a re-pulled model with new
    weights under the same name answered every call."""
    for served in ("b" * 64, None):
        llm, seen = _local(PIN, served)
        with pytest.raises(ModelDigestMismatch):
            llm.complete("s", "p", deep=False)
        assert seen["post"] == 0


def test_a17_matching_pin_is_checked_once_and_no_pin_checks_nothing():
    llm, seen = _local("sha256:" + PIN[:12].upper(), "sha256:" + PIN)
    assert llm.complete("s", "p", deep=False) == "ok" and llm.complete("s", "p", deep=False) == "ok"
    assert seen == {"digest": 1, "post": 2}
    llm, seen = _local(None, "b" * 64)
    assert llm.complete("s", "p", deep=False) == "ok" and seen["digest"] == 0
    with pytest.raises(ValueError, match="local_llm_digest"):
        LocalLLM({"llm_provider": "local", "local_llm_model": "m", "local_llm_digest": "abc"})


# ---------------------------------------------------------------- integration: the trader stage
def test_trader_model_weight_is_bounded_to_the_rules_weight(caplog: pytest.LogCaptureFixture) -> None:
    """Lane S2 left the trader open: a model trader could write +0.9 where its own rules said
    about 0, and the PM's 'rules' blend then started from the model's figure. The trader's
    model weight is now held within risk.trader_model_band of the rules weight, the gap is
    logged, and both figures are kept on the proposal."""
    import logging
    from datetime import date
    from types import SimpleNamespace

    from agentic_trader.agents.trader import Trader
    from agentic_trader.config import make_config
    from agentic_trader.state import Action

    cfg = make_config()
    trader = Trader(None, cfg)
    debate = SimpleNamespace(score=0.0, winner="neutral", conviction=0.5, untrusted=False)
    neutral = cfg["risk"].get("neutral_weight", {}).get("equity", 0.0)    # the rules weight at score 0
    band, flag = cfg["risk"]["pm_model_band"], cfg["risk"]["pm_model_flag"]
    replies = iter([{"action": "SELL", "target_weight": neutral - 0.9, "rationale": "strong conviction"},
                    {"action": "HOLD", "target_weight": neutral - flag / 2, "rationale": "small"}])
    trader.ask_json = lambda *a, **k: next(replies)             # type: ignore[method-assign]

    def state() -> SimpleNamespace:
        return SimpleNamespace(
            debate=debate, last_price=100.0, forecast=None, current_weight=None, track_record={},
            instrument=SimpleNamespace(symbol="AAPL", display="AAPL", asset_class="equity", is_fx=False),
            as_of=date(2020, 1, 2), reports={}, untrusted_inputs=False, proposal=None,
            history=None, px=lambda v: v, unpx=lambda v: v, reports_digest=lambda: "",
            verdict_block=lambda: "", lessons_block=lambda: "", evidence=[], policy_hits=[])
    import agentic_trader.agents.trader as tr
    orig_atr, orig_short, orig_pp = tr.atr14, tr.allow_short, tr.policy_passages
    tr.atr14, tr.allow_short, tr.policy_passages = (lambda s: 2.0), (lambda s, c: True), (lambda s: "")
    try:
        with caplog.at_level(logging.WARNING):
            far = trader.run(state())
        near = trader.run(state())
    finally:
        tr.atr14, tr.allow_short, tr.policy_passages = orig_atr, orig_short, orig_pp
    assert far.rule_weight == pytest.approx(neutral) and far.model_weight == pytest.approx(neutral - 0.9)
    assert far.target_weight == pytest.approx(neutral - band) and far.source == "llm"
    assert "bounded to" in far.rationale and "trader model weight" in caplog.text
    assert isinstance(far.action, Action)
    assert near.target_weight == pytest.approx(neutral - flag / 2) and "trader model weight" not in near.rationale
    assert near.rule_weight == pytest.approx(neutral)
