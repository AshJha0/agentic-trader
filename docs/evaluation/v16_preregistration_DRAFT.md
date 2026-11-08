# v0.16 pre-registration (DRAFT): the one holdout look for the LLM study

**Status: draft, not signed, not executed.** Written 2026-11-08, before any LLM study cell has
run on any date. No holdout decision has been made by any LLM cell. This draft becomes binding
only when it is signed (a commit that removes "DRAFT" from the title and fills the design-period
section) and that commit lands before the holdout run (`git log -- docs/evaluation/v16_preregistration*.md`).
If no cell clears the design bar below, the holdout look is not run at all and this file says so.

## What is being tested

PLAN.md P2 asks whether a local open-weight model (7-8B instruct, Q4, served by Ollama on
the owner's machine, OD-6) improves the desk when it reasons in some roles. The results are
for that model class only, not for Claude; Claude cells exist as dry-run cost estimates.

The reduced first pass (`scripts/llm_study.py --first-pass`) runs three cells on the design
period (2016-01-04 to 2021-12-31): 15 core names x 20 evenly spaced design dates x 1 seed.

| cell | model roles | registered trial (`evaluation.TRIALS`, v0.16) |
|---|---|---|
| rules | none (control desk) | - (the existing rules desk) |
| local_analysts | analysts only; trader, risk, PM on rules | `P2 local_analysts: ...` |
| local_all | every role | `P2 local_all: local model in every role` |

Both model cells were registered before any run, so they count in every deflated-Sharpe
statement whether or not one is adopted.

## The design bar (decided now, before any design result)

A cell is a candidate for the holdout look only if **all** of these hold on the design pass:

1. **Admissible**: at most 10% of its model calls fell back to rules or failed the contract
   (`MAX_FALLBACK_SHARE`). Above that the run measures the rules more than the model.
2. **No fallback bias**: the chi-square independence tests of fallback against HMM regime
   label and against date both have p >= 0.05 (2.5). A model that fails mostly in stressed
   regimes leaves a biased sample of model decisions.
3. **Beats the control**: portfolio Sharpe minus the vol-target control (long-only, 10% vol
   target, 63-day vol, equal-weighted over names, held to the next design date) is positive
   with the 95% circular block-bootstrap interval (block 3 dates, 2,000 resamples) above zero.
4. **Beats the rules desk** by the same paired test, so the gain comes from the model and not
   from the desk structure the rules cell also has.
5. **Survives selection**: deflated Sharpe probability > 0.95 with the trial count equal to
   `len(evaluation.TRIALS)` at the time of signing (72 at writing).

If more than one cell passes, the one with the larger lower bound in (3) goes forward; the
other is reported but not looked at on the holdout. If none passes, the study is closed as a
null on the design period and no holdout run is made.

## The holdout look (run once, only if a cell passes)

- **Period**: 2022-01-03 to 2026-06-30 (`evaluation.PERIODS["holdout"]`). The rules desk has
  been reported on it (v0.8), so it is spent for rule choices; no LLM cell has ever been run on
  it, so it is unseen for this question. The model's training data covers these years; the
  anonymisation (prices rebased, names and dates scrubbed) is the only guard, and the 2.4
  recall audit must have reported its hit rate before signing.
- **Design**: same 15 names, dates spaced as on the design pass (about 15 dates over the
  period), 1 seed, the chosen cell and the rules cell and the control on the same dates.
- **Statistic**: Sharpe(cell) - Sharpe(vol-target control), paired circular block bootstrap,
  two-sided p, one look. Also reported: Sharpe(cell) - Sharpe(rules), fallback share,
  fallback-by-regime test. No re-runs, no parameter changes, no second model.
- **Decision rule**: the cell is adopted as an opt-in desk mode only if the holdout difference
  is positive with p < 0.05 and the fallback share stays under 10%. Anything else is reported
  as a failed replication, and the default desk stays on rules.

## Minimum detectable effect

For two return streams with correlation rho over T years, the standard error of the annual
Sharpe difference is about sqrt(2(1 - rho) / T) (iid approximation, Sharpe near zero; it
depends on years, not on how many dates are sampled). With T = 4.5 years, alpha 0.05
two-sided and 80% power (z sum 2.80):

| correlation with control | SE of difference | MDE (annual Sharpe) |
|---:|---:|---:|
| 0.5 | 0.47 | 1.32 |
| 0.8 | 0.30 | 0.83 |
| 0.9 | 0.21 | 0.59 |

Plainly: the holdout can detect only a large improvement. A cell that adds 0.3 Sharpe would
pass the look less than one time in five. A null holdout result is therefore weak evidence
against a small effect, and the write-up must say so. The forward paper record remains the only
unseen data after this look.

## To fill at signing

- design-pass results table (`python scripts/llm_study.py --report --out results/p2/first_pass.jsonl`),
  with the admissible cap line;
- the chosen cell (or "none passed; holdout not run");
- the model tag and digest served (`model_served` in the run rows);
- the trial count and deflated Sharpe probability;
- the 2.4 recall-audit hit rate.
