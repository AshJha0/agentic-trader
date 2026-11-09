# Forward paper-trading record: 2026-09-29 -> 2026-11-06 (30 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -1.11 | -2.16 | (interval after 60 sessions) |
| core15/B&H vol-target | -1.09 | -2.04 |  |
| core15/Buy&Hold | -2.32 | -2.24 |  |
| etf11/B&H vol-target | +0.61 | 0.28 |  |
| etf11/Buy&Hold | +0.61 | 0.27 |  |
| etf11/TSMOM(12-1) | -0.33 | -1.42 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.56 | -5.51 |  |
| fx15/Carry | +0.69 | 2.89 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.63 | 0.71 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 30.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 4 cell(s) of 2026-11-06, the session the previous run recorded, moved in this run (columns: core15/AgenticTrader, etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
