"""Command-line interface.

    agentic-trader analyze AAPL --date 2024-03-01
    agentic-trader analyze EURUSD --date 2024-03-01 --llm anthropic --data yahoo
    agentic-trader backtest NVDA --start 2024-01-01 --end 2024-03-29 --every 5
    agentic-trader baselines USDJPY --start 2023-01-01 --end 2023-12-31
    agentic-trader info
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

from . import quant
from .backtest import run_agent_backtest
from .config import make_config
from .graph import TradingGraph


def _config(args) -> dict:
    over: dict = {"data_provider": args.data, "llm_provider": args.llm}
    if args.csv_dir:
        over["csv_dir"] = args.csv_dir
    if args.rounds is not None:
        over["max_debate_rounds"] = args.rounds
        over["max_risk_discuss_rounds"] = args.rounds
    if args.deep_model:
        over["deep_think_llm"] = args.deep_model
    if args.quick_model:
        over["quick_think_llm"] = args.quick_model
    if getattr(args, "allow_short", False):
        over["risk"] = {"allow_short_equity": True}
    if getattr(args, "no_memory", False):
        over["memory_path"] = None
    return make_config(over)


def _print_event(stage: str, msg: str) -> None:
    print(f"  [{stage:>8}] {msg}", flush=True)


def cmd_analyze(args) -> int:
    cfg = _config(args)
    cfg["save_reports"] = args.save
    as_of = date.fromisoformat(args.date) if args.date else date.today() - timedelta(days=1)
    graph = TradingGraph(cfg, on_event=_print_event)
    print(f"AgenticTrader | {args.symbol} as of {as_of} | llm={cfg['llm_provider']} "
          f"data={cfg['data_provider']} quant={quant.BACKEND}")
    state, dec = graph.propagate(args.symbol, as_of, args.asset_class)
    print()
    if args.json:
        print(json.dumps(dec.to_dict(), indent=2))
    else:
        print(state.to_markdown())
    return 0


def cmd_backtest(args, include_agent: bool = True) -> int:
    cfg = _config(args)
    cfg["memory_path"] = None
    n = [0]

    def on_dec(d):
        n[0] += 1
        print(f"  {d.as_of}  {d.action.value:<4} {d.target_weight:+.2f}", flush=True)

    print(f"Backtest {args.symbol} {args.start} -> {args.end} | llm={cfg['llm_provider']} "
          f"data={cfg['data_provider']} quant={quant.BACKEND}")
    rep = run_agent_backtest(args.symbol, args.start, args.end, cfg,
                             rebalance_every=getattr(args, "every", 5),
                             asset_class=args.asset_class, include_agent=include_agent,
                             on_decision=on_dec if include_agent else None)
    bt = rep.backtest_config
    print(f"\n{rep.instrument.display}: {len(rep.dates)} bars, cost {bt.cost_bps:.2f}bps + "
          f"slippage {bt.slippage_bps:.2f}bps, carry {bt.carry_annual:+.2%} p.a., "
          f"shorts {'on' if bt.allow_short else 'off'}")
    print(rep.table().to_string())
    if args.out:
        rep.equity_curves().to_csv(args.out)
        print(f"equity curves written to {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentic-trader",
                                description="Multi-agent LLM trading framework (equity & FX)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("symbol", help="AAPL, EURUSD, EUR/USD, USDJPY ...")
        sp.add_argument("--asset-class", choices=["equity", "fx"], default=None)
        sp.add_argument("--data", choices=["synthetic", "yahoo", "csv"], default="synthetic")
        sp.add_argument("--csv-dir", default=None)
        sp.add_argument("--llm", choices=["offline", "anthropic"], default="offline")
        sp.add_argument("--deep-model", default=None)
        sp.add_argument("--quick-model", default=None)
        sp.add_argument("--rounds", type=int, default=None, help="debate / risk rounds")
        sp.add_argument("--allow-short", action="store_true", help="allow equity shorts")
        sp.add_argument("-v", "--verbose", action="store_true")

    a = sub.add_parser("analyze", help="run the agent firm for one date")
    common(a)
    a.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    a.add_argument("--save", action="store_true", help="write results/<SYM>/<date>/report.md")
    a.add_argument("--json", action="store_true", help="print only the final decision")
    a.add_argument("--no-memory", action="store_true", help="do not read/write the memory log")
    a.set_defaults(func=cmd_analyze)

    for name, agent in (("backtest", True), ("baselines", False)):
        b = sub.add_parser(name, help="walk-forward backtest vs baselines" if agent
                           else "rule-based baselines only (fast, C++)")
        common(b)
        b.add_argument("--start", required=True)
        b.add_argument("--end", required=True)
        if agent:
            b.add_argument("--every", type=int, default=5, help="rebalance every N bars")
        b.add_argument("--out", default=None, help="CSV path for equity curves")
        b.set_defaults(func=lambda args, _a=agent: cmd_backtest(args, _a))

    i = sub.add_parser("info", help="show quant backend and default config")
    i.set_defaults(func=cmd_info)
    return p


def cmd_info(args) -> int:
    print(f"quant backend: {quant.BACKEND}")
    print(json.dumps(make_config(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if getattr(args, "verbose", False) else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
