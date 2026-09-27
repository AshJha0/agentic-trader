"""Shared plumbing every subcommand uses: config assembly from parsed args, the header
line, symbol-list parsing, LLM usage printing, and the ``.env`` loader.

Kept separate from the ``cmd_*`` handlers (``decisions.py``, ``research.py``,
``evaluate.py``, ``services.py``) and from ``parser.py`` (the argparse wiring) so each of
those can be read, tested and changed without pulling in the whole CLI surface -- the
single 700-line ``cli.py`` this package replaces mixed all four concerns in one file.
"""
from __future__ import annotations

import logging
import os
from datetime import date, timedelta

from .. import quant
from ..config import RULES_V02, RULES_V03, make_config

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
    costs = {}
    if getattr(args, "impact", None) is not None:
        if args.impact < 0:
            raise ValueError("--impact must be >= 0")
        costs["impact_coeff"] = args.impact
    if getattr(args, "execution_algo", None):
        costs["execution_algo"] = args.execution_algo
    if getattr(args, "ac_kappa", None) is not None:
        if args.ac_kappa < 0:
            raise ValueError("--ac-kappa must be >= 0")
        costs["ac_kappa"] = args.ac_kappa
    if costs:
        over["costs"] = costs
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
    if getattr(args, "no_edgar", False):
        over["edgar"] = False
    if getattr(args, "edgar_cache", None):
        over["edgar_cache_dir"] = args.edgar_cache
    if getattr(args, "anonymize", False):
        over["llm_anonymize"] = True
    if getattr(args, "deep_effort", None):
        over["deep_effort"] = args.deep_effort
    if getattr(args, "analysts", None):
        over["analysts"] = _symbols(args.analysts)
    if getattr(args, "xalpha_universe", None):
        from ..evaluation import UNIVERSES
        x = args.xalpha_universe
        over["xalpha_universe"] = UNIVERSES[x] if x in UNIVERSES else _symbols(x)
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


def load_dotenv(path: str = ".env") -> list[str]:
    """Load ``KEY=VALUE`` lines from a local ``.env`` into the environment.

    Existing environment variables are never overridden, values are never printed, and
    the file is optional. It exists because Windows user-level environment variables do
    not reliably reach a process started before they were set; a project-local file does.
    """
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
