# Portfolio construction policy

## Inputs

Portfolio construction starts from one target weight per instrument produced by the
desk, and from the trailing covariance of instrument returns estimated without look-ahead
at each rebalance date.

## Covariance estimation

The default estimator is exponentially weighted with a 60-day half-life, shrunk toward a
constant-correlation target with the Ledoit-Wolf intensity. Shrinkage stabilises the
matrix when the number of instruments is large relative to the window.

## Weighting schemes

Equal weight gives each sleeve the same capital. Inverse volatility scales each sleeve by
one over its volatility so that each contributes similar standalone risk. Risk parity
solves for weights whose risk contributions are equal under the full covariance. Minimum
variance and mean-variance with the desk's signals as expected returns are available for
long-only mandates with a per-sleeve cap. Every scheme scales the signed desk targets, so
a flat sleeve stays flat.

## Constraints

Per-sleeve weights are capped at the configured maximum, gross exposure is capped at 1.0
by default, and the portfolio is scaled to the 15% volatility target when the scheme
produces a lower expected volatility. Rebalancing follows the desk's decision cadence and
the no-trade band applies per sleeve.

## Risk report

Every portfolio run reports expected volatility, the marginal and component contributions
to risk of each sleeve, the diversification ratio, and the correlation matrix used.
