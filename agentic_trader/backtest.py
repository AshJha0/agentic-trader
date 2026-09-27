"""Walk-forward backtests of the agent firm against rule-based baselines.

At each rebalance date the full agent graph is run with data up to that date's
close and the position the engine actually holds coming into that bar (the
previous decision's units drifted with the market, or flat after a stop / take
exit); the resulting target weight (and its stop / take-profit levels) is held as
a constant number of units until the next rebalance. Returns and metrics come
from the C++ backtester (conventions in cpp/include/at/backtest.hpp).

Idle cash earns the provider's point-in-time risk-free rate (``risk_free_series``;
a constant from ``config["risk_free_annual"]`` for providers without one) and every
Sharpe is computed on excess returns over the same per-bar rate.

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
from .algo import algo_cost_ratio
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
    rf: np.ndarray | None = None  # annual risk-free rate per bar credited on cash and used for Sharpe

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
        cfg.funded = False  # forwards: the whole account earns the cash rate, carry is the differential
    else:
        cfg.cost_bps = costs["equity_cost_bps"]
        cfg.slippage_bps = costs["equity_slippage_bps"]
        cfg.borrow_annual = costs["equity_borrow_annual"]
        cfg.allow_short = risk["allow_short_equity"]
        cfg.funded = True
    return cfg


def risk_free_series(provider: MarketDataProvider, dates: pd.DatetimeIndex, config: dict) -> np.ndarray:
    """Annual risk-free rate per date (fraction, NaN = unknown), point-in-time from the provider.

    Providers without ``risk_free_series`` get the constant ``config["risk_free_annual"]``.
    """
    fn = getattr(provider, "risk_free_series", None)
    if not callable(fn):
        return np.full(len(dates), float(config["risk_free_annual"]))
    rf = np.asarray(fn(dates), dtype=float)
    if rf.shape != (len(dates),):
        raise ValueError(f"risk_free_series returned shape {rf.shape} for {len(dates)} dates")
    return rf


def _cash_rate(rf: np.ndarray) -> np.ndarray | None:
    """Engine input for a rate series: None when nothing is known (credits nothing, metrics use
    the constant), the series itself otherwise (unknown days credit nothing)."""
    return None if np.isnan(rf).all() else rf


def impact_coefficients(full: pd.DataFrame, ins: Instrument, config: dict,
                        periods_per_year: float | None = None) -> np.ndarray | None:
    """Per-bar square-root impact coefficient ``K_t`` for the backtester, or ``None`` when off.

    The execution simulator (``algo.simulate_execution``) prices a slice of ``q`` units at
    ``impact_coeff * daily_vol * sqrt(q / ADV)``. For a weight change ``dw`` on an account
    of ``capital``, ``q = |dw| * capital / price``, so the cost as a fraction of equity is
    ``|dw|^1.5 * K_t`` with ``K_t = coeff * daily_vol_t * sqrt(capital / (price_t * ADV_t))``.
    ``capital`` is ``initial_capital``; the engine rescales ``K_t`` by
    ``sqrt(equity_t / initial_capital)`` so a compounding account is charged for the notional
    it actually trades. Everything in ``K_t`` is known at the close of bar ``t``: trailing
    20-day volatility and trailing 20-day average volume. Bars without volume get no impact
    (equities with missing volume, and FX unless ``costs.fx_adv_notional`` is set).

    This single-shot formula implicitly assumes the day's trade is spread across the session
    in proportion to volume (VWAP), which ``algo.algo_cost_ratio`` shows minimises impact cost
    under the square-root law -- so it is also exactly what ``costs.execution_algo`` unset (or
    ``"vwap"``) means here. Setting it to ``"twap"`` or ``"ac"`` (Almgren-Chriss, urgency
    ``costs.ac_kappa``) scales ``K_t`` by that schedule's cost relative to VWAP on the same
    session, so a trade's simulated cost then depends on how it would be worked, not only on
    its size; the default is unchanged so every existing published number stays reproducible.
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
    algo = costs.get("execution_algo")
    if algo and algo != "vwap":
        n = 288 if ins.is_fx else 78
        kappa = costs.get("ac_kappa")
        kappa = 3.0 if kappa is None else float(kappa)   # 0 is TWAP, not "unset"
        ratio_algo = algo_cost_ratio(algo, n, "fx" if ins.is_fx else "equity", kappa)
        # A NaN coefficient means "no impact" to the engine, so a non-finite schedule cost must
        # fail loudly rather than silently switch impact off.
        if not np.isfinite(ratio_algo) or ratio_algo <= 0:
            raise ValueError(f"execution algo {algo!r} (kappa {costs.get('ac_kappa')}) has a non-finite "
                             f"cost ratio {ratio_algo}; impact cannot be charged")
        k = k * ratio_algo
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
                       include_agent: bool = True,
                       capital_share: pd.Series | None = None,
                       rebalance_offset: int = 0) -> ComparisonReport:
    """Walk-forward backtest of the desk and the baselines on one instrument.

    ``capital_share`` (a date-indexed fraction of ``initial_capital``, for a portfolio sleeve)
    scales the impact coefficient by ``sqrt(share_t)``: ``K_t`` is proportional to the square
    root of the capital traded, so a sleeve running 1/N of the book pays the impact of an
    account of ``capital / N``. ``rebalance_offset`` is the bar of the first decision
    (``0 <= offset < rebalance_every``); sweeping it measures the cadence's phase noise.
    """
    cfg = make_config(config)
    ins = Instrument.parse(symbol, asset_class)
    start, end = _parse(start), _parse(end)
    if end < start:
        raise ValueError(f"end {end} is before start {start}")
    if not 0 <= rebalance_offset < max(1, rebalance_every):
        raise ValueError(f"rebalance_offset must be in [0, {max(1, rebalance_every)})")
    provider = provider or get_provider(cfg)

    full = provider.history(ins, start - timedelta(days=cfg["lookback_days"]), end)
    mask = (full.index >= pd.Timestamp(start)) & (full.index <= pd.Timestamp(end))
    window = full.loc[mask]
    if len(window) < 2:
        raise ValueError(f"backtest window {start}..{end} has fewer than 2 bars for {ins.display}")
    prices = window["Close"].to_numpy()
    bt = backtest_config_for(ins, cfg, prices, provider, start)
    carry = provider.carry_series(ins, window.index) if ins.is_fx else None
    rf = risk_free_series(provider, window.index, cfg)
    cash = _cash_rate(rf)
    ohlc = dict(open=window["Open"].to_numpy(), high=window["High"].to_numpy(),
                low=window["Low"].to_numpy())
    k_full = impact_coefficients(full, ins, cfg)
    impact = None if k_full is None else k_full[np.asarray(mask, dtype=bool)]
    if impact is not None and capital_share is not None:
        share = capital_share.reindex(window.index).to_numpy(dtype=float)
        if np.isnan(share).any() or (share < 0).any():
            raise ValueError("capital_share must be a non-negative fraction on every bar of the window")
        impact = impact * np.sqrt(share)

    results: dict[str, quant.BacktestResult] = {}
    decisions: list[FinalDecision] = []
    if include_agent:
        graph = TradingGraph(cfg, provider=provider,
                             llm=llm if llm is not None else get_llm(cfg),
                             memory=DecisionMemory(None), on_event=lambda *_: None)
        n = len(window)
        w = np.zeros(n)
        stop, take = np.full(n, np.nan), np.full(n, np.nan)
        reb = np.zeros(n)
        extras = dict(carry=carry, rebalance=reb, impact=impact, cash_rate=cash)
        if cfg.get("backtest", {}).get("use_stops"):
            extras.update(ohlc, stop=stop, take=take)
        sources: dict[str, int] = {}
        held = 0.0
        for i in range(rebalance_offset, n - 1, max(1, rebalance_every)):
            if i > 0:
                # The weight the desk actually holds coming into bar i: replay the engine on the
                # bars so far (its last position is the previous decision's units drifted with
                # the market, or 0 after a stop / take exit or ruin).
                held = float(quant.run_backtest(
                    prices[:i + 1], w[:i + 1], bt,
                    **{k: (None if v is None else v[:i + 1]) for k, v in extras.items()}).positions[i])
            st, dec = graph.propagate(ins, window.index[i].date(), current_weight=held)
            for s in _sources(st):
                sources[s] = sources.get(s, 0) + 1
            # Hold each decision (weight and its protective levels) until the next one. A
            # decision to keep the current position (the PM's no-trade band; reported to 4
            # decimals) is executed as no trade, not as a trade to the rounded weight.
            w[i:] = held if dec.target_weight == round(held, 4) else dec.target_weight
            stop[i:] = np.nan if dec.stop_loss is None else dec.stop_loss
            take[i:] = np.nan if dec.take_profit is None else dec.take_profit
            reb[i] = 1.0
            decisions.append(dec)
            if on_decision:
                on_decision(dec)
        results[AGENT] = quant.run_backtest(prices, w, bt, **extras)

    for name, weights in baseline_weights(full, bt.allow_short, cfg["risk"]["target_vol"],
                                          cfg["risk"]["max_position"],
                                          ins.periods_per_year).items():
        results[name] = quant.run_backtest(prices, weights[mask], bt, carry=carry, impact=impact,
                                           cash_rate=cash)
    return ComparisonReport(ins, window.index, results, decisions, bt, carry,
                            sources if include_agent else {}, prices, rf)


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
    rf: np.ndarray | float | None = None      # per-bar (or constant) annual risk-free rate the metrics used

    def table(self) -> pd.DataFrame:
        rows = {}
        for name, m in self.metrics.items():
            rows[name] = {"CR%": 100 * m.cumulative_return, "AR%": 100 * m.annualized_return,
                          "Vol%": 100 * m.annualized_vol, "Sharpe": m.sharpe,
                          "t(SR)": m.sharpe_tstat, "MDD%": 100 * m.max_drawdown,
                          "Calmar": m.calmar, "Exp%": 100 * m.avg_exposure}
        return pd.DataFrame(rows).T.round(2)

    def sharpe_difference(self, a: str = AGENT, b: str = "B&H vol-target", block: int = 10,
                          n_boot: int = 5000, seed: int = 0):
        """Sharpe(a) - Sharpe(b) over the same days with a paired block bootstrap over time
        (``stats.paired_sharpe_block_bootstrap``), on the same excess-return convention as
        ``metrics``: the interval a portfolio-level comparison needs, which the
        cross-instrument bootstrap cannot give."""
        from .stats import paired_sharpe_block_bootstrap
        ppy = max(r.instrument.periods_per_year for r in self.sleeves.values())
        # ``metrics`` are computed from the equity curve, whose first return (bar 0, before
        # any position) does not exist; use the same bars so sharpe_a equals metrics[a].sharpe.
        rf = self.rf[1:] if isinstance(self.rf, np.ndarray) else self.rf
        return paired_sharpe_block_bootstrap(self.returns[a].to_numpy(dtype=float)[1:],
                                             self.returns[b].to_numpy(dtype=float)[1:], ppy,
                                             rf=rf, block=block, n_boot=n_boot, seed=seed)


def run_portfolio_backtest(symbols: list[str], start: date | str, end: date | str,
                           config: dict | None = None, rebalance_every: int = 5,
                           provider: MarketDataProvider | None = None, llm: LLM | None = None,
                           on_decision: Callable[[FinalDecision], None] | None = None,
                           weighting: str = "equal", cov_window: int = 120,
                           class_budgets: dict[str, float] | None = None,
                           rebalance_offset: int = 0) -> PortfolioReport:
    """Run every symbol as its own sleeve and combine the sleeves.

    Each sleeve is a full walk-forward backtest (costs, carry, stops) of the agent
    and of every baseline, sized with the capital it actually receives: the
    allocation is computed first, from the provider's history alone, and each
    sleeve's market impact is charged for an account of ``capital * share_t``
    (``run_agent_backtest(capital_share=...)``). Sleeve returns are combined daily:

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
    0 that day. The portfolio Sharpe is on excess returns over the same per-bar
    risk-free rate the sleeves credit on idle cash.
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
    start_d, end_d = _parse(start), _parse(end)
    instruments = {s: Instrument.parse(s) for s in symbols}
    keys = list(instruments)
    # History first: the allocation must exist before the sleeves run, so that each sleeve
    # can be charged impact for the capital it is actually given.
    lookback_start = start_d - timedelta(days=cfg["lookback_days"])
    history = {s: provider.history(ins, lookback_start, end_d) for s, ins in instruments.items()}
    in_window = {s: h.index[(h.index >= pd.Timestamp(start_d)) & (h.index <= pd.Timestamp(end_d))]
                 for s, h in history.items()}
    idx = pd.DatetimeIndex(sorted(set().union(*in_window.values())))
    ppy = max(ins.periods_per_year for ins in instruments.values())

    # Trailing instrument returns (for covariance) including the warm-up before `start`.
    inst_returns = pd.DataFrame({s: h["Close"].pct_change() for s, h in history.items()}).dropna(how="all")

    alloc_hist = None
    groups = {s: ins.asset_class for s, ins in instruments.items()}
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

    sleeves = {s: run_agent_backtest(s, start, end, cfg, rebalance_every, provider, llm,
                                     on_decision=on_decision, capital_share=alloc[s],
                                     rebalance_offset=rebalance_offset) for s in keys}
    strategies = list(next(iter(sleeves.values())).results)
    rf = risk_free_series(provider, idx, cfg)
    rf_arg = cfg["risk_free_annual"] if np.isnan(rf).all() else rf

    rets, metrics = {}, {}
    for name in strategies:
        def frame(attr):
            return pd.DataFrame({s: pd.Series(np.abs(getattr(r.results[name], attr)), index=r.dates)
                                 for s, r in sleeves.items()}).reindex(idx).fillna(0.0)
        per = pd.DataFrame({s: pd.Series(r.results[name].returns, index=r.dates)
                            for s, r in sleeves.items()}).reindex(idx).fillna(0.0)
        port = (per * alloc).sum(axis=1)
        rets[name] = port
        equity = cfg["initial_capital"] * np.cumprod(1.0 + port.to_numpy())
        metrics[name] = quant.compute_metrics(equity, (frame("positions") * alloc).sum(axis=1).to_numpy(), ppy,
                                              rf_arg, traded=(frame("traded") * alloc).sum(axis=1).to_numpy())
    return PortfolioReport(list(symbols), idx, pd.DataFrame(rets, index=idx), metrics, sleeves,
                           weighting, alloc_hist, rf_arg)
