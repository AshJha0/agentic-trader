"""Plan item 4.7: the paper OMS (offline, synthetic, no network, $0)."""

from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from agentic_trader import quant
from agentic_trader.agentic.domain import EvidenceType
from agentic_trader.agentic.policy import DenyApprovalGateway, QueuedApprovalGateway
from agentic_trader.backtest import impact_coefficients
from agentic_trader.config import make_config
from agentic_trader.instruments import Instrument
from agentic_trader.oms import (
    LEGAL_TRANSITIONS,
    OMS,
    IllegalTransition,
    KillSwitch,
    MarketSnapshot,
    Order,
    OrderState,
    SleeveCalendar,
    fill_cost,
    kill_switch_for,
    market_snapshot,
    nyse_holidays,
    reconcile,
)

UTC = timezone.utc
FRI_1555 = datetime(2026, 11, 6, 20, 55, tzinfo=UTC)  # 15:55 New York (EST)
BIG = MarketSnapshot(price=200.0, adv=1e9, impact_k=None)


@pytest.fixture
def cfg():
    c = make_config(data_provider="synthetic", memory_path=None)
    c["oms"] = {"max_order_notional": 100_000, "max_order_quantity": 5_000, "borrow_list": ["MSFT"]}
    return c


def _order(oms, cid="o1", sym="AAPL", side="buy", qty=100, px=200.0, last=199.0, at=FRI_1555):
    return oms.submit(cid, sym, side, qty, price=px, last_close=last, at=at)


# ---------------------------------------------------------------- state machine
ALL = list(OrderState)


@pytest.mark.parametrize("src", ALL)
@pytest.mark.parametrize("dst", ALL)
def test_every_transition_is_legal_or_refused(src, dst):
    o = Order("x", "AAPL", "equity", "buy", 1, 1.0, FRI_1555, state=src)
    legal = {
        (OrderState.NEW, OrderState.ACKED),
        (OrderState.NEW, OrderState.REJECTED),
        (OrderState.NEW, OrderState.CANCELLED),
        (OrderState.ACKED, OrderState.PARTIALLY_FILLED),
        (OrderState.ACKED, OrderState.FILLED),
        (OrderState.ACKED, OrderState.CANCELLED),
        (OrderState.PARTIALLY_FILLED, OrderState.PARTIALLY_FILLED),
        (OrderState.PARTIALLY_FILLED, OrderState.FILLED),
        (OrderState.PARTIALLY_FILLED, OrderState.CANCELLED),
    }
    if (src, dst) in legal:
        o.move(dst, FRI_1555, "t", "ev")
        assert o.state is dst and o.history[-1].at == FRI_1555
    else:
        with pytest.raises(IllegalTransition):
            o.move(dst, FRI_1555, "t", "ev")
        assert o.state is src


@settings(max_examples=200, deadline=None)
@given(st.lists(st.sampled_from(ALL), max_size=12))
def test_random_walks_only_take_legal_steps(steps):
    o = Order("x", "AAPL", "equity", "buy", 1, 1.0, FRI_1555)
    for s in steps:
        before = o.state
        try:
            o.move(s, FRI_1555, "", "")
        except IllegalTransition:
            assert s not in LEGAL_TRANSITIONS[before] and o.state is before
        else:
            assert s in LEGAL_TRANSITIONS[before]
    terminal = [t.state for t in o.history if not LEGAL_TRANSITIONS[t.state]]
    assert len(terminal) <= 1 and (not terminal or o.history[-1].state is terminal[0])


def test_transitions_are_timestamped_and_evidenced(cfg):
    oms = OMS(cfg)
    o = _order(oms)
    oms.execute("o1", BIG, FRI_1555)
    assert [t.state for t in o.history] == [OrderState.NEW, OrderState.ACKED, OrderState.FILLED]
    for t in o.history:
        assert t.at.tzinfo is not None and oms.evidence.resolve(t.evidence_id)
    assert oms.evidence.get(o.history[-1].evidence_id).payload["state"] == "FILLED"
    assert oms.evidence.by_type(EvidenceType.APPROVAL)
    with pytest.raises(IllegalTransition):
        oms.execute("o1", BIG, FRI_1555)
    with pytest.raises(ValueError):
        oms.submit("o2", "AAPL", "buy", 1, 200.0, 199.0, datetime(2026, 11, 6, 15, 55))  # naive


def test_client_order_id_is_idempotent(cfg):
    oms = OMS(cfg)
    o = _order(oms)
    n = len(oms.evidence)
    assert _order(oms) is o and len(oms.evidence) == n and len(oms.orders) == 1
    with pytest.raises(ValueError, match="new id"):
        _order(oms, qty=101)


# ---------------------------------------------------------------- pre-trade checks
@pytest.mark.parametrize(
    "kwargs,prefix",
    [
        ({"qty": 600}, "fat_finger_notional"),
        ({"qty": 6000, "px": 1.0, "last": 1.0}, "fat_finger_quantity"),
        ({"px": 230.0}, "price_collar"),
        ({"at": datetime(2026, 11, 7, 16, 0, tzinfo=UTC)}, "market_hours"),  # Saturday
        ({"at": datetime(2026, 11, 26, 16, 0, tzinfo=UTC)}, "market_hours"),  # Thanksgiving
        ({"at": datetime(2026, 11, 6, 21, 30, tzinfo=UTC)}, "market_hours"),  # 16:30 NY
        ({"side": "sell"}, "borrow"),
    ],
)
def test_each_pre_trade_check_rejects_with_its_reason(cfg, kwargs, prefix):
    oms = OMS(cfg)
    o = _order(oms, **kwargs)
    assert o.state is OrderState.REJECTED and o.reject_reason.startswith(prefix)


def test_duplicate_guard_and_short_notional_cap(cfg):
    oms = OMS(cfg)
    assert _order(oms, "a").state is OrderState.ACKED
    assert _order(oms, "b", at=FRI_1555 + timedelta(seconds=30)).reject_reason.startswith("duplicate")
    assert _order(oms, "c", at=FRI_1555 + timedelta(seconds=90)).state is OrderState.ACKED
    cfg["oms"]["max_short_notional"] = 0.1  # 10% of 100k = 10k
    oms2 = OMS(cfg)
    assert _order(oms2, "s1", sym="MSFT", side="sell", qty=40).state is OrderState.ACKED  # 8k short
    assert _order(oms2, "s2", sym="MSFT", side="sell", qty=20).reject_reason.startswith("short_notional")


def test_fx_hours_follow_the_new_york_roll(cfg):
    oms = OMS(cfg)
    fri_after_roll = datetime(2026, 11, 6, 22, 30, tzinfo=UTC)  # Fri 17:30 NY: closed
    sun_after_open = datetime(2026, 11, 8, 22, 30, tzinfo=UTC)  # Sun 17:30 NY: Monday's trade date
    assert _order(oms, "f1", "EURUSD", qty=1000, px=1.1, last=1.1, at=fri_after_roll).reject_reason.startswith("market_hours")
    assert _order(oms, "f2", "EURUSD", qty=1000, px=1.1, last=1.1, at=sun_after_open).state is OrderState.ACKED
    assert (
        _order(oms, "f3", "EURUSD", side="sell", qty=1000, px=1.1, last=1.1, at=sun_after_open + timedelta(minutes=5)).state
        is OrderState.ACKED
    )  # FX short: no borrow


def test_approval_gateway_gates_orders(cfg):
    assert _order(OMS(cfg, approval=DenyApprovalGateway())).reject_reason == "approval: refused"
    assert _order(OMS(cfg, approval=QueuedApprovalGateway())).reject_reason.startswith("approval: pending")


# ---------------------------------------------------------------- kill switch
def test_kill_switch_blocks_every_path_and_persists(cfg, tmp_path):
    path = tmp_path / "kill.json"
    cfg["oms"]["kill_switch_path"] = str(path)
    oms = OMS(cfg)
    _order(oms, "live")
    KillSwitch(path).engage("AAPL", "fat fingers upstream")  # another process engages it
    assert _order(oms, "new", qty=50).reject_reason.startswith("kill_switch: AAPL")
    assert oms.execute("live", BIG, FRI_1555) is None and oms.orders["live"].state is OrderState.ACKED
    assert _order(oms, "m", sym="MSFT").state is OrderState.ACKED  # other sleeve unaffected
    KillSwitch(path).engage("global", "desk halt")
    assert _order(oms, "m2", sym="MSFT", qty=7).reject_reason.startswith("kill_switch: global")
    assert oms.cancel("live", FRI_1555).state is OrderState.CANCELLED  # cancels still allowed
    assert set(json.loads(path.read_text())) == {"global", "AAPL"}
    KillSwitch(path).release("global")
    KillSwitch(path).release("aapl")
    assert kill_switch_for(cfg).engaged() == {}
    KillSwitch(path).engage("fx", "fx halt")
    assert _order(oms, "fx", "EURUSD", qty=1000, px=1.1, last=1.1).reject_reason.startswith("kill_switch: fx")


def test_kill_switch_blocks_the_agentic_submit_order_tool(cfg, tmp_path):
    from agentic_trader.agentic.servers import DeskTools
    from agentic_trader.data import get_provider

    path = tmp_path / "kill.json"
    cfg["oms"]["kill_switch_path"] = str(path)
    desk = DeskTools(get_provider(cfg), cfg)
    KillSwitch(path).engage("global", "halt")
    with pytest.raises(ValueError, match="kill_switch: global"):
        desk.submit_order("AAPL", "buy", 10, "shares", 2000.0, "USD", 200.0, "any-plan")
    KillSwitch(path).release("global")
    with pytest.raises(ValueError, match="plan_id"):  # past the switch, the usual checks run
        desk.submit_order("AAPL", "buy", 10, "shares", 2000.0, "USD", 200.0, "any-plan")


# ---------------------------------------------------------------- fills and costs
def test_partial_fills_at_the_participation_cap(cfg):
    oms = OMS(cfg)
    _order(oms, qty=300)
    snap = MarketSnapshot(200.0, adv=2000.0, impact_k=None)  # 10% cap -> 200 per fill
    f1 = oms.execute("o1", snap, FRI_1555)
    o = oms.orders["o1"]
    assert f1.quantity == 200 and o.state is OrderState.PARTIALLY_FILLED and o.remaining == 100
    oms.execute("o1", snap, FRI_1555 + timedelta(minutes=1))
    assert o.state is OrderState.FILLED and oms.positions["AAPL"] == 300


def test_fill_cost_matches_the_backtester_on_a_toy_order(cfg):
    cfg["costs"]["impact_coeff"] = 1.0
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2026-01-02", periods=40)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 40)))
    hist = pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": np.full(40, 50_000.0)}, index=idx)
    ins = Instrument.parse("AAPL")
    k = impact_coefficients(hist, ins, cfg)[-1]
    snap = market_snapshot(hist, ins, cfg)
    assert snap.impact_k == pytest.approx(k) and snap.adv == pytest.approx(50_000.0)
    capital, w = 100_000.0, 0.3
    notional = w * capital
    bt = quant.BacktestConfig(
        initial_capital=capital, cost_bps=cfg["costs"]["equity_cost_bps"], slippage_bps=cfg["costs"]["equity_slippage_bps"]
    )
    res = quant.run_backtest(np.array([100.0, 100.0]), np.array([w, w]), bt, impact=np.array([k, k]))
    assert fill_cost(ins, cfg, notional, 100.0, k, capital) / capital == pytest.approx(-res.returns[1], rel=1e-12)


# ---------------------------------------------------------------- reconciliation
def test_reconciliation_detects_qty_cash_and_price_breaks(cfg):
    oms = OMS(cfg)
    _order(oms)
    oms.execute("o1", BIG, FRI_1555)
    clean = reconcile(oms, {"AAPL": 100}, ledger_cash=oms.cash_balance(), ledger_prices={"AAPL": 200.0})
    assert clean.ok and clean.checked == 3 and oms.evidence.resolve(clean.evidence_id)
    bad = reconcile(oms, {"AAPL": 90, "MSFT": 5}, ledger_cash=-20_000.0, ledger_prices={"AAPL": 201.0})
    kinds = sorted((b.kind, b.key) for b in bad.breaks)
    assert kinds == [("cash", "USD"), ("price", "AAPL"), ("qty", "AAPL"), ("qty", "MSFT")]
    assert list(bad.to_frame().columns) == ["kind", "key", "oms", "ledger", "diff"]
    assert reconcile(oms, {"AAPL": 100}, ledger_prices={"AAPL": 200.05}, price_tol_bps=5.0).ok


# ---------------------------------------------------------------- settlement, calendars, FX roll
def test_nyse_holiday_rules():
    h = nyse_holidays(2026)
    assert {date(2026, 4, 3), date(2026, 6, 19), date(2026, 7, 3), date(2026, 11, 26), date(2026, 12, 25)} <= h
    assert date(2022, 1, 1) not in nyse_holidays(2022) and date(2021, 12, 31) not in nyse_holidays(2021)
    assert date(2023, 1, 2) in nyse_holidays(2023)  # Sunday New Year observed Monday


@pytest.mark.parametrize(
    "cls,trade,settle",
    [
        ("equity", date(2026, 11, 6), date(2026, 11, 9)),  # Fri -> Mon
        ("equity", date(2026, 11, 25), date(2026, 11, 27)),  # over Thanksgiving
        ("equity", date(2026, 4, 2), date(2026, 4, 6)),  # over Good Friday
        ("fx", date(2026, 11, 5), date(2026, 11, 9)),  # Thu -> Mon
        ("fx", date(2026, 11, 9), date(2026, 11, 12)),  # skips Veterans Day (USD holiday)
        ("fx", date(2026, 12, 23), date(2026, 12, 28)),  # skips Christmas and the weekend
    ],
)
def test_settlement_dates(cls, trade, settle):
    assert SleeveCalendar(cls).settlement_date(trade) == settle


def test_cash_projection_by_currency_and_settle_date(cfg):
    oms = OMS(cfg)
    _order(oms)
    oms.execute("o1", BIG, FRI_1555)
    at = datetime(2026, 11, 5, 15, 0, tzinfo=UTC)
    oms.submit("fx", "EURUSD", "buy", 5_000, price=1.1, last_close=1.1, at=at)
    oms.execute("fx", MarketSnapshot(1.1, None, None), at)
    p = oms.cash_projection().set_index(["currency", "settle_date"])["amount"]
    assert p[("EUR", date(2026, 11, 9))] == pytest.approx(5_000)
    assert p[("USD", date(2026, 11, 9))] == pytest.approx(-20_004.0 - 5_500 - oms.orders["fx"].cost)


@pytest.mark.parametrize("when", ["winter", "summer"])
def test_fx_roll_at_1700_new_york_across_dst(cfg, when):
    oms = OMS(cfg)
    if when == "winter":
        day, utc_hour = date(2026, 11, 17), 22  # EST: 17:00 NY = 22:00 UTC
    else:
        day, utc_hour = date(2026, 7, 14), 21  # EDT: 17:00 NY = 21:00 UTC
    t0 = datetime(day.year, day.month, day.day, 15, 0, tzinfo=UTC)
    oms.submit("fx", "EURUSD", "buy", 5_000, price=1.1, last_close=1.1, at=t0)
    oms.execute("fx", MarketSnapshot(1.1, None, None), t0)
    first = oms.fx_value_dates["EURUSD"]
    before = datetime(day.year, day.month, day.day, utc_hour - 1, 59, tzinfo=UTC)
    assert oms.roll_fx(before) == []
    rolls = oms.roll_fx(datetime(day.year, day.month, day.day, utc_hour, 0, tzinfo=UTC))
    cal = SleeveCalendar("fx")
    assert len(rolls) == 1 and rolls[0]["from"] == first
    assert rolls[0]["to"] == cal.settlement_date(day + timedelta(days=1)) > first
    assert oms.evidence.resolve(rolls[0]["evidence_id"])
    assert oms.roll_fx(datetime(day.year, day.month, day.day, utc_hour, 30, tzinfo=UTC)) == []  # once per roll


def test_unknown_oms_config_key_is_refused(cfg):
    cfg["oms"]["fat_finger"] = 1
    with pytest.raises(ValueError, match="unknown oms config"):
        OMS(cfg)


# ---------------------------------------------------------------- paper desk integration
def _paper_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "paper_trade_v09.py"
    spec = importlib.util.spec_from_file_location("paper_trade_v09_oms", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_paper_oms_flag_writes_a_separate_record_and_leaves_the_ledger_unchanged(tmp_path):
    mod = _paper_module()
    args = ["--data", "synthetic", "--freeze", "2024-01-02", "--as-of", "2024-02-15"]
    assert mod.main(args + ["--out", str(tmp_path / "off")]) == 0
    assert mod.main(args + ["--out", str(tmp_path / "on"), "--oms"]) == 0
    assert not (tmp_path / "off" / "oms").exists()
    a = (tmp_path / "off" / "ledger.csv").read_text()
    assert a == (tmp_path / "on" / "ledger.csv").read_text()
    run = json.loads((tmp_path / "on" / "oms" / "runs.jsonl").read_text().splitlines()[-1])
    assert run["label"] == "oms_shadow_v14" and set(run["books"]) <= {"core15", "etf11", "fx15"}
