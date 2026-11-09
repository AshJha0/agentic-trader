# Paper record engine freeze

## The idea

The forward paper record (`scripts/paper_trade_v09.py`) recomputes the frozen v0.9 books
every day from the freeze session. If the code or config that computes them changes, the
ledger quietly starts mixing two engines. Before v0.17 nothing stopped that: the workflow
checks out `main` and runs whatever is there (review N1).

Now the engine is pinned by a hash. The run refuses when the engine differs, and a
deliberate change is a recorded re-freeze with a new vintage id.

## The mechanism

`docs/evaluation/paper_freeze.json` holds:

- `engine_files`: globs of the modules that compute the books (backtest, config, algo,
  portfolio, graph, validate, instruments, `quant/*.py`, `agents/*.py`);
- `config_keys`: the config blocks that move numbers (risk, costs, rules, combination and
  so on; not paths, LLM settings or the data provider);
- `engine_hash`: SHA-256 over those files (CRLF read as LF), those config values, and
  `repr(BOOKS)` (`scripts/paper_ops.py:engine_fingerprint`);
- `vintage_id`, `frozen_on`, `reason`, and `history` (every earlier vintage).

Each run computes the hash first. A mismatch exits non-zero before any data is read
("engine changed since freeze vintage ..."), so the workflow fails and the report job opens
an issue. Each ledger row gets its vintage in `ledger_vintage.csv` (date, vintage_id),
appended with the row, and `runs.jsonl` records `vintage_id` per run. (Evidence: code and
`tests/test_v17_desk_ops.py::test_a_changed_engine_is_refused_and_a_refreeze_starts_a_new_vintage`.)

## Re-freezing on purpose

    .venv\Scripts\python.exe scripts\paper_trade_v09.py --refreeze v09-engine-2 --reason "L2 cost-model fix, v0.17"

This moves the old vintage to `history`, records the new hash, id, date and reason, and
exits without recording a session. The id must be new and the reason non-empty. Commit
`paper_freeze.json` in the same PR as the engine change, and name the vintage in the
CHANGELOG. Rows recorded before the change keep the old vintage id; the ledger is never
rewritten. A comparison across vintages must say so.

Worked example: a PR changes `agentic_trader/backtest.py`. Its CI is fine, but the next
scheduled paper run would fail with "engine changed since freeze vintage v09-engine-1". The
PR author runs the command above, commits the updated JSON, and from that day on
`ledger_vintage.csv` shows `v09-engine-2`.

## Limits

- The hash covers the listed files only. A change in another module the engine imports
  (for example `data/yahoo.py`, or numpy/pandas versions) is not caught; installed versions
  are covered separately by the hashed lock files and `runs.jsonl` provenance.
- An environment override (a `.env` entry that changes a hashed config block) also changes
  the hash, and the run refuses. That is intended.
