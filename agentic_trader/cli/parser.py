"""``build_parser()``: every subcommand's argparse wiring in one place, dispatching to the
``cmd_*`` handlers in ``decisions.py``, ``research.py``, ``evaluate.py`` and ``services.py``.

Kept as one function (argparse subparsers naturally read as one declarative tree) but no
longer sharing a module with 700 lines of command *logic* -- this file is wiring only.
"""
from __future__ import annotations

import argparse

from .decisions import cmd_analyze, cmd_scan, cmd_task
from .evaluate import cmd_calibrate, cmd_evaluate
from .research import cmd_alpha, cmd_backtest, cmd_execute, cmd_portfolio, cmd_stats, cmd_xalpha
from .services import cmd_info, cmd_mcp, cmd_serve, cmd_tools


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
        sp.add_argument("--xalpha-universe", default=None,
                        help="peers for the xalpha analyst: core | extended | all, or a comma list of symbols "
                             "(default: the core universe of the instrument's asset class)")
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
        sp.add_argument("--edgar-cache", default=None, help="directory for cached SEC EDGAR downloads")
        sp.add_argument("--no-edgar", action="store_true",
                        help="do not use SEC EDGAR for point-in-time fundamentals and filing news")
        sp.add_argument("--rules", choices=["default", "v02", "v03"], default="default",
                        help="v02 / v03 reproduce earlier rule sets for before/after comparisons")
        sp.add_argument("--anonymize", action="store_true",
                        help="hide ticker, dates and price level from the model (backtests)")
        sp.add_argument("--deep-effort", choices=["low", "medium", "high", "xhigh", "max"],
                        default=None, help="effort for the deep-tier model")
        sp.add_argument("-v", "--verbose", action="store_true")

    def cost_opts(sp):
        sp.add_argument("--impact", type=float, default=None,
                        help="square-root market-impact coefficient (0 = off, 1.0 = textbook)")
        sp.add_argument("--capital", type=float, default=None,
                        help="account size that trade sizes (and so impact) scale with")
        sp.add_argument("--execution-algo", choices=["twap", "vwap", "ac"], default=None,
                        help="how the day's trade is worked, for --impact's cost (default: vwap-equivalent)")
        sp.add_argument("--ac-kappa", type=float, default=None,
                        help="Almgren-Chriss urgency for --execution-algo ac (default 3.0)")

    def backtest_opts(sp):
        sp.add_argument("--start", required=True)
        sp.add_argument("--end", required=True)
        sp.add_argument("--every", type=int, default=5, help="rebalance every N bars")
        sp.add_argument("--stops", choices=["on", "off"], default=None,
                        help="enforce decision stop-loss / take-profit (default: config)")
        cost_opts(sp)
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
    t.add_argument("--capital", type=float, default=None,
                   help="account size the desk tools size orders from (default: config initial_capital)")
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
    ev.add_argument("--repeats", type=int, default=1,
                    help="run the agent this many times per (period, symbol) to measure model variance")
    ev.add_argument("--workers", type=int, default=1,
                    help="backtests run in parallel (useful with --llm anthropic)")
    cost_opts(ev)
    ev.add_argument("--out", default=None, help="JSON path for all rows")
    ev.set_defaults(func=cmd_evaluate)

    cb = sub.add_parser("calibrate", help="dispersion / anchoring / drift of the desk's judgement on one state")
    common(cb)
    cb.add_argument("--date", default=None, help="YYYY-MM-DD (default: yesterday)")
    cb.add_argument("--n", type=int, default=5, help="runs per anchor")
    cb.add_argument("--anchors", default="none,-0.5,0,0.5", help="comma list of current weights; 'none' = no book")
    cb.add_argument("--compare", default=None, help="earlier calibration JSON on the same state, for drift")
    cb.add_argument("--out", default=None, help="JSON path for the report")
    cb.set_defaults(func=cmd_calibrate)

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
    ex.add_argument("--capital", type=float, default=None,
                    help="order-sizing capital in the account currency (default: config initial_capital, "
                         "the same convention as the desk tools, task and API)")
    ex.add_argument("--algo", choices=["twap", "vwap", "pov", "ac"], default=None)
    ex.add_argument("--participation", type=float, default=0.10, help="POV participation")
    ex.add_argument("--ac-kappa", type=float, default=None,
                    help="Almgren-Chriss urgency for --algo ac, dimensionless: 0 = TWAP, larger = more "
                         "front-loaded (default: config costs.ac_kappa, 3.0)")
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
    st.add_argument("--var-backtest", action="store_true",
                    help="Kupiec + Christoffersen coverage test of a rolling historical VaR forecast "
                         "against the same return series")
    st.add_argument("--var-window", type=int, default=250, help="trailing window for the VaR forecast")
    st.add_argument("--var-alpha", type=float, default=0.95, help="VaR confidence level")
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
    sv.add_argument("--capital", type=float, default=None,
                    help="account size the desk tools size orders from (default: config initial_capital)")
    sv.add_argument("--task-db", default=None, help="SQLite file for a persistent task store")
    sv.add_argument("--ssl-cert", default=None, help="TLS certificate (PEM); needs --ssl-key")
    sv.add_argument("--ssl-key", default=None, help="TLS private key (PEM)")
    sv.add_argument("--allow-dev-keys", action="store_true",
                    help="allow the shipped development API keys on a non-loopback host (tests only)")
    sv.add_argument("--workers", type=int, default=None, help="task threads per process (default 4)")
    sv.add_argument("--processes", type=int, default=1,
                    help="uvicorn worker processes; more than one needs --task-db")
    sv.set_defaults(func=cmd_serve)

    mc = sub.add_parser("mcp", help="MCP server over stdio (needs the [mcp] extra)")
    common(mc, symbol_required=None)
    mc.add_argument("--role", choices=["viewer", "analyst", "trader", "risk", "admin"], default="trader",
                    help="the role every call is evaluated for (stdio carries no identity)")
    mc.add_argument("--approval", choices=["auto", "queued", "deny"], default=None,
                    help="gateway for tools that need approval (default: config agentic.approval); "
                         "queued is refused: nothing can answer on a stdio server")
    mc.set_defaults(func=cmd_mcp)

    i = sub.add_parser("info", help="show quant backend and default config")
    i.set_defaults(func=cmd_info)
    return p
