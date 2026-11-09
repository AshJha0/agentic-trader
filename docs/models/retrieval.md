# Card: retrieval (TF-IDF, BM25 hybrid, MiniLM)

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** research, gated. **Code:** `agentic_trader/agentic/research_rag.py`
(`analyst_retriever`; the dense option uses `sentence-transformers/all-MiniLM-L6-v2`).

## Purpose
Find filing passages and central-bank statements for the text analysts. A corpus reaches an
analyst only if it passes the recall@5 >= 0.8 gate (`text_analysts.py`, wiring comment).

## Inputs
EDGAR filing sections and central-bank statements, point in time by acceptance or release date.

## Validation evidence
- Real filings: recall@5 0.92 (TF-IDF), 0.98 (hybrid) (real-rules; `what_the_model_adds.md`
  row 3.7). The review notes the 50 real questions were written from the gold passages, which
  flatters recall (Appendix A, B5).
- Fixture corpus: recall@5 0.990 for both (fixture).

## Limitations
Questions written by the same person who chose the gold passages; no held-out question set.

## Monitoring
The gate re-runs whenever a corpus is built; a failure leaves the analyst with its own
sections (fail closed).

## Status
Research; off unless `text_analyst_options.research_retrieval` is set.
