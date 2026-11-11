# Lane A: resumable long scripts

## What changed

- `agentic_trader/checkpoint.py` (new): `Checkpoint`, an append-only JSON-lines file. Line 1 is
  a header with a sha256 fingerprint of the inputs; each later line is one finished unit,
  written with a single `write` then `flush` + `fsync`. On open, a fingerprint mismatch raises
  `CheckpointMismatch`; a torn or corrupt tail (process killed mid-write) is truncated back to
  the last complete line and that unit simply runs again.
- `scripts/v17_exec_lag.py`: every finished (trial, lag) goes to
  `<out>/checkpoint_<provider>.jsonl`. `--resume` (default) skips finished units; `--fresh`
  deletes the checkpoint first. Progress prints `k/N` with N = trials x lags known upfront.
  The provider is only built when there is a unit left to run.
  - Header fingerprint: sha256 of the script and `agentic_trader/backtest.py`, package
    version, provider, period name and dates, core universe, rebalance step, control, lags,
    and each trial's (name, version, overrides).
  - `trials_lag_<p>.json` and `.md` are built only from the checkpoint, in fixed unit order,
    with `\n` line endings, so a resumed run writes the same bytes as an uninterrupted one.
  - Output change: the per-row `seconds` field is gone (wall time made rows irreproducible).
    `meta_<p>.json` now has `seconds_this_session`, `checkpoint` and
    `checkpoint_fingerprint`. Meta is not byte-stable by design (provenance, timing).

## Tests

`tests/test_v019_checkpoint.py` (fake backtest, 3 trials x 2 lags, no data or network):
resumed == full run byte for byte, and only the 2 unfinished units rerun; `k/N` progress
lines; `--fresh` reruns everything; a different trial list is refused; a half-written last
line is ignored and truncated. 4 passed. ruff and mypy clean on touched files.

## Limits and open items

- The data fingerprint covers the provider and period, not the downloaded bars. A Yahoo data
  revision between two sessions would not be detected. Hashing the bars would mean loading
  them before the first unit; left as a follow-up.
- `code_sha256` covers only the script and `backtest.py`. A change in another engine module
  would not refuse a resume. Using the git commit instead would refuse on any unrelated commit.
- Other long scripts checked:
  - `scripts/measure_v08.py run_trials`: already skips trials whose `trial_<slug>.json` exists,
    so it resumes. But the files are written non-atomically and carry no fingerprint, so a
    file from older code would be silently reused. Fix: write to a temp file and `os.replace`,
    and check a fingerprint stored in `meta`. Done 2026-11-11 (inputs-only fingerprint;
    legacy files without one are kept, so registered statistics do not move).
  - `scripts/v16_local_study.py`: has its own JSONL checkpoint already; could move to the
    shared helper later. No header fingerprint.
  - `scripts/v17_costs.py`: synthetic grid (4 spreads x 2 vols x seeds) plus a per-symbol,
    per-alpha loop on design frames; writes at the end. Probably minutes, not hours; not
    converted. Worth converting if `--provider yahoo` runs prove slow.
  - `v17_planner_quality.py`, `v17_retrieval_eval.py`, `v17_eval_baseline.py`: short,
    read recorded inputs; no change needed.
  - No v17 conformal script exists under `scripts/`.
