# Point-in-time data policy

## Principle

An agent deciding as of a date may only see information that existed at that date's
close. Every data path enforces this twice: the provider returns nothing after the as-of
date, and the orchestration layer clips price history again before any agent runs.

## Prices

Daily bars are cleaned before use: sorted, de-duplicated, rows without a positive close
dropped, missing open, high and low filled from the close, and highs and lows widened to
contain the open and the close so stop simulation never sees an impossible bar. A decision
is refused when fewer than 30 bars are available or when the latest bar is more than seven
days before the as-of date.

## Fundamentals

Synthetic quarterly reports become visible thirty days after the quarter end. Yahoo
Finance fundamentals are a current snapshot and are therefore refused for any as-of date
more than seven days in the past.

## News and social posts

Headlines are filtered to those published on or before the as-of date, both by the
provider and again by the analysts. Yahoo Finance serves only recent headlines, so
historical backtests on real data run without news. Timestamps have day granularity, so a
headline published after the close on the as-of date is visible to that day's decision;
this is a known residual.

## Memory

Past decisions are resolved only once their horizon has elapsed by the current as-of
date, and lessons are visible only from their resolution date onward.

## Macro

Policy rates and inflation are publication-lagged and staleness-checked, as described in
the FX carry methodology.
