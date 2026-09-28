# Position sizing methodology

## Strategic weight and tactical tilt

Every instrument has a strategic (benchmark) weight held when the desk has no directional
view. For equities it is 1.0, the long-run risk premium. For currency pairs it is the carry
premium: the point-in-time rate differential the macro analyst was allowed to know, divided
by 2 and capped at 0.5 in absolute value (`rules.fx_carry_neutral`, on by default), so a 1%
differential holds 0.5; a pair with no known differential holds 0. The trader sets the
target as the strategic weight plus a tilt of twice the debate score when the absolute
score exceeds the decision threshold of 0.10. Weights are clipped to the range -1 to +1,
and to 0 or above for an instrument that may not be shorted. The proposal's holding horizon
is 10 trading days; a model-supplied horizon is clipped to 1 to 90 trading days.

## Volatility targeting

The neutral risk analyst scales the trader's target so that the position's expected
annualised volatility equals the 15% target: weight multiplied by target volatility over
the 20-day realised volatility. A more volatile instrument receives a smaller position for
the same conviction. When realised volatility is zero or unavailable the vol-targeted
weight is zero.

## Aggressive and conservative views

The aggressive analyst recommends the larger of 1.25 times the trader's size and the
vol-targeted size. The conservative analyst recommends half of the smaller of the two,
then reduces it further so that the position's one-day 95% VaR stays within the 2% cap,
reading the VaR of the position's own side (the right tail of the return distribution for
a short).

## Blending

The portfolio manager blends the latest views with weights of 25% aggressive, 50% neutral
and 25% conservative, or takes the language model's proposed weight when one is
available. Firm limits then apply.

## The position the desk starts from

Between decisions the backtester holds units, not a constant weight: the position the desk
is told it holds is the previous decision's units drifted with the market, or flat after a
stop or take-profit exit. The no-trade band and the execution plan start from that true
position, so a decision to keep it trades nothing.

## What the fundamentals analyst refuses to score

The fundamentals score, one input to the debate the trader sizes on, is built only from
figures current at the decision date. A point-in-time report older than 120 days at the
decision date (a skipped periodic filing) is not scored at all: the analyst abstains and
says how old the report is. A term whose four-quarter window ends more than 100 days behind
the report period, as the provider flags it (revenue growth on `revenue_period_end`, net
margin on `net_income_period_end`, P/E and the negative-earnings penalty on
`eps_period_end`, free-cash-flow yield on `ocf_period_end`), is skipped with a key point
naming the window's end and its lag; a window one quarter behind is scored as before. When
every term is skipped the analyst abstains, and a report carrying only its date and age,
no figure, abstains too. The summary names every lagging window. Providers without lag
flags (synthetic data) are scored exactly as before.

## Track record adjustment

When the decision memory shows a hit rate below 40% over the last resolved calls on the
instrument, at least five of them, recorded on the same data provider, the trader cuts the
target by 25%. Recent poor calls reduce size; they do not change direction. The cut is a
rule switch (`rules.track_record_cut`, on by default and on in every published backtest)
so that it can be measured on and off. The v0.8 evaluation measures it both ways on the
2016 to 2021 design period under the protocol (`eval_no_trackrecord_cut` in `results/v08`,
rendered in `results/v08/tables.md` as "track-record size cut off (a) vs on (b)", a paired
table whose intervals and p come from a bootstrap over instruments (`scheme=instruments`
on the rows quoted here) and which prints no Benjamini-Hochberg flag): on the core design
period the mean Sharpe is 0.66 with the cut and 0.66 without, a difference of
+0.00 [-0.00, +0.01] p 0.51, so the design period cannot tell the two apart and the default
stays on; on the extended universe's design period the difference is +0.01 [+0.00, +0.01]
p 0.01, and removing the cut is worth about +0.01 on nearly every other slice, recorded as
information for the next rule change, not as a basis for this one.
