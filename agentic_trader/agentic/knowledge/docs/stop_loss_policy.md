# Stop-loss and take-profit policy

## Levels

Every directional decision carries a protective stop and a take-profit target expressed
in units of the 14-day average true range: the stop sits 2 ATR from the entry price
against the position, the target sits 3 ATR in favour of it. Sizing stops in ATR units
adapts them to the instrument's current volatility instead of a fixed percentage.

## Sanity rules

A stop must sit on the losing side of the entry and a target on the winning side: below
the entry for a long, above it for a short. A model-supplied level on the wrong side or a
non-positive level is replaced by the ATR-based level; a null level means the ATR-based
level; a level that is present but is not a finite number (a string, `NaN`, infinity)
rejects the model's whole reply, and the rule-based proposal is used instead. When the
portfolio manager flips the direction of a proposal, both levels are rebuilt for the final
direction.

## Simulation

In backtests with stops enabled, a position held over a bar is closed inside that bar if
a level trades. The open is resolved first against both levels: when the market gaps
through the stop or through the take-profit, the fill is the open, whichever level it was.
Otherwise the fill is the level itself, and if both the stop and the target trade within
one daily bar, the stop is assumed to fill first, the pessimistic assumption when intraday
ordering is unknown. After an exit the position stays flat until the next decision bar (a
rebalance, or a change of target) re-arms it, and the exit pays the usual transaction cost
and market impact. The desk is told it is flat after an exit: the next decision starts from
a position of zero, not from the weight it last asked for, and the no-trade band cannot keep
a position that no longer exists.

## Evaluation finding

On the 2016 to 2021 design period, core universe, re-measured under the v0.8 engine
(`results/v08/tables.md`, trials registry, from `results/v08/trials.json`), enforcing
intraday stops gave a design mean Sharpe of 0.45 against the control's 0.47, a mean
cumulative return of 44.10% against 58.24%, a mean maximum drawdown of 12.67% against
13.31% and 292.20 trades per instrument against 254.20: stops cut the cumulative return by
about a quarter at a similar Sharpe ratio, so they are off by default in backtests. They
remain available for mandates that require them.
