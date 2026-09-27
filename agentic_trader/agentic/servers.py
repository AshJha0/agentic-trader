"""Tool servers: the desk's capabilities as catalogued, policy-gated tools.

Six servers are built over a data provider and the quant core:

| server        | tools                                                   | evidence      |
|---------------|---------------------------------------------------------|---------------|
| market_data   | history, news, social, fundamentals, macro              | DATA          |
| quant         | technical, risk, alpha, baselines                       | CALCULATION   |
| knowledge     | search, list_documents                                  | DOCUMENT      |
| portfolio     | position, construct                                     | CALCULATION   |
| execution     | plan (simulation, read-only) · submit_order (HIGH risk) | CALCULATION / DECISION |

One definition serves the in-process executor, the planner's catalogue and the
optional MCP stdio server (``mcp_server.py``). Tool payloads are plain JSON
(lists, dicts, numbers, ISO dates) so they hash, serialise and cross a process
boundary unchanged.

``RecordingProvider`` wraps a provider so that the desk's agents reach data only
through these tools: every provider call the analysts make becomes a policy
check and an evidence record.
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from .. import quant
from ..alpha import alpha_report, alpha_snapshot
from ..backtest import baseline_weights
from ..data.base import MarketDataProvider, NewsItem
from ..instruments import Instrument
from ..portfolio import METHODS, construct
from .domain import Capability, EvidenceType, RiskLevel, ToolAnnotations
from .rag import KnowledgeBase, default_knowledge_base
from .tools import ToolExecutor, ToolRegistry

_DATA = ToolAnnotations(True, RiskLevel.LOW, frozenset({Capability.READ_MARKET_DATA}), EvidenceType.DATA)
_CALC = ToolAnnotations(True, RiskLevel.LOW, frozenset({Capability.RUN_ANALYTICS}), EvidenceType.CALCULATION)
_DOC = ToolAnnotations(True, RiskLevel.LOW, frozenset({Capability.READ_KNOWLEDGE}), EvidenceType.DOCUMENT)
_ORDER = ToolAnnotations(False, RiskLevel.HIGH, frozenset({Capability.PROPOSE_TRADES}), EvidenceType.DECISION)


def _clean(obj: Any) -> Any:
    """JSON-safe copy: numpy -> Python, NaN -> None, dates -> ISO."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return _clean(obj.tolist())
    if isinstance(obj, (date, pd.Timestamp)):
        return obj.isoformat()[:10]
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _as_date(v: date | str) -> date:
    return date.fromisoformat(v) if isinstance(v, str) else v


def _frame_payload(df: pd.DataFrame) -> dict[str, Any]:
    return {"dates": [d.isoformat()[:10] for d in df.index],
            **{c: _clean(df[c].to_numpy()) for c in df.columns}}


def frame_from_payload(payload: dict[str, Any]) -> pd.DataFrame:
    idx = pd.to_datetime(payload["dates"])
    cols = {k: v for k, v in payload.items() if k != "dates"}
    return pd.DataFrame(cols, index=idx).astype(float)


class DeskTools:
    """Holds the objects the tool functions close over."""

    def __init__(self, provider: MarketDataProvider, config: dict, knowledge: KnowledgeBase | None = None,
                 positions: dict[str, float] | None = None, capital: float | None = None):
        self.provider = provider
        self.config = config
        self.knowledge = knowledge or default_knowledge_base()
        self.positions = {k.upper(): float(v) for k, v in (positions or {}).items()}
        self.capital = float(capital if capital is not None else config.get("initial_capital", 100_000.0))
        self.account_currency = str(config.get("account_currency", "USD")).upper()
        self.orders: list[dict[str, Any]] = []
        self.plans: dict[str, dict[str, Any]] = {}   # plan_id -> the plan execution.plan produced

    @property
    def order_cap(self) -> float:
        """Largest notional one ticket may carry, in the account currency."""
        cap = self.config.get("execution", {}).get("max_order_notional")
        return float(cap) if cap else self.capital * float(self.config["risk"].get("max_position", 1.0))

    def _history(self, symbol: str, as_of: date, lookback_days: int | None,
                 alpha: bool = False) -> tuple[Instrument, pd.DataFrame]:
        """History up to ``as_of``. ``lookback_days=None`` means the configured window:
        ``lookback_days`` for the desk, ``alpha_lookback_days`` for the alpha library."""
        if lookback_days is None:
            lookback_days = int(self.config.get("alpha_lookback_days", 900) if alpha else self.config["lookback_days"])
        ins = Instrument.parse(symbol)
        df = self.provider.history(ins, as_of - timedelta(days=lookback_days), as_of)
        return ins, df[df.index <= pd.Timestamp(as_of)]

    # ------------------------------------------------------- market_data
    def history(self, symbol: str, as_of: date, lookback_days: int | None = None) -> dict:
        """Daily OHLCV bars up to and including the as-of close (point in time). The lookback
        defaults to the desk's configured window."""
        _, df = self._history(symbol, _as_date(as_of), lookback_days)
        return _frame_payload(df)

    def news(self, symbol: str, as_of: date, lookback_days: int = 7) -> list[dict]:
        """Headlines published on or before the as-of date within the lookback."""
        d = _as_date(as_of)
        items = self.provider.news(Instrument.parse(symbol), d, lookback_days)
        return [_news_payload(i) for i in items if i.published <= d]

    def social(self, symbol: str, as_of: date, lookback_days: int = 7) -> list[dict]:
        """Social-media posts on or before the as-of date within the lookback."""
        d = _as_date(as_of)
        items = self.provider.social(Instrument.parse(symbol), d, lookback_days)
        return [_news_payload(i) for i in items if i.published <= d]

    def fundamentals(self, symbol: str, as_of: date) -> dict:
        """Point-in-time company fundamentals (empty for FX or when unavailable)."""
        return _clean(self.provider.fundamentals(Instrument.parse(symbol), _as_date(as_of)))

    def macro(self, symbol: str, as_of: date) -> dict:
        """Point-in-time policy rates and inflation for a currency pair."""
        return _clean(self.provider.macro(Instrument.parse(symbol), _as_date(as_of)))

    # --------------------------------------------------------------- quant
    def technical(self, symbol: str, as_of: date, lookback_days: int | None = None) -> dict:
        """Technical indicator snapshot: moving averages, RSI, MACD, Bollinger, KDJ, ATR, momentum."""
        from ..agents.analysts import TechnicalAnalyst
        from ..state import TradingState
        ins, df = self._history(symbol, _as_date(as_of), lookback_days)
        if len(df) < 30:
            raise ValueError(f"not enough history for {ins.display}")
        return _clean(TechnicalAnalyst(None, self.config).gather(TradingState(ins, _as_date(as_of), df), self.provider))

    def risk(self, symbol: str, as_of: date, proposed_weight: float = 0.0, lookback_days: int | None = None) -> dict:
        """Risk facts for a proposed weight: realised vol, VaR95, CVaR95, drawdown, ATR, firm limits."""
        from ..agents.risk import risk_facts
        from ..state import Action, TradeProposal, TradingState
        ins, df = self._history(symbol, _as_date(as_of), lookback_days)
        if len(df) < 30:
            raise ValueError(f"not enough history for {ins.display}")
        st = TradingState(ins, _as_date(as_of), df)
        st.proposal = TradeProposal(Action.HOLD, float(proposed_weight), 0.0, st.last_price, None, None, 10, "")
        return _clean(risk_facts(st, self.config))

    def alpha(self, symbol: str, as_of: date, horizon: int = 10, lookback_days: int | None = None) -> dict:
        """Latest alpha signals and their information coefficients over the lookback (default:
        the configured alpha window, alpha_lookback_days)."""
        ins, df = self._history(symbol, _as_date(as_of), lookback_days, alpha=True)
        if len(df) < 300:
            raise ValueError(f"alpha evaluation needs at least 300 bars for {ins.display}")
        carry = self.provider.carry_series(ins, df.index) if ins.is_fx else None
        rep = alpha_report(df, ins, horizon, carry_series=carry)
        snap = alpha_snapshot(df, ins, carry)
        return _clean({"horizon": horizon, "latest": snap, "ic": rep.table.to_dict(orient="index"),
                       "best": rep.best(3)})

    def xalpha(self, symbols: list[str], as_of: date, horizon: int = 10, lookback_days: int | None = None) -> dict:
        """Cross-sectional alpha scores across a universe: today's z-scored ranks per name, the
        per-date IC summary of every alpha over the lookback, and the best alphas."""
        from ..xalpha import xalpha_report, xalpha_snapshot
        if len(symbols) < 3:
            raise ValueError("a cross-sectional view needs at least 3 symbols")
        d = _as_date(as_of)
        frames, instruments, carry = {}, {}, {}
        for s in symbols:
            ins, df = self._history(s, d, lookback_days, alpha=True)
            if len(df) < 300:
                raise ValueError(f"cross-sectional evaluation needs at least 300 bars for {ins.display}")
            frames[ins.symbol], instruments[ins.symbol] = df, ins
            if ins.is_fx:
                carry[ins.symbol] = self.provider.carry_series(ins, df.index)
        rep = xalpha_report(frames, instruments, horizon, carry=carry or None)
        snap = xalpha_snapshot(frames, instruments, carry=carry or None)
        return _clean({"horizon": horizon, "latest": snap, "ic": rep.table.to_dict(orient="index"),
                       "best": rep.best(3), "groups": rep.groups})

    def baselines(self, symbol: str, start: date, end: date) -> dict:
        """Rule-based baseline backtests (buy & hold, vol-target, SMA, MACD, KDJ+RSI, ZMR)."""
        ins = Instrument.parse(symbol)
        s, e = _as_date(start), _as_date(end)
        if e <= s:
            raise ValueError("end must be after start")
        full = self.provider.history(ins, s - timedelta(days=self.config["lookback_days"]), e)
        mask = (full.index >= pd.Timestamp(s)) & (full.index <= pd.Timestamp(e))
        prices = full.loc[mask, "Close"].to_numpy()
        if prices.size < 2:
            raise ValueError("fewer than 2 bars in the window")
        cfg = quant.BacktestConfig(periods_per_year=ins.periods_per_year, allow_short=ins.is_fx)
        out = {}
        for name, w in baseline_weights(full, ins.is_fx, periods_per_year=ins.periods_per_year).items():
            m = quant.run_backtest(prices, w[mask], cfg).metrics
            out[name] = {"CR": m.cumulative_return, "Sharpe": m.sharpe, "MDD": m.max_drawdown}
        return _clean(out)

    # ----------------------------------------------------------- knowledge
    def search(self, query: str, k: int = 3) -> list[dict]:
        """Retrieve the most relevant passages from the desk's runbooks and policies."""
        if not 1 <= k <= 10:
            raise ValueError("k must be between 1 and 10")
        return [p.to_dict() for p in self.knowledge.search(query, k)]

    def list_documents(self) -> list[str]:
        """Titles of the documents in the knowledge base."""
        return self.knowledge.documents

    # ----------------------------------------------------------- portfolio
    def position(self, symbol: str) -> dict:
        """The current position weight for a symbol (0 when not held), the account capital, and
        any tickets recorded against the symbol this session (``pending``)."""
        sym = Instrument.parse(symbol).symbol
        out = {"symbol": sym, "weight": self.positions.get(sym, 0.0), "capital": self.capital}
        pending = [{k: t[k] for k in ("id", "side", "intent", "quantity", "quantity_unit", "notional", "status")}
                   for t in self.orders if t["symbol"] == sym]
        if pending:
            out["pending"] = pending
        return out

    def construct(self, symbols: list[str], targets: list[float], as_of: date,
                  method: str = "risk_parity", lookback_days: int | None = None) -> dict:
        """Allocate capital across signed targets using trailing covariance (no look-ahead)."""
        if len(symbols) != len(targets) or not symbols:
            raise ValueError("symbols and targets must be non-empty and the same length")
        if method not in METHODS:
            raise ValueError(f"method must be one of {METHODS}")
        d = _as_date(as_of)
        rets = {}
        for s in symbols:
            ins, df = self._history(s, d, lookback_days)
            rets[ins.symbol] = df["Close"].pct_change()
        frame = pd.DataFrame(rets).dropna(how="all")
        pw = construct({Instrument.parse(s).symbol: t for s, t in zip(symbols, targets)}, frame, method,
                       max_weight=self.config["risk"].get("max_position", 1.0),
                       target_vol=self.config["risk"].get("target_vol"))
        return _clean({**pw.to_dict(), "contributions": pw.contributions.to_dict(orient="index")})

    # ----------------------------------------------------------- execution
    def _adv(self, ins: Instrument, df: pd.DataFrame, last: float) -> float | None:
        """Average daily volume in the order's units: 20-day share volume for equities; for FX the
        configured notional ADV (``costs.fx_adv_notional``, quote currency) in base units, or None."""
        if ins.is_fx:
            adv_notional = self.config["costs"].get("fx_adv_notional")
            return float(adv_notional) / last if adv_notional else None
        return float(df["Volume"].tail(20).mean()) if df["Volume"].sum() > 0 else None

    def _next_session(self, ins: Instrument, as_of: date) -> pd.Series | None:
        """The first daily bar after ``as_of`` (the session a decision at that close can trade in),
        or None when the provider has none yet."""
        df = self.provider.history(ins, as_of + timedelta(days=1), as_of + timedelta(days=14))
        df = df[df.index > pd.Timestamp(as_of)] if len(df) else df
        return df.iloc[0] if len(df) else None

    def plan(self, symbol: str, as_of: date, target_weight: float, current_weight: float | None = None,
             algo: str | None = None) -> dict:
        """Size a weight change into an order and simulate working it (no order is sent).

        The order is sized at the as-of close from the desk's position book (``current_weight``
        may be given when the book does not know the symbol; a value that disagrees with the
        book is refused), in whole shares or whole FX lots, with the notional in the account
        currency and the quantity in shares or the base currency (``quantity_unit``). A negative
        equity target under the long-only policy is truncated to flat (``intent`` says reduce vs
        short). Fills are simulated on the NEXT session's bars, the first a decision at the
        as-of close can trade in; when the provider has no such session yet the plan is returned
        with ``simulated: false`` instead of a fill on the as-of day. ``plan_id`` is what
        ``submit_order`` requires."""
        from ..algo import base_to_account_rate, plan_execution, simulate_execution, synthetic_intraday_bars
        from ..state import Action, FinalDecision
        d = _as_date(as_of)
        ins, df = self._history(symbol, d, 60)
        if df.empty:
            raise ValueError(f"no bars for {ins.display}")
        held = self.positions.get(ins.symbol)
        if current_weight is None:
            cw = 0.0 if held is None else held
        else:
            cw = float(current_weight)
            if held is not None and abs(held - cw) > 1e-6:
                raise ValueError(f"current_weight {cw:+.4f} disagrees with the desk's book "
                                 f"({ins.symbol} held at {held:+.4f})")
        last = float(df["Close"].iloc[-1])
        adv = self._adv(ins, df, last)
        risk = self.config["risk"]
        allow_short = bool(risk["allow_short_fx"] if ins.is_fx else risk["allow_short_equity"])
        rate = None
        if ins.is_fx and self.account_currency not in (ins.base, ins.quote):
            rate = base_to_account_rate(self.provider, ins.base, self.account_currency, d)
        target = float(target_weight)
        dec = FinalDecision(ins.symbol, d, Action.HOLD, target, 0.0, None, None, "")
        plan = plan_execution(dec, ins, cw, self.capital, last, adv, algo,  # type: ignore[arg-type]
                              account_currency=self.account_currency, base_to_account=rate,
                              allow_short=allow_short,
                              lot_size=self.config.get("execution", {}).get("fx_lot_size", 1000.0),
                              ac_kappa=float(self.config["costs"].get("ac_kappa") or 3.0))
        if plan is None:
            effective = target if (allow_short or target >= 0) else 0.0
            note = "" if effective == target else \
                f" (target {target:+.2f} truncated to flat: shorting {ins.display} is not allowed)"
            return {"trade": False, "reason": "target equals current position" + note}
        self.plans[plan.id] = plan.to_dict()
        out: dict[str, Any] = {"trade": True, **plan.to_dict(), "as_of": d.isoformat()}
        nxt = self._next_session(ins, d)
        if nxt is None:
            out.update(simulated=False, note=f"no session after {d} is available yet: the order executes on the "
                                             "next session, so no fill was simulated")
            return _clean(out)
        bars = synthetic_intraday_bars(nxt, plan.slices, "fx" if ins.is_fx else "equity")
        daily_vol = _daily_vol(df)
        spread = self.config["costs"]["fx_spread_pips"] * ins.pip_size / last * 1e4 if ins.is_fx else 2.0
        rep = simulate_execution(plan.schedule(bars), bars, plan.side, plan.algo, spread, 1.0, daily_vol, adv,
                                 requested=plan.quantity)
        out.update(simulated=True, execution_date=pd.Timestamp(nxt.name).date().isoformat(), **rep.to_dict())
        return _clean(out)

    def submit_order(self, symbol: str, side: str, quantity: float, quantity_unit: str, notional: float,
                     notional_currency: str, price: float, plan_id: str, note: str = "") -> dict:
        """Record an order ticket for the desk's OMS. High risk: always needs approval.
        The framework never connects to a broker; this writes a ticket only.

        A ticket is the plan ``execution.plan`` produced, not a bare number: ``quantity`` in
        ``quantity_unit`` (whole shares, or whole lots of the pair's base currency), ``notional``
        in ``notional_currency`` (the account currency), the reference ``price`` it was sized at,
        and the ``plan_id`` that binds those fields together. The ticket is refused when the
        fields do not match the plan reference, the notional exceeds the per-order cap, or it
        would take a long-only book short; ``intent`` records reduce vs short against the book."""
        from ..algo import plan_reference, trade_intent
        ins = Instrument.parse(symbol)
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        for name, v in (("quantity", quantity), ("notional", notional), ("price", price)):
            if not (isinstance(v, (int, float)) and math.isfinite(float(v)) and float(v) > 0):
                raise ValueError(f"{name} must be a positive finite number")
        quantity, notional, price = float(quantity), float(notional), float(price)
        expected_unit = str(ins.base) if ins.is_fx else "shares"
        if str(quantity_unit) != expected_unit:
            raise ValueError(f"quantity_unit for {ins.display} must be {expected_unit!r}, got {quantity_unit!r}")
        if str(notional_currency).upper() != self.account_currency:
            raise ValueError(f"notional_currency must be the account currency {self.account_currency}, "
                             f"got {notional_currency!r}")
        if plan_id != plan_reference(ins.symbol, side, quantity, quantity_unit, notional, notional_currency, price):
            raise ValueError("plan_id does not match the ticket's fields: submit the plan execution.plan produced, "
                             "unchanged")
        lot = float(self.config.get("execution", {}).get("fx_lot_size", 1000.0) or 1.0) if ins.is_fx else 1.0
        if abs(quantity / lot - round(quantity / lot)) > 1e-6:
            what = f"whole lots of {lot:g} {expected_unit}" if ins.is_fx else "whole shares"
            raise ValueError(f"quantity {quantity} is not {what}")
        if notional > self.order_cap:
            raise ValueError(f"notional {notional:,.0f} {self.account_currency} exceeds the per-order cap "
                             f"{self.order_cap:,.0f}")
        before = self.positions.get(ins.symbol, 0.0)
        after = before + (1.0 if side == "buy" else -1.0) * notional / self.capital
        one_lot = notional / quantity * lot / self.capital   # a residual below one lot counts as flat
        risk = self.config["risk"]
        allow_short = bool(risk["allow_short_fx"] if ins.is_fx else risk["allow_short_equity"])
        if not allow_short and after < -1e-9:
            raise ValueError(f"{ins.display} is long-only and the book holds {before:+.4f}: a {side} of "
                             f"{notional:,.0f} {self.account_currency} would leave it at {after:+.4f} (short); "
                             f"at most {max(before, 0.0) * self.capital:,.0f} may be sold (reduce to flat)")
        ticket = {"id": f"ORD-{len(self.orders) + 1:05d}", "plan_id": plan_id, "symbol": ins.symbol,
                  "side": side, "intent": trade_intent(before, after, tol=one_lot), "quantity": quantity,
                  "quantity_unit": quantity_unit, "notional": notional, "notional_currency": self.account_currency,
                  "price": price, "position_before": before, "position_after": round(after, 6),
                  "plan_known": plan_id in self.plans, "note": note, "status": "ticketed"}
        self.orders.append(ticket)
        return ticket


def _daily_vol(df: pd.DataFrame, default: float = 0.02) -> float:
    """Trailing 20-day close-to-close volatility (daily, decimal); ``default`` when there are too
    few bars for a finite, positive estimate."""
    v = df["Close"].pct_change().tail(20).std()
    return float(v) if np.isfinite(v) and v > 0 else default


def ticket_from_plan(plan: dict[str, Any], note: str = "") -> dict[str, Any]:
    """The ``execution.submit_order`` arguments for a plan payload returned by ``execution.plan``."""
    if not plan.get("trade"):
        raise ValueError("the plan has nothing to trade")
    return {"symbol": plan["symbol"], "side": plan["side"], "quantity": plan["quantity"],
            "quantity_unit": plan["quantity_unit"], "notional": plan["notional"],
            "notional_currency": plan["notional_currency"], "price": plan["price"], "plan_id": plan["plan_id"],
            "note": note}


def _news_payload(i: NewsItem) -> dict:
    return {"published": i.published.isoformat(), "headline": i.headline, "source": i.source,
            "summary": i.summary, "sentiment": i.sentiment}


def build_registry(tools: DeskTools) -> ToolRegistry:
    reg = ToolRegistry()
    for fn in (tools.history, tools.news, tools.social, tools.fundamentals, tools.macro):
        reg.register("market_data", fn, annotations=_DATA)
    for fn in (tools.technical, tools.risk, tools.alpha, tools.xalpha, tools.baselines):
        reg.register("quant", fn, annotations=_CALC)
    reg.register("knowledge", tools.search, annotations=_DOC)
    reg.register("knowledge", tools.list_documents, annotations=_DOC)
    reg.register("portfolio", tools.position, annotations=_DATA)
    reg.register("portfolio", tools.construct, annotations=_CALC)
    reg.register("execution", tools.plan, annotations=_CALC)
    reg.register("execution", tools.submit_order, annotations=_ORDER)
    return reg


class RecordingProvider(MarketDataProvider):
    """A provider whose every call goes through the tool executor.

    The desk's analysts keep calling ``provider.news(...)`` as before; here each
    call is a policy-checked ``market_data.*`` tool call that leaves an evidence
    record. A denied or failed call returns "no data", so an analyst abstains
    instead of seeing something it was not allowed to see.
    """

    name = "recording"

    def __init__(self, executor: ToolExecutor, inner: MarketDataProvider, correlation_id: str):
        super().__init__(inner.config)
        self.executor, self.inner, self.cid = executor, inner, correlation_id
        self.real_world = inner.real_world

    def _call(self, name: str, **args: Any) -> Any:
        res = self.executor.call(name, correlation_id=self.cid, requested_by="analyst", **args)
        return res.payload if res.ok else None

    def history(self, instrument: Instrument, start: date, end: date) -> pd.DataFrame:
        lookback = max((end - start).days, 1)
        payload = self._call("market_data.history", symbol=instrument.symbol, as_of=end, lookback_days=lookback)
        if payload is None:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        return frame_from_payload(payload)

    def news(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        items = self._call("market_data.news", symbol=instrument.symbol, as_of=as_of, lookback_days=lookback_days)
        return [_news_item(i) for i in items or []]

    def social(self, instrument: Instrument, as_of: date, lookback_days: int) -> list[NewsItem]:
        items = self._call("market_data.social", symbol=instrument.symbol, as_of=as_of, lookback_days=lookback_days)
        return [_news_item(i) for i in items or []]

    def fundamentals(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        return self._call("market_data.fundamentals", symbol=instrument.symbol, as_of=as_of) or {}

    def macro(self, instrument: Instrument, as_of: date) -> dict[str, Any]:
        return self._call("market_data.macro", symbol=instrument.symbol, as_of=as_of) or {}

    def carry_series(self, instrument: Instrument, dates: pd.DatetimeIndex) -> np.ndarray:
        return self.inner.carry_series(instrument, dates)


def _news_item(d: dict) -> NewsItem:
    return NewsItem(date.fromisoformat(d["published"]), d["headline"], d.get("source", ""),
                    d.get("summary", ""), d.get("sentiment"))
