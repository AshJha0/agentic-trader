# Forward paper-trading record

Published 2026-11-07. Written by `scripts/paper_trade_v09.py`, run daily at 07:30 UK time on the owner's machine. Paper only: no orders, no capital.

| File | What it holds |
|---|---|
| `ledger.csv` | Daily returns of each frozen book (rules v0.8.0, frozen 2026-09-29), fully costed as in the walk-forward. Append-only: a session is added once and never rewritten. |
| `revisions.csv` | Every value where a later recomputation differs from the ledger: run time, as-of date, session, column, old and new value. |
| `runs.jsonl` | One line per run (the local Python path in `executable` is masked for publication): run time, as-of date, sessions appended, data source and the largest revision per column. |
| `ledger_recomputed.csv` | The latest full recomputation, for comparison with the ledger. |
| `summary.md` | Cumulative return and Sharpe per book; intervals start at 60 sessions. |

**Data vintage.** Prices come from Yahoo Finance and are revised after the fact, so a recomputation can differ from the ledger. By 2026-11-07 `revisions.csv` held 1,232 logged differences across all runs, 6 of them a session that went missing in a recomputation. The largest numeric revision is 0.08 percentage points of one day's return. The latest run differed from the ledger in 141 cells and one dropped session.

**Gap.** The job failed from about 2026-10-31 to 2026-11-06 because its Python environment pointed at a missing install. It was rebuilt on 2026-11-07, and that run appended 10 sessions (2026-10-26 to 2026-11-06) recomputed from data available on 2026-11-07, not recorded on their own days (`runs.jsonl`, `appended: 10`).

**Not recorded yet.** Daily exposure and cost per book are not in the ledger; costs follow the frozen configuration. Adding them is a later change.

**Reading it.** No decision before session 3600 (docs/evaluation/v09_preregistration.md). 30 sessions say nothing about edge.
