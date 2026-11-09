# v0.17 lane L9a: integration leftovers

Branch `worktree-agent-a79c651a1f651b275`, based on `feat/v0.17` @ d8ef3fe. $0, no network, no
model calls. `scripts/llm_study.py`, `scripts/v16_local_study.py`, CHANGELOG and PLAN not
touched. Every default keeps published numbers unchanged (checked by bit-identity tests).

## What changed, item by item

| # | Item | Change | Files | Tests | Evidence class |
|---|------|--------|-------|-------|----------------|
| 1 | Financing in the engine (L8 A5) | `BacktestConfig.funding_spread` / `cash_spread` (annual fractions, default 0). Next to the cash leg, both engines subtract `(max(\|w\|-1,0)*funding_spread + max(1-\|w\|,0)*cash_spread)/ppy`, the `financing.financing_drag` formula. Read opt-in from `costs.funding_spread_bps` / `costs.cash_spread_bps` in `backtest_config_for` (absent = 0, so config hashes and frozen paper configs do not move). C++ mirror in `backtest.hpp`/`backtest.cpp`, pybind fields in `module.cpp`; the dispatcher copies every dataclass field, so no dispatcher change was needed. | `quant/pycore.py`, `cpp/include/at/backtest.hpp`, `cpp/src/backtest.cpp`, `cpp/bindings/module.cpp`, `backtest.py` | defaults bit-identical; in-loop == `apply_financing` to 1e-15 when re-targeted every bar; validation | tested |
| 2 | Stop slippage + participation cap (L8 C1) | `BacktestConfig.stop_half_spread` / `stop_range_frac` (default 0): `_exit_fill` (and C++ `exit_fill`) slip a triggered stop exactly as `execution_realism.stop_fill_with_slippage` (gap: open less half spread; intrabar: stop less half spread less `range_frac` of stop-to-low, floored at the low; mirrored for shorts). Take-profit fills unchanged. Config: `costs.stop_half_spread_bps`, `costs.stop_range_frac`. Participation: `backtest.participation_capper` applies `execution_realism.cap_participation` (20-bar ADV in shares, `initial_capital`) to the agent path (also inside its held-weight replays) and to every baseline when `costs.backtest_participation_cap` is set; None (default) is the identity; FX is never capped. | `quant/pycore.py`, C++ files above, `backtest.py` | engine fill == `stop_fill_with_slippage` on 2,000 random bars; slippage changes returns only on exit bars; capper identity/caps; agent backtest identical with flag None | tested |
| 1/2 | C++ parity | `test_cpp_parity_for_financing_and_stop_slippage` skips here (`_atcore` not built for this venv). Checked by hand instead: a scratch g++ 15 driver linking `cpp/src/backtest.cpp` on a 60-bar path with funding 50 bp, cash spread 20 bp, stop slippage 5 bp + 0.3 range and 9 stop exits gave equity **bit-identical** to `pycore` (max relative difference 0.0). CI with the compiled core runs the parity test. | | 1 (skips locally) | measured (local build, not CI) |
| 3 | Paper OMS hooks (L8 C3/C5, L5) | `oms.paper_session`: before the orders, actions with ex-date in `(dates[-3], dates[-2]]` from `provider.corporate_actions` go through `corporate_actions.apply_actions`; when one falls in the window the held quantity is first re-measured at the as-traded close of `dates[-3]` (`provider.as_traded_close`) so a split is not counted twice through split-adjusted prices. Cash goes to `OMS.cash_flows` via `cash_flow_rows` (so it shows in `cash_projection.csv`), events to `actions.csv`. After fills, `tca.tca_rows` (arrival = decision close, predicted = `tca.predicted_cost` with the backtester's unit cost) to `tca.csv`. Providers without `corporate_actions` (synthetic, CSV) give the old orders. | `oms.py` | session with and without a split + dividend provider; out-of-window no-op | tested (synthetic) |
| 4 | Ed25519 from config (L7 A6) | `signed_gateway_from_config` accepts `public_keys: {approver: 64-hex Ed25519 public key}` (public material may sit in config) next to or instead of `approvers` (HMAC env-var names); passes `public_keys=` to `SignedApprovalGateway`. Bad hex, wrong length, an approver in both maps, or an empty block raise. Note: L7's hook text suggested an env-var NAME per public key; inline hex was chosen because a public key is not a secret. | `agentic/harness.py` | 1 | tested |
| 5 | Output guard on desk memory (L7 C3) | `TradingGraph.record` passes the decision rationale through `output_guard.check_output` (allowed: the symbol, `agentic.symbol_universe`, `xalpha_universe`; canaries `agentic.canaries`). On refusal the memory line is `[summary withheld by output guard: <categories>]` (categories only: the guard's reasons quote the offending text, so storing them would plant the URL again); a `guard` event and a warning are emitted. `agentic.memory_output_guard: false` disables. | `graph.py` | clean summary kept; poisoned one redacted to categories; off switch | tested (hand-written cases) |
| 6 | Replay payload safety (L4 A7 second half) | Digest allowlist. `Recording.save` appends the SHA-256 of the written bytes to `replay_allowlist_path()` (`$AGENTIC_TRADER_REPLAY_ALLOWLIST` or `~/.agentic_trader/replay_allowlist.txt`, outside any recording directory). `load_recording` hashes the bytes and raises `ReplayUntrusted` before unpickling anything not listed; `allow_recording(path)` lists a checked file; `trust=True` skips for one call. JSON payloads were not chosen: tapes hold DataFrames and exceptions whose exact round trip is the point of bit-for-bit replay. `tests/conftest.py` points the allowlist at a temp file for every test. | `agentic/replay.py`, `tests/conftest.py`, `tests/test_v17_governance.py` (format-1 test loads with `trust=True`) | saved file loads; edited byte refused; a command-running pickle refused before unpickling | tested |
| 7 | Flaky tests | Sweep test: `TaskStore(clock=...)` (injected epoch clock), `AgentHarness.heartbeat_once()` (one tick), `agentic.heartbeat_thread: false` (no thread); the test drives a manual clock and ticks by hand, no sleeps. A new test checks the thread still starts by default. Stdio test: no wall-clock assertions; the slow tool sleeps 600 s so a head-of-line-blocked session would fail the fast call outright; budgets 10 s (executor) / 12 s (session). Remote-session test: see the load run below. | `agentic/store.py`, `agentic/harness.py`, `tests/test_v08_agentic.py` | load run below | measured |
| 8 | Walk-forward gate (L3 N6) | `alpha.walk_forward_gated_series(sig, close, horizon, window=504, step=horizon, min_bars=126)`: at each refit `t` it calls `combine.trailing_ics` (labels with `i + horizon <= t` only), keeps alphas whose purged IC clears its own Student-t bar (`PurgedIC.significant`), weights by the shrunk IC and combines bars `t..t+step-1`. `alpha_report(..., walk_forward=True)` adds the `significance_gated_wf` row and an `in-sample selection` column (1 only for the full-sample row); off by default so the desk's `quant.alpha` tool payload and cost do not change (prompts and replay tapes stay the same). `research alpha` CLI turns it on. `COMBINATION_ROWS` excludes the new row from `best()` and the correlations. `significant_alpha_signal` was left byte-for-byte unchanged (its source is part of the prompt bundle hash); it never sees the row because the desk tool does not turn it on. **Not done:** the cross-sectional (`xalpha`) gated row is still the flagged in-sample diagnostic; a trailing per-date CS-IC version needs the same loop over `grouped_cross_sectional_ic` slices. | `alpha.py`, `cli/research.py` | no-look-ahead test (future changed, past identical); opt-in row | tested |
| 9 | 'Reuters' wording | The one remaining case (`tests/test_v15_text.py` GDELT fixture: "- Reuters" / reuters.com, "- AP" / ap.org) now reads "- Wire A" / wire-a.example and "- Wire B" / wire-b.example. `git grep -i reuters` is empty. | `tests/test_v15_text.py` | existing test passes | done |

## Numbers

- Financing, 1.6x / 0.3x alternating book, 250 bars, zero costs, funding 50 bp, cash spread 20 bp:
  per-bar drag 1.2e-5 at 1.6x. Re-targeted every bar, in-loop and post-hoc agree to 1e-15.
  Held between decisions, the weight drifts on the financed equity, so `apply_financing` is
  first-order only: max per-bar gap 9.7e-6, mean below 2e-6. The `financing.py` docstring's
  "exact when transaction costs are zero" holds only when the weight is reset every bar;
  worth a one-line fix by the docs pass.
- C++ vs numpy with all four new fields on: max relative equity difference 0.0 (local g++ build).

## Flaky tests under load (item 7)

Each of the three tests ran 20 times in one pytest process per round, while 12 busy-loop
processes held all 12 logical CPUs (scratch script, not committed). Results: sweep 20/20, stdio
concurrency 20/20, remote fail-closed 20/20; about 60 s a round, 1,304 s in total (measured on
this laptop). The remote fail-closed test needed no change: its budgets were already 30 s
per call and 60 s to start, and it did not fail under this load. Before the change the sweep
test failed 3/20 (L8 notes).

Full suite after the change: 1,805 passed, 50 skipped. The 12 failures that remain also
fail on d8ef3fe without this lane's changes (checked in a clean worktree): paper engine
freeze/refreeze (6), Yahoo corporate-action parsing (4), the eval regression gate (1) and
`test_v08_data` refresh (1). They belong to the L5 refreeze and L6 baseline items. Two
`test_v08_agents` fence tests now set `agentic.memory_output_guard: false`, because the guard
redacts the injected marker before it reaches memory. They still check that a stored payload
stays fenced.

## Follow-ups

- xalpha walk-forward gated row (item 8, cross-sectional half).
- `financing.py` docstring: exactness needs per-bar re-targeting (see Numbers).
- Paper OMS: the TCA rows measure the OMS's own fills against the decision close, so the
  slippage is rounding and participation only until fills come from somewhere else (as L8 C5 said).
- Confirm `test_cpp_parity_for_financing_and_stop_slippage` runs (not skips) in the CI job that builds `_atcore`.

## COOKBOOK recipe text (for the maintainer to number and insert)

**Financing and stop slippage in a backtest.** In the config:
`costs: {funding_spread_bps: 50, stop_half_spread_bps: 5, stop_range_frac: 0.25,
backtest_participation_cap: 0.1}`. Every key is optional and absent means the historical
behaviour. A 1.5x book then pays rf + 50 bp on the borrowed half (about 0.25 % a year on the
account), a triggered long stop fills 5 bp under the stop less a quarter of the way to the
bar's low, and no bar trades more than 10 % of its 20-day average volume.

**Signed approvals with Ed25519 from config.** Each approver runs
`ed25519_keypair()` on their own machine, keeps the private half, and sends the hex of the
public half; the config holds `approval: {public_keys: {alice: "<64 hex>", bob: "<64 hex>"},
submit_order_quorum: 2}`. The server can verify but never mint a signature.
