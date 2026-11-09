# v0.17 lane L3: research honesty (R1.2-R1.5, plus N4-N8, N10)

All changes are offline, $0, no model calls. Evidence class for everything below: method (code
plus tests); no new research result was produced.

## What changed

### R1.2 gate power and the "purged" label
- `stats.newey_west_lag(n, horizon)`: Newey-West (1994) rule `floor(4 (n/100)^(2/9))`, raised to
  `horizon` for overlapping labels.
- `stats.newey_west_t(x, lag=None, horizon=1)` -> `NeweyWest(mean, se, t, lag, n, n_eff)`, Bartlett
  kernel. Known-answer test against a hand computation (x = 1..5, lag 1: S = 2.8, t = 4.0089).
- `stats.rank_ic_newey_west(signal, fwd, horizon)`: HAC t of a time-series rank IC (mean of
  standardised rank products).
- `stats.min_detectable_ic(n, alpha=0.05, power=0.8, se=None)`: `(z_.975 + z_.8) * se`, or Fisher
  `tanh(2.8016 / sqrt(n - 3))` without an se (n = 1000 -> 0.0886).
- `leakage.PurgedIC` gains `t_nw`, `nw_lag`, `mde_ic`, `method`; `as_gate()` now also carries
  `t_NW`, `MDE_IC`, `df`. Alias `FoldIC`.
- Renamed `ic_purged` -> `ic_blocked_folds`, `ic_purged_series` -> `ic_blocked_folds_series`
  (old names kept as aliases, all callers work unchanged). Module and function docstrings now say
  the purge is inactive for fixed signals; "purged" is reserved for fitted things (combination,
  regime, conformal).
- `alpha_report` rows and `xalpha.ic_summary` now print `t_NW` and `MDE_IC` next to the fold t.
- Docs: `docs/quant/quant.md` section 6 has a v0.17 correction paragraph (plain, formal, worked
  example), the module table row and the question table row are relabelled.

### R1.3 multiple testing and DSR
- `leakage.GATE_FAMILIES` states the families: time series = alphas x names x horizons of one
  alpha-report run; cross section = alphas of one `xalpha_report`.
- `leakage.gate_p_value(entry, use="nw"|"fold")`, `leakage.gate_family_bh(entries, q, use="nw")`
  (nominal gate AND BH), `leakage.format_gate_family(...)` (Markdown table with fold t, NW t, MDE,
  p, nominal and family verdicts, plus a family-size footer). BH runs on Newey-West p (N7).
- `evaluation.PRE_REGISTRY_CONSTANTS` (7 groups, 32 hand-set constants with source lines) and
  `PRE_REGISTRY_VALUES_PER_CONSTANT = 3` (stated, deliberately generous) ->
  `PRE_REGISTRY_TRIALS_ESTIMATE = 64`. Evidence class: estimate.
- `stats.selection_report(..., pre_registry_trials=K)` adds DSR at `n_trials + K` beside the
  registered-count DSR. With 77 registered trials today the conservative figure uses 141.

### N8 effective number of trials
- `stats.effective_trials(returns_matrix)` -> `(N_eff, mean_corr)`, N_eff = participation ratio of
  the correlation-matrix eigenvalues; `stats.deflated_sharpe_effective(...)` uses N_eff trials with
  the trial-Sharpe variance divided by `1 - mean_corr` (correlated one-rule ablations shrink the
  dispersion). `selection_report(..., trial_returns=M)` adds `trials_effective`,
  `trials_mean_corr`, `deflated_sharpe_prob_effective` and the method string.

### N7 one gate in xalpha
- `xalpha.significance_gated_scores`: the fixed `min_tstat=2.0` default is gone (default `None`:
  an entry without its own `t_crit` never passes); entries are held to `t_crit` (2.776 at 4 df)
  and must also pass BH over the report's alphas on Newey-West p (`family_q=0.05`).
- `xalpha.gate_entry(row)` builds the gate shape from a report row (recovers df from t_crit).
- `tests/test_v05.py` fixture entries updated to carry `t_crit`, `df`, `t_NW`.

### N4 / N5 / N6 cross-sectional tables
- N4: `grouped_cross_sectional_ic` and `grouped_quantile_spread` compute within asset class and
  average; `xalpha_report` uses them for `mean IC`, spreads and decay. Pooled mixed-class IC is
  the labelled extra column `mean IC (pooled)`. This changes xalpha numbers on mixed universes.
- N5: `rolling_beta_panel` (point-in-time, trailing 252 bars, group equal-weight market) and
  `beta_neutralise` (per-date OLS residual on [1, beta] within group); `xalpha_report(...,
  neutralise="beta")`, default `"none"` to keep earlier results reproducible. Each row prints
  `breadth`, `min breadth`, `names/side`.
- N6: the `significance_gated` row is flagged (`in-sample selection = 1`) and stays excluded from
  `best()`; `best()` docstring says it is an in-sample ranking. A walk-forward version (trailing
  ICs per date) was not built: follow-up.

### R1.4 recall audit precondition
- Prereg DRAFT: new section "Precondition: the 2.4 recall audit must pass" (hit rate <= chance +
  2 SE for ticker, month, month +-1; n >= 100; <= 10% unparsed; ticker bar 0.102 at n = 200);
  holdout bullet now says "passed". The hand-copied "(72 at writing)" count is replaced by a
  pointer to `len(evaluation.TRIALS)` plus the two extra DSR counts.
- Code: `evaluation.recall_audit_verdict(result)`, `evaluation.require_recall_pass(path)` (raises
  `HoldoutLocked`), `evaluation.touches_holdout(periods)`. `evaluation.evaluate` calls the guard
  for any `llm_provider == "local"` run whose periods overlap the holdout (default path
  `results/v16_local/recall.json`, config key `recall_audit_path`). Design-period runs are
  unaffected.
- `scripts/llm_study.py` was NOT edited (lane L1). It has no holdout path today. If L1 adds one,
  the one line before any holdout period is used is:
  `evaluation.require_recall_pass(args.recall_audit or evaluation.DEFAULT_RECALL_AUDIT_PATH)`.

### R1.5 model-changed P&L
- `kpi.model_changed_attribution(records, by="sign"|"weight", n_boot, ci, seed)`: count, share,
  model and rules hit rates on the changed subset, P&L delta total and per decision, percentile
  bootstrap CIs over dates. `kpi_table` carries it as `model_changed` plus six table rows.

### N10 docs counts and breadth
- `docs/evaluation/evaluation.md`: "62 to 65" replaced by a pointer to `len(evaluation.TRIALS)`;
  a breadth sentence added (15 names, 10 equities + 5 FX, 2 or 1 names a side in xalpha). A test
  forbids a "(N at writing)" count in the prereg and "62 to 65" in evaluation.md.
- Not touched (rule 3 or other lanes): `docs/review/PLAN.md` ("62 trials"),
  `agentic_trader/agentic/knowledge/docs/evaluation_protocol.md:80` ("62 trials as of v0.12",
  dated, so correct as history). Maintainer may want to add "77 at v0.17" or a pointer.

## Tests
- New `tests/test_v17_stats.py`: 23 tests (NW known answer, lag rule, HAC vs naive on overlap,
  MDE known answer, rank-IC HAC, blocked-fold fields and label, BH removing a nominal pass in a
  401-test family, gate p-values, pre-registry DSR, effective trials, recall verdict worked
  example, guard file states, evaluate refusing a local-model holdout run, prereg/doc text,
  model-changed worked example, CI brackets zero on noise, grouped IC vs pooled, beta
  residualisation, no fixed 2.0 bar (fails on old code), df recovery).
- Run: test_v17_stats, test_v05, test_v14_leakage, test_v08_stats, test_v16_kpi, test_v14_combine,
  test_v08_protocol, test_v16_eval: 129 passed after updating two expectations
  (`test_v14_leakage` gate key set, `test_v05` gate fixture). ruff clean. mypy on touched files:
  one error, `alpha.py:365` in `alpha_snapshot`, pre-existing (not in lines touched).

## Tables not refreshed (need data, not offline-cheap)
No gate/IC table script runs offline without Yahoo data or results files. To refresh after merge:
- `agentic-trader alpha ...` / `agentic-trader xalpha --data yahoo --horizon 10` (CLI in
  `cli/research.py`) for the per-alpha tables with the new `t_NW`, `MDE_IC`, breadth columns.
- `python scripts/render_v08_tables.py` and `python scripts/render_v11_doc.py` for DSR tables; to
  show the pre-registry and effective-trial rows, pass `pre_registry_trials=
  evaluation.PRE_REGISTRY_TRIALS_ESTIMATE` and `trial_returns=` (the per-trial design return
  matrix) to `selection_report` in those scripts (not edited here).

## COOKBOOK recipe text (for the maintainer to number)
**Is a null IC a real null?** `r = leakage.ic_blocked_folds(signal, fwd, horizon=10)`; read
`r.t` against `r.t_crit`, then `r.t_nw` and `r.mde_ic`: "cannot detect |IC| below r.mde_ic".
For a family: `print(leakage.format_gate_family({(name, sym, h): r.as_gate() ...}))`.

## Follow-ups
- N6 walk-forward gated row (trailing ICs per date) instead of flagging.
- Wire `pre_registry_trials` and `trial_returns` into the render scripts and the prereg bar 5.
- B8 (null-recentred bootstrap p in llm_study) belongs to L1.
