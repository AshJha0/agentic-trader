# v0.18 lane A: quant leftovers (L2, L8)

## Status of the three items on entry (main @ f0838f1)

1. Financing spread in pycore and the C++ core: already done in v0.17
   (`BacktestConfig.funding_spread` / `cash_spread` in `pycore.py`, `backtest.hpp`,
   `backtest.cpp`, bound in `cpp/bindings/module.cpp`; config keys `costs.funding_spread_bps`,
   `costs.cash_spread_bps`; tests in `tests/test_v17_integration.py`). No change needed.
2. Stop slippage through `_exit_fill` (`stop_half_spread`, `stop_range_frac`, both backends) and
   the opt-in participation cap (`costs.backtest_participation_cap`, default None = identity):
   already done in v0.17, tested in `tests/test_v17_integration.py`. No change needed.
3. Next-open execution combined with stops: was open (both backends raised). Done here.

## What changed

- `pycore.validate_backtest_inputs` and `cpp/src/backtest.cpp` no longer refuse
  `fill_next_open` with stop/take levels. The engine loop already had the right shape: with
  next-open fills the position is on from `open[t+1]`, so `_exit_fill` sees bar t+1's open
  first (a level already through it exits at the open, after the overnight leg was booked to
  the old position) and then the bar's range. Stop slippage applies the same way.
- Comments in `pycore.py`, `backtest.hpp` and COOKBOOK section 121 updated.
- Defaults unchanged: only a combination that used to raise now runs.

## Tests (tests/test_exec_lag.py)

- Hand examples: stop hit inside the entry bar; stop gapped through the open (exit at the
  open); take-profit; gapped stop with half-spread slippage.
- All-NaN levels with next-open equal the no-levels run bit for bit.
- C++ parity matrix extended to next-open with levels, with and without stop slippage
  (runs in CI where `_atcore` is built; skipped locally without a toolchain).
- The old "stop/take raises" validation case now asserts the run succeeds.

## Open

- C++ change not compiled locally (no toolchain); the parity tests in CI are the check.
- Quadratic replay fix (needs C++ resumable state) not attempted: not small.
- Lag-1 / next-open trial reruns on real data (yahoo, detached) still queued from L2.
