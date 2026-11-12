# Amendment record for the v0.16 pre-registration, 2026-11-12

This page records what was changed in
[the pre-registration](v16_preregistration.md) on 2026-11-12, why, and what had already
been seen. It exists so that a reader can check the amendment was made before the cells it
governs produced any data, and can see exactly what moved.

## Why an amendment was needed

An outside review of the repository (2026-11-12, findings C4, C5, C6, B2, B3, B4, B6, B7, B10)
found that the study could not yet support the word "pre-registered":

- the document was an unsigned draft while interim results were already committed;
- the statistic that decides the main cell could be passed by a model that adds nothing;
- the leakage control declared an effect real unless a small sample proved otherwise;
- the holdout lock in the code read an audit the document itself calls void.

## What had been seen, and what had not

Seen (so nothing below can be called blind to it):

| item | state on 2026-11-12 |
|---|---|
| first pass, cell `rules` | 300 of 300 decisions |
| first pass, cell `local_analysts` | 300 of 300 decisions; interim report in `docs/results/v17/` |
| first pass, cell `local_all` | 27 of 300 decisions |
| first pass, cell `critic_on` | not started |
| judge agreement | 30 hand-written cases |
| recall audit v2 | run once; output lost in a workspace cleanup; queued to re-run |

Not seen: any row of `decisive_ta` or `postcutoff_ta`. Neither cell had been started, and the
smoke test of the design runner had not been run. No LLM decision exists on the holdout.

Evidence class for this table: file counts read from the run folder on 2026-11-12 after the
machine restarted (the rows file had 627 parseable rows: 300, 300 and 27).

## The changes

| # | item | before | after | why |
|---|---|---|---|---|
| 1 | primary metric, `decisive_ta` and `postcutoff_ta` | Spearman over names of (model signal minus rule signal) against the 5-day return | residual IC: the model signal net of a pooled fit on the rule signal, correlated with return ranks inside each asset class | C4. Model = 0.5 x rule next to a rule with IC -0.06 scored +0.06. A copy of the rule now scores 0. |
| 2 | cross-section | 10 equities and 5 FX pairs ranked together | ranked inside each asset class, classes weighted by names | C5. A model that is more bullish on equities than on FX scored as if it selected names. |
| 3 | design dates of the two new cells | one per 7 days from 2016-01-04, weekdays | the same anchors moved to the next NYSE session when closed | C6. About 28 of 313 anchors were Monday closures: equities read on Friday's bar, FX on Monday's. |
| 4 | first-pass dates | 20 weekdays, two of them closures | grid unchanged; the two closed dates dropped at scoring for every name | C6, and owner decision D1: the cells already run are kept, not restarted. |
| 5 | leakage control | effect is "memory" only if the post-cutoff interval excludes the design estimate | a design pass is adopted only if the post-cutoff one-sided 95 % lower bound is above zero | B2. With 70 dates the old rule would almost never call anything memory. |
| 6 | holdout look for LLM cells | 2022-01-03 to 2026-06-30 | 2022-01-03 to 2025-06-30 | B6. `postcutoff_ta` reads 2025-07 to 2026-06 for the same question, so the "one look" would have been a second look at those months. |
| 7 | recall gate in code | the v0.16 audit result | the v2 audit, `recall_flagged: false`, at least 100 items, placebo arm present | B3. The enforced gate was the one declared void. |
| 8 | planning MDE, `decisive_ta` | 0.093 IC | 0.044 IC | B10. The design effect for pooled decisions does not apply to a mean of per-date rank statistics. |
| 9 | truncated runs | `--limit` accepted | refused for a registered cell | B10. It keeps the earliest dates only. |
| 10 | first-pass 20-bar IC | called "primary" in the report | called "descriptive", computed within asset class | B7. It was added to the runner without being named in the document. |
| 11 | signature | none | the runner refuses a registered cell until the owner signs | B4. |

Not changed: the model and its build, the prompt, the 15 names, the 5-day horizon, the futility
rule, the 10 % fallback cap, the skip rule, and the design bar for the Sharpe look.

## A statistic that was tried and rejected the same day

The first repair of item 1 was a per-date rank residual: regress the ranks of the model signal
on the ranks of the rule signal inside each date and correlate the residual with the return
ranks. In simulation (313 dates, a rule with IC 0.30) a model that only rounds the rule passed
in about two runs in three. Ranks discard the spacing between names; a rounded copy keeps some
of it, and that spacing carries information about returns that the rule's ranks no longer hold.
The pooled fit on the rule's values (item 1 as adopted) removes any function of the rule,
spacing included. This is recorded because a statistic chosen after trying another is itself a
choice a reader should know about. It was made on simulated data only; no study row was scored
with either version before the choice.

## What happened next

The study was stopped later the same day and the decisive test was not run; see
[the status page](v16_prereg_status_2026-11-12.md). The section below records the plan as it
stood when the amendment was written.

## What happens to the study that is running

Owner decision D1 (2026-11-12): no restart. The 627 first-pass rows are kept and the remaining
first-pass cells finish on the same grid with the same code. Only the scoring changes, and the
first pass decides nothing in any case. `decisive_ta` and `postcutoff_ta` start only after the
signature, on the amended code and dates.

## How the owner signs

1. Read the amended document and this page. If you disagree with a change, edit the draft
   first; nothing is binding yet.
2. Make sure the first-pass run header is where the script looks
   (`results/v17_local/first_pass.jsonl.header.json`), or have the model digest ready
   (`ollama list`).
3. Run `python scripts/sign_prereg.py --signer "Your Name"` in a clean checkout of `main`
   after this amendment is merged.
4. Read the diff, then `git add -A` and `git commit -m "Sign the v0.16 pre-registration"`.
   If you sign commits with a key, add `-S`.
5. Push through a pull request like any other change. The signing commit must be on `main`
   before the first `decisive_ta` row is written; the run header of that cell records the
   SHA-256 of the signed file.

## Self-check

- Could the amended statistic still be passed by a model that adds nothing? Name one such
  model that the tests do not cover, and run it through `study_design.incremental_ic`.
- Which of the eleven changes could have been influenced by the interim result, and in which
  direction would each move the chance of a pass? (Items 1, 2 and 5 all make a pass harder.)
- What can the study still not tell you after these changes? (Anything about a 20-day horizon,
  about text-reading analysts, and about any model other than this one.)
