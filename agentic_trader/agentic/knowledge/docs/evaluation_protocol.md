# Evaluation protocol

## Periods

Rules and defaults are chosen on the design period, 2016 to 2021, and nothing else. The
holdout period, 2022 to mid 2026, is run once with frozen rules and reported whatever it
shows. The first quarter of 2024 is reported separately as a short reference window.

## Universe

Ten equities across technology, financials, energy, healthcare and the index, and five
currency pairs. Fifteen instruments is a small sample: differences in mean Sharpe below
about 0.1 between variants are noise.

## Baselines

Buy and hold, buy and hold scaled to the risk team's 15% volatility target from trailing
volatility, and four classic rule-based strategies: a 20/50 moving-average crossover, MACD,
KDJ with RSI, and a 20-day z-score mean reversion. The volatility-targeted buy and hold is
the fair control for a risk-managed strategy: beating plain buy and hold on drawdown is
automatic when holding less.

## Metrics

Cumulative and annualised return, annualised volatility, Sharpe ratio, its t-statistic,
Sortino, maximum drawdown, Calmar, win rate, average exposure, trades and stop exits. The
t-statistic is the mean daily return over its standard error; about two is needed before a
Sharpe ratio is distinguishable from zero.

## Multiple testing

When several variants are compared, the best one's Sharpe is inflated by selection. The
deflated Sharpe ratio adjusts for the number of trials and the dispersion of their Sharpe
ratios, and the probabilistic Sharpe ratio gives the probability that the true Sharpe
exceeds a benchmark given the sample length, skew and kurtosis. Both are reported for any
chosen variant.

## Findings to date

Out of sample the rule-based desk does not beat buy and hold on Sharpe per instrument. It
takes about half the drawdown. As a diversified portfolio it beats plain buy and hold but
not the volatility-targeted control. The language-model mode has not been evaluated.
