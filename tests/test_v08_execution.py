"""v0.8 execution chain (review findings 6, 16, 30, 31, 32, 71, 72, 73, 89, 90, 91): one impact
model shared by the simulator, the backtester and algo_cost_ratio; account-currency FX sizing;
honest POV completion; next-session execution; dimensionless AC urgency; explicit tickets with
a size guard; plans sized from the book; long-only truncation; the credited carry line; one
capital convention; whole-share / whole-lot quantities. Offline, numpy backend."""
import math
import re
from datetime import date, timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from agentic_trader import make_config, quant
from agentic_trader.agentic import (AutoApprovalGateway, EvidenceStore, PolicyEngine, QueuedApprovalGateway, Role,
                                    Task, ToolExecutor, build_registry, validate_plan)
from agentic_trader.agentic.servers import DeskTools, ticket_from_plan
from agentic_trader.algo import (algo_cost_ratio, base_to_account_rate, plan_execution, plan_reference,
                                 simulate_execution, synthetic_intraday_bars, twap_schedule, vwap_schedule)
from agentic_trader.cli import build_parser, main
from agentic_trader.cli.common import _config
from agentic_trader.cli.research import carry_summary, cmd_backtest
from agentic_trader.data import SyntheticProvider
from agentic_trader.data.base import MarketDataProvider, clip_history
from agentic_trader.instruments import Instrument
from agentic_trader.state import Action, FinalDecision

CFG = make_config(memory_path=None)
AS_OF = date(2024, 3, 1)
NEXT = date(2024, 3, 4)


def _decision(symbol, target, current=0.0):
    return FinalDecision(symbol, AS_OF, Action.BUY if target > current else Action.SELL, target, 0.0, None, None, "")


def _flat_day(price, volume=1e6):
    return pd.Series({"Open": price, "High": price, "Low": price, "Close": price, "Volume": volume})


class StubProvider(MarketDataProvider):
    """Hand-built daily bars per symbol; raises for anything else (no silent data)."""
    name = "stub"
    real_world = False

    def __init__(self, frames):
        super().__init__(CFG)
        self.frames = frames

    def history(self, instrument, start, end):
        if instrument.symbol not in self.frames:
            raise ValueError(f"no data for {instrument.symbol}")
        return clip_history(self.frames[instrument.symbol], start, end)


def _history(close, n=30, end=AS_OF, volume=1e6, last=None, after=None):
    """``n`` flat bars ending at ``end`` (the last one optionally overridden), plus an optional
    bar for the next session, so the decision day and the execution day are distinguishable."""
    idx = pd.bdate_range(end=end, periods=n)
    df = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": volume}, index=idx,
                      dtype=float)
    if last:
        for k, v in last.items():
            df.loc[idx[-1], k] = v
    if after:
        row = pd.DataFrame([{"Open": close, "High": close, "Low": close, "Close": close, "Volume": volume, **after}],
                           index=[pd.Timestamp(NEXT)], dtype=float)
        df = pd.concat([df, row])
    return df


# ------------------------------------------------------------------ 6: one impact model
def test_vwap_impact_equals_the_single_shot_law_for_any_slice_count():
    Q, ADV, DV = 100_000.0, 1_000_000.0, 0.02
    law = DV * math.sqrt(Q / ADV) * 1e4                     # 63.2456 bps: backtest.impact_coefficients' model
    got = []
    for n in (10, 78, 390):
        bars = synthetic_intraday_bars(_flat_day(100.0, ADV), n, "equity")
        rep = simulate_execution(vwap_schedule(Q, bars["Volume"].to_numpy()), bars, "buy", "vwap", 2.0, 1.0, DV, ADV)
        assert rep.impact_cost_bps == pytest.approx(law, rel=1e-6)
        got.append(rep.impact_cost_bps)
    assert max(got) - min(got) < 1e-9 * law                 # not a function of how finely the order is sliced
    # The old model charged sqrt(q_i / daily ADV) per slice: 7.6 bps at n=78. That is gone.
    assert got[1] > 60.0


@pytest.mark.parametrize("algo,kind,n,kappa", [("twap", "equity", 78, 3.0), ("twap", "equity", 10, 3.0),
                                                ("ac", "equity", 78, 3.0), ("ac", "equity", 78, 0.7),
                                                ("twap", "fx", 288, 3.0)])
def test_simulator_reproduces_algo_cost_ratio(algo, kind, n, kappa):
    Q, ADV, DV = 100_000.0, 1_000_000.0, 0.02
    if kind == "fx":
        bars = synthetic_intraday_bars(pd.Series({"Open": 1.1, "High": 1.1, "Low": 1.1, "Close": 1.1, "Volume": 0}),
                                       n, "fx")
        prof = np.full(n, 1.0 / n)
    else:
        bars = synthetic_intraday_bars(_flat_day(100.0, ADV), n, "equity")
        prof = bars["Volume"].to_numpy()
    vwap = simulate_execution(vwap_schedule(Q, prof), bars, "buy", "vwap", 2.0, 1.0, DV, ADV)
    sched = twap_schedule(Q, n) if algo == "twap" else quant.almgren_chriss(Q, n, kappa)
    other = simulate_execution(sched, bars, "buy", algo, 2.0, 1.0, DV, ADV)
    assert other.impact_cost_bps / vwap.impact_cost_bps == pytest.approx(algo_cost_ratio(algo, n, kind, kappa), rel=1e-6)
    assert vwap.impact_cost_bps == pytest.approx(DV * math.sqrt(Q / ADV) * 1e4, rel=1e-6)


def test_fx_without_a_notional_adv_has_no_impact_and_nothing_fills_in_an_empty_bar():
    bars = synthetic_intraday_bars(pd.Series({"Open": 1.1, "High": 1.11, "Low": 1.09, "Close": 1.1, "Volume": 0}), 10, "fx")
    assert simulate_execution(twap_schedule(1e6, 10), bars, "buy", "twap", 0.8, 1.0, 0.01, None).impact_cost_bps == 0.0
    eq = synthetic_intraday_bars(_flat_day(100.0, 1e6), 5, "equity")
    eq.loc[2, "Volume"] = 0.0
    rep = simulate_execution(twap_schedule(500, 5), eq, "buy", "twap", 0.0, 0.0)
    assert rep.executed == pytest.approx(400) and [f.slice for f in rep.fills] == [0, 1, 3, 4]


# ------------------------------------------------------------- 16: account-currency FX sizing
@pytest.mark.parametrize("symbol,price,rate,lot,qty,notional", [
    ("USDJPY", 145.0, None, 1000, 500_000.0, 500_000.0),      # base == account: 500k USD is 500k units
    ("EURUSD", 1.10, None, 1, 454_545.0, 499_999.5),          # quote == account: notional / price
    ("EURJPY", 158.0, 1.10, 1000, 454_000.0, 499_400.0),      # cross: needs EURUSD, never the JPY price
    ("EURGBP", 0.86, 1.10, 1000, 454_000.0, 499_400.0),
    ("EURGBP", 0.86, 1.10, 1, 454_545.0, 499_999.5),
])
def test_fx_quantity_is_base_currency_for_a_usd_account(symbol, price, rate, lot, qty, notional):
    ins = Instrument.parse(symbol)
    p = plan_execution(_decision(symbol, 0.5), ins, 0.0, 1e6, price, base_to_account=rate, lot_size=lot)
    assert p.quantity == qty and p.quantity_unit == ins.base
    assert p.notional == pytest.approx(notional) and p.notional_currency == "USD" and p.price == price
    assert p.quantity % lot == 0


def test_cross_without_a_rate_is_refused_and_account_currency_is_explicit():
    with pytest.raises(ValueError, match="EURUSD"):
        plan_execution(_decision("EURGBP", 0.5), Instrument.parse("EURGBP"), 0.0, 1e6, 0.86)
    eur = plan_execution(_decision("EURUSD", 0.5), Instrument.parse("EURUSD"), 0.0, 1e6, 1.10, account_currency="EUR")
    assert eur.quantity == 500_000.0 and eur.notional_currency == "EUR"          # base == account on a EUR book
    jpy = plan_execution(_decision("USDJPY", 0.5), Instrument.parse("USDJPY"), 0.0, 1e6, 145.0, account_currency="JPY",
                         lot_size=1)
    assert jpy.quantity == math.floor(5e5 / 145.0) and jpy.quantity_unit == "USD"  # quote == account


def test_base_to_account_rate_reads_the_direct_or_inverse_pair():
    direct = StubProvider({"EURUSD": _history(1.10)})
    assert base_to_account_rate(direct, "EUR", "USD", AS_OF) == pytest.approx(1.10)
    inverse = StubProvider({"USDCHF": _history(0.90)})
    assert base_to_account_rate(inverse, "CHF", "USD", AS_OF) == pytest.approx(1 / 0.90)
    assert base_to_account_rate(inverse, "USD", "USD", AS_OF) == 1.0
    with pytest.raises(ValueError, match="no GBPUSD or USDGBP rate"):
        base_to_account_rate(inverse, "GBP", "USD", AS_OF)
    # point in time: a rate printed after as_of is not used
    later = StubProvider({"EURUSD": _history(1.10, after={"Close": 9.9})})
    assert base_to_account_rate(later, "EUR", "USD", AS_OF) == pytest.approx(1.10)


def test_plan_tool_carries_quantity_unit_and_notional_currency_for_a_cross():
    prov = StubProvider({"EURJPY": _history(158.0, volume=0, after={"Open": 158.5, "High": 159, "Low": 158, "Close": 158.8}),
                         "EURUSD": _history(1.10, volume=0)})
    tools = DeskTools(prov, CFG, capital=100_000.0)
    p = tools.plan("EURJPY", AS_OF, 0.5)
    assert p["quantity"] == 45_000.0 and p["quantity_unit"] == "EUR"      # 50,000 USD / 1.10 -> whole 1,000 lots
    assert p["notional"] == pytest.approx(49_500.0) and p["notional_currency"] == "USD" and p["price"] == 158.0
    assert p["simulated"] and p["execution_date"] == NEXT.isoformat() and p["arrival"] == 158.5
    with pytest.raises(ValueError, match="EURUSD"):
        DeskTools(StubProvider({"EURJPY": _history(158.0, volume=0)}), CFG).plan("EURJPY", AS_OF, 0.5)


# ------------------------------------------------------------- 30: POV completion and IS
def test_pov_reports_the_unfilled_remainder_and_its_opportunity_cost():
    ins = Instrument.parse("AAPL")
    plan = plan_execution(_decision("AAPL", 1.0), ins, 0.0, 5e8, 100.0, adv=1e6)
    assert plan.algo == "pov" and plan.quantity == 5_000_000
    day = pd.Series({"Open": 100.0, "High": 104.0, "Low": 99.0, "Close": 103.0, "Volume": 1e6})
    bars = synthetic_intraday_bars(day, 78, "equity")
    rep = simulate_execution(plan.schedule(bars), bars, "buy", "pov", 2.0, 0.0, 0.02, 1e6, requested=plan.quantity)
    assert rep.requested == 5_000_000 and rep.executed == pytest.approx(100_000)      # 10% of the day's volume
    assert rep.completion == pytest.approx(0.02) and rep.unfilled == pytest.approx(4_900_000)
    # Perold: the 98% never bought is marked at the close, +300 bps from arrival.
    assert rep.opportunity_cost_bps == pytest.approx(300.0 * 0.98)
    executed_leg = (rep.avg_price / rep.arrival - 1) * 1e4 * 0.02
    assert rep.is_bps == pytest.approx(executed_leg + rep.opportunity_cost_bps)
    assert rep.to_dict()["completion"] == 0.02 and rep.to_dict()["unfilled"] == pytest.approx(4_900_000)
    # A day with no volume fills nothing and says so; it does not report completion 1.0.
    dead = synthetic_intraday_bars(pd.Series({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 0}),
                                   78, "equity")
    with np.errstate(all="ignore"):
        empty = simulate_execution(plan.schedule(dead), dead, "buy", "pov", 2.0, 0.0, 0.02, None, requested=plan.quantity)
    assert empty.executed == 0 and empty.completion == 0.0 and empty.opportunity_cost_bps == pytest.approx(50.0)
    assert empty.is_bps == pytest.approx(50.0)
    with pytest.raises(ValueError, match="requested"):
        simulate_execution(twap_schedule(100, 5), synthetic_intraday_bars(_flat_day(100.0), 5), "buy", requested=50)


def test_complete_fill_shortfall_is_unchanged_by_the_opportunity_leg():
    bars = synthetic_intraday_bars(pd.Series({"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1e6}), 20, "equity", 1)
    rep = simulate_execution(twap_schedule(1000, 20), bars, "sell", "twap", 10.0, 0.0)
    assert rep.completion == 1.0 and rep.opportunity_cost_bps == 0.0
    assert rep.is_bps == pytest.approx(-(rep.avg_price / rep.arrival - 1) * 1e4)


# ------------------------------------------------------- 31: execute on the next session
def test_plan_tool_sizes_at_the_close_and_fills_on_the_next_session():
    prov = StubProvider({"AAPL": _history(100.0, last={"Open": 100.0, "High": 102.0, "Close": 102.0},
                                          after={"Open": 103.0, "High": 104.0, "Low": 102.5, "Close": 103.5})})
    p = DeskTools(prov, CFG, capital=100_000.0).plan("AAPL", AS_OF, 0.5)
    assert p["price"] == 102.0 and p["quantity"] == math.floor(50_000 / 102.0)     # sized at the as-of close
    assert p["as_of"] == AS_OF.isoformat() and p["execution_date"] == NEXT.isoformat()
    assert p["arrival"] == 103.0 and p["close"] == 103.5                           # filled on t+1, never on t
    assert p["simulated"] is True and 0 < p["completion"] <= 1


def test_plan_tool_says_so_when_the_next_session_is_not_available():
    p = DeskTools(StubProvider({"AAPL": _history(100.0)}), CFG, capital=100_000.0).plan("AAPL", AS_OF, 0.5)
    assert p["trade"] and p["simulated"] is False and "no session after 2024-03-01" in p["note"]
    assert "is_bps" not in p and "arrival" not in p and p["quantity"] == 500


def test_cli_execute_says_when_the_next_session_is_not_available(monkeypatch, capsys):
    import agentic_trader.data as data
    monkeypatch.setattr(data, "get_provider", lambda cfg: StubProvider({"AAPL": _history(100.0)}))
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5", "--capital", "100000"]) == 0
    out = capsys.readouterr().out
    assert "BUY 500 shares (notional 50,000 USD at 100)" in out
    assert "no session after 2024-03-01 is available yet" in out and "implementation shortfall" not in out


def test_cli_execute_reports_the_next_session(capsys):
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5"]) == 0
    out = capsys.readouterr().out
    nxt = SyntheticProvider(CFG).history(Instrument.parse("AAPL"), NEXT, NEXT).iloc[0]
    assert f"on {NEXT}; arrival {nxt['Open']:.5g}" in out and f"close {nxt['Close']:.5g}" in out
    assert "executed" in out and " of " in out and "implementation shortfall" in out


# ------------------------------------------------------ 32: dimensionless AC urgency
def test_ac_schedule_does_not_depend_on_price_level_seed_or_path():
    ins = Instrument.parse("AAPL")
    plan = plan_execution(_decision("AAPL", 0.5), ins, 0.0, 1e6, 100.0, adv=5e6, algo="ac")
    scheds = []
    for price, seed in ((1.1, 0), (10.0, 1), (100.0, 0), (1000.0, 7)):
        day = pd.Series({"Open": price, "High": price * 1.005, "Low": price * 0.995, "Close": price, "Volume": 1e6})
        scheds.append(plan.schedule(synthetic_intraday_bars(day, 78, "equity", seed)))
    for s in scheds[1:]:
        np.testing.assert_allclose(s, scheds[0])
    np.testing.assert_allclose(scheds[0], quant.almgren_chriss(plan.quantity, 78, CFG["costs"]["ac_kappa"]))
    assert scheds[0][0] > scheds[0][-1] and scheds[0].sum() == pytest.approx(plan.quantity)
    bars = synthetic_intraday_bars(_flat_day(100.0), 78, "equity")
    np.testing.assert_allclose(plan.schedule(bars, kappa=0.0), twap_schedule(plan.quantity, 78))
    urgent = plan_execution(_decision("AAPL", 0.5), ins, 0.0, 1e6, 100.0, adv=5e6, algo="ac", ac_kappa=6.0)
    np.testing.assert_allclose(urgent.schedule(bars), quant.almgren_chriss(urgent.quantity, 78, 6.0))
    with pytest.raises(ValueError):
        plan_execution(_decision("AAPL", 0.5), ins, 0.0, 1e6, 100.0, algo="ac", ac_kappa=-1)


def test_cli_execute_exposes_ac_kappa(capsys):
    args = build_parser().parse_args(["execute", "AAPL", "--target", "0.5", "--algo", "ac", "--ac-kappa", "0.5"])
    assert args.ac_kappa == 0.5 and _config(args)["costs"]["ac_kappa"] == 0.5
    base = ["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5"]
    assert main(base + ["--algo", "ac", "--ac-kappa", "0"]) == 0
    ac0 = capsys.readouterr().out
    assert main(base + ["--algo", "twap"]) == 0
    twap = capsys.readouterr().out
    fill = re.compile(r"avg fill ([0-9.]+)")
    assert fill.search(ac0).group(1) == fill.search(twap).group(1)      # kappa 0 is TWAP, exactly


# ------------------------------------------------------------ 71: explicit tickets
def _executor(tools, gateway=None, **policy):
    return ToolExecutor(build_registry(tools), PolicyEngine({"max_position": 1.0, **policy}), EvidenceStore(),
                        Role.TRADER, gateway or AutoApprovalGateway())


def test_submit_order_rejects_bare_floats():
    tools = DeskTools(SyntheticProvider(CFG), CFG)
    res = _executor(tools).call("execution.submit_order", symbol="USDJPY", side="buy", quantity=3448.28)
    assert not res.ok and "missing arguments" in res.error and "notional" in res.error and not tools.orders
    with pytest.raises(TypeError):
        tools.submit_order("USDJPY", "buy", 1e12)


def test_ticket_carries_units_notional_price_and_a_verifiable_plan_reference():
    tools = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0)
    plan = tools.plan("USDJPY", AS_OF, 0.5)
    assert plan["quantity"] == 50_000.0 and plan["quantity_unit"] == "USD" and plan["notional"] == 50_000.0
    args = ticket_from_plan(plan)
    assert args["plan_id"] == plan_reference("USDJPY", "buy", 50_000.0, "USD", 50_000.0, "USD", plan["price"])
    ticket = tools.submit_order(**args)
    assert ticket["quantity"] == 50_000.0 and ticket["quantity_unit"] == "USD" and ticket["notional"] == 50_000.0
    assert ticket["notional_currency"] == "USD" and ticket["price"] == plan["price"] and ticket["plan_id"] == plan["plan_id"]
    assert ticket["intent"] == "open_long" and ticket["plan_known"] and ticket["status"] == "ticketed"
    # edited after planning: refused
    for change in ({"quantity": 3448.28}, {"notional": 500_000.0}, {"price": 1.0}, {"plan_id": "PLAN-000000000000"}):
        with pytest.raises(ValueError):
            tools.submit_order(**{**args, **change})
    with pytest.raises(ValueError, match="quantity_unit"):
        tools.submit_order(**{**args, "quantity_unit": "shares",
                              "plan_id": plan_reference("USDJPY", "buy", 50_000.0, "shares", 50_000.0, "USD", plan["price"])})
    with pytest.raises(ValueError, match="account currency"):
        tools.submit_order(**{**args, "notional_currency": "JPY",
                              "plan_id": plan_reference("USDJPY", "buy", 50_000.0, "USD", 50_000.0, "JPY", plan["price"])})
    # the evidence record and the ticket both say what the number is
    ex = _executor(tools)
    res = ex.call("execution.submit_order", **args)
    assert res.ok and ex.evidence_for(res).arguments["notional"] == 50_000.0


def test_ticket_size_guard_before_approval_and_at_execution():
    tools = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0)
    assert tools.order_cap == 100_000.0
    big = plan_reference("AAPL", "buy", 1000.0, "shares", 150_000.0, "USD", 150.0)
    with pytest.raises(ValueError, match="per-order cap"):
        tools.submit_order("AAPL", "buy", 1000.0, "shares", 150_000.0, "USD", 150.0, big)
    frac = plan_reference("AAPL", "buy", 10.5, "shares", 1575.0, "USD", 150.0)
    with pytest.raises(ValueError, match="whole shares"):
        tools.submit_order("AAPL", "buy", 10.5, "shares", 1575.0, "USD", 150.0, frac)
    with pytest.raises(ValueError, match="whole lots"):
        tools.submit_order("USDJPY", "buy", 1500.0, "USD", 1500.0, "USD", 145.0,
                           plan_reference("USDJPY", "buy", 1500.0, "USD", 1500.0, "USD", 145.0))
    gate = QueuedApprovalGateway()
    ex = _executor(tools, gate, max_order_notional=tools.order_cap)
    res = ex.call("execution.submit_order", symbol="AAPL", side="buy", quantity=1000.0, quantity_unit="shares",
                  notional=150_000.0, notional_currency="USD", price=150.0, plan_id=big)
    assert not res.ok and "argument_guard" in res.error and "per-order cap" in res.error
    assert gate.pending() == [] and not tools.orders                # never reached an approver
    assert tools.order_cap == float(DeskTools(SyntheticProvider(CFG), make_config(CFG, execution={"max_order_notional": 5e3}),
                                              capital=100_000.0).order_cap) * 20
    frozen = DeskTools(SyntheticProvider(CFG), make_config(CFG, execution={"max_order_notional": 0}), capital=100_000.0)
    assert frozen.order_cap == 0.0                                    # zero freezes ticketing; it is not "unset"
    with pytest.raises(ValueError, match="per-order cap 0"):
        frozen.submit_order(**ticket_from_plan(frozen.plan("AAPL", AS_OF, 0.1)))


def test_submit_order_accepts_only_plans_this_desk_produced():
    # Finding 71 residual: plan_id is a checksum anyone can compute; what authenticates a
    # ticket is that this desk planned it, with these numbers.
    tools = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0)
    forged = plan_reference("USDJPY", "buy", 1e12, "USD", 1000.0, "USD", 150.0)
    with pytest.raises(ValueError, match="not one this desk produced"):
        tools.submit_order("USDJPY", "buy", 1e12, "USD", 1000.0, "USD", 150.0, forged)
    forged = plan_reference("AAPL", "buy", 1e9, "shares", 10_000.0, "USD", 0.00001)
    with pytest.raises(ValueError, match="not one this desk produced"):
        tools.submit_order("AAPL", "buy", 1e9, "shares", 10_000.0, "USD", 0.00001, forged)
    assert tools.orders == []
    ex = ToolExecutor(build_registry(tools), PolicyEngine({"max_position": 1.0, "max_order_notional": tools.order_cap}),
                      EvidenceStore(), Role.TRADER, AutoApprovalGateway())
    r = ex.call("execution.submit_order", symbol="USDJPY", side="buy", quantity=1e12, quantity_unit="USD", notional=1000.0,
                notional_currency="USD", price=150.0,
                plan_id=plan_reference("USDJPY", "buy", 1e12, "USD", 1000.0, "USD", 150.0))
    assert not r.ok and "not one this desk produced" in r.error and tools.orders == []
    # the desk's own plan is accepted, unchanged; the same numbers under another plan's id are not
    plan = tools.plan("USDJPY", AS_OF, 0.5)
    other = tools.plan("USDJPY", AS_OF, 0.25)
    ticket = tools.submit_order(**ticket_from_plan(plan))
    assert ticket["plan_known"] is True and ticket["quantity"] == plan["quantity"]
    with pytest.raises(ValueError):
        tools.submit_order(**{**ticket_from_plan(plan), "plan_id": other["plan_id"]})
    # a plan produced by another desk (or process) needs the operator's explicit opt-in
    elsewhere = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0).plan("AAPL", AS_OF, 0.1)
    with pytest.raises(ValueError, match="allow_external_plans"):
        tools.submit_order(**ticket_from_plan(elsewhere))
    lenient = DeskTools(SyntheticProvider(CFG), make_config(CFG, execution={"allow_external_plans": True}),
                        capital=100_000.0)
    t = lenient.submit_order(**ticket_from_plan(elsewhere))
    assert t["status"] == "ticketed" and t["plan_known"] is False
    assert CFG["execution"].get("allow_external_plans", False) is False


def test_plan_tool_treats_ac_kappa_zero_as_twap():
    # Finding 32 residual: ``costs.ac_kappa: 0`` (documented as TWAP) fell through ``or 3.0``.
    twap = make_config(CFG, costs={"ac_kappa": 0.0})
    p0 = DeskTools(SyntheticProvider(twap), twap, capital=1e6).plan("AAPL", AS_OF, 0.5, algo="ac")
    pt = DeskTools(SyntheticProvider(twap), twap, capital=1e6).plan("AAPL", AS_OF, 0.5, algo="twap")
    p3 = DeskTools(SyntheticProvider(CFG), CFG, capital=1e6).plan("AAPL", AS_OF, 0.5, algo="ac")
    assert p0["ac_kappa"] == 0.0 and p3["ac_kappa"] == 3.0 and p0["algo"] == "ac"
    assert p0["avg_price"] == pytest.approx(pt["avg_price"]) and p0["impact_cost_bps"] == pytest.approx(pt["impact_cost_bps"])
    assert p0["avg_price"] != pytest.approx(p3["avg_price"]) or p0["impact_cost_bps"] != pytest.approx(p3["impact_cost_bps"])


# ---------------------------------------------------------- 72: plan sizes from the book
def test_plan_reads_the_desk_position_book():
    tools = DeskTools(SyntheticProvider(CFG), CFG, positions={"AAPL": 0.4}, capital=100_000.0)
    p = tools.plan("AAPL", AS_OF, 0.5)
    px = p["price"]
    assert p["current_weight"] == 0.4 and p["quantity"] == math.floor(10_000 / px) and p["intent"] == "add_long"
    assert p["notional"] == pytest.approx(p["quantity"] * px) and p["notional"] < 10_000 < 50_000
    assert tools.plan("AAPL", AS_OF, 0.5, current_weight=0.4)["quantity"] == p["quantity"]
    with pytest.raises(ValueError, match="disagrees with the desk's book"):
        tools.plan("AAPL", AS_OF, 0.5, current_weight=0.0)
    assert tools.plan("MSFT", AS_OF, 0.5, current_weight=0.3)["current_weight"] == 0.3   # unknown to the book
    assert tools.plan("AAPL", AS_OF, 0.4) == {"trade": False, "reason": "target equals current position"}


def test_validate_plan_leaves_a_declared_current_weight_to_the_runs_book():
    # v0.8 regression (h): this test asserted the argument was pinned to the task's value, which
    # sent a declared position above the cap into the argument guard; the run's book carries the
    # declared fact now and the plan step does not repeat it.
    reg = build_registry(DeskTools(SyntheticProvider(CFG), CFG))
    raw = [{"type": "tool", "name": "execution.plan",
            "arguments": {"symbol": "AAPL", "as_of": "2024-03-01", "target_weight": 0.5, "current_weight": 0.0}}]
    plan = validate_plan(raw, Task("AAPL", AS_OF, current_weight=0.4), Instrument.parse("AAPL"), ["technical"], reg)
    step = next(s for s in plan.steps if s.name == "execution.plan")
    assert "current_weight" not in step.arguments
    assert any("current_weight" in n and "+0.4000" in n and "book" in n for n in plan.notes)
    plan2 = validate_plan(raw, Task("AAPL", AS_OF), Instrument.parse("AAPL"), ["technical"], reg)
    assert next(s for s in plan2.steps if s.name == "execution.plan").arguments["current_weight"] == 0.0
    # the run's book is what the step then plans from
    tools = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0)
    view = tools.for_book({"AAPL": 0.4})
    p = view.plan("AAPL", AS_OF, 0.5)
    assert p["current_weight"] == 0.4 and p["intent"] == "add_long" and p["plan_id"] in tools.plans
    assert tools.positions == {} and tools.plan("AAPL", AS_OF, 0.5)["intent"] == "open_long"


# ------------------------------------------------- v0.8 regression (j): the plan says when it is not ticketable
def test_plan_flags_a_notional_over_the_desk_cap_as_unticketable():
    tools = DeskTools(SyntheticProvider(CFG), CFG, positions={"EURUSD": -0.6}, capital=100_000.0)
    assert tools.order_cap == 100_000.0
    p = tools.plan("EURUSD", AS_OF, 0.6)
    assert p["trade"] and p["intent"] == "reverse_to_long" and p["notional"] > 100_000.0
    assert p["ticketable"] is False and p["order_cap"] == 100_000.0 and "per-order cap" in p["note"]
    assert p["plan_id"] not in tools.plans and p["simulated"] is True
    with pytest.raises(ValueError, match="per-order cap"):
        ticket_from_plan(p)
    # through the executor a flagged plan is evidence, never a submittable ticket
    ex = _executor(tools, max_order_notional=tools.order_cap)
    res = ex.call("execution.plan", symbol="EURUSD", as_of=AS_OF.isoformat(), target_weight=0.6)
    assert res.ok and res.payload["ticketable"] is False and res.payload["order_cap"] == 100_000.0
    ok = tools.plan("EURUSD", AS_OF, 0.0)
    assert ok["ticketable"] is True and ok["order_cap"] == 100_000.0 and ok["plan_id"] in tools.plans and "note" not in ok
    assert tools.submit_order(**ticket_from_plan(ok))["intent"] == "buy_to_cover"
    # (v0.8 final review (h): the ticket moves the book to flat, so the executor check above runs
    # before it; the same reversal now fits the cap as a second leg, see test_two_leg_reduce_...)
    # a cap of zero flags every plan, and the no-session note still travels with the cap note
    frozen = DeskTools(StubProvider({"AAPL": _history(100.0)}), make_config(CFG, execution={"max_order_notional": 0}),
                       capital=100_000.0)
    fp = frozen.plan("AAPL", AS_OF, 0.1)
    assert fp["ticketable"] is False and fp["order_cap"] == 0.0 and fp["simulated"] is False
    assert "per-order cap 0" in fp["note"] and "no session after 2024-03-01" in fp["note"]


# ------------------------------------------------- v0.8 regression (m): below one lot is a no-trade, not an error
def test_plan_returns_no_trade_for_a_change_below_one_lot():
    tools = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0)
    p = tools.plan("AAPL", AS_OF, 0.25, current_weight=0.2499)
    assert set(p) == {"trade", "reason"} and p["trade"] is False
    assert "below one share" in p["reason"] and "nothing to trade" in p["reason"] and "+0.2499 -> +0.2500" in p["reason"]
    assert tools.plan("AAPL", AS_OF, 0.25, current_weight=0.25) == {"trade": False, "reason": "target equals current position"}
    fx = tools.plan("USDJPY", AS_OF, 0.005)                          # 500 USD is below one 1,000-unit lot
    assert fx["trade"] is False and "below one lot of 1000 USD" in fx["reason"]
    res = _executor(tools).call("execution.plan", symbol="AAPL", as_of=AS_OF.isoformat(), target_weight=0.25,
                                current_weight=0.2499)
    assert res.ok and res.payload["trade"] is False and tools.plans == {}
    # the long-only truncation note still travels with it
    held = DeskTools(SyntheticProvider(CFG), CFG, positions={"AAPL": 0.0001}, capital=100_000.0)
    t = held.plan("AAPL", AS_OF, -0.3)
    assert t["trade"] is False and "truncated to flat" in t["reason"] and "below one share" in t["reason"]
    # invalid inputs are still errors
    with pytest.raises(ValueError, match="unknown execution algo"):
        tools.plan("AAPL", AS_OF, 0.5, algo="vwip")


def test_position_reports_tickets_recorded_against_the_symbol():
    tools = DeskTools(SyntheticProvider(CFG), CFG, positions={"AAPL": 0.4}, capital=100_000.0)
    assert "pending" not in tools.position("AAPL")
    t = tools.submit_order(**ticket_from_plan(tools.plan("AAPL", AS_OF, 0.1)))
    pos = tools.position("AAPL")
    # v0.8 final review (h): the book moves to the ticket's position_after (this line asserted the
    # weight stayed 0.4 after a ticket to 0.1 before, the enshrined defect)
    assert pos["weight"] == t["position_after"] == pytest.approx(0.1, abs=0.01) and pos["weight"] != 0.4
    assert pos["pending"][0]["id"] == t["id"] and pos["pending"][0]["intent"] == "sell_to_reduce"


# ------------------------------------------------------ 73: long-only truncation
def test_long_only_equity_plan_is_truncated_to_flat_and_the_ticket_says_reduce():
    tools = DeskTools(SyntheticProvider(CFG), CFG, positions={"AAPL": 0.4}, capital=100_000.0)
    p = tools.plan("AAPL", AS_OF, -0.3)
    px = p["price"]
    assert p["side"] == "sell" and p["intent"] == "sell_to_close" and p["target_weight"] == 0.0
    assert p["quantity"] == math.floor(40_000 / px) and "truncated to flat" in p["reason"]
    ticket = tools.submit_order(**ticket_from_plan(p))
    assert ticket["intent"] == "sell_to_close" and abs(ticket["position_after"]) < px / 100_000
    flat = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0).plan("AAPL", AS_OF, -0.5)
    assert flat["trade"] is False and "truncated to flat" in flat["reason"]
    # a ticket that would take the long-only book short is refused, whatever the plan reference says
    short = plan_reference("AAPL", "sell", 300.0, "shares", 60_000.0, "USD", 200.0)
    with pytest.raises(ValueError, match="long-only"):
        tools.submit_order("AAPL", "sell", 300.0, "shares", 60_000.0, "USD", 200.0, short)
    # with shorting allowed the same request is a reversal, and says so
    loose = DeskTools(SyntheticProvider(CFG), make_config(CFG, risk={"allow_short_equity": True}),
                      positions={"AAPL": 0.4}, capital=100_000.0)
    p2 = loose.plan("AAPL", AS_OF, -0.3)
    assert p2["intent"] == "reverse_to_short" and p2["quantity"] == math.floor(70_000 / p2["price"])
    assert loose.submit_order(**ticket_from_plan(p2))["intent"] == "reverse_to_short"
    fx = tools.plan("USDJPY", AS_OF, -0.5)
    assert fx["intent"] == "sell_short" and fx["target_weight"] == -0.5       # FX shorts are allowed by default


def test_cli_execute_honours_the_long_only_policy_and_allow_short(capsys):
    base = ["execute", "AAPL", "--date", "2024-03-01", "--target", "-0.3", "--current", "0.4", "--capital", "100000"]
    assert main(base) == 0
    out = capsys.readouterr().out
    assert "SELL" in out and "truncated to flat" in out and "intent sell_to_close" in out
    assert main(base + ["--allow-short"]) == 0
    assert "intent reverse_to_short" in capsys.readouterr().out
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "-0.3"]) == 0
    assert "nothing to trade" in capsys.readouterr().out


# ------------------------------------------------------------ 89: the credited carry line
def test_carry_summary_reports_what_the_backtester_credited():
    # The final bar never accrues (carry is earned over the step to the next bar), so 63
    # bars are 62 accruing ones: 36 with a rate, 26 without.
    c = np.array([0.0325] * 36 + [np.nan] * 27)
    line = carry_summary(c, 0.0)
    assert line.startswith(f"carry {36 * 0.0325 / 62:+.2%} p.a. credited") and "+1.89%" in line
    assert "+3.25% on 36/62 accruing bars" in line and "0 on 26 with no point-in-time rate" in line
    assert carry_summary(np.full(63, 0.0325), 0.0) == "carry +3.25% p.a. credited (point-in-time, all 62 accruing bars)"
    assert carry_summary(np.full(5, np.nan), 0.0) == \
        "carry +0.00% p.a. credited (4/4 accruing bars with no point-in-time rate)"
    assert carry_summary(None, 0.0252) == "carry +2.52% p.a."


def test_cli_backtest_prints_the_credited_carry(monkeypatch, capsys):
    import agentic_trader.cli.research as research
    carry = np.array([0.0325] * 36 + [np.nan] * 27)
    bt = quant.BacktestConfig(cost_bps=0.3, slippage_bps=0.2, carry_annual=0.0325, allow_short=True)
    fake = SimpleNamespace(instrument=Instrument.parse("USDJPY"), dates=pd.bdate_range("2026-07-01", periods=63),
                           carry=carry, backtest_config=bt, table=lambda: pd.DataFrame({"CR%": [1.0]}, index=["x"]))
    monkeypatch.setattr(research, "run_agent_backtest", lambda *a, **k: fake)
    args = build_parser().parse_args(["baselines", "USDJPY", "--start", "2026-07-01", "--end", "2026-09-25"])
    assert cmd_backtest(args, include_agent=False) == 0
    out = capsys.readouterr().out
    assert "carry +1.89% p.a. credited (+3.25% on 36/62 accruing bars, 0 on 26 with no point-in-time rate)" in out
    assert "+3.25% p.a. (mean" not in out


# ------------------------------------------------------------ 90: one capital convention
def test_execute_capital_defaults_to_config_initial_capital(capsys):
    assert build_parser().parse_args(["execute", "AAPL", "--target", "0.5"]).capital is None
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5"]) == 0
    out = capsys.readouterr().out
    assert f"capital {CFG['initial_capital']:,.0f} USD" in out
    printed = int(re.search(r"BUY ([\d,]+) shares", out).group(1).replace(",", ""))
    desk = DeskTools(SyntheticProvider(CFG), CFG).plan("AAPL", AS_OF, 0.5)
    assert printed == desk["quantity"] and f"notional {desk['notional']:,.0f} USD" in out
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5", "--capital", "1000000"]) == 0
    assert "capital 1,000,000 USD" in capsys.readouterr().out
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5", "--capital", "0"]) == 2


def test_task_and_serve_accept_capital():
    args = build_parser().parse_args(["task", "AAPL", "--capital", "250000"])
    assert _config(args)["initial_capital"] == 250_000.0
    assert _config(build_parser().parse_args(["serve", "--capital", "3e6"]))["initial_capital"] == 3e6
    assert _config(build_parser().parse_args(["task", "AAPL"]))["initial_capital"] == CFG["initial_capital"]


# -------------------------------------------------- 91: whole shares / whole lots, once
def test_quantities_are_rounded_once_at_plan_time_and_used_everywhere(capsys):
    ins = Instrument.parse("AAPL")
    p = plan_execution(_decision("AAPL", 0.5), ins, 0.0, 100_000.0, 223.219, adv=5e6)
    assert p.quantity == 223.0 and p.quantity.is_integer() and p.notional == pytest.approx(223 * 223.219)
    bars = synthetic_intraday_bars(_flat_day(223.219), 78, "equity")
    assert p.schedule(bars).sum() == pytest.approx(223.0)
    fx = plan_execution(_decision("EURUSD", 0.5), Instrument.parse("EURUSD"), 0.0, 100_000.0, 1.0851, lot_size=1000)
    assert fx.quantity == 46_000.0 and fx.notional == pytest.approx(46_000 * 1.0851)
    tools = DeskTools(SyntheticProvider(CFG), CFG, capital=100_000.0)
    payload = tools.plan("AAPL", AS_OF, 0.5)
    ticket = tools.submit_order(**ticket_from_plan(payload))
    assert payload["quantity"].is_integer() and payload["quantity"] == ticket["quantity"] == payload["requested"]
    assert payload["executed"] == pytest.approx(payload["quantity"]) and payload["completion"] == 1.0
    assert main(["execute", "AAPL", "--date", "2024-03-01", "--target", "0.5", "--capital", "100000"]) == 0
    out = capsys.readouterr().out
    assert f"BUY {payload['quantity']:,.0f} shares" in out and f"executed {payload['quantity']:,.0f} of" in out
    # a change below one share is a no-op, not an error (v0.8 regression (m): this asserted a ValueError)
    assert plan_execution(_decision("AAPL", 0.001), ins, 0.0, 100_000.0, 223.219) is None
    with pytest.raises(ValueError, match="unknown execution algo"):
        plan_execution(_decision("AAPL", 0.5), ins, 0.0, 100_000.0, 223.219, algo="vwip")


# ------------------------------------------------- v0.8 final review (h): a ticket moves the book
def test_two_leg_reduce_sizes_the_second_leg_from_the_ticketed_book():
    tools = DeskTools(SyntheticProvider(CFG), CFG, positions={"EURUSD": -0.6}, capital=100_000.0)
    assert tools.plan("EURUSD", AS_OF, 0.6)["ticketable"] is False       # the whole reversal is over the cap
    leg1 = tools.submit_order(**ticket_from_plan(tools.plan("EURUSD", AS_OF, 0.0)))
    assert leg1["intent"] == "buy_to_cover" and leg1["position_before"] == -0.6
    assert leg1["position_after"] == pytest.approx(0.0, abs=0.02) and tools.positions["EURUSD"] == leg1["position_after"]
    pos = tools.position("EURUSD")
    assert pos["weight"] == leg1["position_after"] and [t["id"] for t in pos["pending"]] == [leg1["id"]]
    leg2 = tools.plan("EURUSD", AS_OF, 0.6)                             # sized from the book the ticket left
    assert leg2["trade"] and leg2["ticketable"] is True and leg2["current_weight"] == leg1["position_after"]
    assert leg2["notional"] <= 100_000.0 and leg2["side"] == "buy"
    t2 = tools.submit_order(**ticket_from_plan(leg2))
    assert t2["position_before"] == leg1["position_after"] and t2["position_after"] == pytest.approx(0.6, abs=0.02)
    assert tools.positions["EURUSD"] == t2["position_after"]
    assert [t["id"] for t in tools.position("EURUSD")["pending"]] == [leg1["id"], t2["id"]]
    with pytest.raises(ValueError, match="disagrees with the desk's book"):   # the pre-ticket weight is stale
        tools.plan("EURUSD", AS_OF, 0.6, current_weight=-0.6)
    # a run's view moves the run's book, never the desk's; a second reduce cannot re-sell sold shares
    desk = DeskTools(SyntheticProvider(CFG), CFG, positions={"AAPL": 0.4}, capital=100_000.0)
    book = {"AAPL": 0.4}
    view = desk.for_book(book)
    first = view.submit_order(**ticket_from_plan(view.plan("AAPL", AS_OF, 0.2)))
    assert first["intent"] == "sell_to_reduce" and book == {"AAPL": first["position_after"]}
    assert desk.positions == {"AAPL": 0.4} and first["position_after"] == pytest.approx(0.2, abs=0.01)
    again = view.plan("AAPL", AS_OF, 0.0)
    assert again["current_weight"] == first["position_after"] and again["notional"] < 0.2 * 100_000.0 + 300
    second = view.submit_order(**ticket_from_plan(again))
    assert second["position_after"] == pytest.approx(0.0, abs=0.01) and 0 <= second["position_after"]
    assert view.orders is desk.orders and len(desk.orders) == 2 and desk.positions == {"AAPL": 0.4}
    assert desk.position("AAPL")["weight"] == 0.4 and len(desk.position("AAPL")["pending"]) == 2
