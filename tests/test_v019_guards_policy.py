"""v0.19 coverage: firm-limit guardrails, the policy gate's six default rules and the
output contract. Offline and deterministic: no network, no model, no wall clock except
the policy's own ``date.today()`` (compared against fixed past/future dates)."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic_trader import contracts, make_config
from agentic_trader.agentic.domain import (Capability, PolicyOutcome, RiskLevel, Role, ToolAnnotations,
                                           ToolDescriptor, ToolRequest)
from agentic_trader.agentic.policy import (DEFAULT_RULES, AppendOnlyApprovalLog, AutoApprovalGateway,
                                           DenyApprovalGateway, PolicyEngine, QueuedApprovalGateway,
                                           SignedApprovalGateway, allow_rule, argument_guard_rule,
                                           capability_rule, deny_list_rule, read_only_rule, risk_level_rule,
                                           sign_approval)
from agentic_trader.agents.risk import PortfolioManager, RiskAnalyst, position_cvar, position_var

CFG = make_config(memory_path=None)
MIN_TRADE = CFG["risk"]["min_trade_weight"]


def _facts(**over):
    f = {"max_position": 1.0, "max_var_95": 0.02, "var_95_1d": 0.01, "var_95_1d_short": 0.015,
         "cvar_95_1d": 0.02, "cvar_95_1d_short": 0.03, "short_selling_allowed": True,
         "rebalance_band": 0.10, "atr14": 2.0, "max_short_notional": None, "proposed_weight": 0.5,
         "realized_vol_20d_annual": 0.2, "target_vol": 0.15}
    f.update(over)
    return f


# ------------------------------------------------------------------ guardrails
finite_w = st.floats(-5, 5, allow_nan=False)


@settings(max_examples=150, deadline=None)
@given(w=finite_w, mx=st.floats(0.05, 2.0), lim=st.floats(0.0, 0.05), var_l=st.floats(0.0, 0.1),
       var_s=st.floats(0.0, 0.1), shorts=st.booleans(),
       short_cap=st.one_of(st.none(), st.floats(0.0, 1.5)))
def test_guardrails_never_breach_a_limit(w, mx, lim, var_l, var_s, shorts, short_cap):
    pm = PortfolioManager(None, CFG)
    f = _facts(max_position=mx, max_var_95=lim, var_95_1d=var_l, var_95_1d_short=var_s,
               short_selling_allowed=shorts, max_short_notional=short_cap)
    out, notes = pm.guardrails(w, f)
    assert math.isfinite(out)
    assert abs(out) <= mx + 1e-12
    if not shorts:
        assert out >= 0.0
    if short_cap is not None:
        assert out >= -short_cap - 1e-12
    if lim > 0:
        assert position_var(f, out) * abs(out) <= lim + 1e-12
    assert out == 0.0 or abs(out) >= MIN_TRADE
    assert (out != w) <= bool(notes)          # every change is explained by a note
    assert pm.guardrails(out, f)[0] == pytest.approx(out)   # idempotent


def test_guardrails_notes_name_each_limit():
    pm = PortfolioManager(None, CFG)
    _, n = pm.guardrails(-0.5, _facts(short_selling_allowed=False))
    assert n == ["short selling not allowed -> flat"]
    w, n = pm.guardrails(-0.9, _facts(max_short_notional=0.3, max_var_95=0.0))
    assert w == pytest.approx(-0.3) and "max short notional" in n[0]
    w, n = pm.guardrails(-1.0, _facts(var_95_1d_short=0.04))     # short side uses the right tail
    assert w == pytest.approx(-0.5) and n[0].startswith("VaR limit")
    w, n = pm.guardrails(MIN_TRADE / 2, _facts())
    assert w == 0.0 and n == ["below minimum trade size -> flat"]


@settings(max_examples=100, deadline=None)
@given(w=st.floats(-1, 1), cur=st.one_of(st.none(), st.floats(-1, 1)), band=st.floats(0, 0.3))
def test_no_trade_band_keeps_only_a_compliant_position(w, cur, band):
    pm = PortfolioManager(None, CFG)
    f = _facts(rebalance_band=band, max_var_95=0.0)
    out, note = pm.no_trade_band(w, cur, f)
    if note is None:
        assert out == w
    else:
        assert out == cur and abs(w - cur) < band
        assert pm.guardrails(cur, f) == (cur, [])


def test_no_trade_band_refuses_to_keep_an_over_limit_position():
    pm = PortfolioManager(None, CFG)
    assert pm.no_trade_band(0.95, 1.0, _facts(max_position=0.9, max_var_95=0.0)) == (0.95, None)
    assert pm.no_trade_band(0.5, 0.5, _facts()) == (0.5, None)
    assert pm.no_trade_band(0.5, None, _facts()) == (0.5, None)
    assert pm.no_trade_band(0.5, 0.45, _facts(rebalance_band=0.0)) == (0.5, None)


def test_position_var_and_cvar_pick_the_side():
    f = _facts()
    assert position_var(f, 0.3) == 0.01 and position_var(f, -0.3) == 0.015
    assert position_cvar(f, 0.3) == 0.02 and position_cvar(f, -0.3) == 0.03


@pytest.mark.parametrize("stance", ["aggressive", "neutral", "conservative"])
@settings(max_examples=100, deadline=None)
@given(w0=st.floats(-1, 1), mx=st.floats(0.1, 1.0), vol=st.one_of(st.none(), st.floats(0.01, 1.0)))
def test_risk_analyst_rules_weight_within_max_position(stance, w0, mx, vol):
    a = RiskAnalyst(None, CFG, stance)
    w = a.rules_weight(_facts(proposed_weight=w0, max_position=mx, realized_vol_20d_annual=vol))
    assert math.isfinite(w) and abs(w) <= mx + 1e-12
    assert w == 0.0 or math.copysign(1, w) == math.copysign(1, w0)


def test_conservative_view_respects_var_and_aggressive_legacy_rule():
    a = RiskAnalyst(None, CFG, "conservative")
    w = a.rules_weight(_facts(proposed_weight=1.0, realized_vol_20d_annual=0.15, var_95_1d=0.2,
                              max_var_95=0.02))
    assert 0.2 * abs(w) <= 0.02 + 1e-12
    cfg = make_config(memory_path=None)
    cfg["risk"]["aggressive_vol_scaled"] = False
    agg = RiskAnalyst(None, cfg, "aggressive")
    assert agg.rules_weight(_facts(proposed_weight=0.4, realized_vol_20d_annual=0.6)) == pytest.approx(0.5)
    assert "Aggressive" in agg.role and agg.name == "aggressive_risk"


# ------------------------------------------------------------------ policy gate
def _tool(name="market_data.prices", read_only=True, risk=RiskLevel.LOW,
          required=frozenset({Capability.READ_MARKET_DATA})):
    return ToolDescriptor(name, name.split(".")[0], "t", {}, ToolAnnotations(read_only, risk, required))


def _req(tool="market_data.prices", **args):
    return ToolRequest(tool, args, "corr-1")


PAST = (date.today() - timedelta(days=30)).isoformat()
FUTURE = (date.today() + timedelta(days=30)).isoformat()


@pytest.mark.parametrize("args,ok", [
    ({}, True),
    ({"symbol": "AAPL"}, True),
    ({"symbol": "ZZZZ"}, False),                          # outside the universe
    ({"symbol": ""}, False),                              # unparseable
    ({"symbols": "AAPL"}, False),                         # not a list
    ({"symbols": ["AAPL", "MSFT"]}, True),
    ({"symbols": ["AAPL"] * 4}, False),                   # above the per-call cap
    ({"quantity": 10}, True),
    ({"quantity": 0}, False), ({"quantity": -1}, False), ({"quantity": True}, False),
    ({"quantity": float("nan")}, False), ({"quantity": "x"}, False), ({"quantity": None}, True),
    ({"as_of": PAST}, True), ({"end": FUTURE}, False), ({"start": "notadate"}, False),
    ({"as_of": date.today() + timedelta(days=1)}, False),
    ({"weight": 0.5}, True), ({"target_weight": -0.6}, False), ({"proposed_weight": "x"}, False),
    ({"weight": float("inf")}, False), ({"weight": True}, False),
    ({"current_weight": 3.0}, True),                      # a fact about the book, never capped
    ({"current_weight": float("nan")}, False),
    ({"lookback_days": 30}, True), ({"lookback_days": 0}, False), ({"lookback_days": 4000}, False),
    ({"lookback_days": "30"}, False),
    ({"notional": 500}, True), ({"notional": 5000}, False), ({"notional": -1}, False),
    ({"notional": "big"}, False), ({"notional": float("nan")}, False),
])
def test_argument_guard_matrix(args, ok):
    cfg = {"symbol_universe": ["aapl", "msft"], "max_symbols_per_call": 3, "max_position": 0.5,
           "max_order_notional": 1000}
    eng = PolicyEngine(cfg)
    d = eng.evaluate(_req(**args), _tool(), Role.ANALYST)
    if ok:
        assert d.outcome is PolicyOutcome.ALLOW
    else:
        assert (d.outcome, d.rule) == (PolicyOutcome.DENY, "argument_guard")


def test_default_rule_order_is_documented():
    assert DEFAULT_RULES == (deny_list_rule, capability_rule, argument_guard_rule, read_only_rule,
                             risk_level_rule, allow_rule)


@pytest.mark.parametrize("role,tool,args,expected", [
    # 1 deny list beats everything, even an admin
    (Role.ADMIN, _tool("ops.wipe"), {}, (PolicyOutcome.DENY, "deny_list")),
    # 2 capability: a viewer cannot run analytics
    (Role.VIEWER, _tool(required=frozenset({Capability.RUN_ANALYTICS})), {},
     (PolicyOutcome.DENY, "required_capabilities")),
    # capability precedes the argument guard
    (Role.VIEWER, _tool(required=frozenset({Capability.RUN_ANALYTICS})), {"symbol": ""},
     (PolicyOutcome.DENY, "required_capabilities")),
    # 3 a bad argument on a state-changing tool is refused, never parked for approval
    (Role.TRADER, _tool("execution.submit_order", False, RiskLevel.HIGH), {"quantity": -5},
     (PolicyOutcome.DENY, "argument_guard")),
    # 4 read-only: state change without PROPOSE_TRADES is denied ...
    (Role.RISK, _tool("execution.submit_order", False, RiskLevel.HIGH), {},
     (PolicyOutcome.DENY, "read_only")),
    # ... and with it needs approval (read-only rule decides before risk level)
    (Role.TRADER, _tool("execution.submit_order", False, RiskLevel.HIGH), {"quantity": 5},
     (PolicyOutcome.REQUIRE_APPROVAL, "read_only")),
    # 5 a read-only HIGH-risk tool still needs approval, even for an admin
    (Role.ADMIN, _tool("config.view", True, RiskLevel.HIGH), {}, (PolicyOutcome.REQUIRE_APPROVAL, "risk_level")),
    # 6 allow
    (Role.VIEWER, _tool(), {}, (PolicyOutcome.ALLOW, "default_allow")),
    (Role.ANALYST, _tool(risk=RiskLevel.MEDIUM), {}, (PolicyOutcome.ALLOW, "default_allow")),
])
def test_each_default_rule_decides_in_order(role, tool, args, expected):
    eng = PolicyEngine({"deny_tools": ["ops.wipe"]})
    d = eng.evaluate(_req(tool.name, **args), tool, role)
    assert (d.outcome, d.rule) == expected
    assert d.reason
    assert eng.decisions[-1] == (tool.name, d)


@settings(max_examples=100, deadline=None)
@given(role=st.sampled_from(list(Role)), read_only=st.booleans(), risk=st.sampled_from(list(RiskLevel)),
       req=st.frozensets(st.sampled_from(list(Capability)), max_size=3), denied=st.booleans(),
       w=st.one_of(st.none(), st.floats(allow_nan=True, allow_infinity=True)))
def test_policy_is_deterministic_and_first_decider_wins(role, read_only, risk, req, denied, w):
    tool = _tool("x.y", read_only, risk, req)
    args = {} if w is None else {"weight": w}
    eng = PolicyEngine({"deny_tools": ["x.y"] if denied else []})
    d1, d2 = eng.evaluate(_req("x.y", **args), tool, role), eng.evaluate(_req("x.y", **args), tool, role)
    assert d1 == d2
    from agentic_trader.agentic.policy import PolicyContext
    ctx = PolicyContext(_req("x.y", **args), tool, role, eng.capabilities(role), eng.config)
    first = next(r(ctx) for r in DEFAULT_RULES if r(ctx) is not None)
    assert first == d1
    if denied:
        assert d1.rule == "deny_list"
    if not read_only or risk is RiskLevel.HIGH:
        assert d1.outcome is not PolicyOutcome.ALLOW


def test_custom_rules_without_terminal_rule_fail_closed():
    eng = PolicyEngine(rules=(deny_list_rule,))
    d = eng.evaluate(_req(), _tool(), Role.ADMIN)
    assert (d.outcome, d.rule) == (PolicyOutcome.DENY, "no_rule")
    assert eng.capabilities(Role.VIEWER)
    assert PolicyEngine(role_capabilities={}).capabilities(Role.ADMIN) == frozenset()


# ------------------------------------------------------------------ approvals
def test_simple_gateways_and_queue_lifecycle():
    r = _req("execution.submit_order", quantity=1)
    assert AutoApprovalGateway().decide("t", r, "x") is True
    assert DenyApprovalGateway().decide("t", r, "x") is False
    q = QueuedApprovalGateway()
    assert q.decide("t1", r, "why") is None and q.decide("t1", r, "why") is None
    assert len(q.all()) == 1 and len(q.pending("t1")) == 1 and q.pending("other") == []
    a = q.pending()[0]
    assert q.get(a.id) is a
    with pytest.raises(KeyError):
        q.get("nope")
    with pytest.raises(KeyError):
        q.resolve("nope", True)
    q.resolve(a.id, True, "ann", "ok")
    with pytest.raises(ValueError):
        q.resolve(a.id, False)
    assert q.decide("t1", r, "why") is True
    q.decide("t2", r, "why")
    assert q.withdraw("t2") == 1 and q.pending("t2") == [] and q.decide("t2", r, "why") is None
    assert q.forget("t1") == 1 and q.forget("t1") == 0


class _Clock:
    """An injected clock that advances on every read."""

    def __init__(self, t=1000.0, step=1.0):
        self.t, self.step = t, step

    def __call__(self):
        self.t += self.step
        return self.t


def test_signed_gateway_quorum_ttl_and_log(tmp_path):
    log = AppendOnlyApprovalLog(tmp_path / "log.jsonl")
    clock = _Clock()
    keys = {"a": b"ka", "b": b"kb"}
    g = SignedApprovalGateway(keys, ttl_s=5, store=log, clock=clock)
    r = _req("execution.submit_order", quantity=1)
    assert g.needed("execution.submit_order") == 2 and g.needed("other") == 1
    assert g.decide("t", r, "x") is None
    aid = g.pending()[0].id
    with pytest.raises(ValueError):
        g.resolve(aid, True, "zed", signature="s")
    with pytest.raises(ValueError):
        g.resolve(aid, True, "a")
    with pytest.raises(ValueError):
        g.resolve(aid, True, "a", signature="bad")
    with pytest.raises(KeyError):
        g.resolve("nope", True, "a", signature="s")
    g.resolve(aid, True, "a", signature=sign_approval(b"ka", aid, r, True))
    assert "1 of 2" in g.get(aid).note
    with pytest.raises(ValueError):
        g.resolve(aid, True, "a", signature=sign_approval(b"ka", aid, r, True))
    g.resolve(aid, True, "b", signature=sign_approval(b"kb", aid, r, True))
    assert set(g.signatures(aid)) == {"a", "b"}
    assert g.decide("t", r, "x") is True
    clock.t += 100                                  # past the TTL
    assert g.decide("t", r, "x") is False and "expired" in g.get(aid).note
    assert log.verify() and [e["kind"] for e in log.entries()][:3] == ["signature", "signature", "decision"]


def test_signed_gateway_price_check_and_rejection():
    px = {"p": 100.0}
    g = SignedApprovalGateway({"a": b"ka"}, quorum={}, price_fn=lambda r: px["p"], clock=_Clock())
    r = _req("execution.submit_order", quantity=1)
    g.decide("t", r, "x")
    aid = g.pending()[0].id
    g.resolve(aid, True, "a", signature=sign_approval(b"ka", aid, r, True))
    assert g.decide("t", r, "x") is True
    px["p"] = 110.0
    assert g.decide("t", r, "x") is False
    r2 = _req("execution.submit_order", quantity=2)
    g.decide("t", r2, "x")
    aid2 = [a for a in g.pending()][0].id
    g.resolve(aid2, False, "a", signature=sign_approval(b"ka", aid2, r2, False))
    assert g.decide("t", r2, "x") is False


@pytest.mark.parametrize("kw", [
    {}, {"keys": {"a": b"k"}, "public_keys": {"a": b"x" * 32}},
    {"public_keys": {"a": b"short"}}, {"keys": {"a": b"k"}, "default_quorum": 2},
])
def test_signed_gateway_config_errors(kw):
    with pytest.raises(ValueError):
        SignedApprovalGateway(**kw)


def test_append_only_log_detects_tampering(tmp_path):
    p = tmp_path / "l.jsonl"
    log = AppendOnlyApprovalLog(p)
    assert log.verify() and log.entries() == []
    log.append({"k": 1})
    log.append({"k": 2})
    assert log.verify()
    lines = p.read_text().splitlines()
    p.write_text("\n".join([lines[1], lines[0]]) + "\n")
    assert not log.verify()
    p.write_text("not json\n")
    assert not log.verify()


# ------------------------------------------------------------------ output contract
@pytest.mark.parametrize("data,bad", [
    ({"target_weight": 0.5, "rationale": "r"}, False),
    ({"target_weight": 1.5, "rationale": "r"}, True),     # rejected, not clipped
    ({"target_weight": -1.0001}, True),
    ({"target_weight": -1.0, "confidence": None}, False),
    ({"target_weight": 0.0, "confidence": 1.2}, True),
    ({"target_weight": float("nan")}, False),             # type gate is the caller's
    ({"target_weight": True}, False),
])
def test_contract_violation_rejects_out_of_range(data, bad):
    assert (contracts.violation(data, contracts.PORTFOLIO_MANAGER) is not None) is bad


def test_contract_enum_exclusive_and_api_schema():
    assert contracts.violation({"action": "buy"}, contracts.TRADER) is None
    assert "not in" in contracts.violation({"action": "HODL"}, contracts.TRADER)
    assert "not in" in contracts.violation({"action": 3}, contracts.TRADER)
    assert contracts.violation({"stop_loss": 0.0}, contracts.TRADER) is not None
    assert contracts.violation({"x": 1}, None) is None
    s = contracts.api_schema(contracts.TRADER)
    assert "minimum" not in s["properties"]["target_weight"]
    assert "minimum -1" in s["properties"]["target_weight"]["description"]
    assert contracts.violation({"target_weight": 2}, contracts.TRADER) is not None


@settings(max_examples=100, deadline=None)
@given(v=st.floats(-3, 3))
def test_contract_signed_bound_is_exact(v):
    assert (contracts.violation({"recommended_weight": v}, contracts.RISK_VIEW) is None) == (-1 <= v <= 1)
