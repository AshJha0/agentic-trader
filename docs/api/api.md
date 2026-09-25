# API reference

This reference covers the public Python API, the quant functions, the CLI, the C++ API and
the standalone C++ tool. Anything not listed here is internal and may change.

```python
from agentic_trader import (TradingGraph, run_agent_backtest, run_portfolio_backtest,
                            ComparisonReport, PortfolioReport, evaluate, EvaluationResult,
                            make_config, DEFAULT_CONFIG, RULES_V02, Instrument, Action,
                            FinalDecision, TradingState)
```

## Orchestration

### `TradingGraph(config=None, provider=None, llm=None, memory=None, on_event=None)`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `config` | `dict \| None` | `DEFAULT_CONFIG` | Deep-merged over the defaults with `make_config` |
| `provider` | `MarketDataProvider \| None` | From `config["data_provider"]` | Data source |
| `llm` | `LLM \| None` | From `config["llm_provider"]` | Any object with `complete(system, prompt, *, deep) -> str \| None`; `None` means offline. Wrapped in `BudgetedLLM` when `config["max_llm_calls"]` is set |
| `memory` | `DecisionMemory \| None` | `DecisionMemory(config["memory_path"])` | Pass `DecisionMemory(None)` for in-memory only |
| `on_event` | `Callable[[str, str], None] \| None` | Logs at INFO | Called with `(stage, message)` for the stages `data`, `analyst`, `debate`, `trader`, `risk`, `decision` and `report` |

#### `propagate(symbol, as_of, asset_class=None, current_weight=None) -> tuple[TradingState, FinalDecision]`

Runs the whole firm once.

- `symbol`: a `str` (`"AAPL"`, `"BRK.B"`, `"EURUSD"`, `"EUR/USD"`, `"USDJPY=X"`) or an
  `Instrument`.
- `as_of`: a `datetime.date` or ISO string. Only data up to and including this close is used.
  A weekend or holiday uses the last close.
- `asset_class`: `"equity"` or `"fx"`, to override auto-detection.
- `current_weight`: the position held going into the decision. The trader and PM see it, and
  the no-trade band may keep it.

It raises `ValueError` in five cases:

- the symbol is invalid;
- fewer than 30 bars are available;
- the latest bar is more than `max_data_staleness_days` before `as_of`;
- `current_weight` is not finite;
- the provider raises it.

The decision is recorded to memory, and when `config["save_reports"]` is set,
`results/<SYM>/<date>/report.md` is written.

#### `scan(symbols, as_of, positions=None) -> pandas.DataFrame`

Runs `propagate` for each symbol, with `positions` mapping symbol to current weight
(case-insensitive). It returns one row per symbol with these columns:

- `symbol`, `asset_class`, `last`
- `action`, `target_weight`, `confidence`
- `stop_loss`, `take_profit`
- `debate`, `score`, `analysts_voting`
- `approved`, `adjustments`, `error`

A failing symbol gets `action == "ERROR"` and its message in `error`; the scan continues.

#### `save_report(state) -> pathlib.Path`

Writes `state.to_markdown()` to `results_dir/<SYM>/<as_of>/report.md`.

## Backtesting

### `run_agent_backtest(symbol, start, end, config=None, rebalance_every=5, provider=None, llm=None, asset_class=None, on_decision=None, include_agent=True) -> ComparisonReport`

Walk-forward backtest of the agent firm plus the six baselines over `[start, end]`, with
`lookback_days` of warm-up.

- **Each rebalance:** runs `propagate` with the position held at that point and keeps the
  decision's weight and stop/take levels until the next rebalance.
- **Stops:** enforced when `config["backtest"]["use_stops"]` is set.
- **FX carry:** taken per bar from `provider.carry_series`.
- **Memory:** in-memory for the run.
- **`include_agent=False`:** only the baselines run (the `baselines` CLI command).

It raises `ValueError` when `end < start` or the window has fewer than 2 bars.

### `ComparisonReport`

| Member | Meaning |
|---|---|
| `instrument` | `Instrument` |
| `dates` | `pd.DatetimeIndex` of the window |
| `results` | `dict[str, quant.BacktestResult]` with keys `AgenticTrader`, `Buy&Hold`, `B&H vol-target`, `SMA(20/50)`, `MACD`, `KDJ+RSI`, `ZMR` |
| `decisions` | `list[FinalDecision]` from each rebalance |
| `backtest_config` | The `quant.BacktestConfig` used (costs, shorting) |
| `carry` | The per-bar annual carry applied (FX), or `None` |
| `table()` | `DataFrame` with columns CR%, AR%, Vol%, Sharpe, t(SR), Sortino, MDD%, Calmar, Win%, Exp%, Trades and Stops, one row per strategy |
| `equity_curves()` / `returns()` | `DataFrame` of equity or daily returns per strategy, indexed by date |

### `run_portfolio_backtest(symbols, start, end, config=None, rebalance_every=5, provider=None, llm=None, on_decision=None) -> PortfolioReport`

Runs one walk-forward sleeve per symbol with equal capital and averages the daily returns
over the union of dates (a missing bar counts as a 0 return). It raises `ValueError` for an
empty list.

| `PortfolioReport` member | Meaning |
|---|---|
| `symbols`, `dates` | The inputs and the combined calendar |
| `returns` | `DataFrame` of daily portfolio returns per strategy |
| `metrics` | `dict[str, quant.Metrics]` per strategy |
| `sleeves` | `dict[str, ComparisonReport]` per symbol |
| `table()` | CR%, AR%, Vol%, Sharpe, t(SR), MDD%, Calmar, Exp% per strategy |

### `backtest_config_for(ins, config, prices, provider, start) -> quant.BacktestConfig`

Builds the cost and shorting model for an instrument:

- **Equity:** bps commission, slippage and borrow.
- **FX:** half-spread in pips converted to bps at `prices[0]`, plus slippage. A constant
  carry is set as a fallback; the backtest passes the per-bar series.

### `baseline_weights(full, allow_short, target_vol=0.15, max_position=1.0, periods_per_year=252) -> dict[str, np.ndarray]`

Target weights for the six baselines. `B&H vol-target` is
`min(max_position, target_vol / trailing 20-day vol)`, with 0 during warm-up.

## Evaluation

### `evaluate(symbols=None, periods=None, config=None, rebalance_every=5, provider=None, progress=None) -> EvaluationResult`

Runs `run_agent_backtest` for every (period, symbol) pair.

- **Defaults:** `symbols` defaults to `evaluation.DEFAULT_UNIVERSE` (10 equities, 5 FX
  pairs). `periods` defaults to `evaluation.PERIODS`: `design` 2016-01-04 → 2021-12-31,
  `holdout` 2022-01-03 → 2026-06-30, and `paper` 2024-01-02 → 2024-03-28.
- **Failures:** recorded in `meta["errors"]`, not raised.
- **Progress:** `progress` receives one line per run.

| `EvaluationResult` member | Meaning |
|---|---|
| `rows` | One row per (period, symbol, strategy), with CR%, AR%, Vol%, Sharpe, t(SR), MDD%, Calmar, Exp%, Trades and Stops |
| `meta` | Periods, symbols, rules, band, stops, errors and run time |
| `summary(period=None)` | Per (period, strategy): n, median Sharpe, and mean CR%, MDD%, Vol% and exposure |
| `head_to_head()` | Per (period, baseline): how many instruments the agent's Sharpe beats, and the median difference |
| `to_json(path)` / `EvaluationResult.from_json(path)` | Round-trip to disk |

## Configuration

### `make_config(overrides=None, **kw) -> dict`

Returns a deep copy of `DEFAULT_CONFIG` with `overrides`, then `kw`, deep-merged in. Nested
dicts merge key by key, so `make_config(risk={"max_position": 0.5})` keeps the other risk
keys.

`RULES_V02` is an override that reproduces the v0.2 rule behaviour:
`make_config(RULES_V02)`. See [architecture/overview.md](../architecture/overview.md#configuration-surface)
for the important keys, and `agentic_trader/config.py` for all of them.

## Instruments

### `Instrument(symbol, asset_class, base=None, quote=None)`

A frozen dataclass.

| Member | Equity | FX |
|---|---|---|
| `is_fx` | `False` | `True` |
| `pip_size` | 0.01 | 0.0001, or 0.01 for JPY-quoted pairs |
| `periods_per_year` | 252 | 260 |
| `yahoo_symbol` | `"AAPL"` | `"EURUSD=X"` |
| `display` | `"AAPL"` | `"EUR/USD"` |

`Instrument.parse(text, asset_class=None)` applies these rules:

- Six letters made of two known currency codes are FX unless `asset_class="equity"`.
- A "/" or "=X" marks FX intent, so an invalid pair raises instead of becoming an equity.
- Equity tickers must match `^?[A-Z0-9]{1,10}([.-][A-Z0-9]{1,5})?`, which covers AAPL,
  BRK.B, BRK-B, ^GSPC and 7203.T.
- It raises `ValueError` for empty input, invalid symbols and unknown asset classes.

## State documents (`agentic_trader.state`)

| Class | Fields |
|---|---|
| `Action` | `str` enum: `BUY` (hold long), `SELL` (short, or exit when shorting is not allowed), `HOLD` (flat) |
| `AnalystReport` | `analyst`, `signal` ∈ [-1, 1], `confidence` ∈ [0, 1], `summary`, `key_points`, `facts`, `source` (`rules` \| `llm`), `abstained` |
| `DebateTurn` | `speaker` (`bull` \| `bear`), `round`, `argument` |
| `DebateOutcome` | `winner` (`bull` \| `bear` \| `balanced`), `score` ∈ [-1, 1], `conviction` ∈ [0, 1], `summary`, `turns`, `source` |
| `TradeProposal` | `action`, `target_weight`, `confidence`, `entry_price`, `stop_loss`, `take_profit`, `horizon_days`, `rationale`, `source` |
| `RiskView` | `stance` (`aggressive` \| `neutral` \| `conservative`), `recommended_weight`, `argument`, `round`, `source` |
| `FinalDecision` | `symbol`, `as_of`, `action`, `target_weight`, `confidence`, `stop_loss`, `take_profit`, `rationale`, `approved`, `adjustments`, `source`; `to_dict()` returns JSON-ready output |
| `TradingState` | `instrument`, `as_of`, `history`, `current_weight`, `reports`, `debate`, `proposal`, `risk_views`, `decision`, `lessons`, `track_record`, `log`; `last_price`, `reports_digest()`, `to_markdown()` |

## Agents (`agentic_trader.agents`)

Every agent is constructed as `Agent(llm, config)`. `RiskAnalyst` also takes
`stance`: `RiskAnalyst(llm, config, "neutral")`.

| Class | Entry point | Tier |
|---|---|---|
| `TechnicalAnalyst`, `FundamentalsAnalyst`, `MacroAnalyst`, `NewsAnalyst`, `SentimentAnalyst` | `run(state, provider) -> AnalystReport` | quick |
| `BullResearcher`, `BearResearcher` | `speak(state, round, history) -> DebateTurn` | deep |
| `DebateFacilitator` | `judge(state, turns) -> DebateOutcome` | deep |
| `Trader` | `run(state) -> TradeProposal` | deep |
| `RiskAnalyst` | `speak(state, facts, round, history) -> RiskView` | deep |
| `PortfolioManager` | `run(state, facts) -> FinalDecision`; `guardrails(w, facts) -> (w, notes)`; `no_trade_band(w, current, facts) -> (w, note)` | deep |

Helpers:

- **Pipeline:** `run_debate(state, bull, bear, facilitator, rounds)`,
  `run_risk_team(state, analysts, pm, rounds)`,
  `researchers.consensus_score(state, weights, skip_abstained=False)`.
- **Trader:** `trader.protective_levels(direction, entry, atr, risk)`,
  `trader.sane_levels(direction, entry, stop, take, fallback)`.
- **Prompts:** `base.untrusted_block(label, lines)`.
- **Registry:** `ANALYSTS` maps analyst names to classes.

**Custom analysts.** Subclass `analysts.Analyst` and set `name`, `role` and `instructions`.
Put free-text fact keys in `untrusted_keys`. Implement `gather(state, provider) -> dict` and
`rules(facts, state) -> AnalystReport`, returning `self.abstain(reason, facts)` when there is
no data. The base `run()` handles the LLM call, validation and clipping.

## LLM (`agentic_trader.llm`)

| Name | Meaning |
|---|---|
| `LLM` | Protocol: `complete(system, prompt, *, deep: bool) -> str \| None` |
| `AnthropicLLM(config)` | Claude through the Anthropic SDK (details below) |
| `BudgetedLLM(inner, max_calls)` | Passes through the first `max_calls` calls, then returns `None`. Exposes `calls`, `refused` and `exhausted` |
| `get_llm(config)` | `None` for `offline`, `AnthropicLLM` for `anthropic` (wrapped when `max_llm_calls` is set); `ValueError` otherwise |
| `extract_json(text)` | The first JSON object in a reply, fenced or bare, or `None` |

`AnthropicLLM` in more detail:

- **Models:** `quick_think_llm` or `deep_think_llm`.
- **Thinking:** adaptive thinking and `output_config.effort` for every model except Haiku 4.5.
- **Timeout:** `llm_timeout_s`.
- **Refusal fallback:** the server-side fallback runs on `claude-opus-5` and `claude-fable-5-1`.
- **Failure handling:** it returns `None` on a refusal, or on a rate-limit, status or connection error.
- **Credentials:** read by the SDK from `ANTHROPIC_API_KEY` or an `ant auth login` profile.

## Data (`agentic_trader.data`)

### `MarketDataProvider(config)`

| Method | Returns | Contract |
|---|---|---|
| `history(instrument, start, end)` | OHLCV `DataFrame` with a `DatetimeIndex` | Inclusive of `start` and `end`; pass it through `clean_ohlcv` (required) |
| `news(instrument, as_of, lookback_days)` | `list[NewsItem]` | Published ≤ `as_of` |
| `social(instrument, as_of, lookback_days)` | `list[NewsItem]` | Published ≤ `as_of` |
| `fundamentals(instrument, as_of)` | `dict` | Point in time; `{}` when unknown |
| `macro(instrument, as_of)` | `dict` | For FX: `base_rate`, `quote_rate`, `rate_diff` and optionally the inflation pair, plus `source`. Default: `fx_macro` |
| `carry_series(instrument, dates)` | `np.ndarray` | Annual carry (decimal) known at each date; NaN if unknown; zeros for equities |

Other data API:

- **`real_world`:** a class attribute, `False` only for `SyntheticProvider`. It decides
  whether the static macro table may be used for historical dates.
- **`NewsItem(published, headline, source="", summary="", sentiment=None, tags=[])`.**
- **`clean_ohlcv(df)`:** sorts, deduplicates, drops non-positive closes, fills missing open,
  high and low from the close, widens impossible bars, strips time zones, and returns
  `Open, High, Low, Close, Volume` as floats.
- **`base.fx_macro(instrument, as_of, config, real_world)`:** the point-in-time macro rules
  (static / FRED / auto).
- **`fred.FredClient`:** `value_asof(spec, as_of)`, `series_asof(spec, dates)`,
  `rate(ccy, as_of)` and `inflation(ccy, as_of)`. `RATE_SERIES` and `CPI_SERIES` hold each
  series' lag and maximum age.

### Implementations and helpers

| Name | Notes |
|---|---|
| `SyntheticProvider(config)` | Deterministic, seeded by `synthetic_seed` and the symbol; `real_world = False` |
| `YahooProvider(config)` | Needs `yfinance`. Total-return prices, coverage-cached downloads. News only within 30 days of today; fundamentals only within 7 |
| `CSVProvider(config)` | Reads `<csv_dir>/<SYMBOL>.csv` (any column case, `Adj Close` accepted) and optional `<SYMBOL>_news.csv` |
| `get_provider(config)` | Builds a provider from `config["data_provider"]` |
| `PROVIDERS` | Registry of provider names to classes |

## Memory (`agentic_trader.memory`)

### `DecisionMemory(path=None)`

A JSONL-backed log with atomic writes when `path` is set; in-memory otherwise. Unreadable
lines are skipped and counted in `skipped_lines`.

| Method | Meaning |
|---|---|
| `record(symbol, as_of, action, weight, price, summary, horizon_days=10)` | Log a decision |
| `resolve(symbol, as_of, price) -> int` | Settle entries whose horizon has elapsed by `as_of`; returns the count |
| `lessons(symbol, as_of, k=3) -> list[str]` | The last *k* lessons resolved on or before `as_of` |
| `track_record(symbol, as_of, k=20) -> dict` | `{n, hit_rate, avg_pnl}` over directional calls, or `{}` |

## Quant (`agentic_trader.quant`)

`quant.BACKEND` is `"cpp"` or `"python"`. Set `AGENTIC_TRADER_BACKEND=python` to force the
numpy backend. Inputs are array-likes; outputs are numpy arrays or floats. Warm-up values
are NaN.

| Function | Returns |
|---|---|
| `sma(x, n)`, `ema(x, n)`, `rolling_std(x, n)`, `zscore(x, n)` | array |
| `rsi(close, n=14)` | array (Wilder) |
| `macd(close, fast=12, slow=26, signal=9)` | `(line, signal, hist)` |
| `bollinger(close, n=20, k=2.0)` | `(mid, upper, lower, percent_b)` |
| `atr(high, low, close, n=14)` | array (Wilder) |
| `kdj(high, low, close, n=9)` | `(K, D, J)` |
| `pct_change(x)` | array |
| `realized_vol(close, n, periods_per_year)` | array (annualised) |
| `quantile(x, q)` | float (linear, NaN-ignoring) |
| `historical_var(returns, alpha=0.95)`, `historical_cvar(returns, alpha=0.95)` | Positive loss fraction |
| `kelly_fraction(p, b)` | float (unclipped) |
| `vol_target_weight(signal, realized_vol_annual, target_vol, max_leverage)` | float (0 for NaN or zero volatility) |
| `position_units(equity, risk_fraction, entry, stop)` | float |
| `strat_buy_hold(close)` | weights |
| `strat_sma_cross(close, fast=20, slow=50, allow_short=False)` | weights |
| `strat_macd(close, fast=12, slow=26, signal=9, allow_short=False)` | weights |
| `strat_kdj_rsi(high, low, close, kdj_n=9, rsi_n=14, rsi_low=30.0, rsi_high=70.0, allow_short=False)` | weights |
| `strat_zmr(close, n=20, entry=1.0, exit=0.0, allow_short=False)` | weights |
| `run_backtest(prices, target_weights, config=None, *, carry=None, open=None, high=None, low=None, stop=None, take=None, rebalance=None)` | `BacktestResult` |
| `compute_metrics(equity, positions, periods_per_year, risk_free_annual=0.0)` | `Metrics` |
| `max_drawdown(equity)` | float |

`run_backtest` optional per-bar arrays (each must match the prices' length):

| Array | Meaning |
|---|---|
| `carry` | Annual rate; overrides `config.carry_annual`; NaN counts as 0 |
| `open`, `high`, `low` | Required when `stop` or `take` is given |
| `stop`, `take` | Absolute levels for the position held over (t, t+1]; NaN means none. Fill rules are in [DIAGRAMS.md](../DIAGRAMS.md#10-intraday-stop-and-target-fills) |
| `rebalance` | Non-zero where a new decision was made; it re-arms after a stop exit. Without it, the position re-arms when the target changes |

Prices must be positive and non-NaN; otherwise it raises `ValueError`.

The backtest types:

| Type | Fields |
|---|---|
| `BacktestConfig` | `initial_capital`=100000, `cost_bps`=1.0, `slippage_bps`=0.0, `periods_per_year`=252, `carry_annual`=0.0, `borrow_annual`=0.0, `max_leverage`=1.0, `allow_short`=True, `risk_free_annual`=0.0 |
| `BacktestResult` | `equity`, `returns`, `positions`, `trades` (`list[Trade]`, exits included), `metrics` (`Metrics`), `stop_exits` |
| `Metrics` | `cumulative_return`, `annualized_return`, `annualized_vol`, `sharpe`, `sharpe_tstat`, `sortino`, `max_drawdown`, `calmar`, `win_rate`, `num_trades`, `turnover`, `periods`, `avg_exposure` |
| `Trade` | `index`, `from_weight`, `to_weight`, `price` |

## CLI

```text
agentic-trader analyze   SYMBOL [--date D] [--position W] [--save] [--json] [--no-memory] [common]
agentic-trader scan      SYM1,SYM2,... [--date D] [--positions JSON] [--out file.csv|.json] [common]
agentic-trader backtest  SYMBOL --start D --end D [--every N] [--stops on|off] [--out curves.csv] [common]
agentic-trader baselines SYMBOL --start D --end D [--out curves.csv] [common]
agentic-trader portfolio SYM1,SYM2,... --start D --end D [--every N] [--stops on|off] [--out returns.csv] [common]
agentic-trader evaluate  [SYM1,SYM2,...] [--periods design,holdout,paper] [--every N] [--out results.json] [common]
agentic-trader info

common: [--asset-class equity|fx] [--data synthetic|yahoo|csv] [--csv-dir DIR]
        [--llm offline|anthropic] [--deep-model ID] [--quick-model ID] [--rounds N]
        [--allow-short] [--band X] [--max-llm-calls N] [--rules default|v02] [-v]
```

| Flag | Effect |
|---|---|
| `--date` | Decision date (default: yesterday) |
| `--position` / `--positions` | Current weight for `analyze`, or a JSON map for `scan` |
| `--save` | Write `results/<SYM>/<date>/report.md` |
| `--json` | Print only `FinalDecision.to_dict()` |
| `--no-memory` | Do not read or write `results/memory.jsonl` |
| `--every N` | Rebalance every N bars |
| `--stops on\|off` | Enforce decision stops and targets in the backtest |
| `--band X` | No-trade band around the current position |
| `--max-llm-calls N` | Hard cap on model calls; agents use rules beyond it |
| `--rules v02` | Reproduce the v0.2 rule set |
| `--periods` | Evaluation periods (`evaluate`) |
| `--out` | Write curves, returns, decisions or evaluation rows |
| `--rounds N` | Set both the debate and risk-discussion rounds (≥ 1) |
| `--allow-short` | Allow equity shorts |
| `-v` | INFO logging, per-decision lines and the traceback on errors |

Exit status is 0 on success. Invalid input (bad symbol, no or stale data, bad dates, bad
JSON) gives status 2 and a one-line `error:` message. `scan` returns 1 if every symbol
failed. `python -m agentic_trader` is equivalent to `agentic-trader`.

## C++ API (`cpp/include/at/*.hpp`, namespace `at`)

`Series` is `std::vector<double>`.

| Header | Declarations |
|---|---|
| `indicators.hpp` | `sma`, `ema`, `rolling_std`, `zscore`, `rsi`, `macd → MACD{line, signal, hist}`, `bollinger → Bollinger{mid, upper, lower, percent_b}`, `atr`, `kdj → KDJ{k, d, j}`, `pct_change`, `realized_vol` |
| `risk.hpp` | `quantile`, `historical_var`, `historical_cvar`, `kelly_fraction`, `vol_target_weight`, `position_units` |
| `strategies.hpp` | `strat_buy_hold`, `strat_sma_cross`, `strat_macd`, `strat_kdj_rsi`, `strat_zmr` |
| `backtest.hpp` | `BacktestConfig`, `BacktestInputs{carry, open, high, low, stop, take, rebalance}`, `Trade`, `Metrics` (incl. `avg_exposure`, `sharpe_tstat`), `BacktestResult` (incl. `stop_exits`), `run_backtest(prices, weights, cfg)`, `run_backtest_ex(prices, weights, cfg, inputs)`, `compute_metrics(equity, positions, ppy, rf)`, `max_drawdown(equity)` |

Invalid inputs throw `std::invalid_argument`: non-positive windows, mismatched lengths,
non-positive or NaN prices, and stops without OHLC. Link against the `at_core` static
library from `CMakeLists.txt`.

## `at_backtest` (C++ CLI)

```text
at_backtest <prices.csv> [--fx] [--short] [--cost-bps X] [--carry X] [--ppy N]
```

The CSV needs a header with `Close` (or `Adj Close`); `High` and `Low` are optional. It
needs at least 60 rows. The tool prints CR, AR, Sharpe, MDD, win rate and trades for the
five paper baselines. `--fx` enables shorts and 260 periods per year.
