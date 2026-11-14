# Provenance: exec-lag sensitivity (final run)

- Code: main at `3f80a69` (after PR #40). Earlier outputs in this folder came from pre-#40 code and are withdrawn.
- Command: `python scripts/v17_exec_lag.py --provider yahoo --out docs/results/v17_exec_lag_final --resume`, then the outputs were moved here.
- Data: Yahoo daily bars, design period 2016-01-04 to 2021-12-31, core universe, rebalance every 5 days, rules only (no LLM).
- Run dates: units 1-85 of 93 ran on 13 Nov 2026. The run stopped on a transient Yahoo USDCAD fetch failure, and the last 8 units ran later that day after a `--resume` from the checkpoint.
- Files: `trials_lag_yahoo.md` and `trials_lag_yahoo.json` (results), `meta_yahoo.json` (settings and code hash). The resume checkpoint is not published.
