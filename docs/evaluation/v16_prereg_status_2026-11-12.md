# Status of the v0.16 pre-registered study: stopped, decisive test not run (2026-11-12)

This page records where the study stands. It does not change the
[signed pre-registration](v16_preregistration.md), which stays as signed and stays in force
for any later run.

## Plainly

The owner decided on 2026-11-12 not to run the rest of the study for now. The decisive test
has not been run, so the project has **no pre-registered result** on whether a local language
model adds information beyond the rules. It has a signed design and a partly run, descriptive
first pass.

## What exists

| cell | registered role | state when stopped |
|---|---|---|
| `rules` (first pass) | control | 300 of 300 decisions |
| `local_analysts` (first pass) | descriptive | 300 of 300 decisions |
| `local_all` (first pass) | descriptive | 59 of 300 decisions |
| `critic_on` (first pass) | descriptive | not started |
| `decisive_ta` | the decisive test | **not started; no row exists** |
| `postcutoff_ta` | its replication | **not started; no row exists** |
| Sharpe holdout look | one look, only if a cell clears the design bar | **not run; no LLM decision exists on the holdout** |
| recall audit v2, calibration, eval, judge (re-runs) | supporting | not re-run after their outputs were lost |
| red-team two-pass | separate | not run |

Evidence class: counts read from the rows file when the run was stopped (659 parseable rows;
SHA-256 of the file begins `98387cad1ad814be`). The rows are kept outside the repository.

Two facts for the record. The 59 `local_all` rows include 32 written on the evening of
2026-11-12, after the amendment was drafted and while the amended code was being merged; they
are first-pass rows on the earlier, pinned code, and the first pass decides nothing. And every
first-pass row was produced before the critic and weight-bound fixes of the same day, so the
model cells describe the desk as it was.

## Why it was stopped

- **Cost.** The remaining queue was about 227 hours of model time at about 59 seconds a call,
  on the owner's only machine: about 45 hours for the rest of `local_all`, 52 for `critic_on`,
  77 for `decisive_ta`, 17 for `postcutoff_ta`, and the rest for the supporting runs.
- **Two of the queued cells had lost their purpose.** `critic_on` would have measured a critic
  rule that was replaced on 2026-11-12, and `local_all` a desk whose model weights are now
  bounded.
- **Nothing had been seen that bears on the decisive test.** The decision was not taken in
  response to a decisive result, because there is none.

## What this means for claims

- The project may say that the test is designed, amended after review and signed, and that it
  has not been run. It may not say or imply a pre-registered finding about what the model adds.
- The interim first-pass table (`docs/results/v17/llm_study_interim_report.md`) is descriptive,
  covers two complete cells, predates the scoring correction and has not been re-scored. Its
  model cell is mostly rules: 404 of 1,200 analyst outputs came from the model.
- The Sharpe holdout look was not run. No cell was put to the design bar, because the first
  pass was not completed.

## If the study is run later

The signed document applies unchanged: the residual IC, NYSE-session dates, the futility rule,
replication after the model's release, and the runner's refusal to start without the signed
file. A later run should start with `decisive_ta` (its first futility look comes after 1,000
decisions, about 16 hours), state in its header that it follows this stop, and treat the first
pass as closed at the counts above unless a new note says otherwise. Dropping or reordering
cells relative to the signed document needs a dated note signed by the owner before any
decisive row exists.

## Self-check

- Is there any number in the repository that a reader could mistake for the decisive result?
  (The interim IC difference of -0.046 is the likeliest; it is labelled descriptive wherever it
  appears.)
- What would have to be true for "the model adds nothing" to be a finding and not an
  expectation? (The decisive cell run to completion or to its futility stop.)
