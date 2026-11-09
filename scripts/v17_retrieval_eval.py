"""v0.17 R3.2: retrieval recall on the old and the paraphrased (v2) question sets, offline.

The fixture corpus (``knowledge/retrieval_eval/corpus.json``, 24 synthetic filing sections and
10 central-bank statements) and both question sets are in the repo, so this runs with no
network. Every v2 question must pass the lexical-overlap check against its gold passage
(``agentic.question_overlap``); the script refuses to report numbers otherwise. The old set's
overlap rate is reported for comparison.

    python scripts/v17_retrieval_eval.py --out docs/results/v17_retrieval

The 50-question real-EDGAR set (v0.15 3.7) needs the git-ignored ``results/edgar_text_cache``,
which is not on this machine; ``scripts/v15_edgar_design.py rag`` reproduces that number when the
cache exists.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agentic_trader.agentic.question_overlap import MAX_CONTAINMENT, lexical_overlap  # noqa: E402
from agentic_trader.agentic.research_rag import (EVAL_DIR, comparison_table, evaluate_retrieval,  # noqa: E402
                                                 load_eval_corpus, load_questions)

SETS = {"v1_fixture": EVAL_DIR / "questions.json", "v2_paraphrased": EVAL_DIR / "questions_v2.json"}


def overlap_stats(corpus, qs) -> dict:
    rows = [(q, lexical_overlap(q.text, corpus.get(q.gold[0]).text)) for q in qs]
    return {"n": len(rows), "rejected": sum(o.rejected for _, o in rows),
            "with_shared_bigram": sum(bool(o.shared_bigrams) for _, o in rows),
            "mean_containment": round(sum(o.containment for _, o in rows) / len(rows), 4),
            "rejected_ids": [q.id for q, o in rows if o.rejected]}


def run() -> dict:
    corpus = load_eval_corpus()
    out: dict = {"corpus": {"passages": len(corpus), "file": "agentic_trader/agentic/knowledge/retrieval_eval/corpus.json"},
                 "overlap_rule": {"max_containment": MAX_CONTAINMENT, "shared_bigram": "reject"}, "sets": {}}
    for name, path in SETS.items():
        qs = load_questions(path)
        missing = [q.id for q in qs if corpus.get(q.gold[0]) is None]
        if missing:
            raise SystemExit(f"{name}: gold passages missing: {missing[:5]}")
        ov = overlap_stats(corpus, qs)
        if name.startswith("v2") and ov["rejected"]:
            raise SystemExit(f"v2 questions fail the overlap check: {ov['rejected_ids']}")
        reps = [evaluate_retrieval(corpus, qs, m) for m in ("tfidf", "hybrid")]
        out["sets"][name] = {"file": str(path.relative_to(ROOT)).replace("\\", "/"), "overlap": ov,
                             "reports": [{**r.__dict__, "passes_gate": r.passes_gate} for r in reps],
                             "table": comparison_table(reps)}
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    res = run()
    for name, s in res["sets"].items():
        print(f"## {name}  (overlap-rejected {s['overlap']['rejected']}/{s['overlap']['n']})\n{s['table']}\n")
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "retrieval_v1_v2.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
        try:
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        except OSError:
            sha = None
        meta = {"run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_head": sha,
                "command": "python scripts/v17_retrieval_eval.py --out docs/results/v17_retrieval",
                "evidence_class": "synthetic fixture corpus (invented filings, real-looking central-bank text); "
                                  "offline, deterministic, no model",
                "note": "Real-EDGAR 50-question set not re-run: results/edgar_text_cache is absent on this machine."}
        (out / "retrieval_v1_v2.meta.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
