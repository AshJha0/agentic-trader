# Round 4 registration (DRAFT, unsigned)

Status: DRAFT, written 2026-11-14 before any Round 4 row exists. It becomes binding only when
the owner signs it in its own commit; until then nothing below may be scored. Owner decision
2026-11-13: Round 4 is a slim new study with two parts, the real-reply checker validation and
the memorisation pair. The v0.16/v0.17 study chains are closed and are not relaunched.

## What exists when this is written

- `results/v19_r4/run.jsonl` is being written (2026-11-14 from 12:50 UTC): one
  `scripts/v16_eval.py run` pass of `qwen2.5:7b-instruct` (Ollama, local, $0) over the 150 frozen
  eval items in `agentic_trader/agentic/knowledge/eval_set/`. These replies are the material for
  part A. Nobody has labelled or read them; the checker verdicts are computed only to stratify
  the sample.
- No memorisation-pair row exists. The post-cutoff dates (2025-07-01 to 2026-10-30) have not
  been read by any LLM cell (`docs/evaluation/v16_prereg_status_2026-11-12.md`).

## Part A: does the deterministic checker agree with a human on real replies?

Plain idea. The checker (`agentic_trader/agentic/eval_set.py`) grades each analyst reply on
fixed criteria. So far its agreement has only been measured on 30 hand-written cases, so the
docs call it "unvalidated". Part A measures agreement against the owner's own blind labels on
real model replies.

- **Sample**: 60 replies drawn from `results/v19_r4/run.jsonl` by
  `scripts/v17_label_kit.py sheet --n 60 --seed 20261109`, stratified by checker verdict so the
  sheet is not all easy passes. The sheet hides the checker verdict and the model name.
- **Labeller**: the owner only, blind, per criterion, pass or fail, following `INSTRUCTIONS.txt`.
  Labels are final once imported; no relabelling after the kappa is seen.
- **Primary statistic**: Cohen's kappa, checker against owner, per criterion, with a 95 %
  percentile bootstrap interval (2,000 resamples of rows; `judge_kit.kappa_bootstrap`).
- **Decision rule**: a criterion is reported as "validated on real replies" when the lower end
  of its interval is at least 0.40 (moderate agreement or better). Otherwise it stays
  "unvalidated", with the measured kappa quoted. The docs change only per criterion, never for
  the checker as a whole.
- **Secondary (descriptive)**: the `llama3.1:8b-instruct-q4_K_M` judge (a different model family
  from the replies) against the owner on the same 60 rows, same statistic, no decision attached.

Worked example. If a criterion has kappa 0.62 with interval [0.44, 0.78], it is validated. With
kappa 0.55 and interval [0.31, 0.74] it is not, and the docs say "kappa 0.55 [0.31, 0.74] on 60
real replies".

## Part B: memorisation pair

Plain idea. If the model has memorised price histories, then showing it the real name and
dates should help before its training cutoff, but not after. Anonymised prompts (rebased prices,
no names or dates) should show no such gap.

- **Arms**: the same model, states and seeds, with two prompts: `named` (real symbol and date)
  and `anon` (the current anonymised prompt). Technical analyst only, as in `decisive_ta`.
- **Windows**: pre-cutoff, weekly design dates already used by the first pass (no new design
  dates are read); post-cutoff, weekly, 2025-07-01 to 2026-10-30, the dates the owner reserved
  on 2026-11-12 for this one question.
- **Primary statistic**: difference in differences of per-date cross-sectional rank IC against
  the 5-trading-day forward return,
  `(IC_named - IC_anon)_pre - (IC_named - IC_anon)_post`, with a 95 % moving-block bootstrap
  interval over dates (block length 4 weeks, 2,000 resamples).
- **Decision rule**: memorisation is reported when the interval lies wholly above zero.
  Otherwise the report says that the pair found no evidence of memorisation at this power, and
  gives the interval. No trading rule is chosen on these dates afterwards.
- **Admissibility**: a cell is admissible when unparseable or fallback replies are at most 10 %
  of decisions, as in the v0.16 rules. An inadmissible cell is reported, not rerun with changes.

## Open items for the owner before signing

1. Accept or change the 0.40 lower-bound threshold in part A and the block length in part B.
2. Confirm the part B sample size (names x dates x seeds) after a dry run prints the wall-clock
   estimate; the dry run reads no prices and calls no model.
3. Sign: one command, its own commit, before any part B row and before importing labels.
