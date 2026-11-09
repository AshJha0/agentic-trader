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

## The first pass is descriptive (added 2026-11-09, review N3)

The first pass cannot accept or reject an edge. Its 19 usable periods (about 115 days apart)
give a minimum detectable effect of about 0.89 annual Sharpe on the portfolio metric
(correlation 0.7 with the control, 6 years, 80 % power, 5 % two-sided) and about 0.36 on
decision-level IC (effective n about 60). Realistic effects are 0.02 to 0.05 IC
(`python -m agentic_trader.study_design --dry-run`, key `first_pass`; evidence class:
design arithmetic). It is therefore reported as descriptive only: contract and fallback
rates, agreement with the rules desk, fallback bias. The design bar below still applies to it
mechanically, but a pass on the first pass is not evidence of edge without the decisive cell.

## The decisive cell and the leakage control (added 2026-11-09, review N3 and N9)

Plain idea: ask one narrow question with enough decisions to answer it. Does the model, given
the same anonymised technical-analyst input as the rule, add information about the next five
trading days that the rule does not have?

| cell | dates | decisions | registered trial (`evaluation.TRIALS`, v0.17) |
|---|---|---:|---|
| `decisive_ta` | weekly, 2016-01-04 to 2021-12-31 (313) | 4,695 | `P2 decisive_ta: ...` |
| `postcutoff_ta` | weekly, 2025-07-01 to 2026-10-30 (70) | about 1,050 | `P2 postcutoff_ta: ...` |

Both: 15 core names, technical analyst only (one model call per decision), anonymised prompt,
rule signal from the same analyst on the same state, 5-trading-day close-to-close forward
return (scoring only). Runtime at 50-100 s per call: 65-130 CPU hours for `decisive_ta`
(`study_design.dry_run`).

Formal statement. IC_t = Spearman over names of (model signal - rule signal) against the
forward 5-day return at date t; the statistic is mean_t IC_t with a Newey-West (lag 1)
standard error over dates (clustered by date by construction; weekly dates and a 5-day
horizon do not overlap). Rows whose model call fell back are excluded and counted; a cell
with more than 10 % fallbacks is inadmissible as above.

- **Decision rule (`decisive_ta`)**: the model adds information if the 95 % interval of the
  incremental IC lies above zero, with fallback share at most 10 %.
- **Futility (decided now)**: after 40 dates, at every 1,000 decisions, stop if
  IC + 1.2816 x SE < 0.03. No efficacy stop.
- **MDE**: with cross-sectional correlation 0.3 the design effect is 5.2, n_eff about 903,
  SE about 0.033, MDE about 0.093 IC at 80 % power. A positive result below 0.09 is
  unlikely to be detected; a null is weak evidence against effects near 0.05.
- **Leakage control (`postcutoff_ta`)**: the same statistic on dates after the model's
  training data. If `decisive_ta` passes and `postcutoff_ta` has an incremental IC whose 95 %
  interval excludes the `decisive_ta` point estimate from above (the effect shrinks), the
  in-sample effect is attributed to memory and the cell is not adopted.
- **Data note**: the post-cutoff window overlaps the holdout (to 2026-06-30) and the reserve
  window (2026-07-01 to 2026-09-25). Running `postcutoff_ta` spends those dates for this LLM
  question; no rule choice may be made on them afterwards. This needs the owner's sign-off at
  signing.

Worked example: if `decisive_ta` gives IC 0.06 (SE 0.033), the 95 % interval is
[-0.005, 0.125]: not a pass. If after 2,000 decisions the IC is -0.02 with SE 0.035, the upper
bound -0.02 + 0.045 = 0.025 is below 0.03 and the run stops for futility.

## Recall audit gate (added 2026-11-09, review N1)

The v0.16 recall audit (fixed candidate order, AAPL first, name-major items) measured option
position, not recall; its result is void. The gate for any holdout look is the v2 audit
(`v16_local_study.py recall2`, `agentic_trader.recall_audit`): shuffled candidates, ranked
top-3 MRR against a label-permutation null, a synthetic placebo arm, a position-bias
diagnostic and a real vs date-shifted forward-return test. The holdout look is allowed only
if the v2 audit does not flag recall (`recall_flagged: false`).

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
- the recall audit v2 result (MRR, permutation p, real minus placebo, position bias), not the
  void v0.16 hit rate;
- the run header ids (`<rows>.header.json`: git SHA, prompt hash, Ollama version, model
  digest) of every run quoted, and any `allowed_change` entries;
- the `decisive_ta` and `postcutoff_ta` results, or "not run".
