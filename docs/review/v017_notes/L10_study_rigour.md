# L10 study rigour (review 2026-11-09: N1, N3, N4, N5, N6, N9)

Lane L10, v0.17. Evidence class for everything below: code plus unit tests with fake HTTP
servers and fake models. No model has been run; no number here is a measurement of a model.

## What changed

| item | change | files |
|---|---|---|
| N1 recall audit (critical) | new library: interleaved items (date-major, then seeded shuffle), per-item shuffled candidate order (seed recorded per row), ranked top-3 scored by MRR, label-permutation null (keeps the model's answer distribution), synthetic drift/vol-matched placebo arm, position-bias chi-square, answer concentration, month test vs permutation null, real vs date-shifted forward-return leak test with date-clustered bootstrap. Verdict: recall flagged only if real MRR beats the permutation null AND the placebo arm (alpha 0.05); no placebo arm = "incomplete", never flagged. New `recall2` subcommand. The old `recall` subcommand is kept only to reproduce the void v0.16 rows. | `agentic_trader/recall_audit.py`, `scripts/v16_local_study.py` |
| N4 context window | `num_ctx` sent on every request (default 8192, `local_llm_num_ctx`); `last_call` now carries `prompt_eval_count`, `eval_count`, `prompt_tok_est`, `num_ctx`, `truncated`; usage counts `truncated`. Truncation = done_reason "length", or window full (`prompt_eval_count >= num_ctx`), or `prompt_eval_count < 0.9 x chars/4`. `temperature` option added (`local_llm_temperature`, default 0, compatible with L1). | `agentic_trader/local_llm.py` |
| N5 lineage | run header (git SHA + dirty flag, `prompt_bundle_hash`, Ollama `/api/version`, model digest/quantisation from `/api/tags`, options) with a stable `header_id`; stored as `<rows>.header.json`; resume refused on any identity change (exit 2) unless `--allow-version-change`, which appends the new header with `allowed_change` and `changed_fields`. Rows written before lineage are refused the same way (`legacy_rows` when allowed). Every row stamped with `header_id`, `git_sha`, `model_digest`, `prompt_sha256`. `swapped_digest()` for mid-run model-swap checks. | `agentic_trader/study_lineage.py`, `local_llm.py` (`server_version`, `model_digest`), call sites in `scripts/llm_study.py` (`--allow-version-change`, `run_study(header=...)`) |
| N6 row schema | P2 rows now store `horizon_days` (from the trader proposal), `entry_bar_date`, `asof_close`, `vintage_hash` (sha256 of the close series as fetched); per-call `prompt_sha256`, `prompt_eval_count`, `eval_count`, `truncated`. `--report` prints how many rows are legacy and the policy (`study_lineage.LEGACY_ROW_POLICY`: re-fetch one vintage per name, recompute entry and forward closes from it, horizon from the stored trader reply or the rules; labelled legacy). | `study_lineage.py`, `scripts/llm_study.py` |
| N3 decisive cell | `decisive_ta`: technical analyst only, 15 core names x weekly design dates (313), 5-day horizon, model signal minus rule signal, per-date Spearman IC with Newey-West SE, futility stop (after 40 dates, every 1,000 decisions, stop if IC + 1.2816 SE < 0.03). Runner, report, dry run. Registered in `evaluation.TRIALS` (v0.17). Preregistration draft updated: first pass labelled descriptive with its MDEs; decision rule; still DRAFT. | `agentic_trader/study_design.py`, `agentic_trader/evaluation.py`, `docs/evaluation/v16_preregistration_DRAFT.md`, `design` subcommand in `scripts/v16_local_study.py` |
| N9 leakage cell | `postcutoff_ta`: same cell, weekly 2025-07-01 to 2026-10-30, registered. | same |

## Numbers (design arithmetic, `python -m agentic_trader.study_design --dry-run`)

- First pass: MDE about 0.89 annual Sharpe (corr 0.7, 6 y) and about 0.36 IC (n_eff 60). Descriptive only.
- `decisive_ta`: 313 dates x 15 names = 4,695 decisions, 4,695 calls, 65-130 CPU hours (2.7-5.4 days at 50-100 s/call). MDE 0.093 IC at rho 0.3 (design effect 5.2, n_eff 903).
- `postcutoff_ta`: about 70 dates, about 1,050 decisions, 15-29 CPU hours.
- Trial count: `len(TRIALS)` 77 -> 79 (tests/test_v11.py updated). If L1 also adds trials, the maintainer must re-count at merge.

## Tests

`tests/test_v017_study_rigour.py` (new, 22 tests), plus updated `tests/test_v14_local_llm.py`
(options now include `num_ctx`; `last_call` has the new keys) and `tests/test_v11.py` (79).
Regression for N1: `test_old_v16_design_flags_always_first_on_a_prefix` shows the v0.16 design
flags an always-first model on a 30-item prefix; `test_always_first_responder_is_not_flagged`
shows v2 does not, at every prefix tried, while the position-bias diagnostic reports it
(first_share 1.0).

## Caveats (stated, not hidden)

- The truncation ratio test uses a heuristic chars/4 estimate; the window-full and length tests are exact. Check one real row (`prompt_eval_count` vs `prompt_tok_est`) on the first smoke run before trusting the flag.
- The leak test detects signal specific to the true future of a window; it cannot by itself separate memory from skill. That separation comes from `decisive_ta` vs `postcutoff_ta`.
- `postcutoff_ta` dates overlap the holdout (to 2026-06-30) and the reserve window (2026-07-01 to 2026-09-25). Running it spends those dates for this LLM question; owner sign-off needed (recorded in the preregistration draft).
- Yahoo bars to 2026-10-30 must exist for the last post-cutoff dates plus 5 bars; dates without forward bars score `fwd_ret: null` and drop out.
- The running v0.16 chain (AgenticTrader-v16) is untouched; its recall rows are void as a recall measure and its P2 rows are legacy under N6.

## Re-run commands (owner queue; smoke first, all $0 local)

Run from a clean checkout of the merged branch with the project venv; Ollama serving `qwen2.5:7b-instruct`.

```
# 1. N1 recall audit v2: smoke (3 real + 1 placebo items, no leak arm), then full
python scripts/v16_local_study.py recall2 --data yahoo --smoke --out results/v17_local/recall2.json
python scripts/v16_local_study.py recall2 --data yahoo --out results/v17_local/recall2.json
#    210 real + 60 placebo recall calls + 210 analyst calls for the leak arm (~480 calls, ~7-13 h)

# 2. N3 decisive cell: dry run, smoke (3 decisions), full
python -m agentic_trader.study_design --dry-run
python scripts/v16_local_study.py design --cell decisive_ta --data yahoo --smoke --out results/v17_local/decisive_ta.jsonl
python scripts/v16_local_study.py design --cell decisive_ta --data yahoo --out results/v17_local/decisive_ta.jsonl

# 3. N9 leakage control (after owner sign-off on spending holdout/reserve dates)
python scripts/v16_local_study.py design --cell postcutoff_ta --data yahoo --smoke --out results/v17_local/postcutoff_ta.jsonl
python scripts/v16_local_study.py design --cell postcutoff_ta --data yahoo --out results/v17_local/postcutoff_ta.jsonl
```

Smoke outputs go to `*.smoke.*`; delete them (and their `.header.json`) before the full run
or the full run resumes on top of the smoke rows' header. A resume after a code or model change
exits 2; add `--allow-version-change` only when the mix is intended.

## Follow-ups

- Kill and re-run the v0.16 chain's recall step with `recall2` (owner; chain is live).
- Optional second fast model (qwen2.5:3b or llama3.2:3b) on `decisive_ta` to bring the MDE near 0.066; would need its own trial entry.
- `llm_strict_model` still compares served names per call; per-call digest pinning is done at run start and by `swapped_digest`. A periodic `swapped_digest` check inside `run_study` is not wired (L1 owns that loop).

## COOKBOOK recipe (text for the maintainer)

**Audit whether a local model recognises anonymised series.** Plain idea: ask the model which
instrument a disguised chart is, with the answer options shuffled, and compare its score to a
shuffled-label null and to fake charts nobody could know. Run
`python scripts/v16_local_study.py recall2 --data yahoo --smoke --out results/v17_local/recall2.json`;
read `recall_flagged`, `real.mrr` vs `real.null_mean`, `real_vs_placebo.diff` and
`position_bias.first_share`. A first_share near 1 with `recall_flagged: false` is a model that
always picks the first option: biased, not remembering.
