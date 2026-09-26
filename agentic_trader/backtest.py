"""Walk-forward backtests of the agent firm against rule-based baselines.

At each rebalance date the full agent graph is run with data up to that date's
close and the current position; the resulting target weight (and its stop /
take-profit levels) is held until the next rebalance. Returns and metrics come
from the C++ backtester.

Baselines are five classic rule-based strategies (Buy & Hold, SMA, MACD, KDJ+RSI,
ZMR) plus ``B&H vol-target``: buy & hold scaled every day to the same volatility target the
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
    # How many agent outputs came from the model vs the rule-based fallback
    # (analyst reports, debate verdict, proposal, risk views, final decision).
    agent_sources: dict[str, int] = field(default_factory=dict)
    prices: np.ndarray | None = None  # closes over the window (for portfolio covariance)

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
                "Impact%": 100 * r.impact_paid,
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


def impact_coefficients(full: pd.DataFrame, ins: Instrument, config: dict,
                        periods_per_year: float | None = None) -> np.ndarray | None:
    """Per-bar square-root impact coefficient ``K_t`` for the backtester, or ``None`` when off.

    The execution simulator (``algo.simulate_execution``) prices a slice of ``q`` units at
    ``impact_coeff * daily_vol * sqrt(q / ADV)``. For a weight change ``dw`` on an account
    of ``capital``, ``q = |dw| * capital / price``, so the cost as a fraction of equity is
    ``|dw|^1.5 * K_t`` with ``K_t = coeff * daily_vol_t * sqrt(capital / (price_t * ADV_t))``.
    Everything in ``K_t`` is known at the close of bar ``t``: trailing 20-day volatility
    and trailing 20-day average volume. Bars without volume get no impact (equities with
    missing volume, and FX unless ``costs.fx_adv_notional`` is set).
    """
    costs = config["costs"]
    coeff = float(costs.get("impact_coeff") or 0.0)
    if coeff <= 0:
        return None
    ppy = periods_per_year or ins.periods_per_year
    close = full["Close"].to_numpy(float)
    vol = quant.realized_vol(close, 20, ppy) / np.sqrt(ppy)  # daily, ex ante
    capital = float(config["initial_capital"])
    if ins.is_fx:
        adv_notional = costs.get("fx_adv_notional")
        if not adv_notional:
            return None
        ratio = np.full(len(close), capital / float(adv_notional))   # q / ADV in notional terms
    else:
        volume = full["Volume"].to_numpy(float) if "Volume" in full else np.zeros(len(close))
        adv = pd.Series(volume).rolling(20).mean().to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            ratio = np.where(adv > 0, capital / (close * adv), np.nan)
    k = coeff * vol * np.sqrt(ratio)
    return np.where(np.isfinite(k), k, np.nan)


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
    k_full = impact_coefficients(full, ins, cfg)
    impact = None if k_full is None else k_full[np.asarray(mask, dtype=bool)]

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
        sources: dict[str, int] = {}
        for i in range(0, n - 1, max(1, rebalance_every)):
            st, dec = graph.propagate(ins, window.index[i].date(), current_weight=held)
            for s in _sources(st):
                sources[s] = sources.get(s, 0) + 1
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
        extras = dict(carry=carry, rebalance=reb, impact=impact)
        if cfg.get("backtest", {}).get("use_stops"):
            extras.update(ohlc, stop=stop, take=take)
        results[AGENT] = quant.run_backtest(prices, w, bt, **extras)

    for name, weights in baseline_weights(full, bt.allow_short, cfg["risk"]["target_vol"],
                                          cfg["risk"]["max_position"],
                                          ins.periods_per_year).items():
        results[name] = quant.run_backtest(prices, weights[mask], bt, carry=carry, impact=impact)
    return ComparisonReport(ins, window.index, results, decisions, bt, carry,
                            sources if include_agent else {}, prices)


def _sources(state) -> list[str]:
    """``source`` of every agent output in a state (abstaining analysts excluded)."""
    out = [r.source for r in state.reports.values() if not r.abstained]
    for doc in (state.debate, state.proposal, state.decision):
        if doc is not None:
            out.append(doc.source)
    out.extend(v.source for v in state.risk_views)
    return out


# ------------------------------------------------------------------ portfolio
@dataclass
class PortfolioReport:
    """Sleeves, one per instrument, combined daily with a weighting scheme."""
    symbols: list[str]
    dates: pd.DatetimeIndex
    returns: pd.DataFrame            # strategy -> portfolio daily returns
    metrics: dict[str, quant.Metrics]
    sleeves: dict[str, ComparisonReport]
    weighting: str = "equal"
    allocations: pd.DataFrame | None = None   # capital share per sleeve over time (agent strategy)

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
                           weighting: str = "equal", cov_window: int = 120,
                           class_budgets: dict[str, float] | None = None) -> PortfolioReport:
    """Run every symbol as its own sleeve and combine the sleeves.

    Each sleeve is a full walk-forward backtest (costs, carry, stops) of the agent
    and of every baseline. Sleeve returns are combined daily:

    * ``weighting="equal"``: 1/N of the capital per sleeve, the same for every
      strategy, so the comparison between the agent and the baselines is fair;
    * any other scheme from ``agentic_trader.portfolio`` (``inverse_vol``,
      ``risk_parity``, ``min_variance``, ``mean_variance``): capital shares are
      re-estimated every ``rebalance_every`` bars from the trailing ``cov_window``
      days of instrument returns (no look-ahead) and held until the next
      rebalance. The scheme applies to every strategy, so a baseline is combined
      the same way as the agent.
    * ``class_budgets`` (e.g. ``{"equity": 0.6, "fx": 0.4}``): cross-asset risk
      budgeting. The scheme allocates within each asset class and risk parity with
      these budgets allocates across classes from the full covariance
      (``portfolio.construct(groups=..., group_budgets=...)``). With
      ``weighting="equal"`` the budgets are applied to capital instead:
      ``budget / n`` per sleeve of the class.

    Equity and FX calendars differ, so a sleeve with no bar on a date contributes
    0 that day.
    """
    if not symbols:
        raise ValueError("run_portfolio_backtest needs at least one symbol")
    from .portfolio import METHODS, construct
    if weighting not in METHODS:
        raise ValueError(f"weighting must be one of {METHODS}")
    if class_budgets is not None and (any(v < 0 for v in class_budgets.values()) or sum(class_budgets.values()) <= 0):
        raise ValueError("class_budgets must be non-negative and not all zero")
    cfg = make_config(config)
    provider = provider or get_provider(cfg)
    sleeves = {s: run_agent_backtest(s, start, end, cfg, rebalance_every, provider, llm,
                                     on_decision=on_decision) for s in symbols}
    keys = list(sleeves)
    dates = sorted(set().union(*(r.dates for r in sleeves.values())))
    idx = pd.DatetimeIndex(dates)
    strategies = list(next(iter(sleeves.values())).results)
    ppy = max(r.instrument.periods_per_year for r in sleeves.values())

    # Trailing instrument returns (for covariance) including the warm-up before `start`.
    lookback_start = _parse(start) - timedelta(days=cfg["lookback_days"])
    inst_returns = pd.DataFrame({
        s: provider.history(r.instrument, lookback_start, _parse(end))["Close"].pct_change()
        for s, r in sleeves.items()}).dropna(how="all")

    alloc_hist = None
    groups = {s: r.instrument.asset_class for s, r in sleeves.items()}
    if class_budgets is not None:
        unknown = sorted(set(groups.values()) - set(class_budgets))
        if unknown:
            raise ValueError(f"class_budgets has no entry for {unknown}")
    if weighting == "equal":
        if class_budgets is None:
            start_alloc = np.full(len(keys), 1.0 / len(keys))
        else:
            live = {g: sum(1 for s in keys if groups[s] == g) for g in class_budgets}
            total = sum(b for g, b in class_budgets.items() if live[g] > 0)
            start_alloc = np.array([class_budgets[groups[s]] / total / live[groups[s]] for s in keys])
        alloc = pd.DataFrame([start_alloc] * len(idx), index=idx, columns=keys)
        alloc_hist = alloc if class_budgets is not None else None
    else:
        rows = {}
        current = np.full(len(keys), 1.0 / len(keys))
        for i, d in enumerate(idx):
            if i % max(1, rebalance_every) == 0:
                hist = inst_returns[inst_returns.index < d].tail(cov_window)
                if len(hist) >= 20:
                    try:
                        pw = construct({s: 1.0 for s in keys}, hist, weighting,  # type: ignore[arg-type]
                                       periods_per_year=ppy, max_weight=1.0, gross_cap=1.0, target_vol=None,
                                       groups=groups if class_budgets else None, group_budgets=class_budgets)
                        current = np.array([pw.allocation[pw.symbols.index(s)] for s in keys])
                    except ValueError:
                        pass  # keep the previous allocation on a degenerate window
            rows[d] = current
        alloc = pd.DataFrame.from_dict(rows, orient="index", columns=keys).reindex(idx)
        alloc_hist = alloc

    rets, metrics = {}, {}
    for name in strategies:
        per = pd.DataFrame({s: pd.Series(r.results[name].returns, index=r.dates)
                            for s, r in sleeves.items()}).reindex(idx).fillna(0.0)
        pos = pd.DataFrame({s: pd.Series(np.abs(r.results[name].positions), index=r.dates)
                            for s, r in sleeves.items()}).reindex(idx).fillna(0.0)
        port = (per * alloc).sum(axis=1)
        rets[name] = port
        equity = cfg["initial_capital"] * np.cumprod(1.0 + port.to_numpy())
        metrics[name] = quant.compute_metrics(equity, (pos * alloc).sum(axis=1).to_numpy(), ppy,
                                              cfg["risk_free_annual"])
    return PortfolioReport(list(symbols), idx, pd.DataFrame(rets, index=idx), metrics, sleeves,
                           weighting, alloc_hist)
