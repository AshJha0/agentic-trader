# Point-in-time data policy

## Principle

An agent deciding as of a date may only see information that existed at that date's
close. Every data path enforces this twice: the provider returns nothing after the as-of
date, and the orchestration layer clips price history again before any agent runs. Where a
value was known at the time only in a form that was later revised, the form known at the
time is used.

## Prices

Daily bars are cleaned before use: sorted, de-duplicated, rows without a positive, finite
close dropped, missing or non-finite open, high and low filled from the close, and highs
and lows widened to contain the open and the close so stop simulation never sees an
impossible bar. A decision is refused when fewer than 30 bars are available or when the
latest bar is more than seven days before the as-of date. Yahoo Finance never serves or
caches a bar dated today, where today is the calendar date in New York whatever the host's
clock: a bar dated D is a close once it is D+1 in New York, so a request made at dawn in
Tokyo does not see the bar still trading and one made after midnight in London does not
wait for the local date; an empty download is an error, not an empty history. The
command line's default as-of date is New York's yesterday for the same reason. A CSV file
that carries both Close and Adj Close is served with every price column on the adjusted
basis; its volume is divided by the split component of the adjustment factor only (a
day-over-day jump of the factor above 5% is a split), never by the dividend drift, so a
dividend payer's volume is served as traded and dollar volume stays as traded across a
split; a row whose Adj Close is blank keeps its close and takes the factor of the nearest
dated row that has one. A file with only Adj Close has its raw open, high and low dropped
and rebuilt from the close, with a warning.

## Fundamentals

On real data the source is SEC EDGAR, point in time by the SEC's own filing date: a fact
exists at the as-of date if and only if it was filed on or before it. Quarterly flows are
reconstructed per concept, where a concept is one XBRL tag or tags proven equivalent for
the filer (a rename: every span both tags print agrees within 1%), never differencing one
concept's span against another's, and a trailing year is assembled from windows each taken
whole from the concept that covers it; the concept already reported is kept across filings
while it covers the window, and rank decides only when it does not. Where a span had been
printed more than once by then, a re-print within 5% of the value held is a revision and
the latest print wins. A re-print more than 5% away is a material change and must be
corroborated: a filing that recasts at least two spans of a concept, or the year-earlier
comparative of a span it prints for the first time, and whose quarters reconcile with its
own annual span (within 2% of the larger of the annual figure and the quarters' total
magnitude; 15% for per-share series), has moved its comparatives onto a new reporting
basis and opens a new basis generation. A lone material re-print is ignored and
remembered; a later filing repeating it within 5% confirms it as a correction, taken in
place within the current basis, never as a basis change. A recast whose quarters do not add
up to its own annual figure is mis-tagged and ignored, and that year's fourth quarter is the
annual span less the quarters held. Every difference and every year-over-year growth is
taken within one concept and one generation, so a restated year is never mixed with an
unrestated one. A fourth quarter printed directly that disagrees with the annual span by
more than 2% is replaced by the annual figure less the three quarters, for additive flows
only; a per-share print is never overridden. A revenue quarter reconstructed at or below
zero is rejected, not reported. Each of these cases is logged once per filer, concept and
span.

Balance-sheet instants (shares, equity, debt) must be dated within 400 days of the report
period. A flow series is dead only when no filing within 120 days of the newest filing
printed any span of it; a live series whose latest complete four-quarter window ends before
the report period is kept and the lag is reported (`revenue_period_end`,
`net_income_period_end`, `eps_period_end`, `ocf_period_end`, each present only when that
window lags). Net margin is reported only when the revenue and net income windows end
together, and free-cash-flow yield only when the operating cash flow and capital
expenditure windows end together or the filer never reports capex, so a stale capex series
removes the free-cash-flow figure rather than the capex. A known multi-class filer's share
count is converted before the market-cap and EPS sanity checks (BRK.B and BRK-B name the
same filer), and a ratio that fails them is dropped. Per-share prints are rebased across
later splits, so P/E and free-cash-flow yield use the close as traded on the as-of date.
The price of these guards: a genuine basis change costs a filer its growth figure until the
comparatives cycle, and a lagging window is scored as lagging or not at all (the position
sizing methodology says what the fundamentals analyst refuses to score). The analyst
scores P/E against a sector benchmark only when one is supplied; EDGAR supplies none, so on
real data that term is absent rather than invented.

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
day's decision; this is a known residual. A currency headline is read clause by clause
from the subject each clause names first: the pair itself is recognised before its legs,
so a clause about the pair or its base currency keeps its tone and only a clause about the
quote currency is flipped.

## Macro and the cash leg

Policy rates and inflation are publication-lagged and staleness-checked, as described in
the FX methodology, which also owns the single-resolver rule: the differential the desk is
shown is the one the backtester credits, or both are absent, and the illustrative static
table is never a fallback on real data, so the answer for a date does not depend on when
it is asked. The on-disk cache of those series expires after a day and a download is
validated before it is written; when the re-download fails, the stale file is served with a
warning naming the series and its last observation, so an offline re-run of a historical
period keeps its macro view. The cash leg is the 3-month Treasury bill rate (DTB3), with a
one-day publication lag, on real data, and the configured constant on synthetic and CSV
data.

## Memory

A past decision is valued on the history the desk holds at the current as-of date, from
the entry bar to the bar exactly `horizon_days` trading days later (bars, not calendar
days), only for entries recorded by the same provider and price basis, and only when the
decision day sat within the desk's data-staleness limit (`max_data_staleness_days`, 7) of
its entry bar: a split or dividend rebase between sessions yields the true return, and a
provider switch never values another provider's entry. An entry whose exit bar the series
cannot supply, or that never arrives, is expired without a verdict once twice its horizon
has elapsed, never booked with a multi-year return. Lessons and the track record are
visible only from their resolution date onward and are scoped to the provider that
recorded them. Entries written before v0.8 carry no provider: they are never valued, and
any named provider's visit expires them once twice their horizon has elapsed, so a
migrated log drains instead of holding them open. Records are appended one line per write
under a file lock, so several processes sharing one memory file lose nothing.
