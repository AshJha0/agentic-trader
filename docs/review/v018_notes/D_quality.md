# v0.18 lane D: quality notes

## N6 / N8: honest trial count in rendered DSR

Plain idea. A deflated Sharpe is only as honest as the trial count it is given. The v0.17 code
could report the DSR at the registered count plus the pre-registry estimate (R1.3) and at the
effective number of trials (N8), but the render paths still called `selection_report` with the
measured trials only.

What changed (source: this branch's diff).
- `scripts/render_v08_tables.py`: the selection-statistics table passes `n_trials=len(registry)`
  and `pre_registry_trials=evaluation.PRE_REGISTRY_TRIALS_ESTIMATE` (64), so the floor
  (registered count) and the conservative ceiling are printed side by side.
- `agentic-trader stats` gains `--pre-registry-trials N` and `--trial-returns CSV`; the second is
  the render command for the effective-trials DSR (`deflated_sharpe_prob_effective`). `--trials`
  is now forwarded as `n_trials`, so a registered count larger than the listed Sharpes is honoured.

Worked example. `agentic-trader stats r.csv --trials 4 --trial-sharpes 0.2,0.4,0.6,0.8
--pre-registry-trials 64 --trial-returns t.csv` reports `trials_incl_pre_registry: 68` beside
the 4-trial figure, plus `trials_effective` (tests/test_v018_quality.py).

The `significance_gated_wf` row (`alpha.walk_forward_gated_series`) was already implemented in
v0.17; it is now covered by a no-look-ahead test (changing the signals from bar t onward leaves
the series before t unchanged).

## Coverage

No `.coverage` file existed and the CPU is shared, so targets were picked by judgment: the
honest-count paths of `stats.selection_report`, `evaluation.pre_registry_trial_estimate`,
`alpha.walk_forward_gated_series` and the `stats` CLI. Nine behaviour and error-path tests in
`tests/test_v018_quality.py`: DSR monotone in the trial count, `n_trials` validation,
effective-trial collapse for near-identical trials, causality of the walk-forward gate, an
all-NaN gate when nothing passes, and the CLI error on a one-column trial matrix.

## Docs

`scripts/check_links.py` (already in the repo) reports no broken internal links across 81
Markdown files and docs/index.html; `docs/models/INVENTORY.md` is already linked from
`docs/INDEX.md`. No doc text changed in this lane.

## Open

- The v0.8 tables in docs were not re-rendered (needs the design CSVs; no runs in this lane).
- A coverage run over the full suite is still to do when the CPU is free.
- README / LEARN / COOKBOOK could mention the two new `stats` flags; left for the combined docs pass.
