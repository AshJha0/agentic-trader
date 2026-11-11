# v0.19 lane B: long-run robustness

Three failures seen in real long local-model runs (Ollama, qwen2.5:7b) and what changed.
For the CHANGELOG and PLAN owner to fold in; this lane did not edit either.

## 1. Ollama hang: bounded retry in `LocalLLM`

- New config `local_llm_retry_budget_s` (default 0 = old behaviour: one failure returns `None`
  and the rules answer applies) and `local_llm_retry_base_s` (default 2 s).
- With a budget set, a transient failure (timeout, refused or reset connection, HTTP 5xx) is
  retried with exponential backoff 2, 4, 8, ... s, capped at 60 s per wait, the waits summing
  to the budget. Each retry logs a warning and counts `usage.retries` (in `usage.summary()`).
- A 4xx and an unreadable body (`ValueError`) are never retried.
- Budget spent: `LocalLLMUnavailable` (a `ConnectionError`) is raised, so the run stops loudly
  instead of turning every later row into a silent rules fallback. The checkpoint keeps every
  row written so far; restart Ollama and resume.
- Determinism: the request body is built once per call and resent byte for byte, so seed,
  options and the recorded prompt digest do not change (test checks the body hash).
- Both study drivers set 600 s: `scripts/v16_local_study.py` (`--retry-budget`, default 600)
  and `scripts/llm_study.py` (`LOCAL_BUDGET`). The desk default stays 0.

## 2. Provider miss: retry, then a recorded skip

- `agentic_trader/study_robust.py`: `retry_provider` retries a `ValueError` (provider "no data")
  3 times, 5 s apart, then raises `ProviderMiss`.
- `run_recall2` (v16_local_study): a unit that still misses is written as a checkpoint row
  `{"skipped": true, "skip_reason", "skip_tries", "kind"}`. The result has a `skipped` block
  (count, units, count by kind real/placebo/leak, ids and reasons). Skipped units leave the
  analysis; they are reported, not dropped silently. A resume retries them.
- `run_study` (llm_study): same, as a skipped row per (cell, seed, name, date). `load_rows`
  excludes skipped rows, new `load_skips` lists those not later completed, and `--report`
  prints the count and each skipped unit.
- Pre-registration: any registered analysis built on these drivers must quote the skip count
  next to N. Added 2026-11-11 (v16 prereg "Skipped units"; cap enforced in `cell_metrics`).

## 3. Progress `k/N`

- `run_recall2` now prints one counter over all units, N = real + placebo + leak (leak only
  when enabled); before, each arm restarted at 1 with its own N.
- `run_study` already printed `[k/total]`; skipped units print there too.

## Tests

`tests/test_v019_robustness.py` (fakes only): backoff bounds, transient classification, retry
then success with unchanged body digest, exhausted budget raises, 4xx and parse error not
retried, default budget keeps the old fallback, provider retry, recall2 skip row + `skipped`
block + `k/N` with N = 15 + resume completes the skip, llm_study skip row + `load_skips` + resume.

## Open items

- Done 2026-11-11: `run_recall` (v1), `run_calibration` and `_fwd` now retry and record skipped rows.
- Long chains already running in other checkouts use the old code; they pick this up only on
  restart, and the git SHA in the lineage header changes (use `--allow-version-change`).
