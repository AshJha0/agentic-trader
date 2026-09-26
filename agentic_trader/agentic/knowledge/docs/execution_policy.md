# Execution policy

## From decision to orders

A decision is a target weight. The execution plan converts the change in weight into a
quantity: shares for equities, notional in the base currency for FX, using the last close
as the reference price. The plan is split into child slices over the trading session by
an execution algorithm.

## Algorithms

TWAP splits the quantity evenly over time and is the default for FX, where there is no
reliable volume curve. VWAP follows the expected intraday volume profile and is the default
for equities. Participation-of-volume trades a fixed fraction of observed volume and is
used when the order is large relative to average daily volume. The Almgren-Chriss schedule
front-loads execution according to a risk-aversion parameter, trading market impact
against timing risk.

## Participation limits

No parent order may exceed 10% of the instrument's 20-day average daily volume in one
session without approval. A participation-of-volume algorithm is capped at 20% of each
slice's volume. FX orders are sized against a notional limit instead of volume.

## Cost model

The simulator charges half the quoted spread on every fill plus temporary market impact
proportional to the square root of the slice's participation. Slippage is measured
against the arrival price (implementation shortfall) and against the session VWAP, in
basis points. Equity spreads default to 2 basis points and FX spreads to the configured
pip spread.

## Approval

Order submission is a state-changing, high-risk action. Through the agentic layer it
always requires approval by a role holding the approve-trades capability; the framework
itself never connects to a broker.
