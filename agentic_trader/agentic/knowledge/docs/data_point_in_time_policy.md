# Point-in-time data policy

## Principle

An agent deciding as of a date may only see information that existed at that date's
close. Every data path enforces this twice: the provider returns nothing after the as-of
date, and the orchestration layer clips price history again before any agent runs. Where a
value was known at the time only in a form that was later revised, the form known at the
time is used.

## Prices

Daily bars are cleaned before use: sorted, de-duplicated, rows without a positive close
dropped, missing open, high and low filled from the close, and highs and lows widened to
contain the open and the close so stop simulation never sees an impossible bar. A decision
is refused when fewer than 30 bars are available or when the latest bar is more than seven
days before the as-of date. Yahoo Finance never serves or caches a bar dated today: a bar
still trading is not a close, so requests end at yesterday's complete bar and a decision as
of today uses it. A CSV file that carries both Close and Adj Close is served with every
price column on the adjusted basis; one with only Adj Close has its raw open, high and low
dropped and rebuilt from the close, with a warning.

## Fundamentals

On real data the source is SEC EDGAR, point in time by the SEC's own filing date: a fact
exists at the as-of date if and only if it was filed on or before it, and where a span had
been printed more than once by then, the latest print known at the time is used, restated
comparatives included. Quarterly flows are reconstructed separately per XBRL tag, never
differencing one tag's span against another's, and a trailing year is assembled from
windows each taken whole from the highest-ranked tag that covers it, preferring the tag of
the most recent window. A filing that re-prints a span more than 5% differently opens a
new reporting-basis generation; every difference and every year-over-year growth is taken
within one tag and one generation, so a restated year is never mixed with an unrestated
one. A revenue quarter reconstructed at or below zero is rejected, not reported.
Balance-sheet instants (shares, equity, debt) must be dated within 400 days of the report
period and flow series must end within one quarter of it, otherwise the derived ratio is
absent. A known multi-class filer's share count is converted before the market-cap and EPS
sanity checks, and a ratio that fails them is dropped. Per-share prints are rebased across
later splits, so P/E and free-cash-flow yield use the close as traded on the as-of date.
The price of these guards: a genuine revision above the 5% tolerance costs a filer its
growth figure until the comparatives cycle, and a taxonomy rename costs one year of
growth. The fundamentals analyst scores P/E against a sector benchmark only when one is
supplied; EDGAR supplies none, so on real data that term is absent rather than invented.

Synthetic quarterly reports become visible thirty days after the quarter end. Yahoo
Finance fundamentals are a current snapshot and are therefore refused for any as-of date
more than seven days in the past. CSV users supply point-in-time data themselves.

## News and social posts

Headlines are filtered to those published on or before the as-of date, both by the
provider and again by the analysts. On real data the news stream is the EDGAR filing stream
(8-K items, periodic reports, ownership filings), dated by filing; Yahoo Finance serves only
recent headlines and is not asked for dates it cannot serve. Social media has no free
point-in-time archive, so that analyst abstains on real data. Timestamps have day
granularity, so a headline published after the close on the as-of date is visible to that
day's decision; this is a known residual.

## Macro and the cash leg

Policy rates and inflation are publication-lagged and staleness-checked, as described in
the FX methodology, which also owns the single-resolver rule: the differential the desk is
shown is the one the backtester credits, or both are absent, and the illustrative static
table is never a fallback on real data, so the answer for a date does not depend on when
it is asked. The on-disk cache of those series expires after a day and a download is
validated before it is written. The cash leg is the 3-month Treasury bill rate (DTB3), with
a one-day publication lag, on real data, and the configured constant on synthetic and CSV
data.

## Memory

A past decision is valued on the history the desk holds at the current as-of date, from
the entry bar to the bar exactly `horizon_days` trading days later (bars, not calendar
days), and only for entries recorded by the same provider and price basis: a split or
dividend rebase between sessions yields the true return, and a provider switch never values
another provider's entry. An entry whose exit bar the series cannot supply is expired
without a verdict once twice its horizon has elapsed, never booked with a multi-year
return. Lessons and the track record are visible only from their resolution date onward
and are scoped to the provider that recorded them. Entries written before v0.8 carry no
provider and can only expire.
