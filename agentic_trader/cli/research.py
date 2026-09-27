"""``backtest`` / ``baselines`` / ``portfolio`` / ``xalpha`` / ``alpha`` / ``execute`` /
``stats``: the quant research commands, run without the agentic harness."""
from __future__ import annotations

import json
from datetime import date, timedelta

import numpy as np

from ..backtest import run_agent_backtest, run_portfolio_backtest
from .common import _as_of, _config, _header, _symbols


def cmd_backtest(args, include_agent: bool = True) -> int:
    cfg = _config(args)
    cfg["memory_path"] = None

    def on_dec(d):
        print(f"  {d.as_of}  {d.action.value:<4} {d.target_weight:+.2f}", flush=True)

    _header(f"backtest {args.symbol} {args.start} -> {args.end}", cfg)
    rep = run_agent_backtest(args.symbol, args.start, args.end, cfg,
                             rebalance_every=getattr(args, "every", 5),
                             asset_class=args.asset_class, include_agent=include_agent,
                             on_decision=on_dec if include_agent and args.verbose else None)
    bt = rep.backtest_config
    known = rep.carry[~np.isnan(rep.carry)] if rep.carry is not None else None
    carry = (f"carry {known.mean():+.2%} p.a. (mean, point-in-time)" if known is not None and known.size
             else "carry n/a (no point-in-time rates)" if known is not None
             else f"carry {bt.carry_annual:+.2%} p.a.")
    print(f"\n{rep.instrument.display}: {len(rep.dates)} bars, cost {bt.cost_bps:.2f}bps + "
          f"slippage {bt.slippage_bps:.2f}bps, {carry}, shorts {'on' if bt.allow_short else 'off'}, "
          f"stops {'on' if cfg['backtest']['use_stops'] else 'off'}")
    print(rep.table().to_string())
    if args.out:
        rep.equity_curves().to_csv(args.out)
        print(f"equity curves written to {args.out}")
    return 0


def cmd_portfolio(args) -> int:
    cfg = _config(args)
    cfg["memory_path"] = None
    syms = _symbols(args.symbol)
    budgets = None
    if args.class_budgets:
        try:
            budgets = {k.strip(): float(v) for k, v in (kv.split("=") for kv in args.class_budgets.split(","))}
        except ValueError:
            raise ValueError("--class-budgets must look like equity=0.6,fx=0.4") from None
    _header(f"portfolio of {len(syms)} sleeves {args.start} -> {args.end} weighting={args.weighting}"
            + (f" class budgets {budgets}" if budgets else ""), cfg)
    rep = run_portfolio_backtest(syms, args.start, args.end, cfg, rebalance_every=args.every,
                                 weighting=args.weighting, class_budgets=budgets)
    print(rep.table().to_string())
    if rep.allocations is not None:
        print("\nlatest capital allocation:")
        print(rep.allocations.iloc[-1].round(3).to_string())
    if args.out:
        rep.returns.to_csv(args.out)
        print(f"portfolio daily returns written to {args.out}")
    return 0


def cmd_xalpha(args) -> int:
    from ..data import get_provider
    from ..instruments import Instrument
    from ..xalpha import xalpha_report
    cfg = _config(args)
    provider = get_provider(cfg)
    syms = _symbols(args.symbol)
    if len(syms) < 3:
        raise ValueError("a cross-sectional report needs at least 3 symbols")
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    frames, instruments, carry = {}, {}, {}
    for s in syms:
        ins = Instrument.parse(s, args.asset_class)
        df = provider.history(ins, start, end)
        if len(df) < 300:
            raise ValueError(f"cross-sectional evaluation needs at least 300 bars; {ins.display} has {len(df)}")
        frames[ins.symbol], instruments[ins.symbol] = df, ins
        if ins.is_fx:
            carry[ins.symbol] = provider.carry_series(ins, df.index)
    _header(f"cross-sectional alpha report, {len(frames)} names {start} -> {end} horizon={args.horizon}", cfg)
    rep = xalpha_report(frames, instruments, args.horizon, carry=carry or None, standardise=args.standardise)
    print(rep.table.to_string())
    print("\nmean IC by horizon:")
    print(rep.decay.to_string())
    print("\nscore correlations:")
    print(rep.correlations.to_string())
    print(f"\nbest by mean IC: {rep.best()}")
    if args.out:
        rep.signals["combined"].to_csv(args.out)
        print(f"combined cross-sectional scores written to {args.out}")
    return 0


def cmd_alpha(args) -> int:
    from ..alpha import alpha_report
    from ..data import get_provider
    from ..instruments import Instrument
    cfg = _config(args)
    provider = get_provider(cfg)
    ins = Instrument.parse(args.symbol, args.asset_class)
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    df = provider.history(ins, start, end)
    if len(df) < 300:
        raise ValueError(f"alpha evaluation needs at least 300 bars; got {len(df)}")
    carry = provider.carry_series(ins, df.index) if ins.is_fx else None
    _header(f"alpha report {ins.display} {start} -> {end} horizon={args.horizon}", cfg)
    rep = alpha_report(df, ins, args.horizon, carry_series=carry)
    print(rep.table.to_string())
    print("\nIC by horizon:")
    print(rep.decay.to_string())
    print("\nsignal correlations:")
    print(rep.correlations.to_string())
    print(f"\nbest by IC: {rep.best()}")
    if args.out:
        rep.signals.to_csv(args.out)
        print(f"signals written to {args.out}")
    return 0


def cmd_execute(args) -> int:
    from ..algo import plan_execution, simulate_execution, synthetic_intraday_bars
    from ..data import get_provider
    from ..instruments import Instrument
    from ..state import Action, FinalDecision
    cfg = _config(args)
    provider = get_provider(cfg)
    ins = Instrument.parse(args.symbol, args.asset_class)
    as_of = _as_of(args)
    df = provider.history(ins, as_of - timedelta(days=60), as_of)
    if df.empty:
        raise ValueError(f"no bars for {ins.display} up to {as_of}")
    last = float(df["Close"].iloc[-1])
    adv = float(df["Volume"].tail(20).mean()) if df["Volume"].sum() > 0 else None
    dec = FinalDecision(ins.symbol, as_of, Action.BUY if args.target > args.current else Action.SELL,
                        args.target, 0.0, None, None, "")
    plan = plan_execution(dec, ins, args.current, args.capital, last, adv, args.algo)
    _header(f"execute {ins.display} {args.current:+.2f} -> {args.target:+.2f} capital {args.capital:,.0f}", cfg)
    if plan is None:
        print("nothing to trade: target equals the current position")
        return 0
    bars = synthetic_intraday_bars(df.iloc[-1], plan.slices, "fx" if ins.is_fx else "equity", seed=args.seed)
    daily_vol = float(df["Close"].pct_change().tail(20).std() or 0.02)
    spread = cfg["costs"]["fx_spread_pips"] * ins.pip_size / last * 1e4 if ins.is_fx else args.spread_bps
    rep = simulate_execution(plan.schedule(bars, participation=args.participation), bars, plan.side,
                             plan.algo, spread, args.impact, daily_vol, adv)
    unit = "units" if ins.is_fx else "shares"
    print(f"{plan.side.upper()} {plan.quantity:,.0f} {unit} (notional {plan.notional:,.0f}) via {plan.algo.upper()} "
          f"in {plan.slices} slices; {plan.reason}")
    if plan.participation_of_adv is not None:
        print(f"order is {plan.participation_of_adv:.2%} of 20-day ADV")
    print(f"executed {rep.executed:,.0f} ({rep.completion:.0%}); arrival {rep.arrival:.5g}, avg fill {rep.avg_price:.5g}, "
          f"session VWAP {rep.session_vwap:.5g}")
    print(f"implementation shortfall {rep.is_bps:+.1f} bps, vs VWAP {rep.vs_vwap_bps:+.1f} bps "
          f"(spread {rep.spread_cost_bps:.1f} bps, impact {rep.impact_cost_bps:.1f} bps), "
          f"max slice participation {rep.max_participation:.1%}" if rep.max_participation == rep.max_participation
          else f"implementation shortfall {rep.is_bps:+.1f} bps, vs VWAP {rep.vs_vwap_bps:+.1f} bps")
    return 0


def cmd_stats(args) -> int:
    import pandas as pd
    from ..stats import rolling_var_forecast, selection_report, sharpe_ci_bootstrap, sharpe_stats, var_backtest
    df = pd.read_csv(args.path, index_col=0)
    col = args.column or df.columns[0]
    if col not in df:
        raise ValueError(f"column {col!r} not in {list(df.columns)}")
    r = df[col].astype(float).dropna().to_numpy()
    s = sharpe_stats(r, args.ppy)
    lo, hi = sharpe_ci_bootstrap(r, args.ppy)
    print(f"{col}: n={s.n} Sharpe {s.sharpe_annual:.3f} (t {s.t_stat:.2f}), skew {s.skew:.2f}, "
          f"kurtosis {s.kurt:.2f}, 95% bootstrap CI [{lo:.3f}, {hi:.3f}]")
    if args.trials:
        trials = [float(x) for x in args.trial_sharpes.split(",")] if args.trial_sharpes else \
            [s.sharpe_annual] * args.trials
        print(json.dumps(selection_report(r, trials, args.ppy), indent=1))
    if args.var_backtest:
        forecast = rolling_var_forecast(r, window=args.var_window, alpha=args.var_alpha)
        vb = var_backtest(r, forecast, alpha=args.var_alpha)
        print(f"\nVaR coverage ({int(args.var_alpha * 100)}%, {args.var_window}-day rolling historical "
              f"VaR forecast, no look-ahead):")
        print(json.dumps(vb.__dict__, indent=1))
        if vb.kupiec_p < 0.05:
            print(f"  -> breach rate {vb.breach_rate:.1%} vs expected {vb.expected_rate:.1%}: "
                  f"REJECTS calibration at 95% (p={vb.kupiec_p:.4f})")
        if vb.christoffersen_p is not None and vb.christoffersen_p < 0.05:
            print(f"  -> breaches cluster in time (p={vb.christoffersen_p:.4f}): REJECTS independence")
    return 0
