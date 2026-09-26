"""Command-line interface.

Decisions
    agentic-trader analyze   AAPL --date 2024-03-01 [--position 0.4]
    agentic-trader task      EURUSD --date 2024-03-01 [--role trader] [--approval queued]
    agentic-trader scan      AAPL,MSFT,EURUSD --date 2024-03-01 --out decisions.csv
Backtests and research
    agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --every 5
    agentic-trader baselines USDJPY --start 2023-01-02 --end 2023-12-29
    agentic-trader portfolio AAPL,MSFT,EURUSD --start ... --end ... [--weighting risk_parity]
    agentic-trader evaluate  --data yahoo --periods design,holdout,q1_2024
    agentic-trader alpha     AAPL --start 2021-01-04 --end 2024-03-28 [--horizon 10]
    agentic-trader execute   AAPL --date 2024-03-01 --target 0.6 --current 0.1 [--algo vwap]
    agentic-trader stats     returns.csv [--trials 16]
Agentic services
    agentic-trader tools     [--json]
    agentic-trader serve     [--host 127.0.0.1 --port 8000]
    agentic-trader mcp       [--data yahoo]
    agentic-trader info

Invalid input (unknown symbol, no data, bad dates) exits with status 2 and a
one-line error instead of a traceback; use -v for details.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

import numpy as np

from . import quant
from .backtest import run_agent_backtest, run_portfolio_backtest
from .config import RULES_V02, RULES_V03, make_config
from .graph import TradingGraph
from .llm import llm_usage

log = logging.getLogger("agentic_trader.cli")


def _config(args) -> dict:
    over: dict = {"data_provider": args.data, "llm_provider": args.llm}
    rules = getattr(args, "rules", "default")
    if rules == "v02":
        over = make_config(RULES_V02, **over)
    elif rules == "v03":
        over = make_config(RULES_V03, **over)
    if args.csv_dir:
        over["csv_dir"] = args.csv_dir
    if args.rounds is not None:
        if args.rounds < 1:
            raise ValueError("--rounds must be >= 1")
        over["max_debate_rounds"] = args.rounds
        over["max_risk_discuss_rounds"] = args.rounds
    if args.deep_model:
        over["deep_think_llm"] = args.deep_model
    if args.quick_model:
        over["quick_think_llm"] = args.quick_model
    risk = {}
    if getattr(args, "allow_short", False):
        risk["allow_short_equity"] = True
    if getattr(args, "band", None) is not None:
        risk["rebalance_band"] = args.band
    if risk:
        over["risk"] = risk
    if getattr(args, "stops", None) is not None:
        over["backtest"] = {"use_stops": args.stops == "on"}
    if getattr(args, "impact", None) is not None:
        if args.impact < 0:
            raise ValueError("--impact must be >= 0")
        over["costs"] = {"impact_coeff": args.impact}
    if getattr(args, "capital", None) is not None and getattr(args, "cmd", "") != "execute":
        if args.capital <= 0:
            raise ValueError("--capital must be positive")
        over["initial_capital"] = args.capital
    if getattr(args, "max_llm_calls", None) is not None:
        over["max_llm_calls"] = args.max_llm_calls
    if getattr(args, "max_llm_cost", None) is not None:
        if args.max_llm_cost < 0:
            raise ValueError("--max-llm-cost must be >= 0")
        over["max_llm_cost_usd"] = args.max_llm_cost
    if getattr(args, "fred_vintages", False):
        over["fred_vintages"] = True
    if getattr(args, "fred_cache", None):
        over["fred_cache_dir"] = args.fred_cache
    if getattr(args, "anonymize", False):
        over["llm_anonymize"] = True
    if getattr(args, "deep_effort", None):
        over["deep_effort"] = args.deep_effort
    if getattr(args, "analysts", None):
        over["analysts"] = _symbols(args.analysts)
    if getattr(args, "no_memory", False):
        over["memory_path"] = None
    agentic = {}
    if getattr(args, "approval", None):
        agentic["approval"] = args.approval
    if getattr(args, "llm_planner", False):
        agentic["llm_planner"] = True
    if agentic:
        over["agentic"] = agentic
    return make_config(over)


def _print_event(stage: str, msg: str) -> None:
    print(f"  [{stage:>8}] {msg}", flush=True)


def _as_of(args) -> date:
    return date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)


def _symbols(text: str) -> list[str]:
    syms = [s.strip() for s in text.replace(";", ",").split(",") if s.strip()]
    if not syms:
        raise ValueError("no symbols given")
    return syms


def _header(what: str, cfg: dict) -> None:
    print(f"AgenticTrader | {what} | llm={cfg['llm_provider']} data={cfg['data_provider']} "
          f"quant={quant.BACKEND}")


def _print_usage(usage: dict | None, sources: dict | None = None) -> None:
    if not usage:
        return
    print(f"\nLLM: {usage['calls']} calls, {usage['errors']} errors, {usage['refusals']} refusals, "
          f"cost ${usage['cost_usd']:.2f}")
    for model, u in usage["by_model"].items():
        cost = "n/a" if u["cost_usd"] is None else f"${u['cost_usd']:.2f}"
        print(f"  {model:<18} {u['calls']:>5} calls  in {u['input_tokens']:>9,}  out {u['output_tokens']:>9,}  {cost}")
    if sources:
        total = sum(sources.values())
        print(f"  agent outputs from the model: {sources.get('llm', 0)}/{total}")


# ------------------------------------------------------------------ decisions
def cmd_analyze(args) -> int:
    cfg = _config(args)
    cfg["save_reports"] = args.save
    as_of = _as_of(args)
    graph = TradingGraph(cfg, on_event=_print_event)
    _header(f"{args.symbol} as of {as_of}", cfg)
    state, dec = graph.propagate(args.symbol, as_of, args.asset_class, args.position)
    print()
    if args.json:
        print(json.dumps(dec.to_dict(), indent=2))
    else:
        print(state.to_markdown())
    _print_usage(llm_usage(graph.llm))
    return 0


def cmd_task(args) -> int:
    """Run the agentic harness: plan -> policy-gated tools -> agents -> critic -> audited report."""
    from .agentic import AgentHarness, Role, Task
    cfg = _config(args)
    cfg["save_reports"] = args.save
    as_of = _as_of(args)
    graph = TradingGraph(cfg, on_event=_print_event if args.verbose else lambda *_: None)
    harness = AgentHarness(graph, positions={args.symbol: args.position} if args.position is not None else None)
    _header(f"task {args.symbol} as of {as_of} role={args.role} approval={cfg['agentic']['approval']}", cfg)
    run = harness.run(Task(args.symbol, as_of, Role(args.role), args.position, args.question or ""))
    print(f"state: {run.state.value}  plan: {run.plan.source}  steps: {len(run.plan.steps)}  "
          f"evidence: {len(run.evidence)}  findings: {len(run.findings)}")
    for note in (run.plan.notes if run.plan else ()):
        print(f"  plan note: {note}")
    for e in run.errors:
        print(f"  error: {e}")
    if run.state.value == "AWAITING_APPROVAL":
        for a in harness.pending_approvals(run.id):
            print(f"  awaiting approval {a.id}: {a.request.tool} {a.request.arguments} ({a.reason})")
        return 3
    if run.report is None:
        return 1
    print()
    if args.json:   # the record alone, so the output is machine-readable
        print(json.dumps(run.to_dict(), indent=2, default=str))
    else:
        print(run.report.to_markdown())
        print(f"\ntrace: {run.tracer.summary()}")
        _print_usage(llm_usage(graph.llm))
    return 0 if run.state.value == "COMPLETED" else 1


def cmd_scan(args) -> int:
    cfg = _config(args)
    cfg["memory_path"] = None
    as_of = _as_of(args)
    syms = _symbols(args.symbol)
    positions = json.loads(args.positions) if args.positions else {}
    _header(f"scan of {len(syms)} symbols as of {as_of}", cfg)
    df = TradingGraph(cfg, on_event=lambda *_: None).scan(syms, as_of, positions)
    cols = [c for c in ("symbol", "action", "target_weight", "confidence", "last", "stop_loss",
                        "take_profit", "debate", "analysts_voting", "error") if c in df]
    print(df[cols].to_string(index=False))
    if args.out:
        (df.to_json(args.out, orient="records", indent=1) if args.out.endswith(".json")
         else df.to_csv(args.out, index=False))
        print(f"decisions written to {args.out}")
    return 1 if (df["action"] == "ERROR").all() else 0


# ------------------------------------------------------------------ research
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


def cmd_evaluate(args) -> int:
    from .evaluation import PERIODS, UNIVERSES, evaluate
    cfg = _config(args)
    cfg["memory_path"] = None
    periods = {p: PERIODS[p] for p in _symbols(args.periods)}
    syms = _symbols(args.symbol) if args.symbol else UNIVERSES[args.universe]
    _header(f"evaluate {len(syms)} symbols x {list(periods)}", cfg)
    res = evaluate(syms, periods, cfg, args.every, progress=lambda m: print("  " + m, flush=True),
                   workers=args.workers)
    print("\n" + res.summary().to_string())
    if "universe" in res.rows and res.rows.universe.nunique() > 1:
        for u in sorted(res.rows.universe.unique()):
            print(f"\n[{u} universe]\n" + res.summary(universe=u).to_string())
    print("\n" + res.head_to_head().to_string(index=False))
    if res.meta["errors"]:
        print(f"\n{len(res.meta['errors'])} failures: {res.meta['errors']}")
    _print_usage(res.meta.get("usage"), res.meta.get("agent_sources"))
    if args.out:
        res.to_json(args.out)
        print(f"results written to {args.out}")
    return 0


def cmd_xalpha(args) -> int:
    from .data import get_provider
    from .instruments import Instrument
    from .xalpha import xalpha_report
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
    from .alpha import alpha_report
    from .data import get_provider
    from .instruments import Instrument
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
    from .algo import plan_execution, simulate_execution, synthetic_intraday_bars
    from .data import get_provider
    from .instruments import Instrument
    from .state import Action, FinalDecision
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
    from .stats import selection_report, sharpe_ci_bootstrap, sharpe_stats
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
    return 0


# ------------------------------------------------------------------ services
def cmd_tools(args) -> int:
    from .agentic import DeskTools, build_registry
    from .data import get_provider
    cfg = _config(args)
    reg = build_registry(DeskTools(get_provider(cfg), cfg))
    if args.json:
        print(json.dumps(reg.catalogue(), indent=1))
        return 0
    print(f"{len(reg)} tools on {len(reg.servers())} servers")
    for d in reg.descriptors():
        flags = ("read-only" if d.annotations.read_only else "STATE-CHANGING") + f", {d.annotations.risk.value} risk"
        args_ = ", ".join(d.input_schema.get("properties", {}))
        print(f"  {d.name:<26} ({args_})  [{flags}]\n      {d.description.splitlines()[0]}")
    return 0


def cmd_serve(args) -> int:
    from .agentic.api import serve
    cfg = _config(args)
    if args.task_db:
        cfg["agentic"]["task_db"] = args.task_db
    scheme = "https" if args.ssl_cert else "http"
    print(f"serving on {scheme}://{args.host}:{args.port}  (docs at /docs; approvals "
          f"{cfg['agentic']['approval']}; task store {args.task_db or 'in memory'})")
    serve(args.host, args.port, cfg, ssl_certfile=args.ssl_cert, ssl_keyfile=args.ssl_key,
          allow_dev_keys=args.allow_dev_keys)
    return 0


def cmd_mcp(args) -> int:
    from .agentic.mcp_server import main as mcp_main
    argv = ["--data", args.data] + (["--csv-dir", args.csv_dir] if args.csv_dir else [])
    return mcp_main(argv)


def cmd_info(args) -> int:
    print(f"quant backend: {quant.BACKEND}")
    print(json.dumps(make_config(), indent=2))
    return 0


# ------------------------------------------------------------------- parser
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic-trader",
                                description="Multi-agent LLM trading framework (equity & FX)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, symbol_help="AAPL, EURUSD, EUR/USD, USDJPY ...", symbol_required=True):
        if symbol_required:
            sp.add_argument("symbol", help=symbol_help)
        elif symbol_required is None:
            pass
        else:
            sp.add_argument("symbol", nargs="?", default=None, help=symbol_help)
        sp.add_argument("--asset-class", choices=["equity", "fx"], default=None)
        sp.add_argument("--data", choices=["synthetic", "yahoo", "csv"], default="synthetic")
        sp.add_argument("--csv-dir", default=None)
        sp.add_argument("--llm", choices=["offline", "anthropic"], default="offline")
        sp.add_argument("--deep-model", default=None)
        sp.add_argument("--quick-model", default=None)
        sp.add_argument("--rounds", type=int, default=None, help="debate / risk rounds")
        sp.add_argument("--analysts", default=None, help="comma list, e.g. technical,alpha,news")
        sp.add_argument("--allow-short", action="store_true", help="allow equity shorts")
        sp.add_argument("--band", type=float, default=None,
                        help="no-trade band: keep the position if the new target is this close")
        sp.add_argument("--max-llm-calls", type=int, default=None,
                        help="hard cap on model calls; agents use rules beyond it")
        sp.add_argument("--max-llm-cost", type=float, default=None,
                        help="hard cap on estimated model spend in USD; agents use rules beyond it")
        sp.add_argument("--fred-vintages", action="store_true",
                        help="read revised FRED series (CPI) from the ALFRED vintage current at each date")
        sp.add_argument("--fred-cache", default=None, help="directory for cached FRED/ALFRED downloads")
        sp.add_argument("--rules", choices=["default", "v02", "v03"], default="default",
                        help="v02 / v03 reproduce earlier rule sets for before/after comparisons")
        sp.add_argument("--anonymize", action="store_true",
                        help="hide ticker, dates and price level from the model (backtests)")
        sp.add_argument("--deep-effort", choices=["low", "medium", "high", "xhigh", "max"],
                        default=None, help="effort for the deep-tier model")
        sp.add_argument("-v", "--verbose", action="store_true")

    def backtest_opts(sp):
        sp.add_argument("--start", required=True)
        sp.add_argument("--end", required=True)
        sp.add_argument("--every", type=int, default=5, help="rebalance every N bars")
        sp.add_argument("--stops", choices=["on", "off"], default=None,
                        help="enforce decision stop-loss / take-profit (default: config)")
        sp.add_argument("--impact", type=float, default=None,
                        help="square-root market-impact coefficient (0 = off, 1.0 = textbook)")
        sp.add_argument("--capital", type=float, default=None,
                        help="account size that trade sizes (and so impact) scale with")
        sp.add_argument("--out", default=None, help="CSV path for the curves / returns")

    a = sub.add_parser("analyze", help="run the desk for one date")
    common(a)
    a.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    a.add_argument("--position", type=float, default=None,
                   help="current position weight going into the decision")
    a.add_argument("--save", action="store_true", help="write results/<SYM>/<date>/report.md")
    a.add_argument("--json", action="store_true", help="print only the final decision")
    a.add_argument("--no-memory", action="store_true", help="do not read/write the memory log")
    a.set_defaults(func=cmd_analyze)

    t = sub.add_parser("task", help="run the agentic harness: plan, policy-gated tools, critic, audited report")
    common(t)
    t.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    t.add_argument("--position", type=float, default=None, help="current position weight")
    t.add_argument("--role", choices=["viewer", "analyst", "trader", "risk", "admin"], default="trader")
    t.add_argument("--approval", choices=["auto", "queued", "deny"], default=None,
                   help="what happens to tool calls that need approval")
    t.add_argument("--llm-planner", action="store_true", help="let the model propose the plan")
    t.add_argument("--question", default=None, help="free-text request shown to the planner")
    t.add_argument("--save", action="store_true", help="write results/<SYM>/<date>/report.md")
    t.add_argument("--json", action="store_true", help="print the full task record as JSON")
    t.add_argument("--no-memory", action="store_true", help="do not read/write the memory log")
    t.set_defaults(func=cmd_task)

    s = sub.add_parser("scan", help="decisions for a comma-separated watchlist")
    common(s, "comma-separated symbols, e.g. AAPL,MSFT,EURUSD")
    s.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    s.add_argument("--positions", default=None,
                   help='current weights as JSON, e.g. \'{"AAPL": 0.4}\'')
    s.add_argument("--out", default=None, help="write decisions to .csv or .json")
    s.set_defaults(func=cmd_scan)

    for name, agent in (("backtest", True), ("baselines", False)):
        b = sub.add_parser(name, help="walk-forward backtest vs baselines" if agent
                           else "rule-based baselines only (fast, C++)")
        common(b)
        backtest_opts(b)
        b.set_defaults(func=lambda args, _a=agent: cmd_backtest(args, _a))

    pf = sub.add_parser("portfolio", help="multi-asset backtest with a weighting scheme")
    common(pf, "comma-separated symbols, e.g. AAPL,MSFT,EURUSD")
    backtest_opts(pf)
    pf.add_argument("--weighting", choices=["equal", "inverse_vol", "risk_parity", "min_variance",
                                            "mean_variance"], default="equal")
    pf.add_argument("--class-budgets", default=None,
                    help="risk budget per asset class, e.g. equity=0.6,fx=0.4 (risk parity across classes)")
    pf.set_defaults(func=cmd_portfolio)

    ev = sub.add_parser("evaluate", help="design / holdout / Q1-2024 / reserve evaluation")
    common(ev, "optional comma-separated symbols (default: --universe)", symbol_required=False)
    ev.add_argument("--periods", default="q1_2024", help="comma list of design,holdout,q1_2024,reserve")
    ev.add_argument("--universe", choices=["core", "extended", "all"], default="all",
                    help="core = the 15 instruments rules were chosen on; extended = the 45 never used "
                         "for a choice; all = both (default)")
    ev.add_argument("--every", type=int, default=5, help="rebalance every N bars")
    ev.add_argument("--workers", type=int, default=1,
                    help="backtests run in parallel (useful with --llm anthropic)")
    ev.add_argument("--out", default=None, help="JSON path for all rows")
    ev.set_defaults(func=cmd_evaluate)

    xa = sub.add_parser("xalpha", help="cross-sectional alpha report over a universe: per-date IC, "
                                       "quantile spreads, breadth")
    common(xa, "comma-separated symbols, e.g. AAPL,MSFT,NVDA,JPM,XOM")
    xa.add_argument("--start", required=True)
    xa.add_argument("--end", required=True)
    xa.add_argument("--horizon", type=int, default=10, help="forward-return horizon in bars")
    xa.add_argument("--standardise", choices=["zscore", "rank"], default="zscore")
    xa.add_argument("--out", default=None, help="CSV path for the combined cross-sectional scores")
    xa.set_defaults(func=cmd_xalpha)

    al = sub.add_parser("alpha", help="alpha library report: IC, decay, hit rate, correlations")
    common(al)
    al.add_argument("--start", required=True)
    al.add_argument("--end", required=True)
    al.add_argument("--horizon", type=int, default=10, help="forward-return horizon in bars")
    al.add_argument("--out", default=None, help="CSV path for the signal series")
    al.set_defaults(func=cmd_alpha)

    ex = sub.add_parser("execute", help="plan and simulate executing a weight change")
    common(ex)
    ex.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    ex.add_argument("--target", type=float, required=True, help="target weight")
    ex.add_argument("--current", type=float, default=0.0, help="current weight")
    ex.add_argument("--capital", type=float, default=1_000_000.0)
    ex.add_argument("--algo", choices=["twap", "vwap", "pov", "ac"], default=None)
    ex.add_argument("--participation", type=float, default=0.10, help="POV participation")
    ex.add_argument("--spread-bps", type=float, default=2.0, help="equity quoted spread")
    ex.add_argument("--impact", type=float, default=1.0, help="square-root impact coefficient")
    ex.add_argument("--seed", type=int, default=0, help="intraday path seed")
    ex.set_defaults(func=cmd_execute)

    st = sub.add_parser("stats", help="Sharpe t-stat, bootstrap CI, probabilistic and deflated Sharpe")
    st.add_argument("path", help="CSV of daily returns (first column = dates)")
    st.add_argument("--column", default=None)
    st.add_argument("--ppy", type=float, default=252.0, help="periods per year")
    st.add_argument("--trials", type=int, default=0, help="number of variants tried (for DSR)")
    st.add_argument("--trial-sharpes", default=None, help="comma list of the trials' annual Sharpes")
    st.set_defaults(func=cmd_stats)

    tl = sub.add_parser("tools", help="list the tool catalogue")
    common(tl, symbol_required=None)
    tl.add_argument("--json", action="store_true")
    tl.set_defaults(func=cmd_tools)

    sv = sub.add_parser("serve", help="HTTP API (needs the [api] extra)")
    common(sv, symbol_required=None)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--approval", choices=["auto", "queued", "deny"], default="queued")
    sv.add_argument("--task-db", default=None, help="SQLite file for a persistent task store")
    sv.add_argument("--ssl-cert", default=None, help="TLS certificate (PEM); needs --ssl-key")
    sv.add_argument("--ssl-key", default=None, help="TLS private key (PEM)")
    sv.add_argument("--allow-dev-keys", action="store_true",
                    help="allow the shipped development API keys on a non-loopback host (tests only)")
    sv.set_defaults(func=cmd_serve)

    mc = sub.add_parser("mcp", help="MCP server over stdio (needs the [mcp] extra)")
    common(mc, symbol_required=None)
    mc.set_defaults(func=cmd_mcp)

    i = sub.add_parser("info", help="show quant backend and default config")
    i.set_defaults(func=cmd_info)
    return p


def load_dotenv(path: str = ".env") -> list[str]:
    """Load ``KEY=VALUE`` lines from a local ``.env`` into the environment.

    Existing environment variables are never overridden, values are never printed, and
    the file is optional. It exists because Windows user-level environment variables do
    not reliably reach a process started before they were set; a project-local file does.
    """
    import os
    loaded: list[str] = []
    try:
        with open(path, encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key, value = key.strip(), value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
                    loaded.append(key)
    except OSError:
        pass
    return loaded


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    load_dotenv()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    try:
        return args.func(args)
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as e:
        if getattr(args, "verbose", False):
            log.exception("failed")
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
