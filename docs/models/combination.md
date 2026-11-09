# Card: IC-weighted signal combination

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** research. **Code:** `agentic_trader/combine.py` (`desk_forecast`), switched on by
`combination.method = "ic"`.

## Purpose
Replace the hand-set weights of the rules desk with one estimated pipeline: trailing rank IC per
signal, James-Stein shrinkage toward zero, expected return IC x vol x z, shrunk mean-variance
and a turnover penalty (`combine.py` docstring).

## Inputs
The alpha library signals and two trend components, standardised over a trailing window; the
`horizon`-bar forward return for the IC (only returns complete at the as-of bar).

## Validation evidence
Design period: IC combination 0.5125 portfolio Sharpe vs control 0.6437, p 0.174; the
pre-registered expectation (tilt near zero, desk near control) did not hold (real-rules;
`docs/review/PLAN.md` row 5.1).

## Limitations
Treats signals as uncorrelated, so `mu` is overstated when correlated signals survive
(`combine.py`, step 4). One registered parameter (`window` = 504).

## Monitoring
`ic_active_signals` and the tilt are reported per decision (`Forecast.facts`).

## Status
Research, not adopted.
