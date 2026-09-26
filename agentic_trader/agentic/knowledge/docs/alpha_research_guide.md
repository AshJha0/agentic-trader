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
and the forward return from t to t plus the horizon. Its t-statistic is the IC times the
square root of the number of observations. An IC of 0.05 with a t-statistic above two is
respectable for a daily signal; an IC above 0.2 on daily data usually indicates a
look-ahead error.

## Decay and turnover

IC decay is the IC measured at increasing horizons; a signal whose IC peaks at ten days
should be traded with a ten-day rebalance. Signal autocorrelation from one day to the next
measures turnover: a signal with autocorrelation 0.95 changes slowly and is cheap to
trade, one with 0.3 churns.

## Combination

Alphas are combined by averaging their values, optionally weighted by their design-period
IC. Correlated alphas add little; a correlation matrix of signals is part of every alpha
report. Combination weights are chosen on the design period only.

## Discipline

Any alpha evaluated on the holdout period is frozen first. The number of alphas tried is
recorded so the deflated Sharpe ratio of the chosen combination accounts for selection.
