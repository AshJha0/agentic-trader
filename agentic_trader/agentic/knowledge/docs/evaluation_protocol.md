# Evaluation protocol

## Periods

Rules and defaults are chosen on the design period, 2016 to 2021, and nothing else. The
holdout period, 2022 to mid-2026, was run once with frozen rules and reported whatever it
showed. The first quarter of 2024 is reported separately as a short reference window, and
a reserve period, July to September 2026, was set aside after the holdout.

No held-out data remains. The holdout has been seen since v0.3; the reserve period and the
extended universe were used to judge the v0.5.1 carry rule and the v0.6 EDGAR and
cross-sectional decisions; v0.8 re-measures every period under the corrected engine. The
next unseen data is the future.

## Universe

The core universe is ten equities across technology, financials, energy, healthcare and the
index, and five currency pairs. The extended universe adds 26 equities, nine macro ETFs and
ten currency crosses (45 instruments), for 60 in all. Fifteen instruments is a small
sample: differences in mean Sharpe below about 0.1 between variants are noise.

## Baselines

Buy and hold, buy and hold scaled to the risk team's 15% volatility target from trailing
volatility, and four classic rule-based strategies: a 20/50 moving-average crossover, MACD,
KDJ with RSI, and a 20-day z-score mean reversion. The volatility-targeted buy and hold is
the fair control for a risk-managed strategy: beating plain buy and hold on drawdown is
automatic when holding less. On the currency pairs, whose realised volatility mostly sits
below the target, the scaled control is capped at the 1.0 position limit and coincides with
buy and hold, so the FX drawdown comparison has no separate control.

## Engine conventions

Every published number is measured under one engine: units are constant between
decisions and the weight drifts with the market; costs and impact come out of equity before
a target is sized; equity is floored at zero (ruin); a gap through a protective level fills
at the open; market impact scales with the square root of current equity, and a portfolio
sleeve pays the impact of the capital it actually receives. Idle cash earns the cash leg:
on real data the 3-month Treasury bill rate per bar, on funded positions (equities) the
uninvested fraction of the account, on currency forwards the whole account. Synthetic data
uses a constant of zero, so synthetic numbers are unchanged by the cash leg.

## Metrics

Cumulative and annualised return, annualised volatility, Sharpe ratio, its t-statistic,
Sortino, maximum drawdown, Calmar, win rate, average exposure, trades and stop exits.
Sharpe, Sortino and the t-statistic are computed on excess returns over the per-bar cash
rate; annualised return, cumulative return and Calmar remain total-return quantities.
Portfolio metrics annualise with the largest periods-per-year among the sleeves (260 when a
currency pair is present). The t-statistic is the mean daily excess return over its
standard error; about two is needed before a Sharpe ratio is distinguishable from zero.

## Statistics

Cross-instrument differences between two strategies use a paired bootstrap. Where the
universe has at least five correlation groups (asset class by universe: `--universe all`)
it is a two-stage cluster bootstrap, drawing whole groups and then instruments within them,
so a cluster's common shock counts once; with fewer groups (core, extended) the plain
instrument bootstrap is used and the table says which scheme applied. A stratified
bootstrap, resampling within groups with counts held fixed, can only narrow the interval
and is not used. Multiple comparisons are controlled with Benjamini-Hochberg on the
unrounded p-values, counting only rows that were tested. A portfolio-level Sharpe
difference between two strategies over the same days uses a circular block bootstrap of
the paired daily excess returns (10-day blocks), and a sweep over rebalance phases gives
the cadence noise floor. An alpha's IC t-statistic uses the effective sample of overlapping
forward returns, n over the horizon. VaR coverage is tested with Kupiec and Christoffersen
tests on the desk's own per-instrument 250-day historical forecast against next-day
returns; book-level VaR was off in every published run and is not covered.

## Multiple testing

When several variants are compared, the best one's Sharpe is inflated by selection. Every
variant ever judged on the design period is registered (`evaluation.TRIALS`: 26 trials, 24
reproducible under the current engine and two historical), and the registry's length is
the trial count for the deflated Sharpe ratio, which adjusts for the number of trials and
the dispersion of their Sharpe ratios; the probabilistic Sharpe ratio gives the probability
that the true Sharpe exceeds a benchmark given the sample length, skew and kurtosis. Both
are reported for any chosen variant, and both are upper bounds: variants tried but not
registered would lower them.

## Provenance

Every saved result carries the package version, commit, quant backend and dependency
versions, and CSV outputs carry a provenance sidecar. The v0.8 numbers are produced by one
measurement driver (`scripts/measure_v08.py`) and rendered into tables by a script, never
typed.

## Findings to date

Out of sample the rule-based desk does not beat buy and hold on Sharpe per instrument. It
takes about half the drawdown. As a diversified portfolio it beats plain buy and hold but
not the volatility-targeted control. The language-model mode has one measurement (v0.5.1:
five stocks, one quarter), not re-derived under the current engine; the multi-year harness
has not been run.
