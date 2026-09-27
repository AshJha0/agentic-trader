# Portfolio construction policy

## Inputs

Portfolio construction starts from one signed target weight per instrument produced by the
desk, and from the trailing covariance of instrument returns estimated without look-ahead
at each rebalance date (at least 20 rows; the portfolio backtest uses a 120-day window by
default).

## Covariance estimation

The default estimator is exponentially weighted with a 60-day half-life, shrunk toward a
constant-correlation target. The shrinkage intensity is the weighted Ledoit-Wolf (2004)
intensity for the estimator it is applied to: the mean, the sampling variance of the
covariance entries and the correlation target are weighted averages under the same
exponential weights, and the intensity is divided by the weights' effective sample size
(Kish's one over the sum of squared weights, which equals the window length for equal
weights, where the formula reduces exactly to the unweighted one). Rows the covariance
ignores therefore do not inflate the shrinkage. A column with zero variance shrinks without
producing NaN. Shrinkage stabilises the matrix when the number of instruments is large
relative to the window.

## Weighting schemes

Equal weight gives each sleeve the same capital. Inverse volatility scales each sleeve by
one over its volatility so that each contributes similar standalone risk. Risk parity
solves for weights whose risk contributions are equal under the full covariance. Minimum
variance and mean-variance with the desk's signals as expected returns are available for
long-only mandates. Every scheme produces a non-negative allocation of capital that
multiplies the signed desk targets, so a flat sleeve stays flat. A window on which no
active sleeve has positive variance, or on which a scheme returns a non-finite allocation,
raises an error, and the portfolio backtest keeps its previous allocation rather than hold
NaN.

## Constraints

The allocation is the split of capital before volatility scaling. It is projected onto the
capped simplex, so every sleeve is at most the per-sleeve cap and the allocation sums to
the gross cap (1.0 by default). The cap is `max_weight` (0.5 by default in `construct`);
a cap below 1/k for k active sleeves is infeasible and is raised to 1/k. Clipping and
renormalising would push the excess back over the cap; projection does not. With cross-asset
risk budgets the cap is enforced after the cross-group step as well, and a budget that
conflicts with it gives way to it. Final weights are allocation times target times scale,
where the scale lifts the book to the 15% volatility target when its expected volatility is
lower, capped so that neither the gross cap nor the per-sleeve cap is exceeded; the report
carries the allocation before scaling and the scale applied. The portfolio backtest calls
the schemes with no per-sleeve cap and no volatility target, so its allocation is the
scheme's own. Rebalancing follows the desk's decision cadence and the no-trade band applies
per sleeve.

## Sleeves in the portfolio backtest

The portfolio backtest computes the allocation first, from the provider's history alone,
and each sleeve is charged market impact for the capital it actually receives (the impact
coefficient scales with the square root of the sleeve's share), not for the whole book.
With equal weighting every strategy is combined identically, so the comparison between the
desk and its baselines is fair. Sleeve returns are combined daily; a sleeve with no bar on
a date contributes zero. The portfolio's Sharpe ratio is on excess returns over the same
per-bar risk-free rate the sleeves credit on idle cash, and portfolio metrics annualise with
the largest periods-per-year among the sleeves (260 when a currency pair is present).

## Risk report

Every portfolio run reports expected volatility, the marginal and component contributions
to risk of each sleeve, the diversification ratio, the correlation matrix used, the
allocation before scaling and the scale applied, and whether the solver converged.
