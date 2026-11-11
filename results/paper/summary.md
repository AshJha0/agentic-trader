# Forward paper-trading record: 2026-09-29 -> 2026-11-09 (31 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -0.47 | -1.19 | (interval after 60 sessions) |
| core15/B&H vol-target | -0.60 | -1.33 |  |
| core15/Buy&Hold | -1.33 | -1.34 |  |
| etf11/B&H vol-target | +1.10 | 0.98 |  |
| etf11/Buy&Hold | +1.25 | 1.14 |  |
| etf11/TSMOM(12-1) | +0.15 | -0.54 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.63 | -5.87 |  |
| fx15/Carry | +0.75 | 3.32 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.71 | 0.92 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 31.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 4 cell(s) of 2026-11-06, the session the previous run recorded, moved in this run (columns: core15/AgenticTrader, etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
