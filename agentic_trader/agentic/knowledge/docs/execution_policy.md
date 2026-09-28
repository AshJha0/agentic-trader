# Execution policy

## From decision to orders

A decision is a target weight. The execution plan (`algo.plan_execution`, behind the
`execution.plan` tool and the `execute` command) converts the change in weight into a parent
order at the as-of close. The notional is the change in weight times the account's capital,
in the account currency (`account_currency`, USD by default). The quantity is that notional
divided by the price of one unit in the account currency, rounded down once, at plan time,
to whole shares for equities or to whole lots of the pair's base currency for FX
(`execution.fx_lot_size`, 1,000 by default). The notional reported is that of the rounded
quantity, and the schedule, the plan payload, the ticket and the command all carry that same
quantity. A change that rounds down to zero shares or zero lots is nothing to trade, not an
error: the `execution.plan` tool answers `trade: false` with the reason, as it does for a
target equal to the current position, and the `execute` command prints the change it
sized (the change actually planned, after any long-only truncation, with a note saying so)
and that it is below one share or one lot.

FX quantities are in the base currency. When the base is the account currency the quantity
equals the notional (USDJPY on a USD account: 500,000 USD is 500,000 USD). When the quote is
the account currency the quantity is the notional divided by the last close (EURUSD). For a
cross (EURJPY on a USD account) the plan needs the base-to-account rate, read point in time
from the provider's direct or inverse pair, and refuses to size the order without it.
Equities are assumed to be quoted in the account currency.

The current position comes from the desk's position book. Inside a task run the book is the
run's own: seeded from the task's declared position and any positions map submitted with
the task, moved by every ticket the run writes, and read by the plan tool, the position
report, the planner and the agents alike, so there is one position and it is a fact, never
a proposal. A caller may supply the current position only when the book does not know the
symbol; a value that disagrees with the book is refused, and the plan validator drops a
model-written value whenever the book holds the symbol. Under the
long-only equity policy a negative target is truncated to flat, so a long-only book only ever
reduces; the plan's reason and its intent (open, add, reduce, close, sell short, buy to
cover, reverse) say so.

## Algorithms

TWAP splits the quantity evenly over time and is the default for FX, where there is no
reliable volume curve. VWAP follows the expected intraday volume profile and is the default
for equities. Participation-of-volume trades a fixed fraction of each slice's observed
volume (10% by default, never above 20%) and is chosen automatically when the order exceeds
10% of the instrument's 20-day average daily volume. The Almgren-Chriss schedule front-loads
execution according to a dimensionless urgency kappa (`costs.ac_kappa`, 3.0 by default; 0 is
TWAP, in the plan tool and the backtester alike; an infinite, undefined or negative kappa is
refused), trading market impact against timing risk; the schedule depends on kappa alone,
not on the price level. A session is sliced into 5-minute bars: 78 for an equity session,
288 for a 24-hour FX day.

## Fills and timing

A decision at the close cannot trade at that close. Fills are simulated on the next
session's bars, the first session after the as-of date, with arrival at that session's
open, and the plan reports the execution date. When the provider has no later session yet
the plan is returned unsimulated, with a note saying so, instead of a fill on the decision
day. A participation-of-volume order that runs out of volume reports what it executed
against what was requested: completion is executed over requested, and the unfilled
remainder is marked at the session close against arrival and reported separately as an
opportunity cost.

## Cost model

There is one impact law. The simulator charges half the quoted spread on every fill plus
temporary market impact of `impact_coeff x daily volatility x sqrt(slice quantity / slice
volume)`, the square-root law at the slice's own participation. Slice volume is the bar's
volume for equities and, for FX, the configured notional average daily volume
(`costs.fx_adv_notional`) spread evenly over the session; without one, FX carries no impact,
and a bar with no volume fills nothing. Worked as VWAP this reproduces the daily
backtester's charge, `daily volatility x sqrt(order / ADV)`, at any slice count, so what the
backtester charges for a day's trade and what the simulator charges for working it are the
same model. Slippage is measured against the arrival price (implementation shortfall on the
requested quantity) and against the session VWAP, in basis points. Equity spreads default to
2 basis points and FX spreads to the configured pip spread.

## Tickets and approval

Order submission (`execution.submit_order`) is a state-changing, high-risk action. It needs
the propose-trades capability to request and, under the queued approval gateway, a person
holding the approve-trades capability to approve. The framework never connects to a broker:
a submitted order is a ticket recorded as evidence and nothing else.

A ticket is the plan the desk produced, not a bare number: the quantity in its unit, the
notional in the account currency, the reference price, and a plan reference that binds those
fields together, so an edited number fails verification. The plan payload says whether the
order is ticketable (`ticketable`) against the desk's per-order cap (`order_cap`:
`execution.max_order_notional`, or capital times the maximum position weight when unset;
a cap of 0 freezes ticketing); a plan over the cap is returned with the cap and a note so
the caller can reduce or split it, and is not one the desk will ticket. The ticket is
refused when the fields do not match the reference, the quantity is not whole shares or
whole lots, the notional exceeds the cap, it would take a long-only book short, or the plan
is not one this desk produced with exactly these fields: the plan reference is a checksum
anyone can compute, and what authenticates a ticket is that this desk planned it
(`execution.allow_external_plans`, off by default, admits tickets planned elsewhere). The
same cap and the symbol universe are checked by the policy engine before any approval is
requested, and so are the arguments themselves, so an oversized, out-of-universe or
malformed order is denied, never parked for a person to approve. The ticket records the
position before and after and moves the book to the position after, pending the fill, so
the second leg of a split order plans from the reduced book and a second reduction cannot
sell the same shares twice; the position report lists tickets pending against a symbol and
its weight already counts them.
