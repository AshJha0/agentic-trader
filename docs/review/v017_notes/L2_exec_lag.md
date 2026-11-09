# L2: execution lag and next-open fills (R1.1, review Q1 / A1 / B2)

## What changed

**The plain idea.** Until now every backtest decided on the close of bar t and filled at that
same close. Nobody can trade at a close they have not seen yet, so the engine was quietly
granting a small amount of look-ahead. Two settings now make the timing explicit:

- `exec_lag = k`: the target decided at bar t is executed at bar t+k.
- `fill_next_open = True`: the executed target fills at open[t+1]. The position that was held
  coming into the bar earns the overnight move close[t] to open[t+1].

**Formal.** Both live on `BacktestConfig` (numpy dataclass in `agentic_trader/quant/pycore.py`
and the C++ struct in `cpp/include/at/backtest.hpp`, exposed through `cpp/bindings/module.cpp`).
The quant dispatcher already copies every dataclass field onto the C++ config, so the two
backends get the same API. In the engine loop, bar t reads `j = t - k`. The weight, the
rebalance flag and the stop/take levels come from bar j: they are decision-tied. Carry, impact
and cash rate come from bar t: they are market data. For j < 0 nothing has been decided yet, so
the book is flat. With next-open fills, a bar grows as `(1 + prev*(o/p - 1)) * (1 - k_in) *
(1 + g)`, where g is measured from the open. The trade is booked at bar t+1 at the open price.
A keep holds the units and so makes no trade at the open. Next-open fills need `open`, and
they raise an error when stop/take levels are also given: the two leg models have not been
reconciled.

**Worked example** (from `test_next_open_hand_example`). Closes are 100, 110, 121 and opens are
100, 105, 120, with a full long decided at bar 0 and zero cost. The fill is at 105 and equity
goes 1, 110/105, 121/105. A same-close fill would have earned 121/100 instead.

**Config.** `config["backtest"]["exec_lag"]` (int, default 0) and `["fill"]` (`"close"` default
or `"next_open"`) are read in `backtest.backtest_config_for` with `.get` defaults. They are not
added to `DEFAULT_CONFIG`, so existing config dicts and their hashes stay the same.
`run_agent_backtest` passes `open` to the agent and to the baselines when next-open is on.
`evaluate()` meta now records `exec_lag` and `fill`.

## Files
- agentic_trader/quant/pycore.py: config fields, validation, engine loop
- cpp/include/at/backtest.hpp, cpp/src/backtest.cpp, cpp/bindings/module.cpp: mirror of the
  same change
- agentic_trader/backtest.py: config plumbing, open passed to the engine for next-open
- agentic_trader/evaluation.py: meta fields
- tests/test_exec_lag.py (new)
- scripts/v17_exec_lag.py (new): runs the protocol amendment

## Tests
Command: `PYTHONPATH=. .venv python -m pytest tests/test_exec_lag.py tests/test_quant.py
tests/test_quant_edges.py tests/test_quant_research.py tests/test_v08_engine.py
tests/test_v08_portfolio.py tests/test_v08_fixes.py`. Result on the numpy backend:
247 passed, 32 skipped (the C++ parity tests skip).

New tests in tests/test_exec_lag.py:
- Lag 0 is bit-identical to the old engine. The test compares a sha256 of the equity,
  positions, traded and exits arrays from a full-featured run (stops, takes, rebalance mask,
  impact, carry, cash, NaN weights) against the hash from the engine at ae26242.
- Lag k (1, 2, 5) gives results exactly equal to shifting weights, rebalance and levels by k
  at lag 0.
- A look-ahead signal `w[t] = sign(r[t+1])` gives Sharpe > 10 at lag 0 and |Sharpe| < 1.5 at
  lag 1. This is the no-look-ahead regression the review asked for.
- Next-open: a hand-computed example, a check that the overnight move belongs to the old
  position, validation errors, and config plumbing.
- C++ vs numpy parity for (lag, next_open) in {(0,F),(1,F),(3,F),(0,T),(2,T)}, at rtol 1e-12.
  This is skipped locally. **C++ was not compiled here** (no compiler, and no `_atcore` for this
  interpreter). The C++ change is written to mirror numpy operation for operation, and its first
  real check is CI's C++ jobs. The maintainer should confirm those jobs, and this parity test
  under the cpp backend, are green before the merge.

Ruff is clean. Mypy on the touched files: no issues.

## Quadratic held-weight replay (backtest.py, run_agent_backtest): NOT changed
At each decision the code replays the engine on prices[:i+1]. That is O(n^2 / rebalance_every)
engine steps. Making it linear without changing a single bit needs a resumable engine state
(prev, prev_target, stopped, ruined, equity) exported by both backends. That is a C++ API change
I could not compile or test locally, so I left the replay as it is. Follow-up: add
`run_backtest_state(...)` returning the loop state, or a Python-side incremental replay used
only on the numpy backend, plus an equality test against the full replay. Cost today: for about
1500 bars at every-5 cadence, roughly 300 prefix replays per sleeve. That is noticeable but not
the bottleneck next to the graph.

## Protocol amendment: registered rules trials at lag 0 vs lag 1
Not a new trial family. TRIALS is unchanged, and no rule is selected on these numbers. The
statistic is the one each trial was registered on: the core-15 design-period equal-capital
portfolio Sharpe at every-5 cadence (the same call as `measure_v08.run_trials`), plus the paired
block-bootstrap Sharpe difference against B&H vol-target. Rules only, with `llm_provider`
offline.

**The real-data run was not done.** The lane rules forbid downloads, and there is no offline
Yahoo price cache on disk. Only FRED and EDGAR caches exist under build/. The script was
started on the synthetic provider for two trials and stopped after one result:
'v0.2 (control)' lag 0, SR 0.533, delta +0.224 vs control, p 0.558. That shows the pipeline
runs end to end. Evidence class: synthetic, and it says nothing about markets. No result files
were written, because the script writes everything at the end. The single trial-lag took about
40 min on the numpy backend while the machine was loaded by other lanes. At that rate the full
30 trials x 2 lags would take tens of hours, so use the C++ backend or a quiet machine, and run
it detached.

Queued command (network: Yahoo + FRED, $0, no model):

    .venv\Scripts\python.exe scripts/v17_exec_lag.py --provider yahoo --out docs/results/v17_exec_lag

Smallest representative subset, if time is short (control, the TSMOM, reversal and stops rules
the review names as lag-sensitive; 8 trial-lags):

    .venv\Scripts\python.exe scripts/v17_exec_lag.py --provider yahoo --trials "v0.2 (control),+ 12-1 month time-series momentum,+ trend-filtered reversal,+ intraday stops"

Outputs are trials_lag_yahoo.json, trials_lag_yahoo.md (the lag-0 vs lag-1 table: SR, delta vs
control, p) and meta_yahoo.json.

Expectation (inference, not measured): lag 1 should lower the short-horizon rules (reversal,
stops, ZMR/KDJ) more than 12-1 TSMOM. The "no edge" conclusion cannot flip, because the
same-close bias works in favour of edge.

## COOKBOOK recipe (text for the maintainer)
**Test a strategy's sensitivity to fill timing.** Set
`make_config(backtest={"exec_lag": 1})` to fill one bar after the decision, or
`{"fill": "next_open"}` to fill at the next open (not with stops on). Re-run the same
evaluation and compare the Sharpe. A result that survives only at lag 0 is a same-close
artefact.

## Follow-ups
- Run the queued command above. Fold the table into evaluation.md as a sensitivity row.
- Confirm CI's C++ build and test_exec_lag's parity cases under the cpp backend.
- Make the agent replay incremental (above).
- Make next-open work together with stop/take levels.
