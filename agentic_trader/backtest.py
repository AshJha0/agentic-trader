"""Walk-forward backtests of the agent firm against rule-based baselines.

At each rebalance date the full agent graph is run with data up to that date's
close and the current position; the resulting target weight (and its stop /
take-profit levels) is held until the next rebalance. Returns and metrics come
from the C++ backtester.

Baselines are the paper's five (Buy & Hold, SMA, MACD, KDJ+RSI, ZMR) plus
``B&H vol-target``: buy & hold scaled every day to the same volatility target the
risk team uses, from trailing (ex-ante) volatility. It is the fair control for a
risk-managed strategy: beating plain buy & hold on drawdown is automatic when you
hold less; beating the vol-targeted version requires good directional calls.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

import numpy as np
import pandas as pd

from . import quant
from .config import make_config
from .data import MarketDataProvider, get_provider
from .graph import TradingGraph
from .instruments import Instrument
from .llm import LLM, get_llm
from .memory import DecisionMemory
from .state import FinalDecision

AGENT = "AgenticTrader"


@dataclass
class ComparisonReport:
    instrument: Instrument
    dates: pd.DatetimeIndex
    results: dict[str, quant.BacktestResult]
    decisions: list[FinalDecision] = field(default_factory=list)
    backtest_config: quant.BacktestConfig | None = None
    carry: np.ndarray | None = None  # annual carry per bar actually applied (FX)

    def table(self) -> pd.DataFrame:
        rows = {}
        for name, r in self.results.items():
            m = r.metrics
            rows[name] = {
                "CR%": 100 * m.cumulative_return, "AR%": 100 * m.annualized_return,
                "Vol%": 100 * m.annualized_vol, "Sharpe": m.sharpe, "t(SR)": m.sharpe_tstat,
                "Sortino": m.sortino, "MDD%": 100 * m.max_drawdown, "Calmar": m.calmar,
                "Win%": 100 * m.win_rate, "Exp%": 100 * m.avg_exposure,
                "Trades": m.num_trades, "Stops": r.stop_exits,
            }
        return pd.DataFrame(rows).T.round(2)

    def equity_curves(self) -> pd.DataFrame:
        return pd.DataFrame({k: r.equity for k, r in self.results.items()}, index=self.dates)

    def returns(self) -> pd.DataFrame:
        return pd.DataFrame({k: r.returns for k, r in self.results.items()}, index=self.dates)


def backtest_config_for(ins: Instrument, config: dict, prices: np.ndarray,
                        provider: MarketDataProvider, start: date) -> quant.BacktestConfig:
    """Cost, carry and shorting model for an instrument.

    The FX spread is converted from pips to bps at the window's *first* price (not
    the window average, which would use prices not yet seen).
    """
    costs, risk = config["costs"], config["risk"]
    cfg = quant.BacktestConfig(
        initial_capital=config["initial_capital"],
        periods_per_year=ins.periods_per_year,
        risk_free_annual=config["risk_free_annual"],
        max_leverage=risk["max_position"],
    )
    if ins.is_fx:
        cfg.cost_bps = costs["fx_spread_pips"] * ins.pip_size / float(prices[0]) * 1e4 / 2
        cfg.slippage_bps = costs["fx_slippage_bps"]
        cfg.allow_short = risk["allow_short_fx"]
        cfg.carry_annual = provider.macro(ins, start).get("rate_diff", 0.0) / 100.0
    else:
        cfg.cost_bps = costs["equity_cost_bps"]
        cfg.slippage_bps = costs["equity_slippage_bps"]
        cfg.borrow_annual = costs["equity_borrow_annual"]
        cfg.allow_short = risk["allow_short_equity"]
    return cfg


def baseline_weights(full: pd.DataFrame, allow_short: bool, target_vol: float = 0.15,
                     max_position: float = 1.0,
                     periods_per_year: float = 252.0) -> dict[str, np.ndarray]:
    c, h, l = (full[k].to_numpy() for k in ("Close", "High", "Low"))
    rv = quant.realized_vol(c, 20, periods_per_year)
    with np.errstate(divide="ignore", invalid="ignore"):
        vt = np.where(rv > 0, np.minimum(max_position, target_vol / rv), 0.0)
    return {
        "Buy&Hold": quant.strat_buy_hold(c),
        "B&H vol-target": np.nan_to_num(vt, nan=0.0),
        "SMA(20/50)": quant.strat_sma_cross(c, 20, 50, allow_short),
        "MACD": quant.strat_macd(c, 12, 26, 9, allow_short),
        "KDJ+RSI": quant.strat_kdj_rsi(h, l, c, 9, 14, 30.0, 70.0, allow_short),
        "ZMR": quant.strat_zmr(c, 20, 1.0, 0.0, allow_short),
    }


def _parse(d: date | str) -> date:
    return date.fromisoformat(d) if isinstance(d, str) else d


def run_agent_backtest(symbol: str, start: date | str, end: date | str,
                       config: dict | None = None, rebalance_every: int = 5,
                       provider: MarketDataProvider | None = None, llm: LLM | None = None,
                       asset_class: str | None = None,
                       on_decision: Callable[[FinalDecision], None] | None = None,
                       include_agent: bool = True) -> ComparisonReport:
    cfg = make_config(config)
    ins = Instrument.parse(symbol, asset_class)
    start, end = _parse(start), _parse(end)
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    provider = provider or get_provider(cfg)

    full = provider.history(ins, start - timedelta(days=cfg["lookback_days"]), end)
    mask = (full.index >= pd.Timestamp(start)) & (full.index <= pd.Timestamp(end))
    window = full.loc[mask]
    if len(window) < 2:
        raise ValueError(f"backtest window {start}..{end} has fewer than 2 bars for {ins.display}")
    prices = window["Close"].to_numpy()
    bt = backtest_config_for(ins, cfg, prices, provider, start)
    carry = provider.carry_series(ins, window.index) if ins.is_fx else None
    ohlc = dict(open=window["Open"].to_numpy(), high=window["High"].to_numpy(),
                low=window["Low"].to_numpy())

    results: dict[str, quant.BacktestResult] = {}
    decisions: list[FinalDecision] = []
    if include_agent:
        graph = TradingGraph(cfg, provider=provider,
                             llm=llm if llm is not None else get_llm(cfg),
                             memory=DecisionMemory(None), on_event=lambda *_: None)
        n = len(window)
        w = np.full(n, np.nan)
        stop, take = np.full(n, np.nan), np.full(n, np.nan)
        reb = np.zeros(n)
        held = 0.0
        for i in range(0, n - 1, max(1, rebalance_every)):
            _, dec = graph.propagate(ins, window.index[i].date(), current_weight=held)
            w[i] = dec.target_weight
            stop[i] = np.nan if dec.stop_loss is None else dec.stop_loss
            take[i] = np.nan if dec.take_profit is None else dec.take_profit
            reb[i] = 1.0
            held = dec.target_weight
            decisions.append(dec)
            if on_decision:
                on_decision(dec)
        # Hold each decision (weight and its protective levels) until the next one.
        w = pd.Series(w).ffill().fillna(0.0).to_numpy()
        seg = np.cumsum(reb)  # decision index per bar (0 before the first)
        first = np.flatnonzero(reb)
        stop = np.where(seg > 0, stop[first[np.maximum(seg.astype(int) - 1, 0)]], np.nan)
        take = np.where(seg > 0, take[first[np.maximum(seg.astype(int) - 1, 0)]], np.nan)
        extras = dict(carry=carry, rebalance=reb)
        if cfg.get("backtest", {}).get("use_stops"):
            extras.update(ohlc, stop=stop, take=take)
        results[AGENT] = quant.run_backtest(prices, w, bt, **extras)

    for name, weights in baseline_weights(full, bt.allow_short, cfg["risk"]["target_vol"],
                                          cfg["risk"]["max_position"],
                                          ins.periods_per_year).items():
        results[name] = quant.run_backtest(prices, weights[mask], bt, carry=carry)
    return ComparisonReport(ins, window.index, results, decisions, bt, carry)


# ------------------------------------------------------------------ portfolio
@dataclass
class PortfolioReport:
    """Equal-capital sleeves, one per instrument, combined daily."""
    symbols: list[str]
    dates: pd.DatetimeIndex
    returns: pd.DataFrame            # strategy -> portfolio daily returns
    metrics: dict[str, quant.Metrics]
    sleeves: dict[str, ComparisonReport]

    def table(self) -> pd.DataFrame:
        rows = {}
        for name, m in self.metrics.items():
            rows[name] = {"CR%": 100 * m.cumulative_return, "AR%": 100 * m.annualized_return,
                          "Vol%": 100 * m.annualized_vol, "Sharpe": m.sharpe,
                          "t(SR)": m.sharpe_tstat, "MDD%": 100 * m.max_drawdown,
                          "Calmar": m.calmar, "Exp%": 100 * m.avg_exposure}
        return pd.DataFrame(rows).T.round(2)


def run_portfolio_backtest(symbols: list[str], start: date | str, end: date | str,
                           config: dict | None = None, rebalance_every: int = 5,
                           provider: MarketDataProvider | None = None, llm: LLM | None = None,
                           on_decision: Callable[[FinalDecision], None] | None = None,
                           ) -> PortfolioReport:
    """Run every symbol as its own sleeve with 1/N of the capital and combine them.

    Each sleeve is a full walk-forward backtest (costs, carry, stops) of the agent
    and of every baseline. The portfolio return on a day is the average of the
    sleeves' returns (equal capital, rebalanced daily). Equity and FX calendars
    differ, so a sleeve with no bar on a date contributes 0 that day.
    """
    if not symbols:
        raise ValueError("run_portfolio_backtest needs at least one symbol")
    cfg = make_config(config)
    provider = provider or get_provider(cfg)
    sleeves = {s: run_agent_backtest(s, start, end, cfg, rebalance_every, provider, llm,
                                     on_decision=on_decision) for s in symbols}
    dates = sorted(set().union(*(r.dates for r in sleeves.values())))
    idx = pd.DatetimeIndex(dates)
    strategies = list(next(iter(sleeves.values())).results)
    rets, metrics = {}, {}
    for name in strategies:
        per = pd.DataFrame({s: pd.Series(r.results[name].returns, index=r.dates)
                            for s, r in sleeves.items()}).reindex(idx).fillna(0.0)
        pos = pd.DataFrame({s: pd.Series(np.abs(r.results[name].positions), index=r.dates)
                            for s, r in sleeves.items()}).reindex(idx).fillna(0.0)
        port = per.mean(axis=1)
        rets[name] = port
        equity = cfg["initial_capital"] * np.cumprod(1.0 + port.to_numpy())
        ppy = max(r.instrument.periods_per_year for r in sleeves.values())
        metrics[name] = quant.compute_metrics(equity, pos.mean(axis=1).to_numpy(), ppy,
                                              cfg["risk_free_annual"])
    return PortfolioReport(list(symbols), idx, pd.DataFrame(rets, index=idx), metrics, sleeves)
