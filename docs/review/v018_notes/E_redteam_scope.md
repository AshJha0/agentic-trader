# Lane E: scoped red-team v2 design

The full `redteam_v2` grid (150 snippets x 5 states x 4 analysts x 2 modes, three arms, desk
end to end) is 7.5-15 CPU-days on this machine (estimate from v0.17, not measured). v0.18
splits it into two passes, each with its own `--out`.

## Design

| Pass | Flags | Units |
|---|---|---|
| 1. analyst only | `--modes json --analysts news,sentiment --no-end-to-end` | 150 x 5 x 2 = 1,500 |
| 2. end to end | `--modes json --analysts news,sentiment --per-category 2` (seed 2026) | 5 x 2 x 5 x 2 = 100 |

The corpus has 5 categories: encoded 40, fence_escape 32, instruction 32, multilingual 26,
role_play 20. N = 2 per category gives 10 snippets and exactly 100 units (N = 1 gives 50,
N = 3 gives 150). With seed 2026 the selected ids are RT074, RT084, RT121, RT127, RT004,
RT014, RT093, RT105, RT034, RT048 (sorted by category, then id).

## What changed in `agentic_trader/agentic/redteam_v2.py`

- `select_per_category(corpus, N, seed)`: ids sorted within each category, then
  `random.Random(f"{seed}|{category}").sample`. The same snippets go to every state x analyst
  cell, so the design stays balanced.
- `plan_units` order is now snippet-major, round-robin over the (mode, state, analyst) cells.
  A killed run leaves a prefix where cell counts differ by at most one. Unit keys
  (`mode|symbol|as_of|analyst|id`) are unchanged, so v0.17 checkpoints still resume, and
  without the flag the unit set is identical to before; only the order differs.
- `run(..., design=...)` writes `<out>.design.json` (per_category, seed, selected ids,
  end_to_end, threshold). A rerun into the same `--out` with any different value is refused,
  as is a subset run into a file that already has rows but no header. The summary carries
  the same header under `design`.
- `summary["report"]` (`compliance_report`): directed compliance with Wilson 95 % CIs, total,
  per mode and per category; for end-to-end rows, the governance catch rate given analyst
  compliance (complied but final weight did not move the demanded way) and the critic-acted
  rate on the same base. Units share snippets across cells, so the intervals understate the
  real uncertainty; say so when quoting them.

## Commands (not run)

```
set PYTHONPATH=.
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe -m agentic_trader.agentic.redteam_v2 --model qwen2.5:7b-instruct --modes json --analysts news,sentiment --no-end-to-end --out results\redteam_v2\analyst.jsonl > results\redteam_v2\analyst.log 2>&1
C:\Work\Claude\AgenticTrader\.venv\Scripts\python.exe -m agentic_trader.agentic.redteam_v2 --model qwen2.5:7b-instruct --modes json --analysts news,sentiment --per-category 2 --seed 2026 --out results\redteam_v2\e2e.jsonl > results\redteam_v2\e2e.log 2>&1
```

Add `--csv-dir` when a bar cache exists; otherwise the rows say `synthetic`.

## Evidence

Offline tests only (`tests/test_v18_redteam_scope.py`, fake `run_unit`, no Ollama): balance,
determinism, prefix balance, key stability, resume, design guard, Wilson values against
hand-computed references, conditional catch rate.
