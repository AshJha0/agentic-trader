# First-pass LLM study rows, re-scored with the corrected scoring (2026-11-14)

**What this is.** The first pass of the v16 study was stopped on 2026-11-12
([status](../../evaluation/v16_prereg_status_2026-11-12.md)). The interim table
([interim report](llm_study_interim_report.md)) was produced before the scoring was corrected.
This page re-scores the same stored rows with the corrected scoring. It is descriptive. The
pre-registration calls the first pass descriptive, so nothing here tests what the model adds,
and no cell was put to the design bar.

**What changed in the scoring.** Information coefficients are now ranked within asset class.
The two design dates that are NYSE closures (2016-01-01, 2017-11-23) are dropped for every
name. The report re-fetches each symbol once and checks stored closes against one common
per-symbol adjustment factor, so entry and forward closes come from a single data vintage.

**How to reproduce.** Report only; no model is called and nothing is spent:

```
python scripts/llm_study.py --report --data yahoo \
  --out C:\Work\Claude\AgenticTrader-study-backup\first_pass_stopped_2026-11-12_2345.jsonl
```

`--data yahoo` is required. The default synthetic provider scores 0 rows from this file. The
row file stays outside the repo (it holds model replies); its path is given so the run can be
repeated on the maintainer's machine. Run on round3-part3 at 1dd4ffb, 2026-11-14.

## Per-decision information (20-bar forward return, IC within asset class)

95 % intervals are date-bootstrap intervals.

| cell | dates | scored | active | IC [95% CI] | hit rate [95% CI] | IC - rules [95% CI] |
|---|---:|---:|---:|---|---|---|
| rules | 18 | 270 | 264 | -0.056 [-0.212, +0.092] | 54.9% [44.7%, 64.9%] | n/a |
| local_analysts | 18 | 270 | 217 | -0.087 [-0.216, +0.046] | 55.8% [45.3%, 65.7%] | -0.030 [-0.140, +0.089] |
| local_all | 3 | 44 | 37 | -0.135 [-0.259, +0.083] | 62.2% [53.8%, 71.4%] | +0.476 [+0.240, +0.830] |

## How to read it

- **Rules and local_analysts.** Both ICs are slightly negative and every interval includes 0.
  The IC difference, -0.030 [-0.140, +0.089], also includes 0. On these 18 dates the model
  analysts neither add nor remove ranking information that can be measured. Only 404 of the
  1,200 analyst outputs in that cell came from the model; the rest fell back to rules by
  design, so the cell is mostly rules.
- **local_all.** It covers 3 dates (59 of 300 decisions). Its IC difference, +0.476
  [+0.240, +0.830], is computed on 3 dates against the full rules cell and cannot be read as
  an effect. A 3-date bootstrap does not support an interval. It is shown only so that the
  table is complete.
- **Secondary Sharpe** (weights held to the next design date; not a decision metric):
  rules +2.28 vs control +1.93, diff +0.35 [+0.01, +0.90], p 0.095. local_analysts +1.77,
  diff -0.16 [-0.85, +0.30], p 0.54. The control is vol-target (10 % target, 63-day vol).
- **Data hygiene.** 0 of 659 rows are legacy, 0 units were skipped for provider misses, and
  no cell exceeds the 10 % fallback admissibility limit.

## Follow-up

Rows and the report header do not yet record the data provider, which is why `--data` has to
be given by hand. Recording the provider is a follow-up for the next registered study (Round 4).
