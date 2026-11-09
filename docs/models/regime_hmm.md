# Card: HMM regime label and conditioning

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** research. **Code:** `agentic_trader/regime.py` (`GaussianHMM`, `fit_hmm`,
`RegimeSeries`), used by `combine.desk_forecast` through `regimes`.

## Purpose
Label each bar with a 2-state Gaussian HMM on volatility, trend and rate-change features
(filtered: each label uses bars up to its own) and estimate ICs and sizing volatility only on
bars of the current regime.

## Inputs
Closes and the risk-free rate; fitted on 2008-07-01 to min(as_of, 2021-12-31)
(`config.py`, `regime`).

## Validation evidence
Design period: regime-conditioned trial 0.465 vs control 0.644, p 0.009, worse (real-rules;
`docs/review/PLAN.md`, log 2026-11-08).

## Limitations
Label switching between fits; fewer bars per estimate inside a regime.

## Monitoring
The label is a fact on each decision when `regime.enabled` is set.

## Status
Research, not adopted.
