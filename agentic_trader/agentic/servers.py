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
        self.orders: list[dict[str, Any]] = []

    def _history(self, symbol: str, as_of: date, lookback_days: int) -> tuple[Instrument, pd.DataFrame]:
        ins = Instrument.parse(symbol)
        df = self.provider.history(ins, as_of - timedelta(days=lookback_days), as_of)
        return ins, df[df.index <= pd.Timestamp(as_of)]

    # ------------------------------------------------------- market_data
    def history(self, symbol: str, as_of: date, lookback_days: int = 400) -> dict:
        """Daily OHLCV bars up to and including the as-of close (point in time)."""
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
    def technical(self, symbol: str, as_of: date, lookback_days: int = 400) -> dict:
        """Technical indicator snapshot: moving averages, RSI, MACD, Bollinger, KDJ, ATR, momentum."""
        from ..agents.analysts import TechnicalAnalyst
        from ..state import TradingState
        ins, df = self._history(symbol, _as_date(as_of), lookback_days)
        if len(df) < 30:
            raise ValueError(f"not enough history for {ins.display}")
        return _clean(TechnicalAnalyst(None, self.config).gather(TradingState(ins, _as_date(as_of), df), self.provider))

    def risk(self, symbol: str, as_of: date, proposed_weight: float = 0.0, lookback_days: int = 400) -> dict:
        """Risk facts for a proposed weight: realised vol, VaR95, CVaR95, drawdown, ATR, firm limits."""
        from ..agents.risk import risk_facts
        from ..state import Action, TradeProposal, TradingState
        ins, df = self._history(symbol, _as_date(as_of), lookback_days)
        if len(df) < 30:
            raise ValueError(f"not enough history for {ins.display}")
        st = TradingState(ins, _as_date(as_of), df)
        st.proposal = TradeProposal(Action.HOLD, float(proposed_weight), 0.0, st.last_price, None, None, 10, "")
        return _clean(risk_facts(st, self.config))

    def alpha(self, symbol: str, as_of: date, horizon: int = 10, lookback_days: int = 900) -> dict:
        """Latest alpha signals and their information coefficients over the lookback."""
        ins, df = self._history(symbol, _as_date(as_of), lookback_days)
        if len(df) < 300:
            raise ValueError(f"alpha evaluation needs at least 300 bars for {ins.display}")
        carry = self.provider.carry_series(ins, df.index) if ins.is_fx else None
        rep = alpha_report(df, ins, horizon, carry_series=carry)
        snap = alpha_snapshot(df, ins, carry)
        return _clean({"horizon": horizon, "latest": snap, "ic": rep.table.to_dict(orient="index"),
                       "best": rep.best(3)})

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
        """The current position weight for a symbol (0 when not held)."""
        sym = Instrument.parse(symbol).symbol
        return {"symbol": sym, "weight": self.positions.get(sym, 0.0), "capital": self.capital}

    def construct(self, symbols: list[str], targets: list[float], as_of: date,
                  method: str = "risk_parity", lookback_days: int = 400) -> dict:
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
    def plan(self, symbol: str, as_of: date, target_weight: float, current_weight: float = 0.0,
             algo: str | None = None) -> dict:
        """Simulate executing a weight change with an execution algorithm (no order is sent)."""
        from ..algo import plan_execution, simulate_execution, synthetic_intraday_bars
        from ..state import Action, FinalDecision
        d = _as_date(as_of)
        ins, df = self._history(symbol, d, 60)
        if df.empty:
            raise ValueError(f"no bars for {ins.display}")
        last = float(df["Close"].iloc[-1])
        adv = float(df["Volume"].tail(20).mean()) if df["Volume"].sum() > 0 else None
        dec = FinalDecision(ins.symbol, d, Action.HOLD, float(target_weight), 0.0, None, None, "")
        plan = plan_execution(dec, ins, float(current_weight), self.capital, last, adv, algo)  # type: ignore[arg-type]
        if plan is None:
            return {"trade": False, "reason": "target equals current position"}
        bars = synthetic_intraday_bars(df.iloc[-1], plan.slices, "fx" if ins.is_fx else "equity")
        daily_vol = float(df["Close"].pct_change().tail(20).std() or 0.02)
        spread = self.config["costs"]["fx_spread_pips"] * ins.pip_size / last * 1e4 if ins.is_fx else 2.0
        rep = simulate_execution(plan.schedule(bars), bars, plan.side, plan.algo, spread, 1.0, daily_vol, adv)
        return _clean({"trade": True, "side": plan.side, "quantity": plan.quantity, "notional": plan.notional,
                       "algo": plan.algo, "slices": plan.slices, "reason": plan.reason,
                       "participation_of_adv": plan.participation_of_adv, **rep.to_dict()})

    def submit_order(self, symbol: str, side: str, quantity: float, note: str = "") -> dict:
        """Record an order ticket for the desk's OMS. High risk: always needs approval.
        The framework never connects to a broker; this writes a ticket only."""
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        if not quantity > 0:
            raise ValueError("quantity must be positive")
        ticket = {"id": f"ORD-{len(self.orders) + 1:05d}", "symbol": Instrument.parse(symbol).symbol,
                  "side": side, "quantity": float(quantity), "note": note, "status": "ticketed"}
        self.orders.append(ticket)
        return ticket


def _news_payload(i: NewsItem) -> dict:
    return {"published": i.published.isoformat(), "headline": i.headline, "source": i.source,
            "summary": i.summary, "sentiment": i.sentiment}


def build_registry(tools: DeskTools) -> ToolRegistry:
    reg = ToolRegistry()
    for fn in (tools.history, tools.news, tools.social, tools.fundamentals, tools.macro):
        reg.register("market_data", fn, annotations=_DATA)
    for fn in (tools.technical, tools.risk, tools.alpha, tools.baselines):
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
