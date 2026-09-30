# API reference

This reference covers the public Python API (the desk, the agentic layer and the research
layer), the HTTP API, the MCP server, the CLI, the C++ API and the standalone C++ tool.
Anything not listed here is internal and may change. Every signature below was read from the
code with `inspect.signature` at v0.8.0; every CLI flag from `build_parser()`; every route
from `agentic/api.py`.

```python
from agentic_trader import (TradingGraph, run_agent_backtest, run_portfolio_backtest,
                            ComparisonReport, PortfolioReport, evaluate, EvaluationResult,
                            make_config, DEFAULT_CONFIG, RULES_V02, Instrument, Action,
                            FinalDecision, TradingState)
from agentic_trader.agentic import (AgentHarness, Task, Role, TaskState, PolicyEngine,
                                    QueuedApprovalGateway, EvidenceStore, KnowledgeBase, ...)
from agentic_trader import alpha, algo, portfolio, stats, quant, provenance
```

`agentic_trader.__version__` is read from `pyproject.toml` (`0.8.0`); see
[Provenance](#provenance-agentic_traderprovenance).

## Part 1 — The desk

### `TradingGraph(config=None, provider=None, llm=None, memory=None, on_event=None)`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `config` | `dict \| None` | `DEFAULT_CONFIG` | Deep-merged over the defaults with `make_config` |
| `provider` | `MarketDataProvider \| None` | From `config["data_provider"]` | Data source |
| `llm` | `LLM \| None` | From `config["llm_provider"]` | Any object with `complete(system, prompt, *, deep) -> str \| None`; `None` means offline. Wrapped in `BudgetedLLM` when `config["max_llm_calls"]` or `max_llm_cost_usd` is set |
| `memory` | `DecisionMemory \| None` | `DecisionMemory(config["memory_path"], max_staleness_days=config["max_data_staleness_days"])` | Pass `DecisionMemory(None)` for in-memory only; `prepare` passes the graph's `max_staleness_days` to every `resolve`, so an injected memory follows the desk's setting too |
| `on_event` | `Callable[[str, str], None] \| None` | Logs at INFO | Called with `(stage, message)` for `data`, `analyst`, `debate`, `trader`, `risk`, `decision` and `report` |

Analysts and the cross-sectional peer universe are configuration, not constructor
arguments: `TradingGraph(make_config(analysts=[...], xalpha_universe=UNIVERSES["all"]))`.

#### `propagate(symbol, as_of, asset_class=None, current_weight=None, book=None) -> tuple[TradingState, FinalDecision]`

Runs the whole desk once. `symbol` is a `str` (`"AAPL"`, `"BRK.B"`, `"EURUSD"`, `"EUR/USD"`,
`"USDJPY=X"`) or an `Instrument`; `as_of` a `date` or ISO string (a weekend or holiday uses
the last close); `current_weight` the position held going into the decision; `book` a
`portfolio.Book` (the other sleeves' weights and returns) for the book-level VaR check when
`risk.max_book_var_95` is set.

It raises `ValueError` when the symbol is invalid, fewer than 30 bars are available, the
latest bar is more than `max_data_staleness_days` before `as_of`, `current_weight` is not
finite, or the provider raises it. The decision is recorded to memory and, with
`config["save_reports"]`, `results/<SYM>/<date>/report.md` is written.

#### Stages

`propagate` is composed of stages the harness reuses:

| Stage | Signature | Does |
|---|---|---|
| `prepare` | `(symbol, as_of, asset_class=None, current_weight=None, provider=None, book=None) -> TradingState` | Point-in-time history, guards, memory (resolved on the provider's own series); no agent runs |
| `analyst_names` | `(instrument) -> list[str]` | The configured analysts for the asset class |
| `run_analyst` | `(state, name, provider=None) -> AnalystReport` | One analyst; stores the report in `state.reports` |
| `run_debate` | `(state, rounds=None) -> DebateOutcome` | Bull/bear rounds and the facilitator |
| `run_trader` | `(state) -> TradeProposal` | The proposal |
| `run_risk` | `(state, rounds=None) -> FinalDecision` | Risk team, portfolio manager, limits and band |
| `record` | `(state) -> None` | Memory (stamped with the provider and price basis) and the optional report file |

#### `scan(symbols, as_of, positions=None, book_lookback_days=250) -> pandas.DataFrame`

One row per symbol: `symbol`, `asset_class`, `last`, `action`, `target_weight`,
`confidence`, `stop_loss`, `take_profit`, `debate`, `score`, `analysts_voting`, `approved`,
`adjustments`, `error`. A failing symbol gets `action == "ERROR"` and the scan continues.
`positions` keys are parsed like the watchlist symbols (`EUR/USD`, `EURUSD=X` and `eurusd`
are one holding); an unparseable key, or two keys naming one symbol with different weights,
raises `ValueError` before anything runs. With `risk.max_book_var_95` set the scan builds the book from `book_lookback_days` of
history for every symbol on the watchlist *and* every held symbol outside it; a held symbol
whose fetch fails keeps an all-NaN column and a symbol with fewer than 20 bars is logged, so
the book check fails closed (the proposal is flattened with a note) rather than treating the
symbol as risk-free.

### State documents (`agentic_trader.state`)

| Class | Fields |
|---|---|
| `Action` | `str` enum: `BUY` (hold long), `SELL` (short, or exit when shorting is not allowed), `HOLD` (flat) |
| `AnalystReport` | `analyst`, `signal` ∈ [-1, 1], `confidence` ∈ [0, 1], `summary`, `key_points`, `facts`, `source` (`rules` \| `llm`), `abstained`, `rule_signal` (the rule view when the model overrode it), `untrusted` (the analyst read third-party text: its summary is fenced downstream), `evidence_ids` |
| `DebateTurn` | `speaker`, `round`, `argument` |
| `DebateOutcome` | `winner` (`bull` \| `bear` \| `balanced`), `score`, `conviction`, `summary`, `turns`, `source`, `evidence_ids` |
| `TradeProposal` | `action`, `target_weight`, `confidence`, `entry_price`, `stop_loss`, `take_profit`, `horizon_days` (trading days), `rationale`, `source`, `evidence_ids` |
| `RiskView` | `stance`, `recommended_weight`, `argument`, `round`, `source`, `evidence_ids` |
| `FinalDecision` | `symbol`, `as_of`, `action`, `target_weight`, `confidence`, `stop_loss`, `take_profit`, `rationale`, `approved`, `adjustments`, `source`, `evidence_ids`, `kept` (`False` by default; `True` exactly when the `PortfolioManager`'s no-trade band held the current position, which it does only when that position passes every firm limit — `run_agent_backtest` passes the held weight through only then; in `to_dict()`) |
| `TradingState` | `instrument`, `as_of`, `history`, `current_weight`, `reports`, `debate`, `proposal`, `risk_views`, `decision`, `lessons`, `track_record`, `log`, `anon`, `knowledge` (retrieved passages), `alpha` (alpha snapshot), `book`, `provider_name`, `price_basis`; `last_price`, `reports_digest()`, `lessons_block()`, `prompt_facts()`, `to_markdown()` |

`state.untrusted_block(label, lines)` is the fence every third-party text goes through
(`agents.base` re-exports it); `reports_digest()` fences the summary and key points of an
`untrusted` report and `lessons_block()` fences memory lessons.

### Agents (`agentic_trader.agents`)

Every agent is constructed as `Agent(llm, config)`; `RiskAnalyst` also takes a stance.

| Class | Entry point | Tier |
|---|---|---|
| `TechnicalAnalyst`, `FundamentalsAnalyst`, `MacroAnalyst`, `NewsAnalyst`, `SentimentAnalyst`, `AlphaAnalyst`, `XAlphaAnalyst` | `run(state, provider) -> AnalystReport` | quick |
| `BullResearcher`, `BearResearcher` | `speak(state, round, history) -> DebateTurn` | deep |
| `DebateFacilitator` | `judge(state, turns) -> DebateOutcome` | deep |
| `Trader` | `run(state) -> TradeProposal` | deep |
| `RiskAnalyst` | `speak(state, facts, round, history) -> RiskView`; `rules_weight(facts)` | deep |
| `PortfolioManager` | `run(state, facts) -> FinalDecision`; `guardrails(w, facts, symbol=None, book=None) -> (w, notes)`; `no_trade_band(w, current, facts, symbol=None, book=None) -> (w, note)` | deep |

`Agent.ask_json(prompt, required, state=None, numeric=()) -> dict | None` is the one model
call: a reply missing a `required` key, or whose `numeric` keys are null, strings, booleans
or non-finite (`extract_json` also rejects bare `NaN`/`Infinity`), is rejected as a whole and
the rules apply (`source="rules"`); numbers are never coerced. `risk.risk_facts(state,
config)` builds the facts every risk agent reads (including `var_95_1d` and, for shorts,
`var_95_1d_short`, the right tail); `risk.position_var(facts, w)` selects the tail by the
sign of `w`, and the PM guardrail, the conservative analyst and the Critic's `firm_limits`
check all use it.

Helpers: `run_debate(state, bull, bear, facilitator, rounds)`, `run_risk_team(state, analysts,
pm, rounds)`, `researchers.consensus_score(state, weights, skip_abstained=False)`,
`trader.protective_levels(direction, entry, atr, risk)`, `trader.sane_levels(...)`,
`trader.policy_passages(state)`, the `ANALYSTS` registry (`technical`, `fundamentals`,
`macro`, `news`, `sentiment`, `alpha`, `xalpha`). To add an analyst, subclass
`analysts.Analyst` (`name`, `role`, `instructions`, `untrusted_keys`, `gather`, `rules`,
`abstain`). The trader's 0.75x size cut on a poor track record is behind
`config["rules"]["track_record_cut"]` (default `True`). `FundamentalsAnalyst.rules` scores
P/E against a sector benchmark only when the data carries `sector_pe` (real-data providers
supply none; the synthetic one does). It abstains when the report is older than
`STALE_REPORT_DAYS` (120; `lag_days`), skips a term whose window lags `report_period_end`
by more than `STALE_WINDOW_DAYS` (100) — `revenue_period_end` for growth,
`eps_period_end` for the P/E term, `net_income_period_end` for the margin,
`ocf_period_end` for free cash flow — with a key point saying so, and abstains when no
term could be scored; a dict of metadata alone (`lag_days`, dates) is not a usable
fundamental.

### LLM (`agentic_trader.llm`, `agentic_trader.anonymize`)

| Name | Meaning |
|---|---|
| `LLM` | Protocol: `complete(system, prompt, *, deep: bool) -> str \| None` |
| `AnthropicLLM(config)` | Claude through the Anthropic SDK: `quick_think_llm` / `deep_think_llm`, `deep_effort` / `quick_effort` (validated at construction: a value outside `EFFORT_LEVELS` raises `ValueError`, it is never silently sent as `high`), `llm_timeout_s`, `llm_max_retries` (default 2: the SDK client is built with `max_retries=0` and `complete` runs its own retry loop, so every attempt is observed and billed), `llm_retry_backoff_s` (0.5; validated finite and `>= 0`; exponential with jitter, at most `MAX_RETRY_DELAY_S` = 8 s), refusal fallback; a rate limit (429) or overload (529) waits the server's `retry-after` / `retry-after-ms` header when the SDK exposes one and it is at most `MAX_RETRY_AFTER_S` = 60 s (`retry_after_seconds(error)`), else the backoff; returns `None` on refusal, rate limit, status or connection errors; records usage keyed by the served (dated) model id; `model_for(deep)`, `estimate_cost(deep)` (what one call on that tier is reserved at, see `llm_budget_mode` below; `ESTIMATED_INPUT_TOKENS` = 8000 of input). A request that times out is billed at a full `max_tokens` reply once per attempt |
| `request_shape(model, effort, max_tokens)`, `MODEL_CAPABILITIES`, `EFFORT_LEVELS` | The request body per model family: only parameters the family accepts (thinking / effort) are sent; an unknown id gets a plain request with one warning |
| `estimate_call_cost(model, max_tokens, input_tokens=8000)` | List-price maximum of one call |
| `BudgetedLLM(inner, max_calls=None, max_cost_usd=None)` | Passes calls through until the call cap or the dollar cap is reached, then returns `None`. Under a dollar cap each call *reserves* `inner.estimate_cost(deep)` before dispatch (`in_flight`, `reserved_usd`) and is refused when `spent + reserved + estimate >= cap`, so N workers cannot each slip one call past the cap. What is reserved is set by `llm_budget_mode`: `hard` (the default) reserves the input estimate plus a full `max_tokens` reply — the most the call can cost, and what a timed-out attempt is billed at — so spend never exceeds the cap and a cap that cannot afford one such call refuses that tier before any spend; `estimate` reserves the input estimate plus `llm_reserve_output_tokens` (2000) and is a soft cap: spend can overshoot by up to the calls in flight × (`max_tokens` − reserve) × the output price. A served model id with no list price exhausts the budget (fails closed); an inner model without `estimate_cost` reserves nothing. `calls`, `refused`, `spent_usd`, `exhausted_for(deep)` (the cap cannot afford one more call on that tier, reservation included — exactly when `complete` would refuse it), `exhausted` (= `exhausted_for(True)`, the deep tier), `usage` |
| `budget_llm(llm, config)` | Wraps `llm` when `max_llm_calls` and/or `max_llm_cost_usd` is set (idempotent); raises `ValueError` at construction when a dollar cap is set with an unpriced configured model id (so does `get_llm`) |
| `UsageTracker` | Thread-safe tokens and outcomes per serving model; `calls`, `cost_usd`, `add_estimate`, `unpriced_models`, `timeouts`, `summary()` (includes `timeouts` and `unpriced_models`) |
| `get_llm(config)`, `llm_usage(llm)` | Build from config; usage summary or `None` |
| `extract_json(text)` | The first JSON object in a reply, or `None`; rejects bare `NaN` / `Infinity` |
| `Anonymizer` | Replaces symbols, names, dates and price levels in prompts and restores them in replies; on with `llm_anonymize`. `facts(dict)` is an allow-list: price-like keys are rebased, dimensionless keys pass, everything else (revenue, EPS, market cap, sector strings, peer lists) is dropped |

### Data (`agentic_trader.data`)

`MarketDataProvider(config)` contract: `history(instrument, start, end)` (OHLCV through
`clean_ohlcv`), `news` and `social(instrument, as_of, lookback_days)` (published ≤ `as_of`),
`fundamentals(instrument, as_of)`, `macro(instrument, as_of)`, `carry_series(instrument,
dates)`, `risk_free_series(dates) -> np.ndarray` (annual fractions, NaN where unknown;
implemented on the base class from `config["cash_leg"]`); `real_world` class attribute;
`macro_sources`, a per-provider tally `{"fred" | "static" | "none": count}` of what every
`macro()` answer was sized on; `reconfigured(config) -> MarketDataProvider`, the same market
data under another configuration (`cash_leg`, `edgar` and the FRED/FX settings are read from
the provider's own config, so a run that overrides one of them needs a provider built from
its config rather than a shared one: the base class builds a fresh provider, `YahooProvider`
returns one that shares the bars, headlines and corporate actions already downloaded, with
its own EDGAR client and `macro_sources` tally). Implementations: `SyntheticProvider`,
`YahooProvider`, `CSVProvider`; `get_provider(config)`, `PROVIDERS`.

`base.fx_rates(instrument, dates, config, real_world) -> (base_rate %, quote_rate %, source)`
is the single resolver behind both `macro()` (via `base.fx_macro`) and `carry_series()`: the
static config table on synthetic data or `fx_macro_source="static"`, FRED `series_asof`
otherwise. In FRED mode a stale, discontinued or unlisted leg is NaN at that date — never
the static table, whatever the wall-clock date — so `fx_macro` returns `{}` (the macro
analyst abstains, the FX strategic weight is 0) and the carry credited is 0 on the same bar.
Every non-empty macro dict carries `macro_source`. `base.cash_rates(dates, config,
real_world, mode=None)` implements `risk_free_series`: `cash_leg` `auto` (FRED 3-month bill
`DTB3` with a 1-day publication lag on real-world providers, `risk_free_annual` on synthetic
and CSV data), `fred`, `static` or `off` (NaN everywhere; the engine credits nothing).

`YahooProvider.history` downloads the union of every range asked so far, so a walk-forward
caller (or the cross-sectional analyst asking for 45 peers) never triggers a download per
step; `clip_history` applies the point-in-time cut at the requested end. It never serves or
caches a bar dated today or later, where "today" is the exchange's calendar date in New
York, never the host's: a bar dated D is served once it is D+1 in New York (which also
lies after the 17:00 New York roll of the FX day, so one rule covers both asset classes),
a request ending today ends at yesterday's complete bar, corporate actions are
re-downloaded once per exchange day, and an empty download raises `ValueError`;
`yahoo._today()` (New York) and `yahoo._now()` are the patchable clock, and the CLI's
default `--date` is `cli.common.default_as_of()`, New York's yesterday, on the same rule.
`YahooProvider` serves historical **fundamentals and news from SEC EDGAR**
when a contact User-Agent is configured (`EDGAR_USER_AGENT="Name email@domain"` in the
environment or `.env`, or `config["edgar_user_agent"]`; the SEC refuses requests without
one). `edgar=False` or `--no-edgar` turns it off; `edgar_cache_dir` / `--edgar-cache` caches
every endpoint call as JSON on disk; `edgar_ciks` overrides ticker → CIK (predecessor filers
after a reorganisation; `XOM` is shipped); `edgar_cache_max_age_days` (7; `None` = forever)
re-fetches cached endpoint files older than that, so a reused cache cannot hide new filings
from a live decision. Without a contact, both fall back to the Yahoo-only behaviour with one
warning. `csv_provider.one_basis` puts all four price columns of a CSV on one basis (with
`Close` and `Adj Close` both present, O/H/L/C are scaled to the adjusted basis; with only
`Adj Close` the raw open/high/low are dropped with a warning; a row with a blank
`Adj Close` is kept on the nearest row's factor). `Volume` follows splits only:
`split_factor(factor)` reads a day-over-day jump of the `Adj Close / Close` factor above
`SPLIT_JUMP` (5%) as a split and `one_basis` divides `Volume` by that component alone, so
`Close × Volume` (dollar volume, ADV, the impact ratio) stays as traded across a split
while the dividend drift never touches the share count (a dividend payer's volume is served
as traded; a special dividend above 5% would be read as a split). `clean_ohlcv` drops a
bar whose `Close` is not finite and repairs `+inf` open/high/low.

`edgar.EdgarClient(user_agent=None, cache_dir=None, fetch=None, min_interval=0.11, ciks=None, cache_max_age_days=7.0)`:
`cik(ticker)`, `profile(ticker)` (name, SIC), `filings(ticker)` (every filing with its date, form,
8-K item codes and accession), `facts(ticker)` (every XBRL fact as a long frame with the date it
was *filed*), `news(ticker, as_of, lookback_days) -> list[NewsItem]` (8-K items mapped to
headlines with a mild tone score, periodic and ownership filings, insider Form 4 counts; routine
prospectus supplements are excluded) and `fundamentals(ticker, as_of, price=None, splits=None) -> dict`
(`report_period_end`, `filed`, `lag_days`, `revenue_ttm`, `revenue_growth_yoy`, `net_margin`,
`eps_ttm`, `pe_ratio`, `debt_to_equity`, `fcf_yield`; `eps_surprise` and `insider_net_buying`
are `None` — EDGAR has no consensus data — and funds/trusts (SIC 6221, index ETFs) return `{}`).
Four keys are present only when a live series' latest four-quarter window ends before
`report_period_end`: `revenue_period_end`, `net_income_period_end`, `eps_period_end` and
`ocf_period_end` (ISO dates; the figure served is that older window's). `net_margin` needs the
revenue and net-income windows to end together, so it is absent whenever one lags the other;
`fcf_yield` is present only when the filer never reports capital expenditure (then FCF =
OCF) or the capex and OCF windows end on the same date — a reported capex series with no
four-quarter window ending with the OCF window removes `fcf_yield`, not capex.
`price` must be the close *as traded* on `as_of` and `splits` maps split ex-dates to ratios: every
EPS and share-count print is brought to the `as_of` share basis (`rebase_per_share`) before quarters
are mixed, which is what `YahooProvider` supplies from a second, unadjusted download
(`as_traded_close`, `splits`).

Point in time means: a fact or filing exists at `as_of` iff `filed <= as_of`; where a span was
printed more than once by then, the value used is the latest print filed on or before `as_of`
(the first print for the newest quarter; restated comparatives for older ones, as the market
held them). Quarterly flows are rebuilt separately per *concept* and per *reporting basis*
(`quarterly_table(known, tags, units=None, positive=False, notes=None) -> DataFrame[val, tag,
gen]`). A concept is one XBRL tag, or the tags a filer has proven to be one concept by
printing an identical `(start, end)` span under both with every shared span's latest print
agreeing within `TAG_EQUIVALENCE_TOLERANCE` (1%; a rename such as `Revenues` →
`RevenueFromContractWithCustomer...` merges, gross and net revenue tags do not); it is
labelled by its best-ranked tag. Within a basis generation the latest print of a span wins
while it differs from the value held by at most `BASIS_CHANGE_TOLERANCE` (5%, an ordinary
revision). A *material* change must be corroborated: a filing opens a new generation only
when it re-prints at least `BASIS_CHANGE_MIN_SPANS` (2) spans materially differently, or one
re-printed span is the year-earlier comparative of a span it prints for the first time (a
first-quarter 10-Q restates exactly one), *and* where that filing prints a year's annual
span with its four quarters they reconcile within `ANNUAL_CHECK_TOLERANCE` (2%) of the year's
scale — `max(|annual|, Σ|quarters|)` — for an additive flow (`PER_SHARE_CHECK_TOLERANCE`,
15%, for a per-share series). A candidate recast whose quarters do not reconcile with its
own annual span is mis-tagged and rejected: no generation opens, its material re-prints and
its quarters inside the mis-tagged year are dropped, and that year's Q4 is the annual span
less the quarters already held. A lone material re-print is ignored (the held value stands)
and remembered; a later filing that re-prints the span within 5% of a remembered value has
confirmed a correction by repetition, taken in place within the current generation (latest
confirmed print wins) and never counted towards a basis change. Every difference (Q4 = FY −
9M, year-to-date differencing, annual minus inside quarters) is taken within one generation
of one concept. For an additive flow a direct Q4 print that disagrees with the annual span by
more than 2% of that scale is replaced by FY minus the three quarters; a per-share series
(`USD/shares`) is never overridden by that cross-check. Trailing-year windows are tiled back
from the latest quarter end, each four consecutive quarters of one concept on one basis;
the concept of each window is the one the previous window used while it still covers the
new one (continuity across filings), rank decides only where no earlier choice covers, and
older windows are re-expressed in the newer window's concept where it covers them, so
growth compares like with like. Year-over-year growth needs the same concept and generation
for both years and two trailing years exactly a year apart. `quarterly_series` is the value
column; `ttm` sums four contiguous quarters; a reconstructed revenue quarter that is not
positive is rejected. Each data-quality case is logged once per (ticker, kind) through
`_warn_once`: `... Q4 taken as the annual figure less the three quarters`, `... re-printed
as <v> on <filed> against <held> held: a material change no other span corroborates;
ignored`, `... re-printed as <v> on <filed>, repeating a print ignored earlier: a correction
confirmed by repetition; taken in place of <held>`, and `... comparatives recast on <filed>
do not reconcile ...: mis-tagged; ignored`.

A flow series is dead — dropped from the report — only when no filing within
`MAX_FLOW_LAG_DAYS` (120) of the newest filing known printed a span of it (a retired tag, a
per-class series); a live series whose latest complete window lags `report_period_end` is
kept and flagged (`revenue_period_end`, `net_income_period_end`, `eps_period_end`,
`ocf_period_end`), and the analyst decides what to do with the lag. Per-share ratios are
absent when a balance-sheet instant is older than `MAX_INSTANT_AGE_DAYS` (400) at the
report period, market capitalisation is below 1% of trailing revenue or trailing EPS
exceeds half the price (a per-share fact of another share class); `SHARE_CLASS_RATIO`
(`{"BRK-B": 1500}`) converts the known multi-class filer first, looked up by the
normalised ticker so `BRK.B` and `BRK-B` both hit. The fundamentals `source` string is
`sec_edgar (point-in-time, as known at as_of)`. `EdgarClient.from_config(config)` returns
`None` when EDGAR is off or unconfigured; `edgar_user_agent(config)` resolves the contact.
At most ten requests per second are made and every response is memoised.

`fred.FredClient(vintages=False, vintage_step_days=31, cache_dir=None, fetch=None, cache_max_age_days=1.0)`:
`value_asof(spec, as_of)`, `series_asof(spec, dates)`, `rate(ccy, as_of)`, `inflation(ccy,
as_of)`, `vintage_date(as_of)`; `requests` counts downloads. With `vintages=True`, a
`FredSeries` marked `revised=True` (every `CPI_SERIES` entry) is read from the ALFRED vintage
current at `as_of` (`alfredgraph.csv?...&vintage_date=`), sampled every `vintage_step_days`
and cached in memory and, with `cache_dir`, on disk; `RATE_SERIES` (USD, EUR, GBP, JPY, CHF,
AUD, CAD, NZD, NOK — SEK's OECD series stopped in 2020-10 and is not listed) are never revised
and bypass vintages; `CASH_SERIES["USD"]` is `DTB3` (lag 1 day, max age 10). A cached
latest-vintage file older than `cache_max_age_days` is re-downloaded (ALFRED vintage
snapshots never expire); a download is parsed and validated before it is written, so an
HTML or empty body is never persisted; `fetch` replaces the HTTP download (tests, offline
recipes; the default uses a 30 s timeout). `default_client(config)` returns one client per
(`fred_vintages`, `fred_vintage_step_days`, `fred_cache_dir`, `fred_cache_max_age_days`).

### Memory (`agentic_trader.memory`)

`DecisionMemory(path=None, max_staleness_days=7)`: `record(symbol, as_of, action, weight,
price, summary, horizon_days=10, provider="", price_basis="")`, `resolve(symbol, as_of,
history, provider="", price_basis="", max_staleness_days=None) -> int`, `lessons(symbol,
as_of, k=3, provider=None)`, `track_record(symbol, as_of, k=20, provider=None)`;
`skipped_lines`, `max_staleness_days`. `resolve` takes the current `Close` history ending
at `as_of` and values each open entry from its entry bar to the bar `horizon_days` *trading
days* later on that one series, only for entries recorded by the same provider and price
basis (`memory.series_basis(provider)`); `max_staleness_days` (the instance's setting when
omitted; `TradingGraph` passes `max_data_staleness_days`) is how far the decision day may
sit after its entry bar. An entry the series cannot value — its entry bar predates the
window, or its exit bar never arrives — is expired (`MemoryEntry.expired`) once more than
twice its horizon has elapsed instead of being booked; another named provider's entries are
neither valued nor expired by a visit; an entry with no provider stamp (written before
v0.8) is never valued and is closed out that way by any named provider's visit past twice
its horizon, so a migrated log drains. A repeated decision for the same
symbol/date/provider replaces the earlier one. Lessons and the track record are
provider-scoped. The file is an append-only log (one entry line per decision, one
`{"resolve": key, ...}` line per resolution, `fsync` per write) under an in-process `RLock`
and a file lock on every append (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere), so
threads and separate `serve` processes sharing `results/memory.jsonl` cannot overwrite each
other; legacy whole-record files still load.

### Backtesting (`agentic_trader.backtest`)

#### `run_agent_backtest(symbol, start, end, config=None, rebalance_every=5, provider=None, llm=None, asset_class=None, on_decision=None, include_agent=True, capital_share=None, rebalance_offset=0) -> ComparisonReport`

Walk-forward backtest of the desk plus eight baselines (the six classic rules and, since v0.9, the `TSMOM(12-1)` and `Carry` streams). Before each decision the engine is
replayed on the bars so far and the desk is told the position it actually holds coming into
the bar: 0 after a stop, take-profit or ruin, otherwise the previous decision's units drifted
with the market. A keep is only what the PM's no-trade band marks (`FinalDecision.kept`,
which the band sets only for a position that passes every firm limit): the held weight is
then passed through unchanged and executed as no trade, even when drift has carried it past
the leverage cap; every other decision is a target the engine clamps to the cap and trades,
including a target equal to the cap while the held weight sits beyond it (a trim at that
decision bar). `rebalance_offset` shifts the decision grid by that many bars (the
rebalance-phase sweep). `capital_share` (a date-indexed fraction of `initial_capital`, set by
`run_portfolio_backtest` for a sleeve) scales the impact coefficient by `sqrt(share_t)`, the
impact of an account of `capital · share_t`. `ComparisonReport`: `instrument`, `dates`,
`prices`, `results` (`AgenticTrader`, `Buy&Hold`, `B&H vol-target`, `SMA(20/50)`, `MACD`,
`KDJ+RSI`, `ZMR`), `decisions`, `backtest_config`, `carry`, `agent_sources`, `rf` (the
per-bar risk-free rate the metrics used), `table()` (`CR%`, `AR%`, `Vol%`, `Sharpe`, `t(SR)`,
`Sortino`, `MDD%`, `Calmar`, `Win%`, `Exp%`, `Trades`, `Stops`, `Impact%`), `equity_curves()`,
`returns()`.

`risk_free_series(provider, dates, config)` is the cash-leg wiring: `provider.risk_free_series(dates)`
when the provider has it, else `config["risk_free_annual"]` everywhere; the series is passed
as `cash_rate` to every strategy and as the per-bar `rf` to the metrics, so every Sharpe,
Sortino and t-stat is on excess returns and idle cash is credited (an all-NaN series,
`cash_leg: off`, credits nothing and the metrics use the constant). AR%, CR% and Calmar
remain total-return quantities.

With `config["costs"]["impact_coeff"] > 0`, `impact_coefficients(full, ins, config,
periods_per_year=None)` builds the per-bar square-root impact coefficient `K_t = coeff ·
daily_vol_t · sqrt(capital / (price_t · ADV_t))` from trailing 20-day volatility and volume
(`capital` is `initial_capital`), and the same series is passed to the engine for the desk
and every baseline; the engine rescales `K_t` by `sqrt(equity_t / initial_capital)` so a
compounding account is charged for the notional it actually trades. FX gets impact only when
`costs["fx_adv_notional"]` is set. `costs.execution_algo` (`twap` or `ac` with
`costs.ac_kappa`) scales `K_t` by `algo.algo_cost_ratio`, the schedule's cost relative to
VWAP; `impact_coefficients` raises `ValueError` when that ratio is not a positive finite
number.

#### `run_portfolio_backtest(symbols, start, end, config=None, rebalance_every=5, provider=None, llm=None, on_decision=None, weighting="equal", cov_window=120, class_budgets=None, rebalance_offset=0) -> PortfolioReport`

One sleeve per symbol. The allocation (equal, `class_budgets`, or the time-varying schemes)
is computed from provider history *before* the sleeves run and each sleeve gets
`capital_share=alloc[s]`, so a 15-sleeve $1B book pays the impact of fifteen sleeves of the
sleeve's capital, not of the whole book. `weighting` ∈ `equal`, `inverse_vol`, `risk_parity`,
`min_variance`, `mean_variance`; the covariance is re-estimated from the trailing `cov_window`
returns at each rebalance and the same allocation is applied to every strategy. An active
sleeve whose returns have zero variance in the window (a frozen or forward-filled series)
is allocated 0 by every scheme, with a warning; only on a window the scheme cannot allocate
at all — no active sleeve with variance — does `construct` raise and the previous allocation
is kept.
`class_budgets` (e.g. `{"equity": 0.6, "fx": 0.4}`) allocates within each asset class by the
scheme and across classes by risk parity with those budgets (capital shares for `equal`).
`PortfolioReport`: `symbols`, `dates`, `returns`, `metrics`, `sleeves`, `weighting`,
`allocations` (per rebalance), `rf`, `table()` (`CR%`, `AR%`, `Vol%`, `Sharpe`, `t(SR)`,
`MDD%`, `Calmar`, `Exp%`), and `sharpe_difference(a="AgenticTrader", b="B&H vol-target",
block=10, n_boot=5000, seed=0) -> stats.SharpeDifference`, the portfolio-level Sharpe
difference over the *same days* with a paired block bootstrap over time on the same
excess-return convention as `metrics`. Portfolio metrics annualise with the largest
periods-per-year across sleeves (260 when an FX sleeve is present).

Also: `backtest_config_for(ins, config, prices, provider, start)` (sets `funded=False` for FX),
`baseline_weights(full, allow_short, target_vol=0.15, max_position=1.0, periods_per_year=252.0)`,
`AGENT` (`"AgenticTrader"`).

### Evaluation (`agentic_trader.evaluation`)

#### `evaluate(symbols=None, periods=None, config=None, rebalance_every=5, provider=None, progress=None, llm=None, workers=1, repeats=1) -> EvaluationResult`

`symbols` defaults to `UNIVERSES["all"]` (60 instruments); `periods` to the three
`DEFAULT_PERIODS` of `PERIODS` (`design` 2016-01-04 → 2021-12-31, `holdout` 2022-01-03 →
2026-06-30, `q1_2024` 2024-01-02 → 2024-03-28; `reserve` 2026-07-01 → 2026-09-25 is opt-in).
`workers > 1` runs backtests in parallel sharing one LLM budget. Failures are recorded in
`meta["errors"]`. Every row carries `universe` (`core`, `extended`, `extended-macro`, `other`)
from `universe_group(symbol)`. `EvaluationResult`: `rows`, `meta` (LLM usage, impact and
vintage settings, `repeats`, `prompts` (the prompt registry), `lookback_days`,
`alpha_lookback_days`, `edgar`, `timings` per job, `macro_sources` (the provider's
`{"fred" | "static" | "none": count}` tally for this run — cleared at the start of
`evaluate`, so a shared provider reports only the run's own calls; `{}` for a provider
without one), and `provenance`, see below),
`summary(period=None, universe=None)`, `head_to_head(universe=None)`, `slowest(n=10)` (the
slowest jobs from `meta["timings"]`), `to_json` / `from_json`.

`repeats > 1` runs the *agent* that many times per (period, symbol) — the baselines once —
and tags every row with `run`; `run_dispersion(metric="Sharpe", strategy="AgenticTrader")`
reports, per period, the mean across instruments of the across-run standard deviation and
range (the model's own variance; zero offline). `paired(baseline="Buy&Hold", metric="Sharpe",
period=None, universe=None, strategy="AgenticTrader", n_boot=10000, seed=0, cluster=True) ->
stats.PairedBootstrap` bootstraps the mean per-instrument difference across the universe
(pairs kept together; repeated runs enter as their mean). With `cluster=True` the
`asset_class:universe` labels are passed as `groups` and the two-stage cluster bootstrap
engages when at least five distinct groups are present (`--universe all`: 5 groups); with
fewer (core: 2, extended: 3) it falls back to the plain instrument bootstrap and says so
(`scheme`). `paired_table(metric="Sharpe", universe=None, strategy="AgenticTrader",
fdr_q=0.05, cluster=True)` does it for every period and baseline: `period`, `baseline`,
`n`, mean difference, 95% interval, two-sided `p`, `wins`, `scheme` (`instruments` \|
`clusters`), `groups` and `significant` (Benjamini-Hochberg at `fdr_q` on the unrounded
`p` across the table; a row with fewer than three paired instruments has `p` NaN and
neither counts towards the correction nor can be flagged). The v0.7 kwarg `stratify` is
gone (renamed, no shim).

`TRIALS` is the registry of every variant ever judged on the design period for the selection
statistics: 26 `Trial(name, version, overrides, recorded_mean_sharpe)` entries (v0.3's 16
rule variants, three alpha-analyst variants, four FX-carry settings, the cross-sectional
analyst, EDGAR off and v0.8's track-record cut off); `reproducible_trials()` returns the 24
that the current configuration can re-run (the two v0.4 alpha-analyst variants are
historical, carried by their recorded mean Sharpe); `trial_slug(name)` names a trial's
result file.

`CORE_UNIVERSE` (`equity`, `fx`: the 15 instruments every rule choice was made on),
`EXTENDED_UNIVERSE` (`equity`, `macro_etf`, `fx`: 45 instruments never used for a choice; judged
in v0.5.1 and v0.6 and re-measured in v0.8, so no longer unseen), `UNIVERSES` (`core`,
`extended`, `all`), `DEFAULT_UNIVERSE` (asset class → every symbol).

### Provenance (`agentic_trader.provenance`)

`package_version(pyproject=None) -> str` (the source tree's `pyproject.toml` first, then
`importlib.metadata`, else `0.0.0+unknown`); `git_info(root=None) -> (sha | None, dirty | None)`
(computed at every call — two short git subprocesses — so a long-running process stamps each
result with the tree as it is at write time; `None` without git); `provenance() -> dict` with `version`, `git_commit`,
`git_dirty`, `quant_backend`, `python`, `implementation`, `platform`, `machine`, `executable`
and `dependencies` (`numpy`, `pandas`, `anthropic`, `yfinance`, `pybind11`, `hypothesis`
versions). `evaluate()` and `calibrate()` write it into `meta["provenance"]`; every
`backtest`/`portfolio --out` CSV gets a `<stem>.provenance.json` sidecar
(`cli.common.write_sidecar(out, extra=None)`); the CLI header prints
`AgenticTrader | <command> | llm=.. data=.. quant=<backend> | v<version> <commit12>[+dirty]`;
the FastAPI app's `version` is the package version.

### Configuration and instruments

`make_config(overrides=None, **kw)` deep-merges over `DEFAULT_CONFIG`; `RULES_V02` reproduces
the v0.2 rules, `RULES_V03` the v0.3–v0.5.0 rules (no FX carry-neutral weight). The
important keys are listed in
[architecture/overview.md](../architecture/overview.md#configuration-surface). Keys added in
v0.8: `account_currency` (`USD`; the currency of `initial_capital`, notionals and tickets),
`cash_leg` (`auto` \| `fred` \| `static` \| `off`), `execution.fx_lot_size` (1000 base units),
`execution.max_order_notional` (`None` = `initial_capital · risk.max_position`; `0` is a
cap of 0, which freezes ticketing) and `execution.allow_external_plans` (`False`: a
`submit_order` ticket must cite a plan this desk produced), `fred_cache_max_age_days` (1),
`llm_max_retries` (2), `llm_retry_backoff_s` (0.5), `llm_budget_mode` (`hard` \|
`estimate`), `llm_reserve_output_tokens` (2000, `estimate` mode only),
`rules.track_record_cut` (`True`), `agentic.max_symbols_per_call` (60),
`agentic.max_plan_lookback_bars` (200 000 symbol-days), `agentic.max_retained_runs` (256),
`agentic.instance_id` (`None` = host:pid:random; a stable id is safe to reuse across a
rolling restart, since the sweep is lease-only), `agentic.lease_s` (90; must be `>= 1`,
refused by the harness and by `validate_app_config` otherwise). `static_macro_max_age_days`
no longer exists: the static table is never a fallback.

`Instrument(symbol, asset_class, base=None, quote=None)`: `is_fx`, `pip_size`,
`periods_per_year`, `yahoo_symbol`, `display`; `Instrument.parse(text, asset_class=None)`
treats six known currency letters, "/" and "=X" as FX intent and validates equity tickers.

## Part 2 — The agentic layer (`agentic_trader.agentic`)

### Domain (`domain.py`)

All frozen dataclasses unless stated.

| Type | Fields / notes |
|---|---|
| `Task(symbol, as_of, role=Role.TRADER, current_weight=None, question="")` | `id` (`TASK-…`), `created_at` |
| `Role` | `viewer`, `analyst`, `trader`, `risk`, `admin` |
| `Capability` | `read_market_data`, `read_knowledge`, `run_analytics`, `run_models`, `propose_trades`, `approve_trades`, `admin`; `ROLE_CAPABILITIES` maps roles to sets |
| `TaskState` | `CREATED`, `PLANNING`, `VALIDATING_PLAN`, `EXECUTING`, `AWAITING_APPROVAL`, `CRITIQUING`, `VALIDATING_EVIDENCE`, `FINALISING`, `COMPLETED`, `FAILED`, `CANCELLED`; `TRANSITIONS` is the legal-move table |
| `StepType` | `tool`, `agent`, `critic`, `validate`, `finalise`, `human_approval` |
| `PlanStep.make(type_, name, arguments=None, depends_on=(), rationale="", id_=None)` | `id` (`STEP-…`), `type`, `name` (tool name, agent stage or governance name), `arguments`, `depends_on`, `rationale` |
| `Plan(steps, source="canonical", notes=())` | `source` is `canonical`, `llm` or `llm+repaired`; `notes` are what the validator changed |
| `ToolAnnotations(read_only=True, risk=RiskLevel.LOW, required=frozenset({READ_MARKET_DATA}), evidence_type=EvidenceType.DATA)` | `RiskLevel` ∈ `low`, `medium`, `high` |
| `ToolDescriptor(name, server, description, input_schema, annotations)` | `name` is `server.tool` |
| `ToolRequest(tool, arguments, correlation_id, requested_by="harness")` | `request_id` property = digest of tool + arguments (the approval identity; the correlation id is deliberately excluded) |
| `ToolResult(request, ok, payload=None, error=None, elapsed_ms=0.0, attempts=1)` | |
| `Evidence.build(type_, source, summary, payload, correlation_id, arguments=None, prefix=None)` | `id` (`EV-…`), `digest` (SHA-256 of canonical JSON); `EvidenceType` ∈ `DATA`, `CALCULATION`, `DOCUMENT`, `MODEL_OUTPUT`, `DECISION`, `APPROVAL` (a failed call is recorded under the tool's own evidence type with a `FAILED …` summary) |
| `Finding.make(agent, claim, confidence, evidence_ids, numbers=None, tags=(), untrusted=False)` | `untrusted` marks a claim written from third-party text (an analyst with untrusted inputs, or a proposal or decision downstream of one): the critic and reporter prompts render it inside an untrusted-data fence, and the flag travels in `TaskRun.to_dict()["findings"]` and the report's `findings` section |
| `PolicyDecision(outcome, rule, reason)` | `PolicyOutcome` ∈ `ALLOW`, `DENY`, `REQUIRE_APPROVAL`; `allowed` |
| `canonical_json(obj)`, `digest(obj)` | Stable serialisation and hash |

### Tools (`tools.py`)

| Name | Meaning |
|---|---|
| `schema_from_signature(fn)` | JSON schema from type hints and defaults |
| `coerce_arguments(schema, arguments)` | Dates, integers, numbers, booleans, strings (≤ 2000 chars), arrays (≤ 1000); rejects extras and bad types with `ValueError` |
| `ToolRegistry()` | `register(server, fn, name=None, annotations=None, description=None)`, `@tool(server, read_only=True, risk=RiskLevel.LOW, ...)`, `register_descriptor(descriptor, fn)`, `get(name)`, `descriptors(server=None)`, `servers()`, `catalogue()`, `len()` |
| `ExecutorConfig(timeout_s=30.0, max_attempts=2, retry_backoff_s=0.2)` | `max_attempts` applies to read-only tools only |
| `ToolExecutor(registry, policy, evidence, role=Role.TRADER, gateway=AutoApprovalGateway(), tracer=Tracer(), config=ExecutorConfig(), task_id="adhoc")` | `call(name, correlation_id=None, requested_by="harness", **arguments) -> ToolResult`; `pending_approval` |
| `invoke_with_deadline(fn, args, timeout_s, name="tool")`, `ToolTimeout` | Runs one attempt on its own daemon thread with a hard deadline; a timed-out worker is abandoned (never kills it, never blocks another call) and counted in the `tool_calls_abandoned_total{tool}` metric |

Execution order in `call`: policy → coercion (so a bare or malformed order is `denied by
policy (argument_guard): bad arguments ...` and never parked) → gateway (when
`require_approval`) → run under a deadline → evidence record (a failure is recorded with a
`FAILED` summary) → metrics and span. Read-only tools get up to `max_attempts` attempts on transient errors; a
state-changing tool gets exactly one, and its timeout or transient failure is reported as
`outcome unknown, not retried`. The executor owns no thread pool: each call's thread ends
with the call.

### Desk tools (`servers.py`)

`lookback_days=None` (the default everywhere) resolves to `config["lookback_days"]` (400) for `market_data.history`, `quant.technical`, `quant.risk` and `portfolio.construct`, and to `config["alpha_lookback_days"]` (900) for `quant.alpha` and `quant.xalpha`.

`DeskTools(provider, config, knowledge=None, positions=None, capital=None)` and
`build_registry(tools)` give 16 tools on five servers (`market_data`, `quant`, `knowledge`,
`portfolio`, `execution`); the descriptors below are the registry's own schemas.
`DeskTools.for_book(positions)` is a view of the desk whose position book is that dict, read
live, sharing the provider, knowledge, capital, the plans it produced and the tickets it
wrote: the harness gives every run its own book (`TaskRun.positions`: the desk's positions
overlaid with the `positions` map passed to `submit` and the task's declared
`current_weight`), so concurrent tasks on one symbol never see each other's facts and nothing
a task declares is written to the desk's own book.

| Tool | Arguments | Evidence | Notes |
|---|---|---|---|
| `market_data.history` | `symbol, as_of, lookback_days=None` | DATA | OHLCV up to the close |
| `market_data.news`, `market_data.social` | `symbol, as_of, lookback_days=7` | DATA | Published ≤ `as_of` |
| `market_data.fundamentals`, `market_data.macro` | `symbol, as_of` | DATA | Point in time |
| `quant.technical` | `symbol, as_of, lookback_days=None` | CALCULATION | Indicator snapshot |
| `quant.risk` | `symbol, as_of, proposed_weight=0.0, lookback_days=None` | CALCULATION | Vol, VaR (both tails), CVaR, drawdown, ATR, limits |
| `quant.alpha` | `symbol, as_of, horizon=10, lookback_days=None` | CALCULATION | `latest` snapshot (its `combined` is the equal-weighted mean of every alpha, ungated), `ic` table (with the overlap-aware `t(IC)` and `up%`), `best` three (needs 300 bars) |
| `quant.xalpha` | `symbols, as_of, horizon=10, lookback_days=None` | CALCULATION | Cross-sectional scores per symbol, per-date IC table, best three, groups (≥ 3 symbols, 300 bars each) |
| `quant.baselines` | `symbol, start, end` | CALCULATION | Six baselines' CR, Sharpe, MDD |
| `knowledge.search` | `query, k=3` | DOCUMENT | `k` in 1–10 |
| `knowledge.list_documents` | — | DOCUMENT | |
| `portfolio.position` | `symbol` | DATA | Weight and capital; `pending` lists tickets recorded against the symbol |
| `portfolio.construct` | `symbols, targets, as_of, method="risk_parity", lookback_days=None` | CALCULATION | Trailing covariance |
| `execution.plan` | `symbol, as_of, target_weight, current_weight=None, algo=None` | CALCULATION | Simulated; no order. `current_weight=None` reads the run's position book, and an explicit value that disagrees with the book by more than 1e-6 is refused (`ValueError`); a change below one share or one lot is `trade: false`, not an error |
| `execution.submit_order` | `symbol, side, quantity, quantity_unit, notional, notional_currency, price, plan_id, note=""` | DECISION | High risk, not read-only: always needs approval; writes a ticket only |

`execution.plan` sizes at the `as_of` close (whole shares, or whole `execution.fx_lot_size`
lots of the base currency; the account currency is `config["account_currency"]`, and an FX
cross fetches the base→account rate from the provider) and simulates the fills on the first
session *after* `as_of` (arrival = that session's open); `costs.ac_kappa` is the
Almgren-Chriss urgency (`0` is TWAP; `None` means 3.0; `inf`/`nan` are refused). Its payload
is `{"trade": True}` plus `ExecutionPlan.to_dict()` — `plan_id`, `symbol`, `side`, `intent`,
`quantity`, `quantity_unit`, `notional`, `notional_currency`, `price`, `algo`, `slices`,
`reason`, `current_weight`, `target_weight`, `adv`, `participation_of_adv`, `ac_kappa`,
`lot_size` — with `as_of`, `ticketable` (the notional fits the desk's per-order cap),
`order_cap` (that cap), `simulated` and, when a later session exists, `execution_date` and
the `ExecutionReport` fields (`requested`, `executed`, `completion`, `is_bps`,
`opportunity_cost_bps`, `unfilled`, `close`, …); when the provider has no later session the
plan is returned with `simulated: false` and a `note`. A plan over the cap is returned with
`ticketable: false` and a note (reduce the change or split it) and is not recorded among
the plans `submit_order` accepts. Nothing to trade gives `{"trade": False, "reason": ...}`
with the reason `target equals current position` or `weight change <from> -> <to> is below
one share; nothing to trade` (or `... below one lot of 1000 <base>`), plus a note when a
long-only target was truncated to flat. `submit_order` refuses (`ValueError`) a side other
than `buy`/`sell`, a non-positive or non-finite number, the wrong unit for the instrument, a
notional currency other than the account's, a `plan_id` that does not verify against the
ticket's fields (`algo.plan_reference`, a checksum: editing a number invalidates it), a
quantity that is not whole shares / whole lots, a notional above `DeskTools.order_cap`
(`execution.max_order_notional`, `0` included, or `initial_capital · risk.max_position`;
`default_order_cap(config, capital=None)` is the helper), a sell that would take a
long-only book short, and — because the checksum is not authentication — a `plan_id` that
is not a plan this desk produced with exactly these fields, unless
`execution.allow_external_plans` is `True`. The ticket carries `id` (`ORD-…`), `plan_id`,
`symbol`, `side`, `intent`, `quantity`, `quantity_unit`, `notional`, `notional_currency`,
`price`, `position_before`, `position_after`, `plan_known` (the plan was produced by this
desk), `note`, `status`; writing it moves the run's book to `position_after` (the position
once the pending ticket fills), so a following `execution.plan` in the same run sizes the
second leg of a split order from it and `portfolio.position` reports the ticket behind the
weight. `ticket_from_plan(plan_payload, note="")` builds the `submit_order` arguments from
an `execution.plan` payload (and refuses one flagged `ticketable: false`).
`DeskTools.account_currency`, `plans` (plan id → payload), `positions` (the book) and
`order_cap` are the related attributes.

`RecordingProvider(executor, inner, correlation_id)` is a `MarketDataProvider` whose calls go
through the executor; `frame_from_payload(payload)` rebuilds a frame from a history payload.

### Policy (`policy.py`)

| Name | Meaning |
|---|---|
| `PolicyContext(request, tool, role, capabilities, config)` | What a rule sees |
| `DEFAULT_RULES` | `deny_list_rule`, `capability_rule`, `argument_guard_rule`, `read_only_rule`, `risk_level_rule`, `allow_rule`, in that order (the guards run *before* the approval decision, so a bad order is denied, never parked for a person); a rule returns a `PolicyDecision` or `None` to pass |
| `argument_guard_rule` | `symbol` and every element of a `symbols` list must parse and lie in `symbol_universe`; `symbols` must be a list of at most `max_symbols_per_call`; `quantity` finite and positive; `as_of`/`start`/`end` dates not in the future; `weight`, `target_weight` and `proposed_weight` finite and within `max_position`; `current_weight` is a fact about the book, not a proposal — finite (a `bool` is rejected) but never capped, so a position above the limit can be reduced; `lookback_days` in (0, 3660]; `notional` a positive finite number and ≤ `max_order_notional` when set |
| `PolicyEngine(config=None, rules=DEFAULT_RULES, role_capabilities=None)` | `evaluate(request, tool, role) -> PolicyDecision`; fails closed with rule `no_rule`; `decisions` (a `deque` of the last 1000). Config keys: `symbol_universe`, `deny_tools`, `max_position`, `max_symbols_per_call`, `max_order_notional` |
| `ApprovalGateway.decide(task_id, request, reason) -> bool \| None` | `AutoApprovalGateway` (True), `DenyApprovalGateway` (False), `QueuedApprovalGateway` (None until resolved; `pending(task_id=None)`, `all()`, `get(approval_id)`, `resolve(approval_id, approve, decided_by="human", note="")`, `withdraw(task_id, note="run finished")` (closes a finished run's pending requests: decided, `approved` None, `decided_by` `harness`), `forget(task_id)` (drops an evicted run's requests)); each has a `name` (`auto`, `deny`, `queued`) |
| `ApprovalRequest` | `id`, `task_id`, `request`, `reason`, `created_at`, `decided`, `approved`, `decided_by`, `note` |

### Evidence (`evidence.py`)

`EvidenceStore()`: `add`, `record(type_, source, summary, payload, correlation_id,
arguments=None)`, `get`, `resolve(ev_id)` (re-hashes the payload), `unresolved(ids)`,
`by_type`, `by_source`, `ids_since(n)`, `summary_rows()`, `len()`. Thread-safe.

### Planning (`planner.py`)

| Name | Meaning |
|---|---|
| `canonical_plan(task, instrument, analysts, config, registry)` | Knowledge search, alpha (when `use_alpha_tool`), analysts, debate, trader, risk, then the governance steps (12 steps for an FX task at the defaults) |
| `governance_steps()` | `critic`, `validate_evidence`, `finalise` |
| `propose_plan(llm, task, instrument, analysts, registry)` | Model-proposed raw steps (or `None`) and the raw reply |
| `validate_plan(raw_steps, task, instrument, analysts, registry, source="llm", config=None, book=None)` | Drops unknown tools and analysts, pins `symbol` and `as_of`, drops a model-written `current_weight` whenever the run's `book` holds the task's symbol (without a `book`, whenever the task declares one), so the book is the single source of the current position; repairs a string `symbols` to `[string]` and drops a step whose `symbols` is any other non-list shape; clips a `symbols` list to `agentic.symbol_universe` (`clip_symbols`: canonical spelling, duplicates removed, unparseable names dropped, a parallel `targets` list kept aligned) and truncates it to `agentic.max_symbols_per_call`, dropping the step only when nothing is left; coerces arguments, drops duplicate `(name, arguments)` tool steps before the step cap, refuses a plan whose tool steps would load more than `agentic.max_plan_lookback_bars` symbol-days (`plan_cost_bars`; alpha tools are costed at `alpha_lookback_days`), appends governance; every repair is a `Plan.notes` entry, never a reason to fail the run |
| `clip_symbols(symbols, universe) -> (kept, dropped, indices)` | The universe clip above; with no universe every parseable entry is kept |
| `make_plan(task, instrument, analysts, config, registry, llm, book=None)` | LLM plan when `agentic.llm_planner`, else canonical; always validated against the run's `book` |
| `step_cost_bars(step, config=None)`, `plan_cost_bars(steps, config=None)`, `max_plan_lookback_bars(config)` | The data budget |
| `plan_to_dict(plan)` | JSON |

### Harness (`harness.py`)

#### `AgentHarness(graph, policy=None, gateway=None, knowledge=None, positions=None, capital=None, store=None, sweep_interrupted=None)`

| Method | Meaning |
|---|---|
| `run(task) -> TaskRun` | `submit` then `resume` |
| `submit(task, positions=None) -> TaskRun` | Register a run in `CREATED` (and persist it) with its own position book (`TaskRun.positions`): the desk's book overlaid with `positions` (symbols parsed, weights finite, else `ValueError`) and the task's `current_weight`; the trading state, `portfolio.position`, `execution.plan` and `submit_order` all read it |
| `resume(run) -> TaskRun` | Drive to a terminal state or `AWAITING_APPROVAL`. Each run has a driving lock: a second caller returns at once with the run untouched, and a decision that lands while a driver is inside is picked up at the step (no lost wake-up). An `IllegalTransition` inside a drive ends in `FAILED` with the error |
| `cancel(task_id) -> TaskRun` | A parked run is cancelled immediately; a driven run at its next step |
| `pending_approvals(task_id=None)` | Queued gateway only |
| `decide_approval(approval_id, approve, decided_by="human", note="", resume=True) -> TaskRun` | Records APPROVAL evidence; with `resume=True` continues the run only when `continuation_due(run)` (parked in `AWAITING_APPROVAL` and undriven). `KeyError` for an unknown id (or one whose run was evicted: its requests are forgotten), `ValueError` — without consuming the approval — when its run is already terminal (a finished run's pending approvals are withdrawn) |
| `continuation_due(run) -> bool` | Whether a continuation may be scheduled for the run |
| `record(task_id) -> dict \| None` | The JSON record of a live run, a cached terminal one, or the store's current copy of a run another process drives |
| `archived_summaries()` | Summaries of the stored / archived runs |
| `close()` | Stops the heartbeat thread (call it when many harnesses are built on stores) |
| `runs`, `archive`, `store`, `registry`, `policy`, `gateway`, `tools`, `critic`, `metrics`, `owner`, `lease_s`, `max_retained`, `config` | State and collaborators |

The gateway defaults to `config["agentic"]["approval"]` (`auto` \| `queued` \| `deny`).
`metrics` is one process-level `Metrics` that every run's tracer writes to. Finished runs
beyond `agentic.max_retained_runs` are evicted from `runs` (into a bounded archive of
terminal records only, when there is no store); a terminal run drops its executor and
provider.

`store` (or `config["agentic"]["task_db"]`) is a `TaskStore`: every run is written at each
terminal / waiting transition and at the end of `resume`, with this instance as `owner`
(`agentic.instance_id`, default host:pid:random), and a heartbeat thread refreshes the
owner's lease every `lease_s / 3` — `heartbeat(owner, task_ids)` scoped to the runs this
instance actually drives, so a predecessor's orphans under a shared configured
`instance_id` are not kept alive. The sweep of interrupted runs is lease-only: on
construction (`sweep_interrupted`, default `config["agentic"]["sweep_interrupted"]`) and
periodically on the heartbeat thread, `mark_interrupted(lease_s=lease_s)` fails only records
whose heartbeat is older than `lease_s` and records with no owner or heartbeat at all
(written before leases existed); the owner never widens the sweep, so a live sibling's runs
survive and a restart under the same configured `instance_id` no longer fails its
predecessor's records at once — only once their lease has expired. A crashed service's
in-flight records are therefore failed after `lease_s` (90 s, at least 1) by any live
instance. Only terminal records are cached; anything
non-terminal is re-read from the store, so a sibling process serves `COMPLETED` and
`/report` once the owner finishes.

#### `TaskStore(path)` (`store.py`)

`save(run, owner=None)`, `save_record(dict, owner=None)`, `load(task_id)`, `load_all()`,
`summaries()`, `heartbeat(owner, task_ids=None) -> int` (refreshes the lease on the given
ids, or on every non-terminal record of the owner when omitted), `ownership(task_id) ->
(owner, heartbeat) | None`, `mark_interrupted(note="process restarted", owner=None,
lease_s=None) -> int` (neither owner nor lease = the ungated legacy sweep of every
non-terminal record; with `lease_s` only records whose heartbeat is older than that, or
that have no owner or heartbeat, are failed — `owner` never widens it and `owner` without
`lease_s` raises `ValueError`, as does a non-positive lease; every update is a
compare-and-swap on the state and version selected, so a record its owner finished in
between keeps its terminal state, and the return value counts rows actually failed),
`delete(task_id)`, `close()`, `len()`. The `tasks` table carries `owner` and `heartbeat` (added with `ALTER TABLE` on an
older file). `record_of(run)` is the record shape: `TaskRun.to_dict(include_report=True)`
plus `evidence_rows`, `spans` and `correlation_id`.

`TaskRun`: `task`, `state`, `plan`, `trading_state`, `findings`, `critic`, `report`,
`evidence`, `tracer`, `history` (state, time and note), `completed_steps`, `step_results`,
`errors`, `pending_step`, `cancel_requested`, `started_at`, `finished_at`, `correlation_id`,
`positions` (the run's book); `id`, `done`, `driving`, `decision`,
`to_dict(include_report=True)` (includes `evidence_count`, the `trace` summary and, on
every `findings` entry, its `untrusted` flag). `IllegalTransition` is raised for a move not in
`TRANSITIONS`. `wait_until_done(run, timeout_s=60.0)` blocks on a run driven by another
thread.

### Critic (`critic.py`)

`Critic(config, llm=None).review(state, findings, evidence, risk_facts=None) ->
CriticReport`. Checks: `evidence_resolves` (error), `model_rule_divergence`,
`analyst_contradiction`, `firm_limits` (error; the VaR tail follows the sign of the target),
`protective_levels` (error), `direction_vs_verdict`, `single_evidence_cap`, and, when the
model critique is enabled, `llm_critique_wellformed` (a warning when the model's critique is
malformed: `concerns` of any type and a missing or non-numeric `confidence_multiplier` are
tolerated, `llm_multiplier` is then `None`, and the run completes). `CriticReport`: `checks`
(`Check(name, passed, detail, severity)`), `multiplier` ≤ 1, `llm_concerns`, `llm_multiplier`,
`passed`, `failed`, `to_dict()`. The model critique's prompt (and the reporter's narrative
prompt) is prefixed with `FENCE_NOTE`; `findings_block(findings, confidence=True)` renders
trusted claims plainly and every `untrusted` claim inside one untrusted-data block after the
list, and `decision_untrusted(state)` (`state.untrusted_inputs`, or an untrusted proposal or
risk view) decides whether the decision rationale is fenced too — the `Decision: ACTION +w.`
line stays in the open.

### Reports (`reporter.py`)

| Name | Meaning |
|---|---|
| `collect_facts(state, critic) -> dict[str, float]` | Every number the narrative may use, counts included |
| `number_audit(narrative, facts, rel_tol=1e-6) -> list[str]` | Numbers that match no fact at the displayed precision (percent-aware) |
| `evidence_audit(narrative, findings, evidence) -> list[str]` | `EV-` ids that do not exist |
| `template_narrative(...)`, `llm_narrative(llm, ...)` | Deterministic or model summary |
| `build_report(task, state, findings, critic, evidence, llm=None) -> Report` | Audits run either way |
| `Report` | `task_id`, `symbol`, `as_of`, `facts`, `sections`, `narrative`, `warnings`, `narrative_source`; `to_dict()`, `to_markdown()` |

### Knowledge (`rag.py`)

`KnowledgeBase.from_dir(path=DOCS_DIR)`, `from_texts({id: text})`, `search(query, k=3,
min_score=0.05) -> list[Passage]`, `get(chunk_id)`, `documents`, `chunks`; `Passage`:
`chunk_id`, `doc_id`, `title`, `text`, `score`, `to_dict()`. `default_knowledge_base()` is
cached (11 documents, 76 chunks at v0.8.0). The embedder is a hashed TF-IDF (`HashedTfidf`),
so no network or model is needed.

### Tracing (`tracing.py`)

`Tracer(metrics=None).span(name, **attrs)` context manager with `Span.set`, `fail`,
`duration_ms`; `to_list()`, `summary()`; `Tracer.metrics` is a `Metrics` with `inc`,
`observe`, `counter`, `histogram(name, **labels)` (`{count, sum, min, max, buckets}`: a
histogram keeps cumulative counts for eleven fixed buckets, never the observations, so a
process-level instance stays the same size however many calls it has seen) and `render()`
(Prometheus text exposition: one `# TYPE` line per family, one sample per label set, label
values escaped, integral values rendered as integers and others at repr precision — a
counter of 1 234 567 is never `1.23457e+06`). `configure_json_logging(level)` switches
the root logger to JSON lines.

### MCP (`mcp_server.py`; needs `pip install "agentic-trader[mcp]"`)

| Name | Meaning |
|---|---|
| `build_mcp_server(registry, name="agentic-trader", executor=None, config=None, role=Role.TRADER, gateway=None, order_cap=None)` | An `MCPServer` with one tool per descriptor, named `server__tool`, annotated read-only/destructive with risk, required capabilities and evidence type in `meta`. Every call is routed through a `ToolExecutor` (`governed_executor(registry, config, role=Role.TRADER, gateway=None, order_cap=None)` when none is given: policy from the config's universe, deny list and notional cap — `order_cap` defaults to `default_order_cap(config)`, the desk's own cap — the configured approval gateway, an evidence store and a tracer) for the configured role; a refusal surfaces as an MCP `ToolError` with the policy reason. A `QueuedApprovalGateway` is refused (`ValueError`): nobody can answer a queue over stdio. `server.executor` is exposed |
| `python -m agentic_trader.agentic.mcp_server [--data synthetic\|yahoo\|csv] [--csv-dir DIR] [--role viewer\|analyst\|trader\|risk\|admin] [--approval auto\|queued\|deny]` | Serve over stdio with the desk's own `order_cap`; `agentic-trader mcp [--role R] [--approval auto\|queued\|deny]` runs the same (default role `trader`; without `--approval` the config's mode, `auto` by default). `queued` — on the flag or in the config — is refused with exit 2: nothing can decide a parked request over stdio. Stdio carries no identity, so one operator-chosen role and approval mode apply to the session; `--approval deny` is the lock-down form |
| `discover(server_args=None)` | The remote tools' names, descriptions, schemas and annotations; rows carry `annotated` and `read_only` is `True` only for an explicit `readOnlyHint` — for display, never for classification |
| `call(name, arguments, server_args=None)` | One remote call in a fresh server process; raises `RuntimeError` on a tool error |
| `registry_from_stdio(server_args=None, overrides=None, call_timeout_s=None, config=None) -> ToolRegistry` | Remote tools as local descriptors, so policy, coercion and evidence apply unchanged. Classification never reads the remote's annotations or `meta` (`classify_remote_tool(tool, override=None)`): every discovered tool is state-changing, risk `high`, requires `propose_trades` and yields DATA evidence whatever the server claims; the operator's `overrides` map (local `server.tool` name → `read_only`, `risk`, `required`, `evidence_type`) is the only relaxation, and `None` means `desk_overrides()` — this package's own catalogue, since the client only ever launches this package's server module; pass `{}` to relax nothing. The registry keeps **one** live server session (`StdioSession`: a single coroutine on its own thread, each request served as its own task so an abandoned call never delays the next; `registry.session.close()` ends it early, else it lives with the registry), so the remote desk keeps its plans, book and tickets across calls. `call_timeout_s` is the per-call deadline on the session: `None` takes `config`'s `agentic.tool_timeout_s` (30 s shipped; `make_config()` when `config` is not given), `math.inf` waits without limit, `<= 0` raises before a server is launched. At the deadline the SDK stops waiting and sends the server a `notifications/cancelled` courtesy notice, which is as far as the cancellation reaches: a synchronous desk tool on the server finishes anyway, so a timed-out state-changing call may still have written its ticket while the caller records an unknown outcome — reconcile through `portfolio.position` (its `pending` tickets) before re-submitting |

### HTTP API (`api.py`; needs `pip install "agentic-trader[api]"`)

`create_app(harness=None, graph=None, config=None, api_keys=None, workers=None,
queue_limit=None)` returns a FastAPI app. Without a `harness` it builds `AgentHarness(graph)`,
so the gateway follows `config["agentic"]["approval"]` (`make_config`'s default is `auto`;
the `serve` command's default is `queued`). Tasks run on a **bounded thread pool** (`workers`,
default `config["agentic"]["workers"]` = 4) rather than one thread per request; `queue_limit`
(default `config["agentic"]["queue_limit"]` = 64) caps the tasks accepted but unfinished, beyond
which `POST /tasks` answers `503` with `Retry-After: 5`. Every pool future has a done-callback
that logs its exception. `serve(host="127.0.0.1", port=8000, config=None, ssl_certfile=None,
ssl_keyfile=None, allow_dev_keys=False, processes=1)` runs it with uvicorn (`agentic-trader
serve [--workers N] [--processes N]`). `processes > 1` starts uvicorn worker processes from
`app_factory` (the configuration travels through a private temp file named by
`AGENTIC_TRADER_APP_CONFIG`) and **requires a task store** (`multiprocess_options` refuses
otherwise): the parent runs one lease-gated `mark_interrupted` sweep, each process owns its
live runs, every process serves every record through the store, and a cancel or approval
that lands on the wrong process answers `409`; a queued approval gateway therefore needs a
sticky load balancer or one process. Every route except `/health` and `/metrics` needs an
`X-API-Key` header mapped to a role (`config["agentic"]["api_keys"]`, development values by
default; an override *replaces* them).

`serve_options(host, config, ssl_certfile=None, ssl_keyfile=None, allow_dev_keys=False) ->
dict` validates the deployment posture: TLS needs both files and they must exist; a
non-loopback bind with any shipped or `dev-` key is refused unless `allow_dev_keys`; a
non-loopback bind without TLS logs a warning. `uses_dev_keys(api_keys)` is the check;
`validate_app_config(config, workers=None, queue_limit=None)` is run in the parent before
workers are forked.

| Method and path | Capability | Returns |
|---|---|---|
| `GET /health` | — | `{status, tasks, live, archived, persistent, tools, workers, queue_limit, in_flight, running, queued, worker_pid, approval, instance}` (`approval` is the gateway name, `instance` the harness owner id) |
| `GET /metrics` | — | One Prometheus exposition for the process: every run's tracer writes to the harness's `Metrics`, so each family appears once and counters are the service's totals (`# no tasks yet` before the first run) |
| `GET /tools` | any key | The catalogue |
| `GET /tasks` | any key | Archived and live tasks (`task_id`, `symbol`, `as_of`, `role`, `state`, `live`) |
| `POST /tasks` `{symbol, as_of, current_weight?, question?, positions?}` | `run_analytics` | `202 {task_id, state}`; the task runs on the pool; `positions` (`{symbol: weight}`) declares the run's own book, overlaid on the desk's and never written to it, and a bad map (unparseable symbol, non-finite weight) is `422`; `503` + `Retry-After` when `queue_limit` tasks are in flight |
| `GET /tasks/{id}` | any key | The task record without the report, plus `live`; records from the store are served the same way |
| `GET /tasks/{id}/report?format=json\|markdown` | any key | The report, or `409` before it exists |
| `GET /tasks/{id}/trace`, `/evidence` | any key | Spans and summary; evidence rows |
| `POST /tasks/{id}/cancel` | `run_analytics` | `{task_id, state}`; `409` for an archived task or one owned by another process |
| `GET /approvals` | `approve_trades` | Pending approvals (`id`, `task_id`, `tool`, `arguments` — the full ticket — `reason`, `created_at`); `409` when the gateway is not queued (`auto` or `deny`) |
| `POST /approvals/{id}` `{approve, note?}` | `approve_trades` | `{approval_id, approved, task_id, state, resumed}`; `resumed` is true when a continuation was scheduled on the pool (the run was parked and nobody was driving it); `404` unknown, queued on another process, or belonging to a run already evicted from memory; `409` already decided, or the run is finished or cancelled (its approvals were withdrawn; the request is not consumed) |

Errors: `401` missing or unknown key, `403` role lacks the capability, `404` unknown task,
`422` invalid body.

## Part 3 — Quant research

### Alphas (`agentic_trader.alpha`)

| Name | Meaning |
|---|---|
| `ALPHAS` | `tsmom_12_1`, `mom_20_vol`, `reversal_5`, `high_52w`, `donchian_20`, `macd_norm`, `rsi_contrarian`, `low_vol`, `carry` (FX); `EQUITY_ALPHAS`, `FX_ALPHAS` |
| `AlphaInputs.from_frame(df, instrument, carry=None)` | Arrays a signal reads |
| `compute_alphas(df, instrument, names=None, carry_series=None) -> DataFrame` | One column per alpha in [-1, 1] or NaN |
| `combine(signals, weights=None) -> Series` | Weighted mean ignoring NaN (equal weights by default) |
| `forward_returns(close, horizon)` | Return from t to t+horizon |
| `information_coefficient(signal, fwd, horizon=1, method="n_eff") -> (ic, t, n)` | Spearman IC with an overlap-aware t-statistic: `n_eff` (default) is `IC · sqrt(max(1, n / horizon))`, the same effective-sample rule `xalpha.ic_summary` uses; `newey_west` is a Bartlett HAC variant with `horizon − 1` lags, exposed for comparison only (it under-corrects on persistent alphas). `n` is the raw pair count; `horizon < 1` or an unknown method raises `ValueError`; `IC_T_METHODS` lists the two |
| `tercile_spread(s, fwd) -> float` | Top-tercile minus bottom-tercile mean forward return with terciles assigned by rank (`n // 3` bars each; bars tied at a boundary share its remaining mass as fractional weights), so a signal stuck at one value on most bars still has a top and a bottom |
| `significant_alpha_signal(latest, ic, min_tstat=2.0, min_n=30) -> (value \| None, names)` | The single source of truth for "the alpha analyst's view" (both `AlphaAnalyst` and `XAlphaAnalyst` use it): the \|IC\|-weighted mean of the alphas whose overlap-aware `t(IC)` clears `min_tstat` with at least `min_n` pairs, clipped to [-1, 1]; `(None, [])` when none does |
| `alpha_report(df, instrument, horizon=10, names=None, carry_series=None, decay_horizons=(1,5,10,21,42), weights=None) -> AlphaReport` | `table` (`IC`, `t(IC)` at the report's horizon, `n`, `hit%`, `up%` (share of positive forward returns on the same pairs, the base rate beside `hit%`), `tercile spread%`, `autocorr`, `coverage%`), `decay`, `correlations`, `signals`, `best(k)` |
| `alpha_snapshot(df, instrument, carry_series=None, weights=None) -> dict` | Latest values plus `combined` (`combine` of the latest values, ungated) |

### Cross-sectional alphas (`agentic_trader.xalpha`)

| Name | Meaning |
|---|---|
| `signal_panels(frames, instruments, names=None, carry=None) -> dict[str, DataFrame]` | Alpha name → (dates × symbols) panel of time-series values |
| `forward_return_panel(closes, horizon)` | Return from t to t+horizon per symbol |
| `cs_zscore(panel, groups=None, min_names=3, clip=3.0)`, `cs_rank(panel, groups=None, min_names=3)` | Per-day standardisation across names within each group, mapped to [-1, 1]; NaN below `min_names` |
| `cross_sectional_ic(signal, fwd, min_names=5) -> Series` | Per-date Spearman IC across names |
| `ic_summary(ic, horizon, periods_per_year=252.0)` | `mean IC`, `IC IR` (annualised for non-overlapping horizons), `t(IC)` (n / horizon independent observations), `IC>0%`, `days` |
| `quantile_spread(signal, fwd, horizon, quantile=0.2, min_names=5) -> Series` | Equal-weight top-minus-bottom quantile return, rebalanced every `horizon` bars |
| `xalpha_report(frames, instruments, horizon=10, names=None, carry=None, groups=None, decay_horizons=(1,5,10,21,42), quantile=0.2, min_names=5, weights=None, standardise="zscore") -> XAlphaReport` | `table` (IC summary, `spread%/period`, `spread t`, `breadth` per alpha and `combined`), `decay`, `correlations`, `spreads`, `signals`, `groups`, `best(k)`. `groups` defaults to the asset class |
| `xalpha_snapshot(frames, instruments, names=None, carry=None, groups=None, weights=None) -> dict` | Symbol → latest cross-sectional score per alpha plus `combined` |

### Execution (`agentic_trader.algo`)

| Name | Meaning |
|---|---|
| `volume_profile(kind, n)`, `synthetic_intraday_bars(day, n, kind="equity", seed=0)` | U-shaped (equity) or session-weighted (FX) profile; Brownian-bridge bars consistent with the daily bar, with `VWAP` |
| `twap_schedule(total, n)`, `vwap_schedule(total, profile)`, `pov_schedule(total, volumes, participation, cap=0.2)`, `almgren_chriss_schedule(total, n, sigma_session, eta, risk_aversion)` | Slice quantities |
| `algo_cost_ratio(algo, n, kind, kappa=3.0)` | A schedule's square-root-impact cost relative to VWAP on the same session (`twap`, `ac` with the dimensionless urgency `kappa`; `plan_execution` uses 78 equity / 288 FX slices); what `costs.execution_algo` scales the backtester's `K_t` by |
| `simulate_execution(schedule, bars, side, algo="custom", spread_bps=2.0, impact_coeff=1.0, daily_vol=0.02, adv=None, requested=None) -> ExecutionReport` | Fills at bar VWAP plus half-spread and per-slice impact `impact_coeff · daily_vol · sqrt(q_i / V_i)` with `V_i` the bar's own volume (FX without volume: `adv / n` when a notional ADV in base units is given, else 0); a slice is capped at the bar's volume and a zero-volume bar fills nothing, so VWAP reproduces `daily_vol · sqrt(Q / ADV)` at any slice count. `requested` is the parent order (both callers pass `plan.quantity`): `completion = executed / requested`, and `is_bps` is the Perold shortfall on the requested quantity — the executed leg plus the unfilled remainder marked at the session `close` against arrival, the latter reported separately as `opportunity_cost_bps` and `unfilled`. Fields: `side`, `algo`, `requested`, `executed`, `arrival`, `close`, `avg_price`, `session_vwap`, `is_bps`, `opportunity_cost_bps`, `vs_vwap_bps`, `spread_cost_bps`, `impact_cost_bps`, `max_participation`, `fills`; `unfilled`, `completion`, `to_dict()` |
| `plan_execution(decision, instrument, current_weight, capital, last_price, adv=None, algo=None, slices=None, max_adv_participation=0.1, *, account_currency="USD", base_to_account=None, allow_short=None, lot_size=None, ac_kappa=3.0) -> ExecutionPlan \| None` | `notional = \|target − current\| · capital` in the account currency. Equity: `floor(notional / price)` whole shares. FX, in the *base* currency: `notional` when the base is the account currency (USDJPY on a USD account: 500 000 USD), `notional / price` when the quote is, and `notional / base_to_account` for a cross (EURJPY needs the EURUSD rate; `base_to_account_rate(provider, base, account, as_of)` reads the direct or inverse pair point in time, and without a rate the call raises `ValueError`), rounded down to whole `lot_size` units (the callers pass `execution.fx_lot_size`, 1000). The rounding happens once, here; the notional is recomputed from the rounded quantity. `None` when there is nothing to trade: the target equals the current position, or the change rounds down to zero shares / lots (logged at INFO); `ValueError` is reserved for invalid inputs — a non-positive `capital`, `last_price` or `lot_size`, an unknown algo, a missing cross rate, or an `ac_kappa` that is negative or not finite (`0` is TWAP, the default 3.0). `allow_short` (`None` = FX yes, equity no; the callers pass `risk.allow_short_*`) truncates a negative target to flat with the reason recorded (`intent` `sell_to_close`). FX → TWAP; equity → VWAP, or POV above the ADV threshold |
| `ExecutionPlan` | `instrument`, `side`, `quantity`, `quantity_unit` (`shares` or the base currency), `notional`, `notional_currency`, `price` (the reference close), `algo`, `slices`, `reason`, `current_weight`, `target_weight` (effective, after truncation), `intent` (`open_long`, `add_long`, `sell_to_reduce`, `sell_to_close`, `sell_short`, `add_short`, `reduce_short`, `buy_to_cover`, `reverse_to_long`, `reverse_to_short` or `none`, from `trade_intent(current, target, tol=1e-9)`), `adv`, `participation_of_adv`, `ac_kappa`, `lot_size`; `id` (`plan_reference(symbol, side, quantity, quantity_unit, notional, notional_currency, price)`, a checksum over the ticket fields), `to_dict()`, `schedule(bars, participation=0.1, kappa=None)` (the chosen algorithm's schedule; `ac` uses `quant.almgren_chriss(total, n, kappa)` with the dimensionless `kappa` defaulting to `ac_kappa`, so the schedule does not depend on the price level or the seed; 0 = TWAP) |

### Portfolio construction (`agentic_trader.portfolio`)

| Name | Meaning |
|---|---|
| `sample_cov`, `ewma_cov(returns, halflife=60.0)`, `ewma_weights(t, halflife)`, `ledoit_wolf_shrink(returns, cov=None, weights=None) -> (cov, delta)`, `estimate_cov(returns, halflife=60.0, shrink=True)` | Annualisation is the caller's; `construct` handles it. `ledoit_wolf_shrink` is the Ledoit-Wolf (2004) constant-correlation intensity for the estimator it is applied to: with `weights` (which needs an explicit `cov`, `ValueError` otherwise) the centring, `pi`, `theta` and `rho` are weighted averages and `kappa` is divided by the Kish effective sample size `1 / sum(w²)`, so `estimate_cov` shrinks the EWMA covariance with `ewma_weights(T, halflife)` at the EWMA's own effective sample; with equal weights it is the unweighted formula. Zero-variance columns shrink without NaN |
| `equal_weights(n)`, `inverse_vol_weights(cov)`, `risk_parity_weights(cov, budget=None, iters=500, tol=1e-10)`, `min_variance_weights(cov, cap=1.0, iters=2000, return_info=False)`, `mean_variance_weights(mu, cov, risk_aversion=5.0, cap=1.0, iters=2000, return_info=False)` | Long-only allocations summing to 1; `risk_parity_weights` raises `ValueError` on a non-finite covariance or one with no positive variance |
| `risk_contributions(w, cov)` | `vol`, `marginal`, `component`, `pct` |
| `construct(targets, returns, method="risk_parity", *, periods_per_year=252.0, halflife=60.0, shrink=True, max_weight=0.5, gross_cap=1.0, target_vol=0.15, risk_aversion=5.0, expected_returns=None, groups=None, group_budgets=None) -> PortfolioWeights` | `symbols`, `allocation` (the pre-vol-target split: sums to `gross_cap`, each ≤ the cap), `weights` (signed: `allocation · sign(target) · min(\|target\|, 1) · scale`), `method`, `expected_vol`, `contributions` (with an `allocation` column on the same convention), `diversification_ratio`, `correlations`, `scale` (the vol-target factor: `max(1, min(target_vol / vol, gross_cap / Σ\|w\|, cap · gross_cap / max\|w\|))`, so scaling up never breaks the gross cap or the per-sleeve cap), `group_risk` (budget, allocation and realised risk share per group when `group_budgets` is given), `converged` (the iterative schemes hit their iteration cap otherwise); `to_dict()`. Every scheme's allocation is projected onto the capped simplex (`max_weight`, raised to `1/k` when infeasible) rather than clipped and renormalised, so the cap is honoured exactly; `max_weight=1.0` leaves an already-feasible allocation untouched. With `groups` (symbol → group) and `group_budgets` (group → share of risk) the scheme allocates within each group and risk parity with the budgets allocates across groups from the full covariance, re-projecting when a budget would push a sleeve over the cap. An active sleeve whose returns have zero sample variance in the window (a frozen or forward-filled series) is marked inactive before any scheme runs, with a warning naming it, so every scheme allocates it 0 (on the group-budget path a group whose only sleeves are flat is dropped rather than failing risk parity for the whole book); it raises `ValueError` only when no active sleeve has positive variance, when there are fewer than 20 rows, or when a scheme returns a non-finite allocation |
| `book_returns(weights, returns) -> ndarray \| None`, `book_var_95(weights, returns, alpha=0.95) -> float \| None` | The book's daily return series (zero-weight symbols dropped before alignment) and its historical VaR: `0.0` for an empty book, `None` below `MIN_BOOK_OBS` (20) aligned rows. A held symbol absent from `returns` still counts as zero-return here; `TradingGraph.scan` guarantees every held symbol has a column |
| `book_var_scale(symbol, proposed_weight, other_positions, returns, max_var_95, alpha=0.95, grid=41) -> (weight, book_var, note)` | Sizes `symbol` so the whole book's VaR stays within `max_var_95` by a grid search over (0, 1] of the proposal (book VaR is not assumed monotonic: a hedge can reduce it). When the rest of the book already breaches and some size of the proposal brings it within the limit, the largest such size is taken (`sized to the largest hedge`); when none does it is flattened; when the book VaR cannot be evaluated (a held symbol with fewer than 20 aligned observations, or the proposed symbol has no column) it fails closed and flattens with a `could not be evaluated` note that `PortfolioManager.guardrails` records |
| `METHODS` | The five method names |

### Statistics (`agentic_trader.stats`)

| Name | Meaning |
|---|---|
| `sharpe_stats(returns, periods_per_year=252.0) -> SharpeStats` | `n`, `mean`, `std`, `skew`, `kurt`, `sharpe` (per period), `sharpe_annual`, `t_stat`. The same zero-variance rule as `compute_metrics` (`sd > quant.ZERO_VARIANCE_TOL · max(1, \|mean\|)`, else 0) applies here, in `sharpe_ci_bootstrap` and in `paired_sharpe_block_bootstrap`, so a flat book reads 0 everywhere rather than ±1e17 |
| `sharpe_ci_bootstrap(returns, periods_per_year=252.0, n_boot=2000, block=10, ci=0.95, seed=0)` | Circular block bootstrap interval of the annual Sharpe |
| `probabilistic_sharpe(sr, n, skew=0.0, kurt=3.0, sr_benchmark=0.0)` | P(true Sharpe > benchmark); per-period inputs |
| `expected_max_sharpe(n_trials, var_trials_sr)` | The DSR benchmark |
| `deflated_sharpe(sr, n, n_trials, var_trials_sr, skew=0.0, kurt=3.0)` | PSR against the expected maximum |
| `min_track_record(sr, sr_benchmark=0.0, skew=0.0, kurt=3.0, confidence=0.95)` | Periods needed; `inf` when not above the benchmark |
| `selection_report(chosen_returns, trial_sharpes_annual, periods_per_year=252.0) -> dict` | All of the above for a chosen variant (the trials come from `evaluation.TRIALS`) |
| `paired_bootstrap(a, b, n_boot=10000, ci=0.95, seed=0, groups=None, min_groups=MIN_CLUSTER_GROUPS) -> PairedBootstrap` | Bootstrap over *instruments* of the mean paired difference `a − b` (one value per instrument for two strategies): `n`, `mean_diff`, `ci_low`, `ci_high`, two-sided `p_value`, `wins`, `significant` (the interval excludes zero), `scheme`, `n_groups`. NaN pairs dropped; fewer than three pairs gives NaN bounds and `p = 1`. With `groups` (one label per instrument) and at least `min_groups` (`MIN_CLUSTER_GROUPS` = 5) distinct labels among the finite pairs it runs a two-stage cluster bootstrap — whole groups drawn with replacement, then instruments within each drawn group, pooled mean — and reports `scheme="clusters"`; below that it is the plain instrument bootstrap (`scheme="instruments"`). Under a common factor (Monte Carlo in the docstring: 6 groups of 6, ρ = 0.6) the plain interval covers a true zero about 65% of the time and the cluster interval about 90%; at ρ = 0 the cluster scheme stays at or above nominal. With exactly five groups it is still somewhat anti-conservative under strong correlation: read few-group results with care |
| `benjamini_hochberg(p_values, q=0.05) -> ndarray[bool]` | Which p-values survive a false-discovery-rate control at `q`; only finite p-values count towards `m`, and NaN entries are never flagged |
| `paired_sharpe_block_bootstrap(a, b, periods_per_year=252.0, rf=None, block=10, n_boot=5000, ci=0.95, seed=0) -> SharpeDifference` | Sharpe(a) − Sharpe(b) over the *same days* (excess of the per-bar `rf` when given) with a paired circular block bootstrap over time: `n`, `sharpe_a`, `sharpe_b`, `diff`, `ci_low`, `ci_high`, `p_value`, `block`, `n_boot`. The interval a portfolio-level comparison needs, which the cross-instrument bootstrap cannot give |
| `rolling_var_forecast(returns, window=250, alpha=0.95) -> ndarray` | The historical VaR forecast *for* day `t` from `returns[t − window : t]` only (no look-ahead); NaN for the first `window` days |
| `var_backtest(returns, var_forecasts, alpha=0.95) -> VarBacktest` | Kupiec (1995) unconditional-coverage and Christoffersen (1998) independence tests of a VaR forecast series against realised returns (a breach is `r_t < −var_t`; NaN pairs dropped): `n`, `breaches`, `breach_rate`, `expected_rate`, `kupiec_lr`, `kupiec_p`, `christoffersen_lr`, `christoffersen_p`, `conditional_coverage_p` |

### Prompt registry (`agentic_trader.prompts`)

`prompt_registry(config) -> {"bundle": hash, "agents": {name: {"system", "template"}}, "shared": hash}` hashes
every agent's system prompt (the text) and prompt-building code (the source of the agent's
class chain; the user prompts are assembled inside their methods) with SHA-256 truncated to 16
hex characters: `analyst:technical` … `analyst:xalpha`, `bull`, `bear`, `facilitator`, `trader`,
`risk:aggressive|neutral|conservative`, `pm` and `firm_context`, plus the `shared` entry: the
source of every callable in `shared_prompt_code()` (`Agent.ask_json` and its helpers,
`fmt_facts`, `untrusted_block` and `state.fenced`, `TradingState`'s prompt facts, report
digest, lessons block, `untrusted_inputs` flag and debate / verdict / proposal / risk-views
blocks, the consensus score, policy passages, `risk_facts` and `risk._pct`, the anonymiser and
`is_scale_free_key`, `DecisionMemory`'s settle and `track_record` methods) and the value of
every constant in `shared_prompt_constants()` (the fence tag `state._TAG`, the anonymiser's
`PRICE_KEYS`, `SCALE_FREE_KEYS`, suffixes, prefixes and date pattern), looked up at call
time. Nothing else is covered — the `prompts.py` module docstring lists the gaps: unlisted
constants, provider fact dictionaries, the knowledge documents, and the agentic critic /
planner / reporter prompts. `prompt_bundle_hash(config)` is the single number that
identifies the whole prompt set; `evaluate` and `calibrate` record it, so two runs can be
shown to have used identical wording without reading transcripts. Every bundle hash
recorded before v0.8 differs from the current one (the `shared` entry did not exist), and
so does every hash recorded before the fix rounds widened `shared` to the fence helpers and
the anonymiser's key sets, although no prompt text changed.

### Calibration (`agentic_trader.calibration`)

`calibrate(graph, symbol, as_of, n=5, anchors=(None, -0.5, 0.0, 0.5), progress=None) ->
CalibrationReport` runs the desk `n` times at each anchor (`current_weight`; `None` = no book)
on one frozen state and collects every decision (`samples`: `run`, `anchor`, `action`,
`target_weight`, `confidence`, `approved`, `llm_share`, `trader_target`).
`dispersion(anchor=None)` gives runs, std and range of the target weight, action agreement with
the modal action and mean confidence; `anchoring()` the least-squares slope of the mean target
on the anchor (0 ignores the book, 1 keeps whatever it holds); `compare(earlier)` the drift
against a stored report on the same state (`same_prompts`, `mean_target_shift`, `std_change`,
`action_distribution_distance` — total variation in [0, 1] — and the anchoring-slope change);
`summary()`, `to_json` / `from_json`; `meta` carries `provenance`. CLI: `agentic-trader calibrate SYMBOL --date --n --anchors
none,-0.5,0,0.5 [--compare earlier.json] [--out report.json]`. Offline the rules are
deterministic (dispersion 0, agreement 1); the harness exists for the LLM desk.

### Quant core (`agentic_trader.quant`)

`quant.BACKEND` is `"cpp"` or `"python"`; `AGENTIC_TRADER_BACKEND=python` forces numpy. A
machine without the compiled core falls back to numpy with one `RuntimeWarning` at import,
silenced by setting that variable explicitly.

| Function | Returns |
|---|---|
| `sma`, `ema`, `rolling_std`, `zscore`, `rolling_max`, `rolling_min` `(x, n)` | array. One NaN rule on both backends: a windowed function is NaN while its window contains the gap; `ema` and the Wilder recursions (`rsi`, `atr`) reset at the gap and re-seed from the next `n` valid inputs, then recover |
| `rsi(close, n=14)`, `macd(close, 12, 26, 9)`, `bollinger(close, 20, 2.0)`, `atr(high, low, close, 14)`, `kdj(high, low, close, 9)`, `pct_change(x)`, `realized_vol(close, n, ppy)` | arrays / tuples |
| `spearman(x, y)` | float (NaN when a side is constant) |
| `almgren_chriss(total, n, kappa)` | slice quantities; finite for any `kappa` (the remaining inventory is `total · exp(−κt) · expm1(−2κ(1−t)) / expm1(−2κ)`, no `sinh` overflow) |
| `quantile`, `historical_var`, `historical_cvar`, `kelly_fraction`, `vol_target_weight`, `position_units`, `max_drawdown` | floats |
| `strat_buy_hold`, `strat_sma_cross`, `strat_macd`, `strat_kdj_rsi`, `strat_zmr` | weights; the crossovers hold no position when the two lines are within rounding noise of each other (`1e-12` relative), so both backends agree on flat windows |
| `run_backtest(prices, target_weights, config=None, *, carry, open, high, low, stop, take, rebalance, impact, cash_rate)` | `BacktestResult` (`equity`, `returns`, `positions` (the weight actually held over (t, t+1]), `traded` (\|dw\| per bar, exit fills at their fill bar), `exits` (1 where a protective level filled), `trades`, `metrics`, `stop_exits`, `impact_paid`, `ruined_at` (bar at which equity reached 0, or −1)) |
| `compute_metrics(equity, positions, periods_per_year, risk_free_annual=0.0, traded=None)` | `Metrics` (`cumulative_return`, `annualized_return`, `annualized_vol`, `sharpe`, `sortino`, `max_drawdown`, `calmar`, `win_rate`, `num_trades`, `turnover`, `periods`, `avg_exposure`, `sharpe_tstat`, `ruined`). `risk_free_annual` is a constant or a per-bar array (NaN → 0; an empty array means absent); Sharpe, Sortino and the t-stat are mean / std of the excess series `r_t − rf_t / ppy`. Zero-variance rule, identical on both backends: with `tol = ZERO_VARIANCE_TOL · max(1, \|mean\|)` (`ZERO_VARIANCE_TOL` = 1e-12, exported from `quant`), an excess series whose standard deviation is at most `tol` has `sharpe`, `sortino`, `sharpe_tstat` and `annualized_vol` of 0 — a flat book under a constant rate, a flat book earning exactly a varying cash leg, a curve compounding at exactly rf, and a constant *negative* excess return (formerly a Sortino of −sqrt(ppy)) — and when only the downside deviation is at most `tol` (every loss is rounding noise) `sortino` alone is 0 while Sharpe and the volatility keep their values. `traded` (|dw| per bar) gives turnover and the trade count exactly; without it (or with an empty array) both are inferred from changes in `positions`, which drift every bar under constant units, and a `RuntimeWarning` says so; `positions` must match `equity` in length (`ValueError`, both backends); statistics stop at the ruin bar |

Engine convention (documented in `cpp/include/at/backtest.hpp` and the `run_backtest`
docstring): a target is executed on a decision bar (the target changes, or `rebalance` is
set); fees and impact on \|dw\| come out of equity first and the target is a fraction of
post-cost equity, `E[t+1] = E[t] · (1 − k_in) · (1 + g) · (1 − k_out)`; between decisions
the *units* are held and the weight drifts as `w · gross / (1 + g)` with no trade and no
cost (carry accrues on the constant notional). The leverage cap applies to targets, so
`positions[t]` can exceed `max_leverage` between decisions; a raw target equal to the weight
currently held is a decision to keep the position and is executed as no trade even when
drift has carried that weight outside the cap (the cap binds on new targets, not on drift;
decision detection then tracks the clamped target so the keep holds on the following bars),
while any other target — one equal to the cap included — is clamped and traded.
`run_agent_backtest` passes the held weight only for a genuine keep (`FinalDecision.kept`).
`impact` is the per-bar
square-root coefficient `K_t`: a trade of `|dw|` at bar `t` costs `|dw|^1.5 · K_t ·
sqrt(equity_t / initial_capital)` of equity (an exit fill `|w|^1.5 · K_{t+1}` scaled the same
way); NaN = none. `cash_rate` is the annual risk-free rate credited on idle cash: `(1 − |w|)`
of the account when `config.funded` (equities), the whole account for FX forwards
(`funded=False`); NaN credits nothing; the metrics use it as the per-bar rf. A gap through
the take-profit fills at the open, as a gap through the stop does; only then does the
stop-first rule apply to the intrabar range. Ruin is judged per factor: when any one leg of
a bar consumes the whole account — the entry cost (`1 − k_in <= 0`), the move (`1 + g <=
0`), the exit cost (`1 − k_out <= 0`) — or the resulting equity rounds to `<= 0`, the bar's
return is −1, equity is 0, the position is written off and every later bar is flat
(`ruined_at`, `Metrics.ruined`); two negative factors never multiply into a surviving
account, and the non-ruin arithmetic is unchanged.

`BacktestConfig`: `initial_capital`=100000.0, `cost_bps`=1.0, `slippage_bps`=0.0,
`periods_per_year`=252.0, `carry_annual`=0.0, `borrow_annual`=0.0, `max_leverage`=1.0,
`allow_short`=True, `risk_free_annual`=0.0, `funded`=True (`backtest_config_for` sets
`False` for FX). Input contract (`quant.pycore.validate_backtest_inputs`, called by both
backends before the engine): prices and bar ranges positive and finite, `rebalance` finite,
`impact` NaN or a finite non-negative number, `carry`, `stop`, `take` and `cash_rate` NaN or
finite, every array one-dimensional and the same length as `prices` (`ValueError`
otherwise). Every window argument is validated at the facade (`operator.index`, no `bool`,
range `[1, quant.MAX_WINDOW]` = `2**31 − 1`; `ValueError` otherwise). Every function accepts
NaN, ±inf, empty and huge inputs without crashing: it returns a well-formed result or raises
`ValueError`, `quantile(x, NaN)` is NaN and `max_drawdown` ignores NaN — properties enforced
by `tests/test_fuzz.py`.

## Part 4 — CLI

```text
agentic-trader analyze   SYMBOL [--date D] [--position W] [--save] [--json] [--no-memory] [common]
agentic-trader task      SYMBOL [--date D] [--position W] [--capital X] [--role R] [--approval auto|queued|deny]
                                [--llm-planner] [--question TEXT] [--save] [--json] [--no-memory] [common]
agentic-trader scan      SYM1,SYM2,... [--date D] [--positions JSON] [--out file.csv|.json] [common]
agentic-trader backtest  SYMBOL --start D --end D [--every N] [--stops on|off] [--impact X] [--capital X]
                                [--execution-algo twap|vwap|ac] [--ac-kappa X] [--out curves.csv] [common]
agentic-trader baselines SYMBOL --start D --end D [--every N] [--stops on|off] [--impact X] [--capital X]
                                [--execution-algo twap|vwap|ac] [--ac-kappa X] [--out curves.csv] [common]
agentic-trader portfolio SYM1,SYM2,... --start D --end D [--every N] [--stops on|off] [--impact X] [--capital X]
                                [--execution-algo twap|vwap|ac] [--ac-kappa X]
                                [--weighting equal|inverse_vol|risk_parity|min_variance|mean_variance]
                                [--class-budgets equity=0.6,fx=0.4] [--out returns.csv] [common]
agentic-trader evaluate  [SYM1,...] [--universe core|extended|all] [--periods design,holdout,q1_2024,reserve]
                                [--every N] [--repeats N] [--workers N] [--impact X] [--capital X]
                                [--execution-algo twap|vwap|ac] [--ac-kappa X] [--out results.json] [common]
agentic-trader calibrate SYMBOL [--date D] [--n N] [--anchors none,-0.5,0,0.5] [--compare earlier.json] [--out report.json] [common]
agentic-trader alpha     SYMBOL --start D --end D [--horizon N] [--out signals.csv] [common]
agentic-trader xalpha    SYM1,SYM2,... --start D --end D [--horizon N] [--standardise zscore|rank] [--out scores.csv] [common]
agentic-trader execute   SYMBOL --target W [--current W] [--date D] [--capital X] [--algo twap|vwap|pov|ac]
                                [--participation P] [--ac-kappa X] [--spread-bps X] [--impact X] [--seed N] [common]
agentic-trader stats     returns.csv [--column NAME] [--ppy N] [--trials N] [--trial-sharpes a,b,c]
                                [--var-backtest] [--var-window N] [--var-alpha A]
agentic-trader tools     [--json] [common]
agentic-trader serve     [--host H] [--port P] [--approval auto|queued|deny] [--capital X] [--task-db FILE]
                                [--workers N] [--processes N] [--ssl-cert PEM --ssl-key PEM] [--allow-dev-keys] [common]
agentic-trader mcp       [--role viewer|analyst|trader|risk|admin] [--approval auto|queued|deny] [common]
agentic-trader info

common: [--asset-class equity|fx] [--data synthetic|yahoo|csv] [--csv-dir DIR]
        [--llm offline|anthropic] [--deep-model ID] [--quick-model ID] [--deep-effort low|medium|high|xhigh|max]
        [--rounds N] [--analysts a,b,c] [--xalpha-universe core|extended|all|SYM,...] [--allow-short] [--band X]
        [--max-llm-calls N] [--max-llm-cost USD] [--fred-vintages] [--fred-cache DIR] [--edgar-cache DIR] [--no-edgar]
        [--rules default|v02|v03] [--anonymize] [-v]
```

`--impact`, `--capital`, `--execution-algo` and `--ac-kappa` (the cost options) apply to
`backtest`, `baselines`, `portfolio` and `evaluate`; `--capital` on `execute`, `task` and
`serve` is the account size the desk tools size orders from (default: the config's
`initial_capital`, 100 000, in `account_currency`). `--stops`, `--band`, `--allow-short` and
`--impact` merge into the chosen `--rules` block rather than replacing it, so `--rules v02
--band 0.2` keeps v0.2's neutral weights. `stats --var-backtest` runs the Kupiec and
Christoffersen coverage tests of a rolling historical VaR forecast (`--var-window`, default
250; `--var-alpha`, default 0.95) against the same return series. `--ac-kappa` must be
finite and `>= 0` (`inf`, `nan` and negatives exit 2; `0` is TWAP). `--date` defaults to
New York's yesterday (`cli.common.default_as_of()`, the last date whose bar is complete
under the Yahoo rule), whatever the host's clock; `evaluate`/`calibrate` share it. `execute`
prints the capital and account currency, the quantity with its unit, the notional, the
intent, the plan id, the execution date (the next session) and `executed X of Y (Z%)`, with
an opportunity-cost clause only when at least one share or one lot went unfilled (a
schedule that sums to 222.99999999999997 of 223 shares is complete); when there is nothing
to trade it says why — `target equals the current position`, or `the change +a -> +b (N USD)
is below one share` sized from the effective (long-only-truncated) target, with the
truncation note when one applied. The `backtest` / `baselines` header's carry line reads
`carry +X% p.a. credited (+Y% on n/m accruing bars, 0 on k with no point-in-time rate)`
(`cli.research.carry_summary`): the mean over the T − 1 bars that accrue (the last bar
earns nothing) with NaN as 0, which is what the engine credits.

`cli.main(argv=None, *, dotenv=None)` reads `.env` only when it parses the real command line
(`argv is None`) or is asked with `dotenv=True`, and never when `AGENTIC_TRADER_NO_DOTENV`
is set. Exit status is 0 on success; invalid input gives 2 and a one-line `error:` message;
`scan` returns 1 when every symbol failed. `python -m agentic_trader` is equivalent.

## Part 5 — C++ API (`cpp/include/at/*.hpp`, namespace `at`)

`Series` is `std::vector<double>`.

| Header | Declarations |
|---|---|
| `indicators.hpp` | `sma`, `ema`, `rolling_std`, `zscore`, `rsi`, `macd → MACD{line, signal, hist}`, `bollinger → Bollinger{mid, upper, lower, percent_b}`, `atr`, `kdj → KDJ{k, d, j}`, `pct_change`, `realized_vol`, `rolling_max`, `rolling_min`, `spearman(x, y)`, `almgren_chriss(total, n, kappa)`; the NaN rule is documented in the header |
| `risk.hpp` | `quantile`, `historical_var`, `historical_cvar`, `kelly_fraction`, `vol_target_weight`, `position_units` |
| `strategies.hpp` | `strat_buy_hold`, `strat_sma_cross`, `strat_macd`, `strat_kdj_rsi`, `strat_zmr` |
| `backtest.hpp` | `BacktestConfig` (incl. `funded`), `BacktestInputs{carry, open, high, low, stop, take, rebalance, impact, cash_rate}`, `Trade`, `Metrics` (incl. `ruined`), `BacktestResult` (incl. `traded`, `exits`, `impact_paid`, `ruined_at`), `run_backtest`, `run_backtest_ex`, `compute_metrics(equity, positions, ppy, risk_free_annual=0.0, traded={})`, `compute_metrics_rf(equity, positions, ppy, rf_series, traded={})`, `max_drawdown`; the engine convention (constant units, post-cost sizing, ruin floor, exit-fill order) is documented in the header |

Invalid inputs throw `std::invalid_argument` (surfaced as `ValueError` in Python). Link
against the `at_core` static library from `CMakeLists.txt`; `ctest` runs one registered
test, `at_core_tests`, whose `main` calls 25 test functions (`cpp/tests/test_core.cpp`).

### `at_backtest` (C++ CLI)

```text
at_backtest <prices.csv> [--fx] [--short] [--cost-bps X] [--carry X] [--ppy N]
```

The CSV needs a header with `Close` (or `Adj Close`); `High` and `Low` are optional and
are read only beside a raw `Close` — with only `Adj Close` the raw high and low would put
KDJ on two price bases, so the bar range collapses to the close; at least 60 rows. It
prints CR, AR, Sharpe, MDD, win rate and trades for the five rule-based baselines. `--fx`
enables shorts and 260 periods per year.
