"""Command-line interface.

    agentic-trader analyze   AAPL --date 2024-03-01
    agentic-trader analyze   EURUSD --date 2024-03-01 --llm anthropic --data yahoo
    agentic-trader scan      AAPL,MSFT,EURUSD --date 2024-03-01 --out decisions.csv
    agentic-trader backtest  NVDA --start 2024-01-02 --end 2024-03-28 --every 5
    agentic-trader baselines USDJPY --start 2023-01-02 --end 2023-12-29
    agentic-trader portfolio AAPL,MSFT,EURUSD --start 2023-01-02 --end 2023-12-29
    agentic-trader evaluate  --data yahoo --periods paper
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
from .config import RULES_V02, make_config
from .graph import TradingGraph

log = logging.getLogger("agentic_trader.cli")


def _config(args) -> dict:
    over: dict = {"data_provider": args.data, "llm_provider": args.llm}
    if getattr(args, "rules", "default") == "v02":
        over = make_config(RULES_V02, **over)
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
    if getattr(args, "max_llm_calls", None) is not None:
        over["max_llm_calls"] = args.max_llm_calls
    if getattr(args, "no_memory", False):
        over["memory_path"] = None
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
    return 0


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
    _header(f"portfolio of {len(syms)} sleeves {args.start} -> {args.end}", cfg)
    rep = run_portfolio_backtest(syms, args.start, args.end, cfg, rebalance_every=args.every)
    print(rep.table().to_string())
    if args.out:
        rep.returns.to_csv(args.out)
        print(f"portfolio daily returns written to {args.out}")
    return 0


def cmd_evaluate(args) -> int:
    from .evaluation import DEFAULT_UNIVERSE, PERIODS, evaluate
    cfg = _config(args)
    cfg["memory_path"] = None
    periods = {p: PERIODS[p] for p in _symbols(args.periods)}
    syms = _symbols(args.symbol) if args.symbol else DEFAULT_UNIVERSE["equity"] + DEFAULT_UNIVERSE["fx"]
    _header(f"evaluate {len(syms)} symbols x {list(periods)}", cfg)
    res = evaluate(syms, periods, cfg, args.every, progress=lambda m: print("  " + m, flush=True))
    print("\n" + res.summary().to_string())
    print("\n" + res.head_to_head().to_string(index=False))
    if res.meta["errors"]:
        print(f"\n{len(res.meta['errors'])} failures: {res.meta['errors']}")
    if args.out:
        res.to_json(args.out)
        print(f"results written to {args.out}")
    return 0


def cmd_info(args) -> int:
    print(f"quant backend: {quant.BACKEND}")
    print(json.dumps(make_config(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic-trader",
                                description="Multi-agent LLM trading framework (equity & FX)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, symbol_help="AAPL, EURUSD, EUR/USD, USDJPY ...", symbol_required=True):
        if symbol_required:
            sp.add_argument("symbol", help=symbol_help)
        else:
            sp.add_argument("symbol", nargs="?", default=None, help=symbol_help)
        sp.add_argument("--asset-class", choices=["equity", "fx"], default=None)
        sp.add_argument("--data", choices=["synthetic", "yahoo", "csv"], default="synthetic")
        sp.add_argument("--csv-dir", default=None)
        sp.add_argument("--llm", choices=["offline", "anthropic"], default="offline")
        sp.add_argument("--deep-model", default=None)
        sp.add_argument("--quick-model", default=None)
        sp.add_argument("--rounds", type=int, default=None, help="debate / risk rounds")
        sp.add_argument("--allow-short", action="store_true", help="allow equity shorts")
        sp.add_argument("--band", type=float, default=None,
                        help="no-trade band: keep the position if the new target is this close")
        sp.add_argument("--max-llm-calls", type=int, default=None,
                        help="hard cap on model calls; agents use rules beyond it")
        sp.add_argument("--rules", choices=["default", "v02"], default="default",
                        help="v02 reproduces the v0.2 rule set for comparisons")
        sp.add_argument("-v", "--verbose", action="store_true")

    def backtest_opts(sp):
        sp.add_argument("--start", required=True)
        sp.add_argument("--end", required=True)
        sp.add_argument("--every", type=int, default=5, help="rebalance every N bars")
        sp.add_argument("--stops", choices=["on", "off"], default=None,
                        help="enforce decision stop-loss / take-profit (default: config)")
        sp.add_argument("--out", default=None, help="CSV path for the curves / returns")

    a = sub.add_parser("analyze", help="run the agent firm for one date")
    common(a)
    a.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    a.add_argument("--position", type=float, default=None,
                   help="current position weight going into the decision")
    a.add_argument("--save", action="store_true", help="write results/<SYM>/<date>/report.md")
    a.add_argument("--json", action="store_true", help="print only the final decision")
    a.add_argument("--no-memory", action="store_true", help="do not read/write the memory log")
    a.set_defaults(func=cmd_analyze)

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

    pf = sub.add_parser("portfolio", help="equal-capital multi-asset backtest")
    common(pf, "comma-separated symbols, e.g. AAPL,MSFT,EURUSD")
    backtest_opts(pf)
    pf.set_defaults(func=cmd_portfolio)

    ev = sub.add_parser("evaluate", help="design / holdout / paper-window evaluation")
    common(ev, "optional comma-separated symbols (default: the 15-instrument universe)",
           symbol_required=False)
    ev.add_argument("--periods", default="paper", help="comma list of design,holdout,paper")
    ev.add_argument("--every", type=int, default=5, help="rebalance every N bars")
    ev.add_argument("--out", default=None, help="JSON path for all rows")
    ev.set_defaults(func=cmd_evaluate)

    i = sub.add_parser("info", help="show quant backend and default config")
    i.set_defaults(func=cmd_info)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
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
