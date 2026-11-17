# Forward paper-trading record: 2026-09-29 -> 2026-11-13 (35 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -0.24 | -0.91 | (interval after 60 sessions) |
| core15/B&H vol-target | -0.55 | -1.27 |  |
| core15/Buy&Hold | -1.51 | -1.42 |  |
| etf11/B&H vol-target | -0.19 | -0.90 |  |
| etf11/Buy&Hold | -0.23 | -0.87 |  |
| etf11/TSMOM(12-1) | -0.26 | -1.25 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.47 | -4.56 |  |
| fx15/Carry | +0.93 | 4.17 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.93 | 1.33 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 35.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 9 cell(s) of 2026-11-12, the session the previous run recorded, moved in this run (columns: core15/AgenticTrader, core15/B&H vol-target, core15/Buy&Hold, etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1), fx15/B&H vol-target, fx15/Carry, fx15/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
