# Forward paper-trading record: 2026-09-29 -> 2026-11-12 (34 sessions, frozen 2026-09-29, rules v0.8.0)

| book / stream | cumulative return % | Sharpe (excess, 260/yr) | vs control: Sharpe difference [95% CI] p |
|:--|--:|--:|:--|
| core15/AgenticTrader | -0.39 | -1.09 | (interval after 60 sessions) |
| core15/B&H vol-target | -0.58 | -1.31 |  |
| core15/Buy&Hold | -1.58 | -1.48 |  |
| etf11/B&H vol-target | -0.02 | -0.67 |  |
| etf11/Buy&Hold | -0.03 | -0.62 |  |
| etf11/TSMOM(12-1) | -0.20 | -1.13 | (interval after 60 sessions) |
| fx15/B&H vol-target | -0.39 | -4.22 |  |
| fx15/Carry | +0.90 | 4.11 | (interval after 60 sessions) |
| fx15/TSMOM(12-1) | +0.95 | 1.50 | (interval after 60 sessions) |

No decision before session 3600 (pre-registered, docs/evaluation/v09_preregistration.md, amendment of 2026-09-29): intervals printed before it are descriptive. Sessions so far: 34.

The ledger is append-only: sessions are added from each run's recomputation and never rewritten; differences between a recomputation and the ledger are logged in revisions.csv and runs.jsonl.

**Same-day revision:** 6 cell(s) of 2026-11-11, the session the previous run recorded, moved in this run (columns: core15/AgenticTrader, core15/B&H vol-target, core15/Buy&Hold, etf11/B&H vol-target, etf11/Buy&Hold, etf11/TSMOM(12-1)). The bar was probably not final when it was fetched; the ledger keeps the first value, see revisions.csv.
