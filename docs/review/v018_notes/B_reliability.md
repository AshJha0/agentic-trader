# v0.18 lane B: reliability leftovers

Source: `docs/review/v017_notes/LEFTOVERS.md` (L4, L8, L10, FLAKES).

## 1. Flaky tests under load: already fixed in v0.17 (L9a), re-verified

- `test_interrupted_sweep_spares_a_live_siblings_runs`: it already uses a shared manual clock
  that advances (`_ManualClock.advance`), with no heartbeat thread (`heartbeat_once()` ticks).
  Re-run 20 times one after another on a loaded machine (a local-model job was running): 0/20 failures.
- `test_stdio_session_serves_calls_concurrently_...`: the wall-clock assertion was removed in
  L9a. The test now checks that a fast call succeeds after a 600 s call is abandoned, with a
  10 s budget for a call that takes milliseconds. A timeout budget is still needed because
  the server is a real subprocess. I did not loosen it further.
- `test_remote_tools_are_classified_fail_closed_...` and `test_services::test_mcp_stdio_round_trip_and_remote_registry`:
  neither has a timing assertion. Under load they are only slow (subprocess start-up); they
  are marked `slow` in `tests/conftest.py`.

No code race was found. No test changes were needed.

## 2. Replay payloads pickled: already done (v0.17 format 2)

`agentic_trader/agentic/replay.py` hashes the file bytes and refuses to unpickle anything whose
digest is not in the allowlist (`trust=True` is the explicit opt-out). Request keys are
canonical JSON. A format-1 recording is refused with a clear error. No change in this lane.

## 3. run_study periodic model-swap check: done here

`scripts/llm_study.py::run_study` now calls `study_lineage.swapped_digest` before the first new
row, then after every `swap_check_every` written rows (default `SWAP_CHECK_EVERY = 25`; 0
disables it). If the digest changes, it raises `ModelSwapped`. Rows written before the swap
stay in the file, so a resume with a new file never mixes two sets of weights. The digest
function can be injected. Test: `tests/test_v017_study_rigour.py::test_llm_study_stops_on_a_mid_run_model_swap`.
