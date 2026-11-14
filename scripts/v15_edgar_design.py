"""v0.15 plan items 3.2 and 3.7 on real EDGAR text, DESIGN period only.

Names: the core single-name equities (``evaluation.CORE_UNIVERSE["equity"]`` minus SPY, which
files no 10-K/10-Q), nine companies.

Step ``download``: every 10-K, 10-Q and kept 8-K (items 2.02, 7.01, 8.01) accepted from about
one year before the design start (warm-up, so the first design filing has a predecessor to
difference against) to the design end. Nothing accepted after ``PERIODS["design"][1]`` is
requested, so the holdout is never read. Documents are cached as plain text in the git-ignored
``results/edgar_text_cache``.

Step ``tone``: the registered trial "v0.15 EDGAR filing tone change (lexicon diff,
10-K/10-Q)". ``alpha.filing_tone_changes`` on the 10-K/10-Q sections, ``tone_change_signal``
with its defaults (hold 63 bars, scale 0.5, fixed before the run), purged IC and decay via
``alpha.text_alpha_decay`` per name on design-period closes, and the mean across names with a
t-statistic across names. Output: ``results/v15/edgar_tone_design.json``.

Step ``rag``: item 3.7 on real text. A corpus of the design-period filing sections, the
hand-labelled questions in ``agentic_trader/agentic/knowledge/retrieval_eval/
edgar_real_questions.json``, ``evaluate_retrieval`` for tfidf and hybrid.
Output: ``results/v15/edgar_rag_eval.json``.

The SEC asks for a descriptive User-Agent: set ``EDGAR_USER_AGENT`` in the environment of the
process (never written to the repo). Network for ``download`` and for the Yahoo closes in
``tone``; the test suite never runs this script.

    .venv\\Scripts\\python.exe scripts/v15_edgar_design.py download|tone|rag|show ACCESSION
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.data.edgar_text import EdgarProvider, extract_sections  # noqa: E402
from agentic_trader.evaluation import CORE_UNIVERSE, PERIODS  # noqa: E402

NAMES = [s for s in CORE_UNIVERSE["equity"] if s != "SPY"]
CACHE = ROOT / "results" / "edgar_text_cache"
OUT = ROOT / "results" / "v15"
QUESTIONS = ROOT / "agentic_trader" / "agentic" / "knowledge" / "retrieval_eval" / "edgar_real_questions.json"
D0 = datetime.fromisoformat(PERIODS["design"][0]).replace(tzinfo=timezone.utc)
D1 = (datetime.fromisoformat(PERIODS["design"][1]) + timedelta(days=1)).replace(tzinfo=timezone.utc)
WARM = D0 - timedelta(days=380)
HORIZONS = (1, 5, 10, 21, 63)


# SEC's current ticker map sends XOM to a new registrant (CIK 2115436, filings from 2026 only);
# the design-period filings are under the historical Exxon Mobil CIK.
CIK_PINS = {"XOM": "34088"}


def provider() -> EdgarProvider:
    return EdgarProvider(cache_dir=CACHE, ciks=CIK_PINS)


def rows_in_window(p: EdgarProvider, sym: str) -> list[dict]:
    return [r for r in p.filing_index(sym) if r["accepted"] is not None and WARM <= r["accepted"] < D1]


def all_sections(p: EdgarProvider, sym: str, design_only: bool = False) -> list:
    out = []
    for r in rows_in_window(p, sym):
        if design_only and r["accepted"] < D0:
            continue
        out.extend(p.filing_sections(sym, r))
    return out


def cmd_download() -> None:
    p = provider()
    t0 = time.time()
    for sym in NAMES:
        rows = rows_in_window(p, sym)
        for r in rows:
            p.document(r)
        print(f"{sym}: {len(rows)} filings, requests so far {p.requests}, {time.time() - t0:.0f}s", flush=True)


def cmd_coverage() -> None:
    """Which kept sections were cut from each filing (cutter inspection)."""
    p = provider()
    for sym in NAMES:
        for r in rows_in_window(p, sym):
            secs = extract_sections(p.document(r), r["form"])
            print(sym, r["form"], r["accession"], r["accepted"].date(), {k: len(v) for k, v in secs.items()}, flush=True)


def cmd_tone() -> None:
    from agentic_trader.alpha import filing_tone_changes, text_alpha_decay, tone_change_signal
    from agentic_trader.config import make_config
    from agentic_trader.data import get_provider
    from agentic_trader.instruments import Instrument

    p = provider()
    prices = get_provider(make_config({"data_provider": "yahoo"}))
    start, end = (datetime.fromisoformat(d).date() for d in PERIODS["design"])
    per, n_filings, n_changes = {}, 0, 0
    for sym in NAMES:
        secs = [s for s in all_sections(p, sym) if s.form.split("/")[0] in ("10-K", "10-Q")]
        changes = [c for c in filing_tone_changes(secs) if c.visible_date >= D0]  # design filings only
        h = prices.history(Instrument.parse(sym), start, end)
        sig = tone_change_signal(h.index, changes)
        dec = text_alpha_decay(sig, h["Close"].to_numpy(float), HORIZONS)
        accns = {c.accession for c in changes}
        n_filings += len(accns)
        n_changes += len(changes)
        per[sym] = {"filings": len(accns), "section_changes": len(changes), "bars": len(h), "decay": dec}
        print(sym, len(accns), {k: (round(v["ic"], 4), round(v["t"], 2)) for k, v in dec.items()}, flush=True)
    pooled = {}
    for hz in HORIZONS:
        ics = np.array([per[s]["decay"][hz]["ic"] for s in NAMES], float)
        ics = ics[np.isfinite(ics)]
        se = ics.std(ddof=1) / np.sqrt(ics.size) if ics.size > 1 else float("nan")
        pooled[hz] = {
            "mean_ic": float(ics.mean()),
            "t_across_names": float(ics.mean() / se),
            "names": int(ics.size),
            "positive": int((ics > 0).sum()),
        }
    res = {
        "trial": "v0.15 EDGAR filing tone change (lexicon diff, 10-K/10-Q)",
        "period": PERIODS["design"],
        "names": NAMES,
        "params": {"hold_bars": 63, "scale": 0.5, "n_folds": 5},
        "filings": n_filings,
        "section_changes": n_changes,
        "pooled": pooled,
        "per_name": per,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "edgar_tone_design.json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
    print(json.dumps(pooled, indent=2))


# The 3.7 corpus: design-period 10-K sections (1A, 7) and 8-K items, paragraphs merged into
# passages of at least 1500 characters. 10-Qs are left out: their risk factors largely repeat
# the 10-K, and the dense TF-IDF index (passages x 4096 buckets) is rebuilt per as_of.
RAG_FORMS = ("10-K", "8-K")
RAG_MIN_CHARS = 1500


def design_corpus():
    from agentic_trader.agentic.research_rag import ResearchCorpus

    p = provider()
    secs = []
    for sym in NAMES:
        secs.extend(s for s in all_sections(p, sym, design_only=True) if s.form in RAG_FORMS)
    return ResearchCorpus.build(secs, min_chars=RAG_MIN_CHARS)


def cmd_rag() -> None:
    from agentic_trader.agentic.research_rag import comparison_table, evaluate_retrieval, load_questions

    t0 = time.time()
    corpus = design_corpus()
    qs = load_questions(QUESTIONS)
    missing = [g for q in qs for g in q.gold if corpus.get(g) is None]
    if missing:
        raise SystemExit(f"gold passage ids not in the corpus: {missing[:5]}")
    late = [q.id for q in qs for g in q.gold if corpus.get(g).visible_date > q.as_of]
    if late:
        raise SystemExit(f"gold passages not visible at the question's as_of: {late}")
    # how hard the point-in-time filter is exercised: same-symbol, same-section passages that
    # the filter hides because they were accepted after as_of (later dividends, CCARs, rulings)
    hidden = sum(
        1
        for q in qs
        for p in corpus.passages
        if p.visible_date > q.as_of and p.symbol == corpus.get(q.gold[0]).symbol and p.section == corpus.get(q.gold[0]).section
    )
    reps = [evaluate_retrieval(corpus, qs, m) for m in ("tfidf", "hybrid")]
    print(comparison_table(reps))
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "edgar_rag_eval.json").write_text(
        json.dumps(
            {
                "passages": len(corpus),
                "questions": len(qs),
                "distinct_as_of": len({q.as_of for q in qs}),
                "later_same_symbol_section_passages_hidden": hidden,
                "reports": [{**r.__dict__, "passes_gate": r.passes_gate} for r in reps],
                "seconds": round(time.time() - t0, 1),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def cmd_find(terms: list[str]) -> None:
    """Labelling aid: passages containing every term (case-insensitive), with id and date."""
    corpus = design_corpus()
    low = [t.lower() for t in terms]
    for ps in corpus.passages:
        tx = ps.text.lower()
        if all(t in tx for t in low):
            print(ps.id, ps.symbol, ps.visible_date.date(), "|", ps.text[:240].replace("\n", " "))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=["download", "coverage", "tone", "rag", "find"])
    ap.add_argument("terms", nargs="*")
    a = ap.parse_args()
    if a.step == "find":
        cmd_find(a.terms)
    else:
        {"download": cmd_download, "coverage": cmd_coverage, "tone": cmd_tone, "rag": cmd_rag}[a.step]()
