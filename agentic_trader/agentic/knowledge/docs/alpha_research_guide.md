# Alpha research guide

## What an alpha is

An alpha is a scale-free signal in the range -1 to +1 computed from information available
at the close, intended to predict the direction of the instrument's return over a horizon
of days to weeks. The library includes time-series momentum over 12 months skipping the
last month, vol-adjusted 20-day momentum, 5-day short-term reversal, proximity to the
52-week high, Donchian breakout, MACD and RSI transformations, a low-volatility signal and,
for currency pairs, carry.

## Information coefficient

The information coefficient is the Spearman rank correlation between the signal at time t
and the forward return from t to t plus the horizon. Forward returns sampled every bar
overlap, so only about n over the horizon of the n pairs are independent; the t-statistic
is the IC times the square root of n over the horizon, the same effective-sample rule the
cross-sectional analyst applies, so the two analysts' gates are the same test. The naive IC
times the square root of n is about the square root of the horizon too large, 3.2 times at
the default ten-day horizon, and would call noise significant most of the time. A
Newey-West variant is offered for comparison only; its window covers the return overlap but
not the slow signals' own memory. An IC of 0.05 with a t-statistic above two is respectable
for a daily signal; an IC above 0.2 on daily data usually indicates a look-ahead error. The
alpha report shows the hit rate next to the base rate of positive forward returns on the
same pairs, so a constant signal is seen to add nothing, and the tercile spread assigns
terciles by rank, with bars tied at a boundary sharing it, so a signal stuck at one value
on most bars still has a top and a bottom tercile.

## Decay and turnover

IC decay is the IC measured at increasing horizons; a signal whose IC peaks at ten days
should be traded with a ten-day rebalance. Signal autocorrelation from one day to the next
measures turnover: a signal with autocorrelation 0.95 changes slowly and is cheap to
trade, one with 0.3 churns.

## Combination

The desk's alpha analyst combines only the alphas whose IC t-statistic is at least two in
absolute value on at least 30 pairs, weighting each by the size of its IC, and abstains
when none qualifies; the cross-sectional analyst applies the same gate to ranks across the
peer universe. The gate is per alpha, with no control for testing eight alphas at once, so
on pure noise the analyst still speaks more often than a single 5% test would. Correlated
alphas add little; a correlation matrix of signals is part of every alpha report.
Combination weights are chosen on the design period only.

## Discipline

Any alpha evaluated on the holdout period is frozen first. Every variant tried on the
design period is entered in the trials registry so the deflated Sharpe ratio of the chosen
combination accounts for selection. The design period was used to judge the alpha analyst
itself, so it is in-sample for that choice, and no held-out period remains: the next unseen
data is the future.
