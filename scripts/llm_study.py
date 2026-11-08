"""The P2 LLM study driver: one desk configuration per cell, run on a sampled design.

Plan item 2.2 (docs/review/PLAN.md). Seven cells, each a variant of which desk roles reason
with a model and how much debate and risk discussion the desk holds:

    rules           no model anywhere (the control)
    local_all       local model in every role (analysts and the deep roles)
    local_text      local model on the free-text roles only (bull and bear researchers)
    local_pm        local model at the portfolio manager only
    local_analysts  local model at the analysts only, rules downstream (v0.16 first pass)
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

``--live`` runs the cells on a local model (``llm_provider`` "local") under LOCAL_BUDGET and
refuses if the Ollama server does not answer or a model cell is not registered in
``evaluation.TRIALS``. It writes one checkpointed JSON line per decision with every raw reply
and resumes where a killed run stopped. ``--smoke`` runs two decisions on ``local_all`` and
exits 1 if any reply fell back or failed the contract. ``--report`` renders the metrics
(items 2.3 and 2.5): portfolio Sharpe minus the vol-target control with a block-bootstrap
interval and p, agent sources, contract rejection and fallback rates against the admissible
cap (MAX_FALLBACK_SHARE), dispersion, the Claude cost equivalent per decision, and the
fallback rate by regime and date with independence tests. ``--first-pass`` is the reduced
v0.16 design: 15 names x 20 dates x 1 seed on rules, local_analysts and local_all.

    python scripts/llm_study.py --dry-run
    python scripts/llm_study.py --first-pass --dry-run
    python scripts/llm_study.py --smoke --model llama3.1:8b-instruct-q4_K_M
    python scripts/llm_study.py --first-pass --live --model llama3.1:8b-instruct-q4_K_M --out results/p2/first_pass.jsonl
    python scripts/llm_study.py --report --out results/p2/first_pass.jsonl
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from agentic_trader.agents import RiskAnalyst
from agentic_trader.config import make_config
from agentic_trader.evaluation import CORE_UNIVERSE, TRIALS
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
    Cell("local_analysts", "local model at the analysts only, rules downstream (trader, risk, PM)",
         ("analysts",)),
    Cell("local_text", "local model on the free-text roles (bull, bear) only", ("bull", "bear")),
    Cell("local_pm", "local model at the portfolio manager only", ("pm",)),
    Cell("no_debate", "local model in every role but the debate (researchers, facilitator on rules)",
         ("analysts", "trader", "risk", "pm")),
    Cell("debate_1", "local model in every role, one debate round", ROLES, {"max_debate_rounds": 1}),
    Cell("neutral_risk", "local model in every role, a single neutral risk analyst", ROLES,
         neutral_risk_only=True),
)


TRIAL_NAMES = frozenset(t.name for t in TRIALS)


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
    head = ("| cell | model roles | calls/decision | decisions | calls | input Mtok | est $ | ceiling $ |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|")
    body = [f"| {r['cell']} | {r['llm_roles']} | {r['calls_per_decision']:.1f} | {r['decisions']:,} | "
            f"{r['calls']:,} | {r['input_mtok']:.2f} | {r['est_usd']:,.2f} | {r['ceiling_usd']:,.2f} |"
            for r in rows]
    note = (f"Prices: quick {config['quick_think_llm']}, deep {config['deep_think_llm']} at list price; "
            f"est assumes {ASSUMED_OUTPUT_TOKENS[False]} / {ASSUMED_OUTPUT_TOKENS[True]} output tokens "
            f"per quick / deep call, ceiling assumes max_tokens={config['max_tokens']}.")
    return "\n".join([head, *body, "", note])


# ---- the run (plan items 2.3, 2.5) -----------------------------------------------------------

# The reduced first pass (v0.16): 15 core names x 20 design dates x 1 seed = 300 decisions per
# cell, on three cells. Each model cell is registered in evaluation.TRIALS before it runs.
FIRST_PASS = {"dates": 20, "seeds": 1, "cells": ("rules", "local_analysts", "local_all")}

# Prompt and timeout budget for a 7-8B Q4 model on CPU (~5 output tokens/s). A contract reply
# (analyst JSON, trade proposal) is 100-250 tokens; 384 leaves headroom without letting a
# runaway reply hold the desk for minutes. Prompt evaluation runs faster than generation, so
# the timeout covers ~1,300 prompt tokens plus 384 generated with margin. Replies to schema
# calls are grammar-constrained (Ollama ``format``), so a truncated reply is the main way a
# schema call can still fail the contract.
LOCAL_BUDGET: dict[str, Any] = {"max_tokens": 384, "local_llm_timeout_s": 300}
SECONDS_PER_CALL = (50.0, 100.0)          # the wall-clock planning range per call on this machine

# The admissible fallback share per cell (2.5): when more than this share of a cell's model
# calls fell back to rules (timeout, empty reply, drift) or failed the contract, the cell's
# result describes the rules more than the model and is marked inadmissible on every table.
MAX_FALLBACK_SHARE = 0.10

CONTROL = "vol-target"                    # long-only B&H at a 10% vol target, per decision
VOL_TARGET, VOL_WINDOW = 0.10, 63
BLOCK, N_BOOT = 3, 2000                   # circular block bootstrap over decision dates


def _first_pass_cells() -> tuple[Cell, ...]:
    by_name = {c.name: c for c in CELLS}
    return tuple(by_name[n] for n in FIRST_PASS["cells"])


def _required(schema: dict[str, Any] | None) -> list[str]:
    return list((schema or {}).get("required") or [])


class StudyLLM:
    """Wraps the desk's backend for the study: every call keeps its raw reply, latency, the
    estimated prompt tokens and a status -- ``ok``, ``fallback`` (no reply: timeout, empty,
    refused, drift) or ``unparseable`` (a reply that is not a JSON object with the schema's
    required keys). ``take()`` hands the calls of one decision to the checkpoint row."""

    def __init__(self, inner: Any):
        self.inner = inner
        self.calls: list[dict[str, Any]] = []

    @property
    def last_call(self) -> Any:
        return getattr(self.inner, "last_call", None)

    def __getattr__(self, item: str) -> Any:          # usage, model_for, estimate_cost, ...
        return getattr(self.inner, item)

    def _book(self, system: str, prompt: str, deep: bool, schema: dict[str, Any] | None,
              reply: str | None, seconds: float) -> str | None:
        from agentic_trader.llm import extract_json
        if reply is None or not str(reply).strip():
            status = "fallback"
        elif schema is not None:
            data = extract_json(reply)
            status = "ok" if isinstance(data, dict) and all(k in data for k in _required(schema)) \
                else "unparseable"
        else:
            status = "ok"
        ev = self.last_call if isinstance(self.last_call, dict) else {}
        self.calls.append({"deep": deep, "schema": schema is not None, "status": status,
                           "seconds": round(seconds, 3), "in_tok_est": estimate_tokens(system, prompt),
                           "out_tok_est": estimate_tokens("", reply or ""), "reply": reply,
                           "model_served": ev.get("model_served"), "stop_reason": ev.get("stop_reason")})
        return reply

    def complete(self, system: str, prompt: str, *, deep: bool) -> str | None:
        t = time.perf_counter()
        reply = self.inner.complete(system, prompt, deep=deep)
        return self._book(system, prompt, deep, None, reply, time.perf_counter() - t)

    def complete_json(self, system: str, prompt: str, *, deep: bool, schema: dict[str, Any]) -> str | None:
        t = time.perf_counter()
        cj = getattr(self.inner, "complete_json", None)
        reply = (cj(system, prompt, deep=deep, schema=schema) if callable(cj)
                 else self.inner.complete(system, prompt, deep=deep))
        return self._book(system, prompt, deep, schema, reply, time.perf_counter() - t)

    def take(self) -> list[dict[str, Any]]:
        out, self.calls = self.calls, []
        return out


def _sources(state: Any) -> dict[str, str]:
    """Which path (``llm`` / ``rules``) produced each desk output of one decision."""
    out = {f"analyst:{k}": getattr(r, "source", "rules") for k, r in state.reports.items()}
    for key, obj in (("debate", state.debate), ("trader", state.proposal), ("pm", state.decision)):
        if obj is not None:
            out[key] = getattr(obj, "source", "rules")
    for i, v in enumerate(state.risk_views):
        out[f"risk:{getattr(v, 'stance', i)}"] = getattr(v, "source", "rules")
    return out


def _market(state: Any) -> dict[str, Any]:
    """Point-in-time facts for the metrics: close, vol-target control weight, regime label."""
    from agentic_trader.regime import regime_labels
    close = state.history["Close"].astype(float)
    r = np.log(close).diff().dropna()
    vol = float(r.tail(VOL_WINDOW).std() * np.sqrt(252)) if len(r) >= 20 else float("nan")
    vt = float(min(1.0, VOL_TARGET / vol)) if vol > 0 else 0.0
    try:
        labels, _, _ = regime_labels(close, None, 2, None, pd.Timestamp(state.as_of))
        regime = int(labels[-1])
    except Exception:                                   # too little history for the HMM
        regime = -1
    return {"close": float(close.iloc[-1]), "vt_weight": vt, "regime": regime}


def _key(row: dict[str, Any]) -> tuple[str, int, str, str]:
    return (row["cell"], int(row["seed"]), row["symbol"], row["as_of"])


def load_rows(path: Path) -> list[dict[str, Any]]:
    """Decision rows of a checkpoint file; a torn last line (killed mid-write) is ignored."""
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "symbol" in row:
                rows.append(row)
    return rows


def run_study(names: list[str], dates: list[date], seeds: int, cells: Iterable[Cell], config: dict,
              out: Path, llm_factory: Callable[[dict], Any] | None = None,
              echo: Callable[[str], None] = print) -> list[dict[str, Any]]:
    """Run ``cells`` on the design, one checkpointed JSON line per decision.

    Resume: decisions already in ``out`` are skipped, so a killed run restarts where it
    stopped. Each line carries the decision, the market facts for the metrics, the source of
    every desk output and every model call with its raw reply. ``llm_factory(config)`` builds
    the backend (default ``get_llm``); the study wraps it in ``StudyLLM``.
    """
    from agentic_trader.llm import get_llm
    factory = llm_factory or (lambda cfg: get_llm(make_config(cfg)))
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():                       # drop a torn last line so the next row starts clean
        raw = out.read_bytes()
        if raw and not raw.endswith(b"\n"):
            out.write_bytes(raw[:raw.rfind(b"\n") + 1])
    done = {_key(r) for r in load_rows(out)}
    cells = list(cells)
    total = len(cells) * seeds * len(names) * len(dates)
    k = 0
    with out.open("a", encoding="utf-8") as fh:
        for cell in cells:
            for seed in range(seeds):
                cfg = {**config, "local_llm_seed": seed}
                llm = StudyLLM(factory(cfg)) if cell.llm_roles else None
                graph = StudyGraph(cell, cfg, llm)
                for d in dates:
                    for name in names:
                        k += 1
                        key = (cell.name, seed, name, d.isoformat())
                        if key in done:
                            continue
                        t = time.perf_counter()
                        state, dec = graph.propagate(name, d)
                        calls = llm.take() if llm is not None else []
                        row = {"cell": cell.name, "seed": seed, "symbol": name, "as_of": d.isoformat(),
                               "action": dec.action.value, "target_weight": float(dec.target_weight),
                               "source": dec.source, "sources": _sources(state), **_market(state),
                               "seconds": round(time.perf_counter() - t, 3), "calls": calls}
                        fh.write(json.dumps(row, default=str) + "\n")
                        fh.flush()
                        bad = sum(c["status"] != "ok" for c in calls)
                        echo(f"[{k}/{total}] {cell.name} s{seed} {d} {name}: {dec.action.value} "
                             f"w={dec.target_weight:+.3f} calls={len(calls)} not_ok={bad} "
                             f"{row['seconds']:.1f}s")
    return load_rows(out)


# ---- metrics ---------------------------------------------------------------------------------

def _sr(x: np.ndarray, ppy: float) -> float:
    s = float(np.std(x, ddof=1)) if len(x) > 1 else 0.0
    return float(np.mean(x) / s * np.sqrt(ppy)) if s > 0 else 0.0


def block_bootstrap_diff(a: np.ndarray, b: np.ndarray, ppy: float, block: int = BLOCK,
                         n_boot: int = N_BOOT, seed: int = 0) -> tuple[float, float, float, float]:
    """Sharpe(a) - Sharpe(b) on paired periods with a circular block bootstrap: (diff, lo, hi, p)
    with a 95% percentile interval and a two-sided p (share of resamples on the far side of 0)."""
    n = len(a)
    diff = _sr(a, ppy) - _sr(b, ppy)
    if n < 3:
        return diff, float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = np.empty(n_boot)
    for i in range(n_boot):
        idx = (rng.integers(0, n, nb)[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        out[i] = _sr(a[idx], ppy) - _sr(b[idx], ppy)
    lo, hi = np.percentile(out, [2.5, 97.5])
    p = float(min(1.0, 2 * min(np.mean(out <= 0), np.mean(out >= 0))))
    return diff, float(lo), float(hi), p


def _cost_per_decision(rows: list[dict[str, Any]], config: dict) -> float:
    models = {False: config["quick_think_llm"], True: config["deep_think_llm"]}
    usd = 0.0
    for r in rows:
        for c in r["calls"]:
            pin, pout = price_for(models[bool(c["deep"])])
            usd += (c["in_tok_est"] * pin + c["out_tok_est"] * pout) / 1e6
    return usd / max(1, len(rows))


def cell_metrics(rows: list[dict[str, Any]], config: dict,
                 cap: float = MAX_FALLBACK_SHARE) -> list[dict[str, Any]]:
    """Per cell: portfolio Sharpe minus the vol-target control (block bootstrap CI and p),
    agent sources, contract rejection and fallback rates, admissibility under ``cap``,
    dispersion across seeds and the Claude list-price cost equivalent per decision.

    The portfolio holds each decision's target weight (equal-weighted over names) from its
    date to the next design date; the control holds the vol-target weight over the same span.
    The last date has no forward span and drops out."""
    out = []
    dates = sorted({r["as_of"] for r in rows})
    gaps = np.diff(pd.to_datetime(dates).values).astype("timedelta64[D]").astype(float)
    ppy = 365.25 / float(np.median(gaps)) if len(gaps) else 1.0
    closes = {(r["symbol"], r["as_of"]): r["close"] for r in rows}
    nxt = dict(zip(dates[:-1], dates[1:]))
    for cell in dict.fromkeys(r["cell"] for r in rows):
        cr = [r for r in rows if r["cell"] == cell]
        port, ctrl = [], []
        for seed in sorted({r["seed"] for r in cr}):
            for d in dates[:-1]:
                ws, vs = [], []
                for r in (x for x in cr if x["seed"] == seed and x["as_of"] == d):
                    c1 = closes.get((r["symbol"], nxt[d]))
                    if c1 is None or not r["close"]:
                        continue
                    f = c1 / r["close"] - 1.0
                    ws.append(r["target_weight"] * f)
                    vs.append(r["vt_weight"] * f)
                if ws:
                    port.append(float(np.mean(ws)))
                    ctrl.append(float(np.mean(vs)))
        a, b = np.asarray(port), np.asarray(ctrl)
        diff, lo, hi, p = block_bootstrap_diff(a, b, ppy)
        calls = [c for r in cr for c in r["calls"]]
        n_calls = len(calls)
        unparse = sum(c["status"] == "unparseable" for c in calls)
        fallback = sum(c["status"] == "fallback" for c in calls)
        share = (unparse + fallback) / n_calls if n_calls else 0.0
        sources: Counter[str] = Counter()
        for r in cr:
            sources.update(f"{k.split(':')[0]}={v}" for k, v in r["sources"].items())
        by_ns: dict[tuple[str, str], list[float]] = {}
        for r in cr:
            by_ns.setdefault((r["symbol"], r["as_of"]), []).append(r["target_weight"])
        disp = [float(np.std(v, ddof=1)) for v in by_ns.values() if len(v) > 1]
        out.append({
            "cell": cell, "decisions": len(cr), "periods": len(a), "sharpe": _sr(a, ppy),
            "control_sharpe": _sr(b, ppy), "sharpe_minus_control": diff, "ci_lo": lo, "ci_hi": hi,
            "p": p, "calls": n_calls, "calls_per_decision": n_calls / max(1, len(cr)),
            "contract_rejection_rate": unparse / n_calls if n_calls else 0.0,
            "fallback_rate": fallback / n_calls if n_calls else 0.0, "fallback_share": share,
            "admissible": share <= cap, "agent_sources": dict(sorted(sources.items())),
            "dispersion": float(np.mean(disp)) if disp else float("nan"),
            "cost_usd_per_decision": _cost_per_decision(cr, config),
            "seconds_per_call": float(np.mean([c["seconds"] for c in calls])) if calls else 0.0,
        })
    return out


def _chi2(table: np.ndarray) -> tuple[float, float]:
    """Chi-square independence test on a (groups x [ok, fell back]) table; (stat, p). Groups
    with no decisions and all-zero columns are dropped; a degenerate table gives (0, 1)."""
    t = table[table.sum(axis=1) > 0]
    t = t[:, t.sum(axis=0) > 0] if t.size else t
    if t.shape[0] < 2 or t.shape[1] < 2:
        return 0.0, 1.0
    t = t.astype(float)
    expected = t.sum(axis=1, keepdims=True) * t.sum(axis=0, keepdims=True) / t.sum()
    stat = float(((t - expected) ** 2 / expected).sum())
    return stat, chi2_sf(stat, (t.shape[0] - 1) * (t.shape[1] - 1))


def chi2_sf(x: float, df: int) -> float:
    """Chi-square survival function, 1 - P(df/2, x/2), by the lower incomplete gamma series
    (no SciPy in the runtime dependencies)."""
    if x <= 0:
        return 1.0
    a, z = df / 2.0, x / 2.0
    term = total = 1.0 / a
    n = 0
    while term > total * 1e-15 and n < 100_000:
        n += 1
        term *= z / (a + n)
        total += term
    lower = math.exp(a * math.log(z) - z - math.lgamma(a)) * total
    return float(min(1.0, max(0.0, 1.0 - lower)))


def fallback_bias(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """2.5: per model cell, the share of decisions with any fallen-back or rejected call by
    HMM regime label and by date, each with a chi-square independence test. A low p says the
    model fails more in some regimes or dates -- the surviving model decisions are then a
    biased sample and the cell's Sharpe is not a clean read of the model."""
    out = []
    for cell in dict.fromkeys(r["cell"] for r in rows):
        cr = [r for r in rows if r["cell"] == cell and r["calls"]]
        if not cr:
            continue
        for by in ("regime", "as_of"):
            groups = sorted({r[by] for r in cr})
            table = np.array([[sum(1 for r in cr if r[by] == g and not _failed(r)),
                               sum(1 for r in cr if r[by] == g and _failed(r))] for g in groups])
            stat, p = _chi2(table)
            out.append({"cell": cell, "by": by, "stat": stat, "p": p,
                        "groups": {str(g): {"decisions": int(t.sum()),
                                            "rate": float(t[1] / t.sum()) if t.sum() else 0.0}
                                   for g, t in zip(groups, table)}})
    return out


def _failed(row: dict[str, Any]) -> bool:
    return any(c["status"] != "ok" for c in row["calls"])


def _cap_note(cap: float) -> str:
    return (f"Admissible fallback share per cell: at most {cap:.0%} of model calls fell back to rules "
            f"or failed the contract; a cell above it is marked NOT admissible and its Sharpe is not read.")


def render_metrics(metrics: list[dict[str, Any]], bias: list[dict[str, Any]],
                   cap: float = MAX_FALLBACK_SHARE) -> str:
    head = ("| cell | decisions | Sharpe | control | diff [95% CI] | p | calls/dec | rejected | "
            "fallback | admissible | dispersion | $/decision (Claude list) |\n"
            "|---|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|")
    body = [f"| {m['cell']} | {m['decisions']} | {m['sharpe']:+.2f} | {m['control_sharpe']:+.2f} | "
            f"{m['sharpe_minus_control']:+.2f} [{m['ci_lo']:+.2f}, {m['ci_hi']:+.2f}] | {m['p']:.3f} | "
            f"{m['calls_per_decision']:.1f} | {m['contract_rejection_rate']:.1%} | {m['fallback_rate']:.1%} | "
            f"{'yes' if m['admissible'] else 'NOT'} | {m['dispersion']:.3f} | {m['cost_usd_per_decision']:.4f} |"
            for m in metrics]
    src = [f"- {m['cell']}: " + ", ".join(f"{k} {v}" for k, v in m["agent_sources"].items()) for m in metrics]
    bh = ["| cell | by | groups | worst rate | chi2 | p |", "|---|---|---:|---:|---:|---:|"]
    bh += [f"| {b['cell']} | {b['by']} | {len(b['groups'])} | "
           f"{max((g['rate'] for g in b['groups'].values()), default=0):.1%} | {b['stat']:.2f} | {b['p']:.3f} |"
           for b in bias]
    return "\n".join([head, *body, "", f"Control: {CONTROL} ({VOL_TARGET:.0%} target, {VOL_WINDOW}-day vol).",
                      _cap_note(cap), "", "Agent sources:", *src, "",
                      "Fallback/refusal by regime and date (2.5):", *bh, "", _cap_note(cap)])


def wall_clock(calls_per_decision: float, decisions: int) -> str:
    lo, hi = (calls_per_decision * decisions * s / 3600 for s in SECONDS_PER_CALL)
    return f"{calls_per_decision * decisions:,.0f} calls, {lo:,.1f}-{hi:,.1f} h at {SECONDS_PER_CALL[0]:g}-{SECONDS_PER_CALL[1]:g} s/call"


def smoke(config: dict, out: Path, llm_factory: Callable[[dict], Any] | None = None,
          names: list[str] | None = None, echo: Callable[[str], None] = print) -> int:
    """Two decisions on ``local_all`` (every role). Exit 1 when any model reply fell back or
    was unparseable, or when no call was made at all; 0 otherwise."""
    if out.exists():
        out.unlink()
    cell = next(c for c in CELLS if c.name == "local_all")
    rows = run_study((names or DEFAULT_NAMES)[:2], design_dates(FIRST_PASS["dates"])[1:2], 1, [cell],
                     config, out, llm_factory, echo)
    calls = [c for r in rows for c in r["calls"]]
    bad = [c for c in calls if c["status"] != "ok"]
    echo(f"smoke: {len(rows)} decisions, {len(calls)} calls, {len(bad)} not ok "
         f"({Counter(c['status'] for c in bad)}), mean {np.mean([c['seconds'] for c in calls] or [0]):.1f} s/call")
    return 1 if bad or not calls else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="call counts and Claude dollar estimate")
    mode.add_argument("--live", action="store_true", help="run the cells on the local model")
    mode.add_argument("--smoke", action="store_true", help="two decisions; exit 1 on any fallback")
    mode.add_argument("--report", action="store_true", help="metrics tables from --out")
    mode.add_argument("--describe", action="store_true", help="print each cell as a trial description")
    ap.add_argument("--first-pass", action="store_true",
                    help="the reduced first pass: 15 names x 20 dates x 1 seed, cells rules/local_analysts/local_all")
    ap.add_argument("--cells", help="comma-separated cell names (default: all, or the first pass)")
    ap.add_argument("--names", default=",".join(DEFAULT_NAMES))
    ap.add_argument("--dates", type=int, default=40, help="design dates, spread evenly")
    ap.add_argument("--seeds", type=int, default=2)
    ap.add_argument("--data", default="synthetic", help="data provider (synthetic | yahoo | csv)")
    ap.add_argument("--model", help="Ollama model name (--live, --smoke)")
    ap.add_argument("--url", help="Ollama URL (default config local_llm_url)")
    ap.add_argument("--out", default="results/llm_study.jsonl")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    config = make_config(STUDY_BASE, data_provider=args.data)
    cells = CELLS
    if args.first_pass:
        args.dates, args.seeds, cells = FIRST_PASS["dates"], FIRST_PASS["seeds"], _first_pass_cells()
    if args.cells:
        want = [c.strip() for c in args.cells.split(",")]
        unknown = set(want) - {c.name for c in CELLS}
        if unknown:
            ap.error(f"unknown cells {sorted(unknown)}")
        cells = tuple(c for c in CELLS if c.name in want)

    if args.describe:
        print(json.dumps([c.describe() for c in cells], indent=1))
        return 0
    if args.dry_run:
        rows = [r for r in dry_run_table(names, args.dates, args.seeds, config)
                if r["cell"] in {c.name for c in cells}]
        print(render(rows, config))
        print("\nLocal wall-clock (one model, sequential):")
        for r in rows:
            print(f"- {r['cell']}: {wall_clock(r['calls_per_decision'], r['decisions'])}")
        return 0
    if args.report:
        rows = load_rows(Path(args.out))
        print(render_metrics(cell_metrics(rows, config), fallback_bias(rows)))
        return 0
    if not args.model:
        ap.error("--live and --smoke need --model (an Ollama model name)")
    config.update(llm_provider="local", local_llm_model=args.model, **LOCAL_BUDGET)
    if args.url:
        config["local_llm_url"] = args.url
    if not reachable(config["local_llm_url"]):
        print(f"refusing --{'smoke' if args.smoke else 'live'}: no Ollama server answers at "
              f"{config['local_llm_url']}", file=sys.stderr)
        return 2
    if args.smoke:
        return smoke(config, Path(args.out).with_suffix(".smoke.jsonl"), names=names)
    unregistered = [c.trial_name for c in cells if c.llm_roles and c.trial_name not in TRIAL_NAMES]
    if unregistered:
        print(f"refusing --live: cells not registered in evaluation.TRIALS: {unregistered}", file=sys.stderr)
        return 2
    run_study(names, design_dates(args.dates), args.seeds, cells, config, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
