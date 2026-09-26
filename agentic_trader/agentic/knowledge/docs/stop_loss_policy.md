# Stop-loss and take-profit policy

## Levels

Every directional decision carries a protective stop and a take-profit target expressed
in units of the 14-day average true range: the stop sits 2 ATR from the entry price
against the position, the target sits 3 ATR in favour of it. Sizing stops in ATR units
adapts them to the instrument's current volatility instead of a fixed percentage.

## Sanity rules

A stop must sit on the losing side of the entry and a target on the winning side: below
the entry for a long, above it for a short. Any model-supplied level on the wrong side, a
non-positive level, or a level that is not a number is replaced by the ATR-based level.
When the portfolio manager flips the direction of a proposal, both levels are rebuilt for
the final direction.

## Simulation

In backtests with stops enabled, a position held over a bar is closed inside that bar if
the level trades. The fill is the level itself, or the open when the market gaps through
the level. If both the stop and the target trade within one daily bar, the stop is assumed
to fill first, the pessimistic assumption when intraday ordering is unknown. After an exit
the position stays flat until the next rebalance re-arms it, and the exit pays the usual
transaction cost.

## Evaluation finding

On the 2016 to 2021 design period, enforcing stops lowered mean return by about 30% at a
similar Sharpe ratio, so stops are off by default in backtests. They remain available for
mandates that require them.
