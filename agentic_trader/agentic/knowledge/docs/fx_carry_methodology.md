# FX carry and macro methodology

## Carry

Carry is the interest-rate differential between the base and the quote currency: base
policy rate minus quote policy rate, in percent per year. A long position in the pair
earns the differential when it is positive and pays it when negative. In backtests carry
accrues each bar as the annual rate divided by 260 trading days, from the rate known on
that bar's date.

## Point-in-time rates

Policy rates come from FRED series: the effective federal funds rate for USD, the ECB
deposit facility rate for EUR, SONIA for GBP, and OECD monthly immediate rates for JPY,
CHF, AUD, CAD and NZD. Each observation becomes visible only after its publication lag:
one day for daily series and about forty days for monthly averages. A series whose latest
visible value is older than its maximum age (ten days for daily series, one hundred days
for monthly) is treated as unavailable rather than carried forward, because several OECD
series stopped updating and a stale value must not stand in for the present.

## Inflation

Consumer-price inflation, year over year, enters the macro analyst's view as a
purchasing-power-parity drag on the higher-inflation currency. It is used only when both
currencies have a fresh value.

## Static table

The configuration holds an illustrative table of policy rates and inflation. It is used
for synthetic data, where it is part of the generated world, and for real data only within
180 days of today. It is never used for a historical date on real data.

## Macro analyst scoring

The macro score is 0.5 times the hyperbolic tangent of the rate differential divided by
1.5, minus 0.2 times the tangent of the inflation differential divided by 2, minus 0.2
times the tangent of the deviation from the 200-day average divided by 8%. A positive
score favours a long position in the pair.
