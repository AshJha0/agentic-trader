"""Walk-forward backtest of the agent firm against rule-based baselines.

At each rebalance date the full agent graph is run with data up to that date's
close; the resulting target weight is held until the next rebalance. Returns and
metrics come from the C++ backtester (CR, AR, Sharpe, MDD as in the paper, plus
volatility, Sortino, Calmar and win rate).
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


@dataclass
class ComparisonReport:
    instrument: Instrument
    dates: pd.DatetimeIndex
    results: dict[str, quant.BacktestResult]
    decisions: list[FinalDecision] = field(default_factory=list)
    backtest_config: quant.BacktestConfig | None = None

    def table(self) -> pd.DataFrame:
        rows = {}
        for name, r in self.results.items():
            m = r.metrics
            rows[name] = {
                "CR%": 100 * m.cumulative_return, "AR%": 100 * m.annualized_return,
                "Vol%": 100 * m.annualized_vol, "Sharpe": m.sharpe, "Sortino": m.sortino,
                "MDD%": 100 * m.max_drawdown, "Calmar": m.calmar, "Win%": 100 * m.win_rate,
                "Trades": m.num_trades,
            }
        return pd.DataFrame(rows).T.round(2)

    def equity_curves(self) -> pd.DataFrame:
        return pd.DataFrame({k: r.equity for k, r in self.results.items()}, index=self.dates)


def backtest_config_for(ins: Instrument, config: dict, prices: np.ndarray,
                        provider: MarketDataProvider, start: date) -> quant.BacktestConfig:
    costs, risk = config["costs"], config["risk"]
    cfg = quant.BacktestConfig(
        initial_capital=config["initial_capital"],
        periods_per_year=ins.periods_per_year,
        risk_free_annual=config["risk_free_annual"],
        max_leverage=risk["max_position"],
    )
    if ins.is_fx:
        half_spread_bps = costs["fx_spread_pips"] * ins.pip_size / float(np.mean(prices)) * 1e4 / 2
        cfg.cost_bps = half_spread_bps
        cfg.slippage_bps = costs["fx_slippage_bps"]
        cfg.allow_short = risk["allow_short_fx"]
        macro = provider.macro(ins, start)
        cfg.carry_annual = macro.get("rate_diff", 0.0) / 100.0
    else:
        cfg.cost_bps = costs["equity_cost_bps"]
        cfg.slippage_bps = costs["equity_slippage_bps"]
        cfg.borrow_annual = costs["equity_borrow_annual"]
        cfg.allow_short = risk["allow_short_equity"]
    return cfg


def baseline_weights(full: pd.DataFrame, allow_short: bool) -> dict[str, np.ndarray]:
    c, h, l = (full[k].to_numpy() for k in ("Close", "High", "Low"))
    return {
        "Buy&Hold": quant.strat_buy_hold(c),
        "SMA(20/50)": quant.strat_sma_cross(c, 20, 50, allow_short),
        "MACD": quant.strat_macd(c, 12, 26, 9, allow_short),
        "KDJ+RSI": quant.strat_kdj_rsi(h, l, c, 9, 14, 30.0, 70.0, allow_short),
        "ZMR": quant.strat_zmr(c, 20, 1.0, 0.0, allow_short),
    }


def run_agent_backtest(symbol: str, start: date | str, end: date | str,
                       config: dict | None = None, rebalance_every: int = 5,
                       provider: MarketDataProvider | None = None, llm: LLM | None = None,
                       asset_class: str | None = None,
                       on_decision: Callable[[FinalDecision], None] | None = None,
                       include_agent: bool = True) -> ComparisonReport:
    cfg = make_config(config)
    ins = Instrument.parse(symbol, asset_class)
    start = date.fromisoformat(start) if isinstance(start, str) else start
    end = date.fromisoformat(end) if isinstance(end, str) else end
    provider = provider or get_provider(cfg)

    full = provider.history(ins, start - timedelta(days=cfg["lookback_days"]), end)
    mask = (full.index >= pd.Timestamp(start)) & (full.index <= pd.Timestamp(end))
    window = full.loc[mask]
    if len(window) < 2:
        raise ValueError("backtest window has fewer than 2 bars")
    prices = window["Close"].to_numpy()
    bt = backtest_config_for(ins, cfg, prices, provider, start)

    results: dict[str, quant.BacktestResult] = {}
    decisions: list[FinalDecision] = []
    if include_agent:
        graph = TradingGraph(cfg, provider=provider,
                             llm=llm if llm is not None else get_llm(cfg),
                             memory=DecisionMemory(None), on_event=lambda *_: None)
        w = np.full(len(window), np.nan)
        for i in range(0, len(window) - 1, max(1, rebalance_every)):
            _, dec = graph.propagate(ins, window.index[i].date())
            w[i] = dec.target_weight
            decisions.append(dec)
            if on_decision:
                on_decision(dec)
        w = pd.Series(w).ffill().fillna(0.0).to_numpy()
        results["AgenticTrader"] = quant.run_backtest(prices, w, bt)

    for name, weights in baseline_weights(full, bt.allow_short).items():
        results[name] = quant.run_backtest(prices, weights[mask], bt)
    return ComparisonReport(ins, window.index, results, decisions, bt)
