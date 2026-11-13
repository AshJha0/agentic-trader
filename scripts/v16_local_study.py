"""v0.16 local-model study, lane A: anonymisation recall audit (2.4) and calibration (2.6).

Plan items 2.4 and 2.6 (docs/review/PLAN.md, OD-6). Every model call goes to a local Ollama
server through ``local_llm.LocalLLM`` ($0, nothing leaves 127.0.0.1). A 7B 4-bit model is a
floor for a small local model, not a measurement of Claude.

    python scripts/v16_local_study.py recall      --out results/v16_local/recall.json
    python scripts/v16_local_study.py calibration --out results/v16_local/calibration_a.json
    python scripts/v16_local_study.py drift --a results/v16_local/calibration_a.json --b results/v16_local/calibration_b.json --out results/v16_local/drift.json
    python scripts/v16_local_study.py recall2     --out results/v17_local/recall2.json
    python scripts/v16_local_study.py design --cell decisive_ta --out results/v17_local/decisive_ta.jsonl

**v0.17 (review 2026-11-09 N1, N3, N5, N9).** ``recall`` is the v0.16 audit, kept only to
reproduce the void v0.16 rows: its fixed candidate order makes it a position-bias measure
(N1). ``recall2`` is the replacement (``agentic_trader.recall_audit``): interleaved items,
per-item shuffled candidates with recorded seeds, ranked top 3 scored by MRR against a label
permutation null, a synthetic placebo arm, a position-bias diagnostic and a real vs
date-shifted forward-return test. ``design`` runs the powered cells of
``agentic_trader.study_design`` (``decisive_ta``, ``postcutoff_ta``). Both write a run header
(``study_lineage``: git SHA, prompt hash, Ollama version, model digest, options) and refuse to
resume on a mismatch unless ``--allow-version-change`` (recorded in the header file).

Each model subcommand appends one row per item to ``<out>.rows.jsonl`` as soon as it is
answered (raw reply kept), resumes from that file on a rerun, prints per-row progress and
writes the summary JSON at the end. ``--smoke`` runs 3 items into ``<out>`` with ``.smoke``
inserted and exits 1 if any reply fails to parse.

**Prompts.** Both studies use the desk's own technical-analyst prompt (``TechnicalAnalyst.
gather`` + ``Analyst.prompt``) on a real point-in-time state (``TradingGraph.prepare`` on the
chosen provider, default Yahoo), anonymised by the same ``anonymize.Anonymizer`` the desk
installs when ``llm_anonymize`` is on (aliases, D-offsets, close rebased to 100, allow-listed
fact keys), then ``scrub``-bed exactly as ``Agent._complete`` does. The technical analyst is
used because it needs only the price series (no EDGAR/FRED call) and it is the prompt that
carries the shape of the return series, the residual leak named in ``anonymize.py``.

**2.4 recall.** 200 prompts = 15 core names x 14 design dates (evenly spread over 2016-2021),
first 200 in name-major order. The anonymised prompt is followed by a question naming the 15
candidate tickers and the design window and asking for ``TICKER: <t>`` and ``MONTH: YYYY-MM``
(free text, plain ``complete``). Chance model: the model is told the closed candidate list and
the window, so a guess uniform over the list hits the ticker with p0 = 1/15 and one uniform over
the 72 design months hits the month with p0 = 1/72 (within +-1 month: 3/72, edge months ignored).
Reported: hits, rate, Wilson 95 % CI, one-sided exact binomial p vs p0. Ablation: on every
item with a ticker or month hit, each fact key in the anonymised prompt is dropped in turn and
the question asked again; a key whose removal loses the hit is listed as leaking.

**2.6 calibration.** 20 frozen states drawn with ``random.Random(seed)`` from names x 40 design
dates. Per state: one baseline call at temperature 0 (fixed seed), ``--repeats`` (5) calls at
``--temperature`` (0.7) with seeds seed+1..seed+n (dispersion), and the ``--anchor-key`` fact
(``rsi14``) set to each of ``--anchor-values`` at temperature 0 (anchoring slope: OLS of signal
on the fact with state fixed effects). Analyst replies use ``complete_json`` with
``contracts.ANALYST`` (grammar-constrained). Drift: ``drift`` compares the baseline signals of
two calibration outputs (same states, e.g. two model builds) -- mean |diff|, sign agreement,
correlation -- and refuses when the state keys differ.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader import contracts  # noqa: E402
from agentic_trader.agents.analysts import TechnicalAnalyst  # noqa: E402
from agentic_trader.anonymize import PRICE_KEYS, Anonymizer  # noqa: E402
from agentic_trader.config import make_config  # noqa: E402
from agentic_trader.evaluation import CORE_UNIVERSE, HoldoutLocked  # noqa: E402
from agentic_trader.graph import TradingGraph  # noqa: E402
from agentic_trader.llm import extract_json  # noqa: E402
from agentic_trader import recall_audit as ra  # noqa: E402
from agentic_trader import study_design as design  # noqa: E402
from agentic_trader import study_lineage as lineage  # noqa: E402
from agentic_trader.local_llm import LocalLLM, reachable  # noqa: E402
from agentic_trader.study_robust import PROVIDER_TRIES, ProviderMiss, retry_provider, skip_row  # noqa: E402

NAMES: list[str] = CORE_UNIVERSE["equity"] + CORE_UNIVERSE["fx"]        # 15 names
DESIGN_START, DESIGN_END = date(2016, 1, 1), date(2021, 12, 31)
DESIGN_MONTHS = 72
RECALL_DATES, RECALL_N = 14, 200
CAL_STATES, CAL_DATES, CAL_SEED = 20, 40, 2026
JSON_SUFFIX = "\n\nRespond with a single JSON object only (no prose outside it)."
RECALL_SYSTEM = ("You are helping audit a data-anonymisation scheme. Answer the question at the end "
                 "with your single best guess, in the exact format asked.")


# ------------------------------------------------------------------ states and prompts
def design_dates(n: int) -> list[date]:
    import numpy as np
    import pandas as pd
    days = pd.bdate_range(DESIGN_START, DESIGN_END)
    return [days[i].date() for i in np.linspace(0, len(days) - 1, n).round().astype(int)]


class FrozenState:
    """One anonymised analyst input: the real state, its facts and its anonymiser."""

    def __init__(self, graph: TradingGraph, symbol: str, as_of: date, placebo_seed: int | None = None):
        self.symbol, self.as_of = symbol, as_of
        self.state = graph.prepare(symbol, as_of)
        if placebo_seed is not None:       # N1 placebo arm: drift/vol-matched synthetic bars
            self.state.history = ra.placebo_ohlc(self.state.history, placebo_seed)
        self.state.anon = Anonymizer(self.state.instrument, self.state.as_of, self.state.last_price)
        self.analyst = TechnicalAnalyst(None, graph.config)
        self.facts = self.analyst.gather(self.state, graph.provider)
        self.bar_date = self.state.history.index[-1].date()

    @property
    def key(self) -> str:
        return f"{self.symbol}@{self.as_of.isoformat()}"

    def prompt_keys(self) -> list[str]:
        """Fact keys that survive anonymisation (the ones the model actually sees)."""
        return sorted(self.state.prompt_facts(self.facts))

    def prompt(self, drop: str | None = None, override: dict[str, Any] | None = None) -> str:
        facts = {k: v for k, v in self.facts.items() if k != drop}
        if override:
            facts.update(override)
        return self.state.anon.scrub(self.analyst.prompt(facts, self.state))

    @property
    def system(self) -> str:
        return self.analyst.system_prompt


def make_graph(data: str) -> TradingGraph:
    cfg = make_config({"memory_path": None, "llm_anonymize": True}, data_provider=data)
    return TradingGraph(cfg, llm=None, on_event=lambda s, m: None)


# ------------------------------------------------------------------ stats
def wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Bin(n, p), exact."""
    return float(min(1.0, sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))))


def rate_row(k: int, n: int, p0: float) -> dict[str, Any]:
    lo, hi = wilson(k, n)
    return {"hits": k, "n": n, "rate": k / n if n else None, "ci95": [lo, hi], "chance": p0,
            "p_one_sided": binom_sf(k, n, p0) if n else None, "above_chance": bool(n and lo > p0)}


# ------------------------------------------------------------------ recall parsing
def recall_question(names: list[str]) -> str:
    return ("\n\nAUDIT QUESTION (not a trading task). The data above is anonymised. It comes from one "
            f"of these instruments: {', '.join(names)}; and the decision day (D0) lies between "
            f"{DESIGN_START:%Y-%m} and {DESIGN_END:%Y-%m}. Which instrument is it and in which "
            "calendar month is D0? Give your best guess even if unsure. Reply with exactly two lines:\n"
            "TICKER: <one ticker from the list>\nMONTH: <YYYY-MM>")


_T = re.compile(r"TICKER\s*[:=]\s*\**\s*([A-Za-z/=.]+)", re.I)
_M = re.compile(r"MONTH\s*[:=]\s*\**\s*(\d{4})-(\d{1,2})", re.I)


def parse_recall(text: str | None, names: list[str]) -> dict[str, Any] | None:
    """``{"ticker", "month"}`` or ``None`` if either line is missing or the ticker is unknown."""
    if not text:
        return None
    t, m = _T.search(text), _M.search(text)
    if not t or not m:
        return None
    raw = t.group(1).upper().replace("/", "").replace("=X", "").strip(".")
    if raw not in names:
        return None
    mo = int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return {"ticker": raw, "month": f"{int(m.group(1)):04d}-{mo:02d}"}


def month_index(s: str) -> int:
    y, m = s.split("-")
    return int(y) * 12 + int(m) - 1


def score(guess: dict[str, Any] | None, symbol: str, as_of: date) -> dict[str, Any]:
    if guess is None:
        return {"ticker_hit": False, "month_hit": False, "month_near": False, "month_err": None}
    err = month_index(guess["month"]) - (as_of.year * 12 + as_of.month - 1)
    return {"ticker_hit": guess["ticker"] == symbol, "month_hit": err == 0, "month_near": abs(err) <= 1,
            "month_err": err}


def parse_analyst(text: str | None) -> dict[str, Any] | None:
    d = extract_json(text)
    if not d:
        return None
    try:
        s, c = float(d["signal"]), float(d["confidence"])
    except (KeyError, TypeError, ValueError):
        return None
    if isinstance(d.get("signal"), bool) or not (math.isfinite(s) and math.isfinite(c)):
        return None
    return {"signal": max(-1.0, min(1.0, s)), "confidence": max(0.0, min(1.0, c))}


# ------------------------------------------------------------------ checkpoint helpers
class Checkpoint:
    def __init__(self, out: Path):
        self.path = out.with_suffix(".rows.jsonl")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.rows: dict[str, dict] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    r = json.loads(line)
                    self.rows[r["id"]] = r

    def add(self, row: dict) -> None:
        self.rows[row["id"]] = row
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")


def _write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")


def _meta(llm: Any, t0: float, **extra: Any) -> dict[str, Any]:
    usage = llm.usage.summary() if hasattr(llm, "usage") else None
    return {"model": getattr(llm, "model", type(llm).__name__), "backend": "ollama (local, $0)",
            "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "runtime_s": round(time.time() - t0, 1), "usage": usage,
            "note": "small local open-weight model: a floor, not a measurement of Claude.", **extra}


# ------------------------------------------------------------------ 2.4 recall
def recall_items(limit: int = 0) -> list[tuple[str, date]]:
    items = [(n, d) for n in NAMES for d in design_dates(RECALL_DATES)][:RECALL_N]
    return items[:limit] if limit else items


def run_recall(llm: Any, graph: TradingGraph, out: Path, *, limit: int = 0, ablate: bool = True,
               log: Callable[[str], None] = print, provider_tries: int = PROVIDER_TRIES,
               sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """A provider miss on one item is retried ``provider_tries`` times, then recorded as a
    skipped row (retried on the next resume) and reported in the result's ``skipped`` block."""
    t0, ck = time.time(), Checkpoint(out)
    items = recall_items(limit)
    q = recall_question(NAMES)
    frozen: dict[str, FrozenState] = {}

    def fs(sym: str, d: date) -> FrozenState:
        k = f"{sym}@{d.isoformat()}"
        if k not in frozen:
            frozen[k] = retry_provider(lambda sym=sym, d=d: FrozenState(graph, sym, d), label=k,
                                       tries=provider_tries, sleep=sleep)
        return frozen[k]

    def done(rid: str) -> bool:
        return rid in ck.rows and not ck.rows[rid].get("skipped")

    def ask(st: FrozenState, drop: str | None) -> dict[str, Any]:
        reply = llm.complete(RECALL_SYSTEM, st.prompt(drop=drop) + q, deep=False)
        g = parse_recall(reply, NAMES)
        return {"raw": reply, "guess": g, "parsed": g is not None, **score(g, st.symbol, st.as_of)}

    for i, (sym, d) in enumerate(items, 1):
        rid = f"{sym}@{d.isoformat()}"
        if not done(rid):
            try:
                st = fs(sym, d)
            except ProviderMiss as e:
                ck.add(skip_row(rid, e.reason, e.tries, kind="base", symbol=sym, as_of=d.isoformat()))
                log(f"skip {rid}: {e.reason}")
                continue
            ck.add({"id": rid, "kind": "base", "symbol": sym, "as_of": d.isoformat(),
                    "bar_date": st.bar_date.isoformat(), "keys": st.prompt_keys(), **ask(st, None)})
            log(f"recall {i}/{len(items)} {time.time() - t0:.0f}s")
    ids = [f"{s}@{d.isoformat()}" for s, d in items]
    skipped = [ck.rows[r] for r in ids if not done(r)]
    base = [ck.rows[r] for r in ids if done(r)]
    if ablate:
        hits = [r for r in base if r["ticker_hit"] or r["month_hit"]]
        todo = [(r, k) for r in hits for k in r["keys"]]
        for j, (r, k) in enumerate(todo, 1):
            aid = f"{r['id']}#-{k}"
            if aid not in ck.rows:
                st = fs(r["symbol"], date.fromisoformat(r["as_of"]))
                ck.add({"id": aid, "kind": "ablation", "base_id": r["id"], "dropped": k, **ask(st, k)})
                log(f"ablation {j}/{len(todo)} {time.time() - t0:.0f}s")
    res = summarise_recall(base, [r for r in ck.rows.values() if r.get("kind") == "ablation"],
                           meta=_meta(llm, t0, prompt_source="TechnicalAnalyst prompt, Anonymizer + scrub"))
    res["skipped"] = _skips(skipped, len(items))
    return res


def _skips(skipped: list[dict], units: int) -> dict[str, Any]:
    """The ``skipped`` block of a result: count, units, and each skipped id with its reason."""
    return {"n": len(skipped), "units": units,
            "rows": [{"id": r["id"], "kind": r.get("kind"), "reason": r.get("skip_reason")} for r in skipped]}


def summarise_recall(base: list[dict], abl: list[dict], meta: dict | None = None) -> dict[str, Any]:
    n = len(base)
    leaks: dict[str, dict[str, int]] = {}
    by_base = {r["id"]: r for r in base}
    for a in abl:
        b = by_base.get(a["base_id"])
        if b is None:
            continue
        row = leaks.setdefault(a["dropped"], {"ticker_lost": 0, "ticker_tested": 0, "month_lost": 0,
                                              "month_tested": 0})
        if b["ticker_hit"]:
            row["ticker_tested"] += 1
            row["ticker_lost"] += int(not a["ticker_hit"])
        if b["month_hit"]:
            row["month_tested"] += 1
            row["month_lost"] += int(not a["month_hit"])
    leaking = sorted((k for k, v in leaks.items() if v["ticker_lost"] or v["month_lost"]),
                     key=lambda k: -(leaks[k]["ticker_lost"] + leaks[k]["month_lost"]))
    by_name: dict[str, int] = {}
    for r in base:
        by_name[r["symbol"]] = by_name.get(r["symbol"], 0) + int(r["ticker_hit"])
    return {
        "study": "2.4 anonymisation recall audit",
        "chance_model": ("closed set told to the model: ticker uniform over 15 candidates (1/15); month "
                         "uniform over 72 design months (1/72; +-1 month 3/72, edges ignored)"),
        "n": n, "unparsed": sum(not r["parsed"] for r in base),
        "ticker": rate_row(sum(r["ticker_hit"] for r in base), n, 1 / len(NAMES)),
        "month": rate_row(sum(r["month_hit"] for r in base), n, 1 / DESIGN_MONTHS),
        "month_within_1": rate_row(sum(r["month_near"] for r in base), n, 3 / DESIGN_MONTHS),
        "ticker_hits_by_name": by_name,
        "ablation": {"calls": len(abl), "per_key": leaks, "leaking_keys": leaking},
        "rows": base, "ablation_rows": abl, "meta": meta or {},
    }


# ------------------------------------------------------------------ 2.6 calibration
class SampledLocalLLM(LocalLLM):
    """``LocalLLM`` whose temperature and seed can be set per call (calibration only)."""

    temperature = 0.0

    def build_request(self, system, prompt, schema=None):
        body = super().build_request(system, prompt, schema)
        body["options"]["temperature"] = float(self.temperature)
        return body


def calibration_states(limit: int = 0, seed: int = CAL_SEED) -> list[tuple[str, date]]:
    grid = [(n, d) for n in NAMES for d in design_dates(CAL_DATES)]
    pick = random.Random(seed).sample(grid, CAL_STATES)
    return pick[:limit] if limit else pick


def _set(llm: Any, temperature: float, seed: int) -> None:
    """Sampling controls on backends that have them (``SampledLocalLLM``; fakes may record)."""
    if hasattr(llm, "temperature"):
        llm.temperature = temperature
    if hasattr(llm, "seed"):
        llm.seed = seed


def run_calibration(llm: Any, graph: TradingGraph, out: Path, *, limit: int = 0, repeats: int = 5,
                    temperature: float = 0.7, seed: int = CAL_SEED, anchor_key: str = "rsi14",
                    anchor_values: tuple[float, ...] = (20.0, 40.0, 60.0, 80.0),
                    log: Callable[[str], None] = print, provider_tries: int = PROVIDER_TRIES,
                    sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """A provider miss on one state is retried ``provider_tries`` times, then the state is
    recorded as one skipped row (retried on the next resume), left out of the summary and
    reported in the result's ``skipped`` block."""
    if anchor_key in PRICE_KEYS:
        raise ValueError("anchor_key must be a scale-free fact (price keys are rebased)")
    t0, ck = time.time(), Checkpoint(out)
    states = calibration_states(limit, seed)
    plan: list[tuple[str, str, float, int, dict | None]] = []   # (suffix, kind, temp, seed, override)
    plan.append(("base", "base", 0.0, seed, None))
    plan += [(f"rep{i}", "repeat", temperature, seed + i, None) for i in range(1, repeats + 1)]
    plan += [(f"anchor={v:g}", "anchor", 0.0, seed, {anchor_key: v}) for v in anchor_values]
    total, done = len(states) * len(plan), 0
    for sym, d in states:
        st: FrozenState | None = None
        key = f"{sym}@{d.isoformat()}"
        skip_id = f"skip:{key}"
        for suffix, kind, temp, sd, override in plan:
            rid = f"{key}#{suffix}"
            done += 1
            if rid in ck.rows:
                continue
            if st is None:
                try:
                    st = retry_provider(lambda sym=sym, d=d: FrozenState(graph, sym, d), label=key,
                                        tries=provider_tries, sleep=sleep)
                except ProviderMiss as e:
                    ck.add(skip_row(skip_id, e.reason, e.tries, kind="skipped", state=key))
                    log(f"skip {key}: {e.reason}")
                    break
                if ck.rows.get(skip_id, {}).get("skipped"):   # recovered on resume
                    ck.add({**ck.rows[skip_id], "skipped": False, "recovered": True})
            _set(llm, temp, sd)
            reply = llm.complete_json(st.system, st.prompt(override=override) + JSON_SUFFIX, deep=False,
                                      schema=contracts.ANALYST)
            p = parse_analyst(reply)
            ck.add({"id": rid, "state": st.key, "kind": kind, "temperature": temp, "seed": sd,
                    "anchor_value": (override or {}).get(anchor_key),
                    "orig_anchor_value": st.facts.get(anchor_key),
                    "raw": reply, "parsed": p is not None, **(p or {"signal": None, "confidence": None})})
            log(f"calibration {done}/{total} {time.time() - t0:.0f}s")
    all_keys = [f"{s}@{d.isoformat()}" for s, d in states]
    skipped = [ck.rows[f"skip:{k}"] for k in all_keys if ck.rows.get(f"skip:{k}", {}).get("skipped")]
    keys = [k for k in all_keys if not ck.rows.get(f"skip:{k}", {}).get("skipped")]
    kept = set(keys)
    rows = [r for r in ck.rows.values() if r.get("state") in kept and r.get("kind") != "skipped"]
    res = summarise_calibration(rows, keys, anchor_key=anchor_key, repeats=repeats, temperature=temperature,
                                meta=_meta(llm, t0, seed=seed, prompt_source="TechnicalAnalyst prompt, "
                                           "Anonymizer + scrub, complete_json(contracts.ANALYST)"))
    res["skipped"] = _skips(skipped, len(all_keys))
    return res


def _std(xs: list[float]) -> float | None:
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def anchoring_slope(points: list[tuple[str, float, float]]) -> dict[str, Any]:
    """OLS slope of signal on the anchor value with state fixed effects (within-state demeaning),
    plus a cluster-free standard error. ``points`` are (state, x, signal)."""
    groups: dict[str, list[tuple[float, float]]] = {}
    for s, x, y in points:
        groups.setdefault(s, []).append((x, y))
    xs, ys = [], []
    for g in groups.values():
        if len(g) < 2:
            continue
        mx, my = sum(p[0] for p in g) / len(g), sum(p[1] for p in g) / len(g)
        xs += [p[0] - mx for p in g]
        ys += [p[1] - my for p in g]
    sxx = sum(x * x for x in xs)
    if not xs or sxx == 0:
        return {"slope": None, "se": None, "n": len(xs), "states": len(groups)}
    b = sum(x * y for x, y in zip(xs, ys)) / sxx
    dof = len(xs) - len([g for g in groups.values() if len(g) >= 2]) - 1
    resid = sum((y - b * x) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(resid / dof / sxx) if dof > 0 else None
    return {"slope": b, "se": se, "n": len(xs), "states": len([g for g in groups.values() if len(g) >= 2])}


def summarise_calibration(rows: list[dict], keys: list[str], *, anchor_key: str, repeats: int,
                          temperature: float, meta: dict | None = None) -> dict[str, Any]:
    per_state, pts, base = [], [], {}
    for k in keys:
        rs = [r for r in rows if r["state"] == k]
        reps = [r["signal"] for r in rs if r["kind"] == "repeat" and r["parsed"]]
        b = next((r for r in rs if r["kind"] == "base"), None)
        if b is not None and b["parsed"]:
            base[k] = b["signal"]
            if b.get("orig_anchor_value") is not None:
                pts.append((k, float(b["orig_anchor_value"]), b["signal"]))
        pts += [(k, float(r["anchor_value"]), r["signal"]) for r in rs if r["kind"] == "anchor" and r["parsed"]]
        signs = {(s > 0) - (s < 0) for s in reps}
        per_state.append({"state": k, "repeat_signals": reps, "std": _std(reps),
                          "range": (max(reps) - min(reps)) if reps else None, "sign_flip": len(signs) > 1})
    stds = sorted(s["std"] for s in per_state if s["std"] is not None)
    return {
        "study": "2.6 calibration (dispersion, anchoring, drift baseline)",
        "states": keys, "n_states": len(keys), "unparsed": sum(not r["parsed"] for r in rows), "calls": len(rows),
        "dispersion": {"repeats": repeats, "temperature": temperature,
                       "mean_std": sum(stds) / len(stds) if stds else None,
                       "median_std": stds[len(stds) // 2] if stds else None,
                       "max_std": stds[-1] if stds else None,
                       "sign_flip_states": sum(s["sign_flip"] for s in per_state), "per_state": per_state},
        "anchoring": {"key": anchor_key, **anchoring_slope(pts)},
        "baseline": base,          # temperature 0, fixed seed: the input to `drift`
        "rows": rows, "meta": meta or {},
    }


def drift(a: dict, b: dict) -> dict[str, Any]:
    """Compare the temperature-0 baselines of two calibration outputs on the same states."""
    if sorted(a["states"]) != sorted(b["states"]):
        raise ValueError("the two runs used different states; drift needs the same frozen states")
    common = [k for k in a["states"] if k in a["baseline"] and k in b["baseline"]]
    xa, xb = [a["baseline"][k] for k in common], [b["baseline"][k] for k in common]
    n = len(common)
    out: dict[str, Any] = {"study": "2.6 drift between two runs", "n": n,
                           "model_a": a.get("meta", {}).get("model"), "model_b": b.get("meta", {}).get("model")}
    if n == 0:
        return {**out, "mean_abs_diff": None, "sign_agreement": None, "corr": None}
    diffs = [abs(p - q) for p, q in zip(xa, xb)]
    sgn = lambda v: (v > 0) - (v < 0)  # noqa: E731
    ma, mb = sum(xa) / n, sum(xb) / n
    va, vb = sum((x - ma) ** 2 for x in xa), sum((x - mb) ** 2 for x in xb)
    corr = sum((p - ma) * (q - mb) for p, q in zip(xa, xb)) / math.sqrt(va * vb) if va > 0 and vb > 0 else None
    return {**out, "mean_abs_diff": sum(diffs) / n, "max_abs_diff": max(diffs),
            "sign_agreement": sum(sgn(p) == sgn(q) for p, q in zip(xa, xb)) / n, "corr": corr,
            "per_state": {k: [p, q] for k, p, q in zip(common, xa, xb)}}


# ------------------------------------------------------------------ v0.17 recall audit v2 (N1)
RECALL2_SEED, RECALL2_DATES, PLACEBO_N, SHIFT_BARS, LEAK_HORIZON = 20261109, 14, 60, 63, 5


def _fwd(graph: TradingGraph, st: FrozenState, offset: int, horizon: int, *, tries: int = PROVIDER_TRIES,
         sleep: Callable[[float], None] = time.sleep) -> float | None:
    """Forward close-to-close return over ``horizon`` bars starting ``offset`` bars after the
    decision bar (scoring only, never shown to the model). Provider misses are retried; after
    ``tries`` misses ``ProviderMiss`` propagates and the caller records a skipped row."""
    import pandas as pd
    from datetime import timedelta
    end = st.bar_date + timedelta(days=int(2 * (offset + horizon)) + 15)
    h = retry_provider(lambda: graph.provider.history(st.state.instrument, st.bar_date, end),
                       label=f"fwd {st.key}", tries=tries, sleep=sleep)
    c = h["Close"].astype(float)
    c = c[c.index >= pd.Timestamp(st.bar_date)]
    if len(c) <= offset + horizon:
        return None
    return float(c.iloc[offset + horizon] / c.iloc[offset] - 1.0)


def run_recall2(llm: Any, graph: TradingGraph, out: Path, *, header: dict[str, Any], limit: int = 0,
                placebo_n: int = PLACEBO_N, leak: bool = True, seed: int = RECALL2_SEED,
                log: Callable[[str], None] = print, provider_tries: int = PROVIDER_TRIES,
                sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """N1 audit: real arm (all names x RECALL2_DATES dates, interleaved, shuffled candidates),
    placebo arm (``placebo_n`` drift/vol-matched synthetic series), and the behavioural leak test
    (analyst signal on each real state vs the real and the SHIFT_BARS-shifted forward return).

    A provider miss on one unit is retried ``provider_tries`` times, then recorded as a skipped
    row (``study_robust``); the result's ``skipped`` block counts them. Progress prints
    ``k/N`` over all units (real + placebo + leak)."""
    t0, ck = time.time(), Checkpoint(out)
    dates = [d.isoformat() for d in design_dates(RECALL2_DATES)]
    real = ra.build_items(NAMES, dates, seed=seed, limit=limit)
    plc = ra.build_items(NAMES, dates, seed=seed, arm="placebo", limit=min(placebo_n, limit or placebo_n))
    window = (f"{DESIGN_START:%Y-%m}", f"{DESIGN_END:%Y-%m}")

    total = len(real) + len(plc) + (len(real) if leak else 0)   # every unit, for the k/N log
    k = 0

    def done(rid: str) -> bool:
        return rid in ck.rows and not ck.rows[rid].get("skipped")

    def frozen(it: ra.AuditItem, rid: str, kind: str, placebo_seed: int | None) -> FrozenState | None:
        try:
            return retry_provider(lambda: FrozenState(graph, it.truth, date.fromisoformat(it.as_of),
                                                      placebo_seed=placebo_seed),
                                  label=rid, tries=provider_tries, sleep=sleep)
        except ProviderMiss as e:
            ck.add(lineage.stamp(skip_row(rid, e.reason, e.tries, kind=kind, symbol=it.truth,
                                          as_of=it.as_of), header))
            log(f"skip {rid}: {e.reason}")
            return None

    def ask(it: ra.AuditItem) -> None:
        if done(it.id):
            return
        st = frozen(it, it.id, it.arm, it.placebo_seed)
        if st is None:
            return
        prompt = st.prompt() + ra.question(it, window)
        reply = llm.complete(RECALL_SYSTEM, prompt, deep=False)
        g = ra.parse_ranked(reply, it.candidates)
        ck.add(lineage.stamp({"id": it.id, "kind": it.arm, "idx": it.idx, "symbol": it.truth, "as_of": it.as_of,
                              "candidates": list(it.candidates), "candidate_seed": it.candidate_seed,
                              "placebo_seed": it.placebo_seed, "raw": reply, "guess": g, "parsed": g is not None,
                              "rr": ra.reciprocal_rank((g or {}).get("ranked"), it.truth),
                              "prompt_sha256": lineage.prompt_sha256(RECALL_SYSTEM, prompt)}, header))

    for it in real + plc:
        k += 1
        ask(it)
        log(f"recall2 {k}/{total} {time.time() - t0:.0f}s")
    leak_rows = []
    if leak:
        for it in real:
            k += 1
            lid = f"leak:{it.truth}@{it.as_of}"
            if not done(lid):
                st = frozen(it, lid, "leak", None)
                fwd: tuple[float | None, float | None] | None = None
                if st is not None:
                    try:   # forward returns first: a miss here skips the unit before the model call
                        fwd = (_fwd(graph, st, 0, LEAK_HORIZON, tries=provider_tries, sleep=sleep),
                               _fwd(graph, st, SHIFT_BARS, LEAK_HORIZON, tries=provider_tries, sleep=sleep))
                    except ProviderMiss as e:
                        ck.add(lineage.stamp(skip_row(lid, e.reason, e.tries, kind="leak", symbol=it.truth,
                                                      as_of=it.as_of), header))
                        log(f"skip {lid}: {e.reason}")
                if st is not None and fwd is not None:
                    reply = llm.complete_json(st.system, st.prompt() + JSON_SUFFIX, deep=False,
                                              schema=contracts.ANALYST)
                    p = parse_analyst(reply)
                    ck.add(lineage.stamp({"id": lid, "kind": "leak", "symbol": it.truth, "as_of": it.as_of,
                                          "raw": reply, "parsed": p is not None, "signal": (p or {}).get("signal"),
                                          "fwd_real": fwd[0], "fwd_shift": fwd[1],
                                          "horizon_days": LEAK_HORIZON, "shift_bars": SHIFT_BARS}, header))
                log(f"leak {k}/{total} {time.time() - t0:.0f}s")
            if done(lid):
                leak_rows.append(ck.rows[lid])
    # Skipped items (provider miss after retries) leave the analysis but are reported: the
    # pre-registered summary carries their count, ids and reasons (never a silent drop).
    skipped = [ck.rows[r] for r in [i.id for i in real + plc] + [f"leak:{i.truth}@{i.as_of}" for i in (real if leak else [])]
               if r in ck.rows and ck.rows[r].get("skipped")]
    real = [i for i in real if done(i.id)]
    plc = [i for i in plc if done(i.id)]
    real_ans = [ck.rows[i.id]["guess"] for i in real]
    plc_ans = [ck.rows[i.id]["guess"] for i in plc]
    res = ra.summarise(real, real_ans, plc, plc_ans, leak_rows)
    skips = {"n": len(skipped), "units": total, "by_kind": {kd: sum(r.get("kind") == kd for r in skipped)
                                                             for kd in ("real", "placebo", "leak")},
             "rows": [{"id": r["id"], "kind": r.get("kind"), "reason": r.get("skip_reason")} for r in skipped]}
    return {"study": "N1 recall audit v2", **res.as_dict(), "skipped": skips, "seed": seed,
            "header_id": header.get("header_id"),
            "rows": [ck.rows[i.id] for i in real + plc], "ablation_rows": [], "leak_rows": leak_rows,
            "meta": _meta(llm, t0, prompt_source="TechnicalAnalyst prompt, Anonymizer + scrub; recall_audit v2")}


def _header(a: argparse.Namespace, llm: Any, graph: TradingGraph, extra: dict[str, Any]) -> dict[str, Any]:
    opts = {"num_ctx": getattr(llm, "num_ctx", None), "num_predict": getattr(llm, "max_tokens", None),
            "temperature": getattr(llm, "temperature", 0.0), "seed": getattr(llm, "seed", None)}
    return lineage.build_header(model=getattr(llm, "model", None), url=getattr(llm, "url", None), options=opts,
                                config=graph.config, extra={"cmd": a.cmd, **extra})


# ------------------------------------------------------------------ CLI
RETRY_BUDGET_S = 600.0     # v0.19: ride out an Ollama hang of up to ~10 min, then stop loudly


def _llm(a: argparse.Namespace) -> LocalLLM:
    cfg = {"llm_provider": "local", "local_llm_model": a.model, "local_llm_timeout_s": a.timeout,
           "local_llm_seed": CAL_SEED, "max_tokens": a.max_tokens,
           "local_llm_num_ctx": getattr(a, "num_ctx", None),
           "local_llm_retry_budget_s": getattr(a, "retry_budget", RETRY_BUDGET_S)}
    llm = SampledLocalLLM(cfg)
    if not reachable(llm.url):
        raise SystemExit(f"no Ollama server at {llm.url}")
    return llm


def _out(a: argparse.Namespace) -> Path:
    p = Path(a.out)
    return p.with_name(p.stem + ".smoke" + p.suffix) if a.smoke else p


def _smoke_exit(rows: list[dict]) -> int:
    bad = [r["id"] for r in rows if not r["parsed"]]
    if bad:
        print(f"SMOKE FAILED: {len(bad)} unparseable replies: {bad}", file=sys.stderr)
        return 1
    print(f"smoke ok: {len(rows)} replies parsed")
    return 0


def main(argv: list[str] | None = None, llm_factory: Callable[[argparse.Namespace], Any] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("recall", "calibration", "recall2", "design"):
        s = sub.add_parser(name)
        s.add_argument("--model", default="qwen2.5:7b-instruct")
        s.add_argument("--out", required=True)
        s.add_argument("--data", default="yahoo", help="price provider for the real states (yahoo | csv | synthetic)")
        s.add_argument("--timeout", type=float, default=300)
        s.add_argument("--retry-budget", type=float, default=RETRY_BUDGET_S,
                       help="seconds of backoff retries on a hung/unreachable Ollama (0 = no retry)")
        s.add_argument("--max-tokens", type=int, default=512)
        s.add_argument("--limit", type=int, default=0)
        s.add_argument("--smoke", action="store_true", help="3 items; exit 1 if any reply fails to parse")
        s.add_argument("--num-ctx", type=int, default=8192, help="Ollama context window (N4)")
        s.add_argument("--allow-version-change", action="store_true",
                       help="resume despite a changed git SHA / prompt hash / server / digest (recorded)")
        if name == "recall2":
            s.add_argument("--placebo", type=int, default=PLACEBO_N)
            s.add_argument("--no-leak", action="store_true")
        elif name == "design":
            s.add_argument("--cell", choices=[c.name for c in design.DESIGN_CELLS], required=True)
            s.add_argument("--no-futility", action="store_true")
        elif name == "recall":
            s.add_argument("--no-ablation", action="store_true")
        else:
            s.add_argument("--repeats", type=int, default=5)
            s.add_argument("--temperature", type=float, default=0.7)
            s.add_argument("--seed", type=int, default=CAL_SEED)
            s.add_argument("--anchor-key", default="rsi14")
            s.add_argument("--anchor-values", default="20,40,60,80")
    d = sub.add_parser("drift")
    d.add_argument("--a", required=True)
    d.add_argument("--b", required=True)
    d.add_argument("--out", required=True)
    a = p.parse_args(argv)

    if a.cmd == "drift":
        res = drift(json.loads(Path(a.a).read_text(encoding="utf-8")), json.loads(Path(a.b).read_text(encoding="utf-8")))
        _write(Path(a.out), res)
        print(json.dumps({k: v for k, v in res.items() if k != "per_state"}, indent=1))
        return 0

    limit = 3 if a.smoke else a.limit
    llm = (llm_factory or _llm)(a)
    graph = make_graph(a.data)
    out = _out(a)
    if a.cmd in ("recall2", "design"):
        hdr = _header(a, llm, graph, {"data": a.data, "limit": limit})
        rows_path = out if a.cmd == "design" else out.with_suffix(".rows.jsonl")
        try:
            hdr = lineage.check_resume(rows_path, hdr, allow_version_change=a.allow_version_change)
        except lineage.LineageMismatch as e:
            print(str(e), file=sys.stderr)
            return 2
        if a.cmd == "design":
            cell = next(c for c in design.DESIGN_CELLS if c.name == a.cell)
            # Review B4 / B3 / B10: a registered cell runs only under the signed pre-registration,
            # with its holdout basis recorded, and never on a truncated grid. The smoke test
            # (three decisions, its own file) is the one exception.
            if not a.smoke:
                if limit:
                    print("refusing design --limit: it keeps the earliest dates only, a different population "
                          "from the registered cell; the futility rule is the only early stop", file=sys.stderr)
                    return 2
                try:
                    gate = design.prereg_gate(ROOT) | design.holdout_access(cell)
                except (design.PreregNotSigned, HoldoutLocked) as e:
                    print(f"refusing design {cell.name}: {e}", file=sys.stderr)
                    return 2
                (out.with_suffix(".gate.json")).write_text(json.dumps(gate, indent=1), encoding="utf-8")
            drows = design.run_cell(cell, NAMES, graph, llm, out, header=hdr, limit=limit,
                                futility_check=not a.no_futility)
            rep = design.report(cell, drows, NAMES)
            _write(out.with_suffix(".report.json"), rep)
            print(json.dumps({k: v for k, v in rep.items() if k != "planned"}, indent=1, default=str)[:4000])
            if a.smoke:
                bad = [f"{r['symbol']}@{r['as_of']}" for r in drows if r.get("signal_model") is None]
                if bad:
                    print(f"SMOKE FAILED: {len(bad)} model calls fell back: {bad}", file=sys.stderr)
                    return 1
                print(f"smoke ok: {len(drows)} decisions")
            return 0
        res = run_recall2(llm, graph, out, header=hdr, limit=limit, placebo_n=1 if a.smoke else a.placebo,
                          leak=not (a.no_leak or a.smoke))
        rows = res["rows"]
    elif a.cmd == "recall":
        res = run_recall(llm, graph, out, limit=limit, ablate=not (a.no_ablation or a.smoke))
        rows = res["rows"] + res["ablation_rows"]
    else:
        vals = tuple(float(x) for x in a.anchor_values.split(",") if x.strip())
        res = run_calibration(llm, graph, out, limit=limit, repeats=a.repeats, temperature=a.temperature,
                              seed=a.seed, anchor_key=a.anchor_key, anchor_values=vals)
        rows = res["rows"]
    _write(out, res)
    print(json.dumps({k: v for k, v in res.items() if k not in ("rows", "ablation_rows", "per_state")},
                     indent=1, default=str)[:4000])
    return _smoke_exit(rows) if a.smoke else 0


if __name__ == "__main__":
    raise SystemExit(main())
