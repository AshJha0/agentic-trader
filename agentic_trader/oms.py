"""Paper order management system (plan item 4.7): simulated, policy-gated, evidenced.

Nothing here talks to a broker. The OMS takes orders, runs pre-trade checks, simulates
fills with the backtester's own cost and impact model, keeps positions, cash and
settlement dates, and writes every state change to the agentic layer's evidence store.

Order life cycle
----------------
``NEW -> ACKED -> PARTIALLY_FILLED -> FILLED``, with ``CANCELLED`` reachable from any
live state and ``REJECTED`` only from ``NEW`` (a pre-trade check or the approval gateway
refused it). ``PARTIALLY_FILLED -> PARTIALLY_FILLED`` is legal (a second partial fill);
``FILLED``, ``CANCELLED`` and ``REJECTED`` are terminal. Any other move raises
``IllegalTransition``. Every transition carries the time it happened and the id of the
DECISION evidence record written for it.

A ``client_order_id`` is the idempotency key: submitting the same id with the same fields
returns the existing order and writes nothing; the same id with different fields is an
error, never a second order.

Pre-trade checks (each refusal names its reason, prefixed by the check)
-----------------------------------------------------------------------
``kill_switch``, ``fat_finger_notional``, ``fat_finger_quantity``, ``price_collar``
(order price against the last close), ``duplicate`` (same symbol, side and quantity
within ``duplicate_window_seconds`` of a live or filled order under another id),
``market_hours`` (per sleeve calendar, below), ``borrow`` (an equity sell that opens or
increases a short needs the symbol on ``borrow_list``), ``short_notional`` (the short
after the order may not exceed ``max_short_notional`` of capital, as
``validate.cap_short_notional`` defines it), then ``approval`` (the approval gateway of the
agentic layer; a pending answer is a rejection, not a parked order).

Calendars and clocks (validate's conventions: New York wall time)
-----------------------------------------------------------------
Equities trade 09:30-16:00 New York on NYSE sessions (weekdays minus the NYSE holiday
rules in ``nyse_holidays``) and settle T+1 on that calendar. FX trades from Sunday 17:00 to
Friday 17:00 New York; an FX trade at or after 17:00 belongs to the next trade date (the
roll), and spot settles T+2 business days, skipping weekends, 1 January, 25 December and
US Federal Reserve holidays. Open FX positions roll at 17:00 New York: their value date
moves to the spot date of the new trade date. Because both clocks are New York wall time,
DST changes move the UTC instants and nothing else.

Documented limitations: the borrow list is a static allow-list (no locate, fee or recall);
non-USD currency holidays and one-off exchange closures are not modelled unless listed
in ``extra_equity_holidays`` / ``extra_fx_holidays``; fills are at the reference price
plus modelled cost (no queue, no intraday path); a partial fill's remainder stays working
until a later ``execute`` or a cancel.

Fill cost parity with the backtester
------------------------------------
A fill of notional ``N`` on an account of capital ``C`` pays
``N * (cost_bps + slippage_bps) / 1e4 + C * K_t * (N / C) ** 1.5``, where the unit cost
comes from ``backtest.backtest_config_for`` and ``K_t`` from
``backtest.impact_coefficients``: exactly the entry cost ``quant.run_backtest`` charges for
a weight change ``N / C`` at bar ``t``. A fill is capped at ``participation_cap`` times the
modelled average daily volume (20-day mean volume for equities; ``costs.fx_adv_notional``
over price for FX, uncapped when unset).

Example (COOKBOOK-ready)::

    from datetime import datetime, timezone
    from agentic_trader.config import make_config
    from agentic_trader.oms import OMS, MarketSnapshot

    cfg = make_config(data_provider="synthetic", memory_path=None)
    cfg["oms"] = {"borrow_list": ["MSFT"], "max_order_notional": 50_000}
    oms = OMS(cfg)                                   # auto-approval gateway, fresh evidence store
    at = datetime(2026, 11, 6, 20, 55, tzinfo=timezone.utc)      # 15:55 New York, a Friday
    order = oms.submit("ord-1", "AAPL", "buy", 100, price=200.0, last_close=199.0, at=at)
    snap = MarketSnapshot(price=200.0, adv=60_000_000, impact_k=None)
    oms.execute("ord-1", snap, at)
    print(order.state, order.filled_qty, round(order.cost, 2))  # OrderState.FILLED 100.0 4.0
    print(oms.cash_projection())     # one row: USD, 2026-11-09 (T+1, a Monday), -20004.0
    oms.kill_switch.engage("global", "end of test")  # every order path now refuses
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from dateutil.easter import easter
from pandas.tseries.holiday import USFederalHolidayCalendar

from .agentic.domain import EvidenceType, ToolRequest
from .agentic.evidence import EvidenceStore
from .agentic.policy import ApprovalGateway, AutoApprovalGateway
from .backtest import backtest_config_for, impact_coefficients
from .instruments import Instrument
from .validate import EQUITY_CLOSE_NY, FX_ROLL_NY, NEW_YORK, cap_short_notional, session_close_utc

EQUITY_OPEN_NY = time(9, 30)

OMS_DEFAULTS: dict[str, Any] = {
    "max_order_notional": None,      # None: servers.default_order_cap(config) (capital x max_position)
    "max_order_quantity": 1_000_000.0,
    "price_collar_pct": 0.10,        # |price / last close - 1| allowed
    "duplicate_window_seconds": 60.0,
    "participation_cap": 0.10,       # largest fill as a fraction of modelled daily volume
    "borrow_list": [],               # equities that may be sold short
    "max_short_notional": 0.5,       # fraction of capital; None = no cap
    "kill_switch_path": None,        # JSON file; None keeps the switch in memory
    "extra_equity_holidays": [],     # ISO dates (one-off closures)
    "extra_fx_holidays": [],
}


def oms_config(config: dict) -> dict[str, Any]:
    """``OMS_DEFAULTS`` overlaid with ``config["oms"]``; unknown keys are an error."""
    given = dict(config.get("oms") or {})
    unknown = sorted(set(given) - set(OMS_DEFAULTS))
    if unknown:
        raise ValueError(f"unknown oms config keys {unknown}; known: {sorted(OMS_DEFAULTS)}")
    return {**OMS_DEFAULTS, **given}


# ------------------------------------------------------------------ calendars
def _observed(d: date) -> date:
    """NYSE observance: Saturday -> Friday, Sunday -> Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> frozenset[date]:
    """Full-day NYSE closures from the standing rules (no one-off closures).

    New Year (a Saturday 1 January is not observed on the Friday before), Martin Luther King
    Jr. Day (from 1998), Washington's Birthday, Good Friday, Memorial Day, Juneteenth (from
    2022), Independence Day, Labor Day, Thanksgiving, Christmas."""
    days: set[date] = set()
    ny = date(year, 1, 1)
    if ny.weekday() != 5:
        days.add(_observed(ny))
    if year >= 1998:
        days.add(_nth_weekday(year, 1, 0, 3))
    days.add(_nth_weekday(year, 2, 0, 3))
    days.add(easter(year) - timedelta(days=2))
    days.add(_last_weekday(year, 5, 0))
    if year >= 2022:
        days.add(_observed(date(year, 6, 19)))
    days.add(_observed(date(year, 7, 4)))
    days.add(_nth_weekday(year, 9, 0, 1))
    days.add(_nth_weekday(year, 11, 3, 4))
    days.add(_observed(date(year, 12, 25)))
    return frozenset(days)


@lru_cache(maxsize=None)
def _usd_holidays(year: int) -> frozenset[date]:
    cal = USFederalHolidayCalendar()
    return frozenset(d.date() for d in cal.holidays(date(year, 1, 1), date(year, 12, 31)))


@dataclass(frozen=True)
class SleeveCalendar:
    """Trading and settlement days of one sleeve (``"equity"`` or ``"fx"``)."""

    asset_class: str
    extra_holidays: frozenset[date] = frozenset()

    def is_trading_day(self, d: date) -> bool:
        if d.weekday() >= 5 or d in self.extra_holidays:
            return False
        if self.asset_class == "equity":
            return d not in nyse_holidays(d.year)
        return (d.month, d.day) not in ((1, 1), (12, 25))

    def is_settlement_day(self, d: date) -> bool:
        if self.asset_class == "equity":
            return self.is_trading_day(d)
        return self.is_trading_day(d) and d not in _usd_holidays(d.year)

    @property
    def settlement_lag(self) -> int:
        return 1 if self.asset_class == "equity" else 2

    def settlement_date(self, trade_date: date) -> date:
        """T+1 (equity) or T+2 (FX spot) settlement days after ``trade_date``."""
        d, n = trade_date, 0
        while n < self.settlement_lag:
            d += timedelta(days=1)
            if self.is_settlement_day(d):
                n += 1
        return d

    def trade_date(self, at: datetime) -> date:
        """The trade date ``at`` belongs to: the New York date, moved to the next day at or
        after the 17:00 roll for FX."""
        local = _aware(at).astimezone(NEW_YORK)
        d = local.date()
        if self.asset_class == "fx" and local.time() >= FX_ROLL_NY:
            d += timedelta(days=1)
        return d

    def is_open(self, at: datetime) -> bool:
        """Equity: 09:30-16:00 New York on a session. FX: the trade date is a trading day
        (Sunday 17:00 to Friday 17:00 New York, minus 1 January and 25 December)."""
        d = self.trade_date(at)
        if not self.is_trading_day(d):
            return False
        if self.asset_class == "fx":
            return True
        t = _aware(at).astimezone(NEW_YORK).time()
        return EQUITY_OPEN_NY <= t <= EQUITY_CLOSE_NY


def calendar_for(ins: Instrument, cfg: dict[str, Any]) -> SleeveCalendar:
    key = "extra_fx_holidays" if ins.is_fx else "extra_equity_holidays"
    return SleeveCalendar(ins.asset_class, frozenset(date.fromisoformat(str(d)) for d in cfg[key]))


def _aware(at: datetime) -> datetime:
    if at.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return at


# ------------------------------------------------------------------ kill switch
class KillSwitch:
    """Global and per-sleeve trading halt. A sleeve is a symbol (``"AAPL"``) or an asset
    class (``"equity"``, ``"fx"``). With a ``path`` the state lives in that JSON file and is
    re-read on every check, so a halt engaged by another process is honoured at once."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self._memory: dict[str, dict[str, str]] = {}

    def _load(self) -> dict[str, dict[str, str]]:
        if self.path is None:
            return dict(self._memory)
        if not self.path.exists():
            return {}
        return dict(json.loads(self.path.read_text(encoding="utf-8")))

    def _save(self, state: dict[str, dict[str, str]]) -> None:
        if self.path is None:
            self._memory = state
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def engage(self, scope: str, reason: str, at: datetime | None = None) -> None:
        """Halt ``scope`` (``"global"`` or a sleeve) with a reason a person can read."""
        state = self._load()
        when = (at or datetime.now(timezone.utc)).isoformat()
        state[_scope(scope)] = {"reason": reason, "at": when}
        self._save(state)

    def release(self, scope: str) -> None:
        state = self._load()
        state.pop(_scope(scope), None)
        self._save(state)

    def engaged(self) -> dict[str, dict[str, str]]:
        return self._load()

    def blocking(self, ins: Instrument) -> str | None:
        """The refusal text when ``ins`` is halted (globally, by asset class or by symbol)."""
        state = self._load()
        for scope in ("global", ins.asset_class, ins.symbol):
            if scope in state:
                return f"kill_switch: {scope} halted ({state[scope]['reason']})"
        return None


def _scope(scope: str) -> str:
    s = str(scope).strip()
    return s.lower() if s.lower() in ("global", "equity", "fx") else s.upper()


def kill_switch_for(config: dict) -> KillSwitch:
    """The persisted kill switch ``config["oms"]["kill_switch_path"]`` names (in memory, and
    so never engaged from outside, when unset). The agentic ``execution.submit_order`` tool
    checks this before writing a ticket."""
    return KillSwitch(oms_config(config)["kill_switch_path"])


# ------------------------------------------------------------------ orders
class OrderState(str, Enum):
    NEW = "NEW"
    ACKED = "ACKED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


LEGAL_TRANSITIONS: dict[OrderState, frozenset[OrderState]] = {
    OrderState.NEW: frozenset({OrderState.ACKED, OrderState.REJECTED, OrderState.CANCELLED}),
    OrderState.ACKED: frozenset({OrderState.PARTIALLY_FILLED, OrderState.FILLED, OrderState.CANCELLED}),
    OrderState.PARTIALLY_FILLED: frozenset({OrderState.PARTIALLY_FILLED, OrderState.FILLED,
                                            OrderState.CANCELLED}),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELLED: frozenset(),
    OrderState.REJECTED: frozenset(),
}
LIVE_STATES = frozenset({OrderState.NEW, OrderState.ACKED, OrderState.PARTIALLY_FILLED})


class IllegalTransition(ValueError):
    """A state change the order life cycle does not allow."""


@dataclass
class Transition:
    state: OrderState
    at: datetime
    note: str
    evidence_id: str


@dataclass
class Fill:
    quantity: float
    price: float
    cost: float
    at: datetime
    trade_date: date
    settle_date: date


@dataclass
class Order:
    client_order_id: str
    symbol: str
    asset_class: str
    side: str                       # "buy" | "sell"
    quantity: float
    price: float                    # reference price the order was checked and is filled at
    submitted_at: datetime
    state: OrderState = OrderState.NEW
    reject_reason: str = ""
    fills: list[Fill] = field(default_factory=list)
    history: list[Transition] = field(default_factory=list)

    @property
    def filled_qty(self) -> float:
        return float(sum(f.quantity for f in self.fills))

    @property
    def remaining(self) -> float:
        return self.quantity - self.filled_qty

    @property
    def cost(self) -> float:
        return float(sum(f.cost for f in self.fills))

    @property
    def signed(self) -> float:
        return 1.0 if self.side == "buy" else -1.0

    def fields(self) -> dict[str, Any]:
        """The fields that define the order (what idempotency compares)."""
        return {"symbol": self.symbol, "side": self.side, "quantity": self.quantity, "price": self.price}

    def snapshot(self) -> dict[str, Any]:
        return {"client_order_id": self.client_order_id, **self.fields(), "asset_class": self.asset_class,
                "state": self.state.value, "filled_qty": self.filled_qty, "cost": self.cost,
                "reject_reason": self.reject_reason}

    def move(self, new: OrderState, at: datetime, note: str, evidence_id: str) -> None:
        """Apply one transition, refusing any the life cycle does not allow."""
        if new not in LEGAL_TRANSITIONS[self.state]:
            raise IllegalTransition(f"{self.client_order_id}: {self.state.value} -> {new.value} is not allowed")
        self.state = new
        self.history.append(Transition(new, _aware(at), note, evidence_id))


@dataclass(frozen=True)
class MarketSnapshot:
    """What a fill needs: the fill price, the modelled average daily volume in order units
    (shares, or base-currency units for FX; None = no participation cap) and the backtester's
    impact coefficient ``K_t`` for the bar (None = no impact)."""

    price: float
    adv: float | None
    impact_k: float | None


def market_snapshot(history: pd.DataFrame, ins: Instrument, config: dict) -> MarketSnapshot:
    """Snapshot at the last bar of ``history`` with the backtester's own ADV and impact inputs."""
    close = float(history["Close"].iloc[-1])
    k = impact_coefficients(history, ins, config)
    k_t = None if k is None or not np.isfinite(k[-1]) else float(k[-1])
    if ins.is_fx:
        adv_notional = config["costs"].get("fx_adv_notional")
        adv = float(adv_notional) / close if adv_notional else None
    else:
        vol = history["Volume"].tail(20).mean() if "Volume" in history else float("nan")
        adv = float(vol) if np.isfinite(vol) and vol > 0 else None
    return MarketSnapshot(close, adv, k_t)


class _NoMacro:
    """``backtest_config_for`` reads FX carry from a provider; fill costs do not use carry."""

    def macro(self, ins: Instrument, as_of: date) -> dict[str, float]:
        return {}


def fill_cost(ins: Instrument, config: dict, notional: float, price: float, impact_k: float | None,
              capital: float) -> float:
    """Cost in account currency of filling ``notional`` at ``price``: the backtester's entry cost
    ``|dw| * unit_cost + K_t * |dw| ** 1.5`` for ``dw = notional / capital``, times capital."""
    bc = backtest_config_for(ins, config, np.array([price]), _NoMacro(), date.min)
    dw = abs(notional) / capital
    return capital * (dw * (bc.cost_bps + bc.slippage_bps) / 1e4 + (impact_k or 0.0) * dw ** 1.5)


# ------------------------------------------------------------------ OMS
class OMS:
    """The paper order book of one account. Not thread-safe: one desk, one caller."""

    def __init__(self, config: dict, evidence: EvidenceStore | None = None,
                 approval: ApprovalGateway | None = None, capital: float | None = None,
                 positions: dict[str, float] | None = None, kill_switch: KillSwitch | None = None):
        self.config = config
        self.cfg = oms_config(config)
        self.evidence = evidence if evidence is not None else EvidenceStore()
        self.approval = approval or AutoApprovalGateway()
        self.capital = float(capital if capital is not None else config.get("initial_capital", 100_000.0))
        self.account_currency = str(config.get("account_currency", "USD")).upper()
        self.kill_switch = kill_switch or KillSwitch(self.cfg["kill_switch_path"])
        self.positions: dict[str, float] = {k.upper(): float(v) for k, v in (positions or {}).items()}
        self.orders: dict[str, Order] = {}
        self.cash_flows: list[dict[str, Any]] = []      # currency, amount, settle_date, client_order_id
        self.fx_value_dates: dict[str, date] = {}       # open FX position -> value date
        self.fx_rolls: list[dict[str, Any]] = []
        if self.cfg["max_order_notional"] is None:
            from .agentic.servers import default_order_cap
            self.max_notional = default_order_cap(config, self.capital)
        else:
            self.max_notional = float(self.cfg["max_order_notional"])

    # ---------------------------------------------------------- evidence
    def _evidence(self, order: Order, summary: str, type_: EvidenceType = EvidenceType.DECISION,
                  extra: dict[str, Any] | None = None) -> str:
        payload = {**order.snapshot(), **(extra or {})}
        return self.evidence.record(type_, "oms", summary, payload, order.client_order_id).id

    def _move(self, order: Order, new: OrderState, at: datetime, note: str) -> None:
        if new not in LEGAL_TRANSITIONS[order.state]:
            raise IllegalTransition(f"{order.client_order_id}: {order.state.value} -> {new.value} is not allowed")
        prior = order.state
        order.state = new   # the evidence payload shows the state being entered
        ev = self._evidence(order, f"{order.client_order_id} {prior.value} -> {new.value}: {note}",
                            extra={"from": prior.value, "at": at.isoformat(), "note": note})
        order.state = prior
        order.move(new, at, note, ev)

    # ---------------------------------------------------------- submit
    def submit(self, client_order_id: str, symbol: str, side: str, quantity: float, price: float,
               last_close: float, at: datetime) -> Order:
        """Accept, check and acknowledge (or reject) an order. Returns the order in ACKED or
        REJECTED state; a repeat of a known ``client_order_id`` returns that order unchanged."""
        _aware(at)
        ins = Instrument.parse(symbol)
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        for name, v in (("quantity", quantity), ("price", price), ("last_close", last_close)):
            if not (isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) > 0):
                raise ValueError(f"{name} must be a positive finite number")
        order = Order(str(client_order_id), ins.symbol, ins.asset_class, side, float(quantity), float(price), at)
        known = self.orders.get(order.client_order_id)
        if known is not None:
            if known.fields() != order.fields():
                raise ValueError(f"client order id {order.client_order_id} was used for {known.fields()}; "
                                 "a new order needs a new id")
            return known
        self.orders[order.client_order_id] = order
        order.history.append(Transition(OrderState.NEW, at, "received",
                                        self._evidence(order, f"{order.client_order_id} NEW: received",
                                                       extra={"at": at.isoformat()})))
        reason = self._pre_trade(order, ins, float(last_close), at) or self._approve(order)
        if reason:
            order.reject_reason = reason
            self._move(order, OrderState.REJECTED, at, reason)
        else:
            self._move(order, OrderState.ACKED, at, "pre-trade checks passed")
        return order

    def _pre_trade(self, order: Order, ins: Instrument, last_close: float, at: datetime) -> str | None:
        cfg = self.cfg
        halted = self.kill_switch.blocking(ins)
        if halted:
            return halted
        notional = order.quantity * order.price
        if notional > self.max_notional:
            return f"fat_finger_notional: {notional:,.2f} exceeds {self.max_notional:,.2f}"
        if order.quantity > float(cfg["max_order_quantity"]):
            return f"fat_finger_quantity: {order.quantity:g} exceeds {float(cfg['max_order_quantity']):g}"
        move = order.price / last_close - 1.0
        if abs(move) > float(cfg["price_collar_pct"]):
            return (f"price_collar: {order.price:g} is {move:+.2%} from the last close {last_close:g} "
                    f"(collar {float(cfg['price_collar_pct']):.0%})")
        window = timedelta(seconds=float(cfg["duplicate_window_seconds"]))
        for other in self.orders.values():
            if (other is not order and other.fields() == order.fields()
                    and other.state not in (OrderState.REJECTED, OrderState.CANCELLED)
                    and abs(at - other.submitted_at) <= window):
                return f"duplicate: same order as {other.client_order_id} within {window.total_seconds():g}s"
        if not calendar_for(ins, cfg).is_open(at):
            return f"market_hours: {ins.asset_class} market closed at {at.astimezone(NEW_YORK):%Y-%m-%d %H:%M} New York"
        before = self.positions.get(ins.symbol, 0.0) + self._working(ins.symbol)
        after = before + order.signed * order.quantity
        if not ins.is_fx and after < 0 and after < before and ins.symbol not in {
                str(s).upper() for s in cfg["borrow_list"]}:
            return f"borrow: {ins.symbol} is not on the borrow list; the order would leave {after:g} short"
        cap = cfg["max_short_notional"]
        if after < 0 and cap is not None:
            weight = after * order.price / self.capital
            if cap_short_notional(weight, float(cap)) != weight:
                return f"short_notional: short of {weight:.2%} of capital exceeds the cap {float(cap):.0%}"
        return None

    def _working(self, symbol: str) -> float:
        """Signed quantity still to fill on live orders in ``symbol``."""
        return sum(o.signed * o.remaining for o in self.orders.values()
                   if o.symbol == symbol and o.state in (OrderState.ACKED, OrderState.PARTIALLY_FILLED))

    def _approve(self, order: Order) -> str | None:
        request = ToolRequest("oms.submit", order.fields(), order.client_order_id, "oms")
        verdict = self.approval.decide(order.client_order_id, request, "paper order")
        self._evidence(order, f"{order.client_order_id} approval via {self.approval.name}: {verdict}",
                       EvidenceType.APPROVAL, {"gateway": self.approval.name, "approved": verdict})
        if verdict is True:
            return None
        return "approval: " + ("pending; resubmit after a decision" if verdict is None else "refused")

    # ---------------------------------------------------------- fills and cancels
    def execute(self, client_order_id: str, market: MarketSnapshot, at: datetime) -> Fill | None:
        """Simulate one fill of a working order against ``market``. The fill is capped at
        ``participation_cap`` of the modelled volume; the remainder keeps working. Returns
        None when nothing could fill (halted, closed market or zero capacity)."""
        _aware(at)
        order = self.orders[client_order_id]
        if order.state not in (OrderState.ACKED, OrderState.PARTIALLY_FILLED):
            raise IllegalTransition(f"{client_order_id} is {order.state.value}; only working orders fill")
        ins = Instrument.parse(order.symbol, order.asset_class)
        cal = calendar_for(ins, self.cfg)
        blocked = self.kill_switch.blocking(ins) or (None if cal.is_open(at) else "market_hours: closed")
        if blocked:
            self._evidence(order, f"{client_order_id} fill withheld: {blocked}", extra={"at": at.isoformat()})
            return None
        qty = order.remaining
        if market.adv is not None:
            qty = min(qty, float(self.cfg["participation_cap"]) * market.adv)
        if qty <= 0:
            return None
        notional = qty * market.price
        trade_date = cal.trade_date(at)
        fill = Fill(qty, market.price, fill_cost(ins, self.config, notional, market.price, market.impact_k,
                                                 self.capital),
                    at, trade_date, cal.settlement_date(trade_date))
        order.fills.append(fill)
        self.positions[order.symbol] = self.positions.get(order.symbol, 0.0) + order.signed * qty
        self._book_cash(order, ins, fill)
        if ins.is_fx:
            if abs(self.positions[order.symbol]) > 1e-9:
                self.fx_value_dates[order.symbol] = fill.settle_date
            else:
                self.fx_value_dates.pop(order.symbol, None)
        done = order.remaining <= 1e-9
        self._move(order, OrderState.FILLED if done else OrderState.PARTIALLY_FILLED, at,
                   f"filled {qty:g} at {market.price:g}, cost {fill.cost:.4f}")
        return fill

    def _book_cash(self, order: Order, ins: Instrument, fill: Fill) -> None:
        flows = [(self.account_currency, -fill.cost)]
        if ins.is_fx:
            flows += [(str(ins.base), order.signed * fill.quantity),
                      (str(ins.quote), -order.signed * fill.quantity * fill.price)]
        else:
            flows.append((self.account_currency, -order.signed * fill.quantity * fill.price))
        for ccy, amount in flows:
            self.cash_flows.append({"currency": ccy, "amount": amount, "settle_date": fill.settle_date,
                                    "client_order_id": order.client_order_id})

    def cancel(self, client_order_id: str, at: datetime, reason: str = "cancelled") -> Order:
        """Cancel a live order (always allowed, even under a kill switch)."""
        order = self.orders[client_order_id]
        self._move(order, OrderState.CANCELLED, _aware(at), reason)
        return order

    # ---------------------------------------------------------- settlement and FX roll
    def cash_projection(self) -> pd.DataFrame:
        """Net cash per currency and settlement date, with the running balance per currency."""
        if not self.cash_flows:
            return pd.DataFrame(columns=["currency", "settle_date", "amount", "balance"])
        df = pd.DataFrame(self.cash_flows).groupby(["currency", "settle_date"], as_index=False)["amount"].sum()
        df = df.sort_values(["currency", "settle_date"]).reset_index(drop=True)
        df["balance"] = df.groupby("currency")["amount"].cumsum()
        return df

    def roll_fx(self, at: datetime) -> list[dict[str, Any]]:
        """At or after 17:00 New York, move every open FX position whose value date precedes the
        new trade date's spot date to that spot date (the tom-next roll). Returns the rolls made."""
        rolls = []
        for symbol, value_date in sorted(self.fx_value_dates.items()):
            cal = calendar_for(Instrument.parse(symbol, "fx"), self.cfg)
            new_value = cal.settlement_date(cal.trade_date(at))
            if new_value > value_date:
                roll = {"symbol": symbol, "quantity": self.positions[symbol], "from": value_date,
                        "to": new_value, "at": _aware(at)}
                self.fx_value_dates[symbol] = new_value
                ev = self.evidence.record(EvidenceType.DECISION, "oms", f"FX roll {symbol} {value_date} -> {new_value}",
                                          {k: str(v) for k, v in roll.items()}, f"roll-{symbol}")
                rolls.append({**roll, "evidence_id": ev.id})
        self.fx_rolls.extend(rolls)
        return rolls

    def cash_balance(self, currency: str | None = None) -> float:
        ccy = (currency or self.account_currency).upper()
        return float(sum(f["amount"] for f in self.cash_flows if f["currency"] == ccy))

    def last_fill_prices(self) -> dict[str, float]:
        """Quantity-weighted fill price per symbol over all fills."""
        num: dict[str, float] = {}
        den: dict[str, float] = {}
        for o in self.orders.values():
            for f in o.fills:
                num[o.symbol] = num.get(o.symbol, 0.0) + f.quantity * f.price
                den[o.symbol] = den.get(o.symbol, 0.0) + f.quantity
        return {s: num[s] / den[s] for s in num if den[s] > 0}


# ------------------------------------------------------------------ reconciliation
@dataclass(frozen=True)
class Break:
    kind: str           # "qty" | "cash" | "price"
    key: str
    oms: float
    ledger: float
    diff: float


@dataclass
class BreakReport:
    breaks: list[Break]
    checked: int
    evidence_id: str = ""

    @property
    def ok(self) -> bool:
        return not self.breaks

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame([asdict(b) for b in self.breaks], columns=["kind", "key", "oms", "ledger", "diff"])


def reconcile(oms: OMS, ledger_positions: dict[str, float], ledger_cash: float | None = None,
              ledger_prices: dict[str, float] | None = None, qty_tol: float = 1e-6, cash_tol: float = 0.01,
              price_tol_bps: float = 5.0) -> BreakReport:
    """End-of-day comparison of the OMS book with the paper ledger.

    A quantity break is any symbol whose OMS and ledger quantities differ by more than
    ``qty_tol``; a cash break is an account-currency balance off by more than ``cash_tol``;
    a price break is a fill price more than ``price_tol_bps`` from the ledger's price. The
    report is written to the evidence store as a CALCULATION record."""
    breaks: list[Break] = []
    ledger = {k.upper(): float(v) for k, v in ledger_positions.items()}
    keys = sorted(set(ledger) | {k for k, v in oms.positions.items() if abs(v) > qty_tol})
    for k in keys:
        a, b = oms.positions.get(k, 0.0), ledger.get(k, 0.0)
        if abs(a - b) > qty_tol:
            breaks.append(Break("qty", k, a, b, a - b))
    checked = len(keys)
    if ledger_cash is not None:
        a = oms.cash_balance()
        checked += 1
        if abs(a - ledger_cash) > cash_tol:
            breaks.append(Break("cash", oms.account_currency, a, float(ledger_cash), a - float(ledger_cash)))
    fills = oms.last_fill_prices()
    for k, px in sorted((ledger_prices or {}).items()):
        if k.upper() in fills:
            checked += 1
            a = fills[k.upper()]
            if abs(a / float(px) - 1.0) * 1e4 > price_tol_bps:
                breaks.append(Break("price", k.upper(), a, float(px), a - float(px)))
    report = BreakReport(breaks, checked)
    report.evidence_id = oms.evidence.record(
        EvidenceType.CALCULATION, "oms.reconcile", f"reconciliation: {len(breaks)} break(s) over {checked} checks",
        [asdict(b) for b in breaks], "reconcile").id
    return report


# ------------------------------------------------------------------ paper desk shadow record
SHADOW_LABEL = "oms_shadow_v14"


def paper_session(as_of: date, config: dict, provider: Any, books: dict[str, tuple], out: Path,
                  freeze: date) -> dict[str, Any]:
    """One OMS shadow session for ``scripts/paper_trade_v09.py --oms``.

    For each book's first (candidate) stream, the last decided weight change per sleeve
    becomes an order: held quantity ``w[T-3] * share * capital / price[T-3]`` (quantities do
    not drift, weights do), target ``w[T-2] * share * capital / price[T-2]``, whole shares
    or whole FX units, submitted one minute before that session's close and filled at its
    close with the backtester's costs. The OMS book is then reconciled against the target
    quantities. Results go to ``out`` (``orders.csv``, ``breaks.csv``, ``cash_projection.csv``,
    ``runs.jsonl``), labelled ``SHADOW_LABEL``. This is a separate record: it never reads or
    writes the frozen ledger, and capital is held at ``initial_capital`` (no compounding)."""
    from .backtest import run_portfolio_backtest
    out.mkdir(parents=True, exist_ok=True)
    capital = float(config["initial_capital"])
    rows, breaks, projections, summary = [], [], [], {}
    for book, (syms, weighting, streams, _) in books.items():
        rep = run_portfolio_backtest(syms, freeze, as_of, config, rebalance_every=5, provider=provider,
                                     weighting=weighting, cov_window=120)
        if len(rep.dates) < 3:
            continue
        stream = streams[0]
        alloc = rep.allocations.reindex(rep.dates) if rep.allocations is not None else None
        oms = OMS(config, capital=capital)
        targets: dict[str, float] = {}
        for sym, sleeve in rep.sleeves.items():
            ins = sleeve.instrument
            pos = np.asarray(sleeve.results[stream].positions, float)
            px = np.asarray(sleeve.prices, float)
            share = alloc[sym].to_numpy(float) if alloc is not None else np.full(len(rep.dates), 1 / len(rep.sleeves))
            share = pd.Series(share, index=rep.dates).reindex(sleeve.dates).ffill().fillna(0.0).to_numpy()
            if len(pos) < 3:
                continue
            held = float(np.trunc(pos[-3] * share[-3] * capital / px[-3]))
            target = float(np.trunc(pos[-2] * share[-2] * capital / px[-2]))
            oms.positions[ins.symbol] = held
            targets[ins.symbol] = target
            d = pd.Timestamp(sleeve.dates[-2]).date()
            hist = provider.history(ins, d - timedelta(days=60), d)
            hist = hist[hist.index <= pd.Timestamp(d)]
            if target == held or len(hist) < 2:
                continue
            at = session_close_utc(d, ins.asset_class) - timedelta(minutes=1)
            cid = f"{book}-{ins.symbol}-{d.isoformat()}"
            side = "buy" if target > held else "sell"
            order = oms.submit(cid, ins.symbol, side, abs(target - held), float(px[-2]),
                               float(hist["Close"].iloc[-2]), at)
            if order.state is OrderState.ACKED:
                oms.execute(cid, market_snapshot(hist, ins, config), at)
            rows.append({"label": SHADOW_LABEL, "book": book, "stream": stream, **order.snapshot(),
                         "trade_date": d.isoformat()})
        report = reconcile(oms, targets)
        breaks += [{"label": SHADOW_LABEL, "book": book, **asdict(b)} for b in report.breaks]
        proj = oms.cash_projection()
        proj.insert(0, "book", book)
        projections.append(proj)
        summary[book] = {"orders": sum(r["book"] == book for r in rows), "breaks": len(report.breaks),
                         "evidence": len(oms.evidence)}
    _append_csv(out / "orders.csv", rows)
    _append_csv(out / "breaks.csv", breaks)
    if projections:
        pd.concat(projections).to_csv(out / "cash_projection.csv", index=False)
    line = {"label": SHADOW_LABEL, "as_of": as_of.isoformat(), "books": summary}
    with open(out / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")
    return line


def _append_csv(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if rows:
        pd.DataFrame(rows).to_csv(path, mode="a", index=False, header=not path.exists())
