# FX carry and macro methodology

## Carry

Carry is the interest-rate differential between the base and the quote currency: base
policy rate minus quote policy rate, in percent per year. A long position in the pair
earns the differential when it is positive and pays it when negative. In backtests carry
accrues each bar as the annual rate divided by 260 trading days, from the rate known on
that bar's date, on the notional actually held: between decisions the position's units are
constant, so carry accrues on that constant notional rather than being re-levered every
day. A bar with no known rate credits nothing. A currency position is a forward, so the
account's capital is not spent buying the base currency: the whole account earns the cash
rate (the 3-month Treasury bill on real data) in addition to the position's carry.

## One resolver

The rate differential the macro analyst is shown and the carry the backtester credits come
from one function, so on every bar they agree or both are absent. What the desk sizes on is
what the backtester credits. The command-line backtest header prints the mean carry
credited over the accruing bars (every bar but the last, which has no following bar to
accrue into), counting a bar with no known rate as zero, and how many accruing bars had no
point-in-time rate.

## Point-in-time rates and publication lag

The carry credited on a bar, and the differential the macro analyst sees, use only rates
whose publication lag had elapsed by that date. Policy rates come from FRED series: the
effective federal funds rate for USD, the ECB deposit facility rate for EUR, SONIA for
GBP, and OECD monthly immediate rates for JPY, CHF, AUD, CAD, NZD and NOK. Each FRED
observation becomes visible only after its publication lag: one day for daily series and
about forty days for monthly averages. A series whose
latest visible value is older than its maximum age (ten days for daily series, one hundred
days for monthly) is treated as unavailable rather than carried forward, because several
OECD series stopped updating and a stale value must not stand in for the present. SEK has
no series (its OECD series stopped in October 2020), so USDSEK has no macro view at any
date on real data. Every macro answer names its source, and the provider keeps a tally per
run, recorded in the evaluation result's metadata, so a run can state whether any decision
used the static table. A cached FRED series that cannot be re-downloaded is served stale
with a warning naming the series and its last observation, so an offline re-run of a
historical period keeps the macro view it had online.

## Inflation

Consumer-price inflation, year over year, enters the macro analyst's view as a
purchasing-power-parity drag on the higher-inflation currency. It is used only when both
currencies have a fresh value.

## Static table

The configuration holds an illustrative table of policy rates and inflation. It is used
for synthetic data, where it is part of the generated world, and when the macro source is
set to `static` explicitly. On real data in the default mode it is never used, at any date:
a date with no FRED value for either leg has no macro view (the analyst abstains and the
strategic FX weight is 0) and no carry. There is no fallback keyed to the wall-clock date,
so the answer for a date does not depend on when it is asked.

## Macro analyst scoring

The macro score is 0.5 times the hyperbolic tangent of the rate differential divided by
1.5, minus 0.2 times the tangent of the inflation differential divided by 2, minus 0.2
times the tangent of the deviation from the 200-day average divided by 8%. A positive
score favours a long position in the pair. Without a point-in-time rate differential the
analyst abstains.
