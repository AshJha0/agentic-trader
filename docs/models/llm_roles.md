# Card: LLM roles

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** research. **Code:** `agentic_trader/agents/` (analysts, researchers, facilitator,
trader, risk, PM through `agents/base.py`), `agentic/planner.py`, `text_analysts.py`, and the
judge in `scripts/v16_eval.py`.

## Purpose
Replace or argue with a rule at a fixed point of the decision: read the analyst facts and
produce a structured reply (signal, confidence, reasons) that a contract check accepts or
rejects. The model never computes a number the rules can compute (`text_analysts.py`
docstring); a rejected or failed reply falls back to the rule.

## Inputs
The same facts the rules see, rendered into prompts. With `llm_anonymize` on, tickers become
aliases, dates become offsets from the decision day, prices are rebased to 100 and only
scale-free facts pass (`anonymize.py`). Since v0.17 the text analysts' filing and
central-bank text goes through `Anonymizer.scrub_text` too (names, accession/CIK, written dates,
years), and any run with a model attached is anonymised unless `allow_deanonymized_llm` is set
(`anonymize.enforce_llm_anonymize`).

## Validation evidence
- Planner: 1,345 of 1,506 proposed steps survived the validator (89.3%), 13 of 200 plans
  unusable (real-local; `docs/evaluation/what_the_model_adds.md`, row 4.2).
- Injection red team: 21 of 150 attacks moved the signal by more than 0.5 (real-local;
  `docs/results/v15_local/redteam_compliance.json`). The 2026-11-09 review notes no benign
  control and one synthetic state (Appendix A, B3).
- Text analysts: macro stance agreed with the label on 11 of 12 statements, 10 of 10 filing
  claims kept (real-local; `docs/results/v15_local/text_analysts.json`). That run predates the
  v0.17 text anonymisation, so its prompts carried real names and dates (review N2).
- No measured trading edge for any LLM role on the local model yet; the P2 study is running and
  its first pass is descriptive only (review N3).

## Limitations
- All study dates fall inside the model's training data (review N9); a post-cutoff slice is
  planned, not run.
- The local context window is 8,192 tokens (`num_ctx`, review N4). The fundamentals-text
  prompt is held to `text_analyst_options.fundamentals_max_prompt_tokens` (default 6,000),
  counted with the conservative character estimate `llm.estimate_tokens`; filing sections go
  in newest first and the ones left out are listed in the report's `facts["prompt_budget"]`. A
  reply the server flags as truncated is rejected and the analyst abstains (review A11). The
  estimate is a heuristic, not a tokeniser, so the server-side check stays in place.
- No per-decision lineage (prompt hash, model digest, code SHA) yet (review N5, lane L1).

## Monitoring
Per call: served model vs configured model (drift), refusals, timeouts, fallbacks, and since
v0.17 the model host and whether a remote host was allowed (`LocalLLM.last_call`).

## Status
Research. No role is on by default.
