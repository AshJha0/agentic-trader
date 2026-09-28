# Risk limits policy

## Purpose

Firm limits bound every position the desk can hold. They are applied by the portfolio
manager after any model output and cannot be overridden by an analyst, a trader, a
debate verdict or a language model. A limit that fires is recorded as an adjustment on
the final decision so the audit trail shows what was changed and why. The critic checks
the final decision against the same limits and reads the same tail.

## Position limits

The maximum absolute position weight is 1.0 (100% of allocated capital) per instrument.
Targets above the cap are reduced to the cap with the same sign. Targets whose absolute
value is below the minimum trade weight of 0.05 are rounded to flat: a position that small
costs spread without changing risk.

## Value-at-risk cap

The one-day historical VaR at 95% confidence of the position, computed over the last 250
daily returns, must not exceed 2% of allocated capital. The tail is the position's own: a
long loses on the left tail of the return distribution, a short on the right, so a short is
sized on the VaR of the negated returns (`var_95_1d_short`), which differs from the
long-side figure on a skewed history. When the proposed weight would breach the cap, the
weight is scaled down to the largest size that satisfies it. A flat return history (zero
VaR) does not trigger scaling. Tested on the holdout period against each core instrument's
next-day return (`results/v08/tables.md`, VaR coverage of the desk's own per-instrument
forecast), this forecast breached on 5.23% to 6.57% of days, every instrument above the
nominal 5%: Kupiec rejects coverage at 5% on 2 of 15 instruments and Christoffersen rejects
independence on 6 of 15, so breaches cluster; the book-level cap below was off in every
published run and its coverage is untested.

## Book-level VaR cap

When `max_book_var_95` is configured, the one-day 95% historical VaR of the whole book, this
instrument's proposed weight plus every other symbol's current weight from the same scan,
is capped as well. Book VaR is not assumed monotonic in the proposal (a new position can be
a partial hedge), so the check searches over sizes of the proposal from the full size down
to zero. If the rest of the book already breaches the limit and some size of the proposal
brings it back within, the largest such size is taken and the note says the position was
sized as a hedge; only when no size does is the proposal flattened, and the note says so.
The check fails closed: a book whose VaR cannot be evaluated (fewer than 20 aligned daily
observations for a held symbol, or no return history for the proposed symbol) flattens the
proposal with a note rather than passing as if the check had run. A scan fetches history
for every held symbol, including those outside the watchlist, so a held symbol is never
silently treated as riskless. The cap is off by default and was off in every published
run; its coverage is untested.

## Shorting policy

Equities are long-only unless the configuration allows short selling. FX positions may be
short, because a short in a currency pair is a long in the quote currency. A negative
equity target under the long-only policy becomes flat.

## No-trade band

If the new target is within 0.10 of the current position, the current position is kept.
The band applies only when the current position itself passes every limit today; the band
never keeps a position that the VaR cap, the book VaR cap or the position cap would now
forbid. A decision the band keeps is marked as a keep (`FinalDecision.kept`), and that mark
is the only thing the backtester executes as no trade; every other decision is a target.

## Order of application

Limits apply in a fixed order: shorting policy, position cap, per-instrument VaR cap, book
VaR cap when configured, minimum trade weight, then the no-trade band. The order matters:
the band is evaluated on the limited target, and the minimum trade rounding happens before
the band so a small legitimate position is not kept by accident.

## Between decisions

The backtester holds units, not a constant weight, between decisions: the held weight
drifts with the market and can sit above the cap until the next decision bar, where the
cap binds on the target. The desk is told the position it actually holds, drifted or flat
after a protective exit, and every limit and the band are evaluated against it. A keep is
executed as no trade; any other decision, including one equal to the cap while the held
weight has drifted past it (a losing short, a capped long with negative carry), is clamped
to the cap and traded, so a position past the cap is trimmed back to it at the next
decision bar. Because the band never keeps a position the cap forbids, a drifted position
past the cap is never held by a keep.
