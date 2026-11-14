> **Read this first (added 2026-11-12).** This table is descriptive, not the pre-registered test. The study was stopped the same day; the decisive test was not run ([status](../../evaluation/v16_prereg_status_2026-11-12.md)). The word "Primary" below is the runner's label at the time and was wrong: the pre-registration calls the first pass descriptive. The scoring has since been corrected (ranking within asset class; the two design dates that are NYSE closures dropped for every name) and this table has not been re-scored here; the re-scored version is [llm_study_rescore_2026-11-14.md](llm_study_rescore_2026-11-14.md). The 20 left-out decisions are the ten equities on those two closed dates, not decisions "without 20 forward bars". In the `local_analysts` cell 404 of 1,200 analyst outputs came from the model.

Primary (per decision, 20-bar forward return): IC and hit rate with 95% date-bootstrap intervals

| cell | dates | scored | active | IC [95% CI] | hit rate [95% CI] | IC - rules [95% CI] | Sharpe at 20d (secondary) |
|---|---:|---:|---:|---|---|---|---:|
| rules | 20 | 280 | 274 | +0.005 [-0.133, +0.146] | 55.1% [45.2%, 65.1%] | n/a | +0.54 |
| local_analysts | 20 | 280 | 227 | -0.042 [-0.173, +0.101] | 54.6% [43.8%, 64.8%] | -0.046 [-0.185, +0.067] | +0.25 |

Left out (20): AAPL 2016-01-01: fewer than 20 bars after the decision; AAPL 2017-11-23: fewer than 20 bars after the decision; AMZN 2016-01-01: fewer than 20 bars after the decision; AMZN 2017-11-23: fewer than 20 bars after the decision; GOOGL 2016-01-01: fewer than 20 bars after the decision; GOOGL 2017-11-23: fewer than 20 bars after the decision; JNJ 2016-01-01: fewer than 20 bars after the decision; JNJ 2017-11-23: fewer than 20 bars after the decision; JPM 2016-01-01: fewer than 20 bars after the decision; JPM 2017-11-23: fewer than 20 bars after the decision ...

Secondary (each weight held to the next design date):

| cell | decisions | Sharpe | control | diff [95% CI] | p | calls/dec | rejected | fallback | admissible | dispersion | $/decision (Claude list) |
|---|---:|---:|---:|---|---:|---:|---:|---:|---|---:|---:|
| rules | 300 | +2.28 | +1.93 | +0.35 [+0.01, +0.90] | 0.095 | 0.0 | 0.0% | 0.0% | yes | nan | 0.0000 |
| local_analysts | 300 | +1.77 | +1.93 | -0.16 [-0.85, +0.30] | 0.539 | 1.3 | 0.0% | 0.0% | yes | nan | 0.0003 |

Control: vol-target (10% target, 63-day vol).
Admissible fallback share per cell: at most 10% of model calls fell back to rules or failed the contract; a cell above it is marked NOT admissible and its Sharpe is not read.

Agent sources:
- rules: analyst=rules 1200, debate=rules 300, pm=rules 300, risk=rules 900, trader=rules 300
- local_analysts: analyst=llm 404, analyst=rules 796, debate=rules 300, pm=rules 300, risk=rules 900, trader=rules 300

Fallback/refusal by regime and date (2.5):
| cell | by | groups | worst rate | chi2 | p |
|---|---|---:|---:|---:|---:|
| local_analysts | regime | 2 | 0.0% | 0.00 | 1.000 |
| local_analysts | as_of | 20 | 0.0% | 0.00 | 1.000 |

Admissible fallback share per cell: at most 10% of model calls fell back to rules or failed the contract; a cell above it is marked NOT admissible and its Sharpe is not read.

Row vintage (N6): 0 of 600 rows legacy. Rows without horizon_days / vintage_hash predate v0.17 N6. They are not spliced with forward closes from a later fetch: the report re-fetches each name once, recomputes both the entry close and the forward close from that single vintage (ignoring the stored close), and takes the horizon from the stored trader reply for model cells or recomputes it with the rules for rule cells. Such rows are labelled 'legacy (single re-fetched vintage)' in every table.
