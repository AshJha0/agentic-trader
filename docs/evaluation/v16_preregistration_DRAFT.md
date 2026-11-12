# v0.16 pre-registration (DRAFT): the one holdout look for the LLM study

**Status: draft, not signed, not executed.** Written 2026-11-08, before any LLM study cell had
run on any date. Amended 2026-11-12 after an outside review, when the first pass was partly run
and no `decisive_ta` or `postcutoff_ta` row existed; what had been seen by then is listed in
"Amendment of 2026-11-12" below, and the record of each change is in
[v16_prereg_amendment_2026-11-12.md](v16_prereg_amendment_2026-11-12.md). No holdout decision has
been made by any LLM cell.

This draft becomes binding only when the owner signs it: `python scripts/sign_prereg.py` renames
the file to `v16_preregistration.md`, removes "DRAFT" from the title and fills the signing block,
and the owner commits the result. Until that file exists the runner refuses to start a registered
cell (`study_design.prereg_gate`), and every run header then carries the signed file's SHA-256.
If no cell clears the design bar below, the holdout look is not run at all and this file says so.

## Amendment of 2026-11-12 (before any decisive row)

Plainly: an outside review found that the decisive statistic could be passed by a model that
adds nothing, that the leakage control let a memory effect through by default, and that the
holdout lock in the code read an audit this document calls void. All three are repaired here,
before the cells they govern have produced a single row.

What had been seen when this was written, and so cannot count as blind:

- the first pass on the design period: cells `rules` (300 of 300 decisions) and `local_analysts`
  (300 of 300) complete, `local_all` 27 of 300, `critic_on` not started; the interim report in
  `docs/results/v17/` (the model cell's 20-bar IC was below the rules cell's);
- the judge agreement on 30 hand-written cases, and one run of the v2 recall audit whose output
  was later lost and is being re-run.

What had not been seen: any `decisive_ta` or `postcutoff_ta` row (neither cell has been started,
smoke test included), and any LLM decision on the holdout.

What changed, each with its reason in the amendment record:

1. the primary metric of the decisive cell (residual IC in place of model-minus-rule);
2. ranking within asset class, in the decisive metric and in the first-pass IC;
3. design dates on NYSE sessions for the two new cells; the first pass keeps its dates and drops
   the two closed ones at scoring;
4. the leakage control, now a replication requirement;
5. the holdout look for LLM cells, now ending 2025-06-30;
6. the recall gate in code, now the v2 audit;
7. the planning MDE of the decisive cell (0.044, was 0.093);
8. no truncated grid: a registered cell is never run with `--limit`.

Nothing else moved: the model, the prompt, the names, the horizon, the futility rule, the
fallback cap and the design bar are as written on 2026-11-08 and 2026-11-09.

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

The first pass cannot accept or reject an edge. Its tables are labelled "descriptive" in
the report, including the 20-bar IC that an earlier report called "primary" (amended 2026-11-12:
that IC was added to the runner on 2026-11-09 without being named here; it is descriptive like
the rest, is computed within asset class, and neither it nor the Sharpe table decides anything).
Two of the 20 first-pass design dates, 2016-01-01 and 2017-11-23, are NYSE closures because the
grid was drawn from weekdays. The grid is not redrawn mid-run; both dates are dropped at scoring
for every name, FX included, and the report says so (18 dates scored). Its 19 usable periods (about 115 days apart)
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

Both: 15 core names (10 equities, 5 FX pairs), technical analyst only (one model call per
decision), anonymised prompt, rule signal from the same analyst on the same state, 5-trading-day
close-to-close forward return (scoring only), temperature 0, one seed. Dates are NYSE sessions:
one per week from the Monday anchor, and an anchor on a closure moves to the next session, so
every name is read on the same bar (amended 2026-11-12; the 313 and 70 counts are unchanged).
A registered cell is run in full or stopped by the futility rule; it is never run with `--limit`,
which would keep only the earliest dates. Runtime at 50-100 s per call: 65-130 CPU hours for
`decisive_ta` (`study_design.dry_run`).

The horizon is 5 trading days. The analyst prompt asks for a view over "the next 1-4 weeks", so
5 days is the short end of what the model is asked for; it is kept because weekly dates then do
not overlap. A null here says nothing about a 20-day effect.

**The statistic (amended 2026-11-12).** Plain idea: take out of the model's signal everything
that could have been predicted from the rule's signal, then ask whether what is left lines up
with the return. A model that only restates the rule has nothing left.

Formal statement (`study_design.incremental_ic`, key `primary`):

1. For each asset class c, fit the model signal on the rule signal over every usable row of the
   cell: up to 20 quantile bins of the rule signal, at least 50 rows per bin, a least-squares
   line inside each bin. No return enters the fit. The residual is e = model signal minus fit,
   and sd_c is its standard deviation over the class.
2. At each date t and class c with at least 5 usable names,
   IC(t, c) = cov over names of (e, rank of the forward return) / (sd_c x sd of those ranks).
3. IC(t) is the average of IC(t, c) weighted by the number of names; the statistic is the mean
   of IC(t) over dates with a Newey-West (lag 1) standard error over dates.

If sd_c is below 5 % of the standard deviation of the model signal in that class, the model is
a function of the rule there and the class scores exactly 0. Excluded and counted: rows whose
model call fell back, rows with no forward return, and rows whose last bar is older than the
decision date. A cell with more than 10 % fallbacks is inadmissible as above.

Worked example. The rule's IC on some stretch is -0.06 and the model answers half the rule's
signal every time. Under the first version of this document the statistic was Spearman(model
minus rule, return) = Spearman(-0.5 x rule, return) = +0.06, a "pass" for a model that adds
nothing. Under this version the fit is exact, the residual is zero and the score is 0. The
first version is still computed and printed as `legacy_model_minus_rule`; it decides nothing.

Checked by simulation before signing (313 dates, 10 + 5 names; test file
`tests/test_study_repair_round0.py`): scaled, flipped, clipped and rounded copies of a rule
with IC 0.30, and pure noise, pass at about the nominal 2.5 % or less; a model with real added
signal passes. A per-date rank residual was tried first and rejected the same day: a model that
rounds the rule passed in about two runs in three, because ranks discard the spacing between
names and the rounded copy keeps some of it. Evidence class: simulation and unit tests.

- **Decision rule (`decisive_ta`)**: the model adds information on the design dates if the
  95 % interval of the residual IC lies above zero, with fallback share at most 10 %.
- **Futility (decided 2026-11-09, unchanged)**: after 40 dates, at every 1,000 decisions, stop
  if residual IC + 1.2816 x SE < 0.03. No efficacy stop.
- **MDE (amended 2026-11-12)**: a common market move does not change ranks inside a date, so
  the null variance of IC(t) is about (10/15)^2 / 9 + (5/15)^2 / 4 = 0.077 (SD 0.278; a
  simulation gives the same). Over 313 dates SE is about 0.0157 and the MDE at 80 % power, 5 %
  two-sided, is about 0.044 IC. The earlier figure of 0.093 applied a design effect for pooled
  decisions that a per-date statistic does not have, and made a null look weaker than it is.
- **Replication (`postcutoff_ta`, amended 2026-11-12)**: the same statistic on dates after the
  model's training data (qwen2.5 was released in September 2024; the cell starts 2025-07-01).
  A pass on `decisive_ta` is adopted only if `postcutoff_ta` is admissible and the one-sided
  95 % lower bound of its residual IC, IC - 1.645 x SE, is above zero
  (`study_design.replication_verdict`). Anything else is reported as "not replicated" and the
  cell is not adopted; the write-up then says that memory and no effect cannot be told apart.
  With 70 dates the SE is about 0.033, so this test detects 0.083 at 80 % power: only a large
  effect can be confirmed. The first version put the burden the other way round (the effect
  counted as real unless the post-cutoff interval excluded it), which a 70-date cell would
  almost never do.
- **Data note (amended 2026-11-12)**: the post-cutoff window overlaps the holdout (to
  2026-06-30) and the reserve window (2026-07-01 to 2026-09-25). Running `postcutoff_ta` spends
  those dates for this LLM question; no rule choice may be made on them afterwards. Owner
  sign-off recorded on 2026-11-09: the cell is approved on these terms. Because the holdout look
  below asks the same question of the same model, it would otherwise read 2025-07-01 to
  2026-06-30 twice. The holdout look for any LLM cell therefore ends on 2025-06-30. The owner
  decided on 2026-11-12 that the post-cutoff dates are spent on this one question only, with the
  anonymised-against-named memorisation pair as its control.

Worked example: if `decisive_ta` gives residual IC 0.025 (SE 0.016), the 95 % interval is
[-0.006, 0.056]: not a pass. If it gives 0.05 (interval [0.019, 0.081]) and `postcutoff_ta`
gives 0.03 (SE 0.033, lower bound -0.024), the design pass is not replicated and the cell is
not adopted. If after 2,000 decisions the IC is -0.02 with SE 0.035, the upper bound
-0.02 + 0.045 = 0.025 is below 0.03 and the run stops for futility.

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
   `len(evaluation.TRIALS)` read from the code at the time of signing (not copied here; the count
   grows as cells are registered), and also at that count plus `evaluation.PRE_REGISTRY_TRIALS_ESTIMATE`
   and at the effective number of trials (`stats.effective_trials`), all three reported.

If more than one cell passes, the one with the larger lower bound in (3) goes forward; the
other is reported but not looked at on the holdout. If none passes, the study is closed as a
null on the design period and no holdout run is made.

## Precondition: the 2.4 recall audit must pass (added v0.17, R1.4)

**Superseded on 2026-11-12.** This section first prescribed the v0.16 audit
(`v16_local_study.py recall`, hit rate at most chance + 2 standard errors), and the code enforced
that rule, although the section above had already declared the v0.16 audit void: with a fixed
candidate order it measured option position, not recall. From this amendment there is one gate.

No holdout look of any kind is run until the v2 audit (`v16_local_study.py recall2`) has been
run on the model build that will make the holdout decisions and reports `recall_flagged: false`,
with at least 100 real items and a placebo arm. If the audit flags recall, the anonymisation is
not a guard against training-window memory, the holdout is not looked at, and the study closes
as "holdout not interpretable".

This is enforced in code, not only here: `evaluation.require_recall_pass(path)` raises
`HoldoutLocked` unless the JSON at `path` is a v2 result that passes `evaluation.recall2_verdict`;
a v0.16 result is refused as void. `evaluation.evaluate` calls it for any local-model run whose
periods overlap the holdout (default path `results/v17_local/recall2.json`, override with config
`recall_audit_path`), `scripts/llm_study.py --live` calls it for its own dates, and the design
runner calls `study_design.holdout_access`, which lets `postcutoff_ta` through on its recorded
basis (dates after the model's release cannot be recalled) and nothing else.
Evidence class: design rule (decided before any v2 result was used for a decision). A known
limit, not repaired here: the audit passes on absence of evidence, and its power at n = 100 has
not been stated; that is review item C11, planned for the next round.

## The holdout look

- **Period**: 2022-01-03 to 2025-06-30 (amended 2026-11-12; `evaluation.PERIODS["holdout"]`
  runs to 2026-06-30, and its last twelve months are read by `postcutoff_ta` instead, see the
  data note above). The rules desk has been reported on it (v0.8), so it is spent for rule
  choices; no LLM cell has ever been run on it, so it is unseen for this question. The model's
  training data covers most of these years; the anonymisation (prices rebased, names and dates
  scrubbed) is the only guard, and the v2 recall audit must have **passed** (precondition above)
  before the look.
- **Design**: same 15 names, dates spaced as on the design pass (about 12 dates over the
  period), drawn from NYSE sessions, 1 seed, the chosen cell and the rules cell and the control on the same dates.
- **Statistic**: Sharpe(cell) - Sharpe(vol-target control), paired circular block bootstrap,
  two-sided p, one look. Also reported: Sharpe(cell) - Sharpe(rules), fallback share,
  fallback-by-regime test. No re-runs, no parameter changes, no second model.
- **Decision rule**: the cell is adopted as an opt-in desk mode only if the holdout difference
  is positive with p < 0.05 and the fallback share stays under 10%. Anything else is reported
  as a failed replication, and the default desk stays on rules.

## Minimum detectable effect

For two return streams with correlation rho over T years, the standard error of the annual
Sharpe difference is about sqrt(2(1 - rho) / T) (iid approximation, Sharpe near zero; it
depends on years, not on how many dates are sampled). With T = 3.5 years (the period as
amended on 2026-11-12; it was 4.5), alpha 0.05 two-sided and 80% power (z sum 2.80):

| correlation with control | SE of difference | MDE (annual Sharpe) |
|---:|---:|---:|
| 0.5 | 0.53 | 1.50 |
| 0.8 | 0.34 | 0.95 |
| 0.9 | 0.24 | 0.67 |

Plainly: the holdout can detect only a large improvement. A cell that adds 0.3 Sharpe would
pass the look less than one time in five. A null holdout result is therefore weak evidence
against a small effect, and the write-up must say so. The forward paper record remains the only
unseen data after this look.

## Skipped units (added 2026-11-11, v0.19 lane B)

Plainly: sometimes the data provider has no prices for one name on one date, even after
retries. That unit never reaches the model, so it is neither a model answer nor a fallback.
It is skipped, and the skip has to be visible next to every count.

The rule. Since v0.19 the runners (`run_study`, `run_recall`, `run_recall2`, `run_calibration`)
retry a provider miss three times, then write a skipped row (`skipped`, `skip_reason`,
`skip_tries`) and leave the unit out of the analysis. A resume retries skipped units. For every
registered statistic built on these runners:

1. N is quoted with the skip count beside it, as "N = 285 (15 skipped)", and `--report` lists
   each skipped unit with its reason.
2. Skips are counted separately from fallbacks. They do not enter `MAX_FALLBACK_SHARE`.
3. A cell with more than 10 % of its units skipped at the end of the run is inadmissible, the
   same cap as fallbacks: above it, which names and dates are missing could drive the result.
4. Skips are rerun (a resume) before the design table is filled. Only skips that persist are
   reported.

Worked example: a first-pass cell has 15 names x 20 dates = 300 units. Yahoo has no data for
one name on 3 dates; after the resume 2 still miss. The table shows N = 298 (2 skipped),
0.7 % skipped, admissible on skips; its fallback share is computed on the 298.

## Signing block

Filled by `python scripts/sign_prereg.py` when the owner signs; empty in the draft.

- Signed by: (not signed)
- Signed on: (not signed)
- Model: `qwen2.5:7b-instruct`, Q4_K_M, digest (filled at signing from the first-pass run header)
- Runner code at signing: (git commit, filled at signing)
- Registered trials at signing, `len(evaluation.TRIALS)`: (filled at signing)
- Seen before signing: as listed in "Amendment of 2026-11-12"; no `decisive_ta` or
  `postcutoff_ta` row.

## To fill when the design pass is complete

- design-pass results table (`python scripts/llm_study.py --report --out results/p2/first_pass.jsonl`),
  with the admissible cap line;
- the chosen cell (or "none passed; holdout not run");
- the model tag and digest served (`model_served` in the run rows);
- the trial count and deflated Sharpe probability;
- the recall audit v2 result (MRR, permutation p, real minus placebo, position bias), not the
  void v0.16 hit rate;
- the model share of each first-pass cell by role (in `local_analysts` most analyst outputs
  came from rules, because the text analysts abstained), so each conclusion is scoped to the
  roles that ran;
- the run header ids (`<rows>.header.json`: git SHA, prompt hash, Ollama version, model
  digest) of every run quoted, and any `allowed_change` entries;
- the `decisive_ta` and `postcutoff_ta` results, or "not run";
- the skip count beside every N, and each persistent skipped unit with its reason.
