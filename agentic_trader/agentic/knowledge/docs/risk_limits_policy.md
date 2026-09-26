# Risk limits policy

## Purpose

Firm limits bound every position the desk can hold. They are applied by the portfolio
manager after any model output and cannot be overridden by an analyst, a trader, a
debate verdict or a language model. A limit that fires is recorded as an adjustment on
the final decision so the audit trail shows what was changed and why.

## Position limits

The maximum absolute position weight is 1.0 (100% of allocated capital) per instrument.
Targets above the cap are reduced to the cap with the same sign. Targets whose absolute
value is below the minimum trade weight of 0.05 are rounded to flat: a position that small
costs spread without changing risk.

## Value-at-risk cap

The one-day historical VaR at 95% confidence of the position, computed over the last 250
daily returns, must not exceed 2% of allocated capital. When the proposed weight would
breach the cap, the weight is scaled down to the largest size that satisfies it. A flat
return history (zero VaR) does not trigger scaling.

## Shorting policy

Equities are long-only unless the configuration allows short selling. FX positions may be
short, because a short in a currency pair is a long in the quote currency. A negative
equity target under the long-only policy becomes flat.

## No-trade band

If the new target is within 0.10 of the current position, the current position is kept.
The band applies only when the current position itself passes every limit today; the band
never keeps a position that the VaR cap or the position cap would now forbid.

## Order of application

Limits apply in a fixed order: shorting policy, position cap, VaR cap, minimum trade
weight, then the no-trade band. The order matters: the band is evaluated on the limited
target, and the minimum trade rounding happens before the band so a small legitimate
position is not kept by accident.
