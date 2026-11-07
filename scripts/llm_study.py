"""The P2 LLM study driver: one desk configuration per cell, run on a sampled design.

Plan item 2.2 (docs/review/PLAN.md). Seven cells, each a variant of which desk roles reason
with a model and how much debate and risk discussion the desk holds:

    rules           no model anywhere (the control)
    local_all       local model in every role (analysts and the deep roles)
    local_text      local model on the free-text roles only (bull and bear researchers)
    local_pm        local model at the portfolio manager only
    no_debate       local model everywhere except the debate (researchers and facilitator on rules)
    debate_1        local model everywhere, one debate round instead of the default two
    neutral_risk    local model everywhere, a single neutral risk analyst instead of three

``--dry-run`` needs no model and makes no network call. It runs the desk once per name on the
first design date with a recording stub that answers nothing (so every agent falls back to its
rules and the run is deterministic), counts the calls each cell makes per decision and the
input tokens of the prompts actually built (``llm.estimate_tokens``), and scales to the
design (names x dates x seeds). The dollar columns price those calls at Claude list prices
(``llm.PRICES_PER_MTOK``) for the configured default models: "est" assumes
ASSUMED_OUTPUT_TOKENS of reply per call, "ceiling" assumes every reply runs to ``max_tokens``.
They say what the cells would cost on Claude; the study itself runs at $0 on a local model.

``--live`` runs the cells on a local model (``llm_provider`` "local") and refuses if the
Ollama server does not answer. It writes one JSON line per decision. It has not been run: the
development machine is below the plan's 16 GB RAM bar (OD-6) and has no Ollama install.

Every cell carries a ``trial_name`` and its config overrides so it can be added to
``evaluation.TRIALS`` when its design-period result exists (item 2.3); none is registered yet.

    python scripts/llm_study.py --dry-run
    python scripts/llm_study.py --live --model llama3.1:8b-instruct-q4_K_M --out results/p2.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from agentic_trader.agents import RiskAnalyst
from agentic_trader.config import make_config
from agentic_trader.evaluation import CORE_UNIVERSE
from agentic_trader.graph import TradingGraph
from agentic_trader.llm import LLM, estimate_tokens, price_for
from agentic_trader.local_llm import reachable

# Every desk role a cell can hand to the model.
ROLES = ("analysts", "bull", "bear", "facilitator", "trader", "risk", "pm")
DEEP_ROLES = tuple(r for r in ROLES if r != "analysts")

# Reply length assumed for the "est" dollar column (thinking included on the deep tier). An
# assumption, not a measurement: the local run (2.3) records the real eval_count per call.
ASSUMED_OUTPUT_TOKENS = {False: 400, True: 1500}

DESIGN_START, DESIGN_END = date(2016, 1, 1), date(2021, 12, 31)   # the design period
DEFAULT_NAMES = CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]       # 15 names
STUDY_BASE: dict[str, Any] = {"memory_path": None, "llm_anonymize": True}


@dataclass(frozen=True)
class Cell:
    name: str
    description: str
    llm_roles: tuple[str, ...]
    overrides: dict[str, Any] = field(default_factory=dict)
    neutral_risk_only: bool = False

    @property
    def trial_name(self) -> str:
        return f"P2 {self.name}: {self.description}"

    def describe(self) -> dict[str, Any]:
        """What a later ``evaluation.Trial`` entry needs to reproduce this cell."""
        return {"trial_name": self.trial_name, "llm_roles": list(self.llm_roles),
                "overrides": self.overrides, "neutral_risk_only": self.neutral_risk_only}


CELLS: tuple[Cell, ...] = (
    Cell("rules", "no model in any role (control)", ()),
    Cell("local_all", "local model in every role", ROLES),
    Cell("local_text", "local model on the free-text roles (bull, bear) only", ("bull", "bear")),
    Cell("local_pm", "local model at the portfolio manager only", ("pm",)),
    Cell("no_debate", "local model in every role but the debate (researchers, facilitator on rules)",
         ("analysts", "trader", "risk", "pm")),
    Cell("debate_1", "local model in every role, one debate round", ROLES, {"max_debate_rounds": 1}),
    Cell("neutral_risk", "local model in every role, a single neutral risk analyst", ROLES,
         neutral_risk_only=True),
)


class StudyGraph(TradingGraph):
    """The desk with the model handed only to ``cell.llm_roles``; every other role runs its
    rules. Sequential use only: ``run_analyst`` swaps ``self.llm`` for the call."""

    def __init__(self, cell: Cell, config: dict, llm: LLM | None):
        super().__init__({**config, **cell.overrides}, llm=llm, on_event=lambda stage, msg: None)
        self.llm_roles = frozenset(cell.llm_roles)
        if cell.neutral_risk_only:
            self.risk_team = [RiskAnalyst(self.llm, self.config, "neutral")]
        agents = {"bull": [self.bull], "bear": [self.bear], "facilitator": [self.facilitator],
                  "trader": [self.trader], "risk": self.risk_team, "pm": [self.pm]}
        for role, members in agents.items():
            if role not in self.llm_roles:
                for a in members:
                    a.llm = None

    def run_analyst(self, state, name, provider=None):
        if "analysts" in self.llm_roles:
            return super().run_analyst(state, name, provider)
        held, self.llm = self.llm, None
        try:
            return super().run_analyst(state, name, provider)
        finally:
            self.llm = held


class RecordingLLM:
    """Answers nothing and keeps every request, so the rules run and the prompts are real."""

    def __init__(self) -> None:
        self.requests: list[tuple[bool, int]] = []      # (deep, estimated input tokens)

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        self.requests.append((deep, estimate_tokens(system, prompt)))
        return None


def design_dates(n: int, start: date = DESIGN_START, end: date = DESIGN_END) -> list[date]:
    """``n`` business days spread evenly over the design period (first and last included)."""
    days = pd.bdate_range(start, end)
    return [days[i].date() for i in np.linspace(0, len(days) - 1, n).round().astype(int)]


def probe(cell: Cell, names: Iterable[str], as_of: date, config: dict) -> list[tuple[bool, int]]:
    """Requests one decision per name makes in ``cell`` (no model, no network)."""
    if not cell.llm_roles:
        return []
    rec = RecordingLLM()
    graph = StudyGraph(cell, config, rec)
    for name in names:
        graph.propagate(name, as_of)
    return rec.requests


def dry_run_table(names: list[str], n_dates: int, seeds: int, config: dict) -> list[dict[str, Any]]:
    """Per cell: calls per decision, calls and dollars for the whole design at Claude list prices."""
    first = design_dates(n_dates)[0]
    decisions = len(names) * n_dates * seeds
    reps = n_dates * seeds                         # each probed name stands for its dates x seeds
    models = {False: config["quick_think_llm"], True: config["deep_think_llm"]}
    rows = []
    for cell in CELLS:
        reqs = probe(cell, names, first, config)
        est = ceiling = 0.0
        input_tokens = 0
        for deep, tin in reqs:
            pin, pout = price_for(models[deep])
            input_tokens += tin
            est += (tin * pin + ASSUMED_OUTPUT_TOKENS[deep] * pout) / 1e6
            ceiling += (tin * pin + config["max_tokens"] * pout) / 1e6
        rows.append({"cell": cell.name, "llm_roles": ",".join(cell.llm_roles) or "-",
                     "calls_per_decision": len(reqs) / len(names), "decisions": decisions,
                     "calls": len(reqs) * reps, "input_mtok": input_tokens * reps / 1e6,
                     "est_usd": est * reps, "ceiling_usd": ceiling * reps})
    return rows


def render(rows: list[dict[str, Any]], config: dict) -> str:
    head = (f"| cell | model roles | calls/decision | decisions | calls | input Mtok | est $ | ceiling $ |\n"
            f"|---|---|---:|---:|---:|---:|---:|---:|")
    body = [f"| {r['cell']} | {r['llm_roles']} | {r['calls_per_decision']:.1f} | {r['decisions']:,} | "
            f"{r['calls']:,} | {r['input_mtok']:.2f} | {r['est_usd']:,.2f} | {r['ceiling_usd']:,.2f} |"
            for r in rows]
    note = (f"Prices: quick {config['quick_think_llm']}, deep {config['deep_think_llm']} at list price; "
            f"est assumes {ASSUMED_OUTPUT_TOKENS[False]} / {ASSUMED_OUTPUT_TOKENS[True]} output tokens "
            f"per quick / deep call, ceiling assumes max_tokens={config['max_tokens']}.")
    return "\n".join([head, *body, "", note])


def run_live(names: list[str], dates: list[date], seeds: int, config: dict, out: Path) -> None:
    """Every cell on the local model; one JSON line per decision. Unrun here (OD-6)."""
    from agentic_trader.llm import get_llm, llm_usage
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as fh:
        for cell in CELLS:
            for seed in range(seeds):
                cfg = {**config, "local_llm_seed": seed}
                llm = get_llm(make_config(cfg)) if cell.llm_roles else None
                graph = StudyGraph(cell, cfg, llm)
                for name in names:
                    for d in dates:
                        state, dec = graph.propagate(name, d)
                        fh.write(json.dumps({
                            "cell": cell.name, "seed": seed, "symbol": name, "as_of": d.isoformat(),
                            "action": dec.action.value, "target_weight": dec.target_weight,
                            "source": dec.source, "llm_calls": state.llm_calls}, default=str) + "\n")
                fh.write(json.dumps({"cell": cell.name, "seed": seed, "usage": llm_usage(llm)}) + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="call counts and Claude dollar estimate")
    mode.add_argument("--live", action="store_true", help="run every cell on the local model")
    mode.add_argument("--describe", action="store_true", help="print each cell as a trial description")
    ap.add_argument("--names", default=",".join(DEFAULT_NAMES))
    ap.add_argument("--dates", type=int, default=40, help="design dates, spread evenly")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--data", default="synthetic", help="data provider (synthetic | yahoo | csv)")
    ap.add_argument("--model", help="Ollama model name (--live)")
    ap.add_argument("--url", help="Ollama URL (--live; default config local_llm_url)")
    ap.add_argument("--out", default="results/llm_study.jsonl")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    config = make_config(STUDY_BASE, data_provider=args.data)

    if args.describe:
        print(json.dumps([c.describe() for c in CELLS], indent=1))
        return 0
    if args.dry_run:
        print(render(dry_run_table(names, args.dates, args.seeds, config), config))
        return 0
    if not args.model:
        ap.error("--live needs --model (an Ollama model name)")
    config.update(llm_provider="local", local_llm_model=args.model)
    if args.url:
        config["local_llm_url"] = args.url
    if not reachable(config["local_llm_url"]):
        print(f"refusing --live: no Ollama server answers at {config['local_llm_url']}", file=sys.stderr)
        return 2
    run_live(names, design_dates(args.dates), args.seeds, config, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
