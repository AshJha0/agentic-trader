# API reference

This reference covers the public Python API, the quant functions, the CLI, the C++ API and
the standalone C++ tool. Anything not listed here is internal and may change.

```python
from agentic_trader import (TradingGraph, run_agent_backtest, ComparisonReport, make_config,
                            DEFAULT_CONFIG, Instrument, Action, FinalDecision, TradingState)
```

## Orchestration

### `TradingGraph(config=None, provider=None, llm=None, memory=None, on_event=None)`

| Parameter | Type | Default | Meaning |
|---|---|---|---|
| `config` | `dict \| None` | `DEFAULT_CONFIG` | Deep-merged over the defaults with `make_config` |
| `provider` | `MarketDataProvider \| None` | From `config["data_provider"]` | Data source |
| `llm` | `LLM \| None` | From `config["llm_provider"]` | Any object with `complete(system, prompt, *, deep) -> str \| None`; `None` means offline |
| `memory` | `DecisionMemory \| None` | `DecisionMemory(config["memory_path"])` | Pass `DecisionMemory(None)` for in-memory only |
| `on_event` | `Callable[[str, str], None] \| None` | Logs at INFO | Called with `(stage, message)` for the stages `data`, `analyst`, `debate`, `trader`, `risk`, `decision` and `report` |

#### `propagate(symbol, as_of, asset_class=None) -> tuple[TradingState, FinalDecision]`

Runs the whole firm once.

- `symbol`: a `str` (`"AAPL"`, `"EURUSD"`, `"EUR/USD"`, `"USDJPY=X"`) or an `Instrument`.
- `as_of`: a `datetime.date` or ISO string. Only data up to and including this close is used.
- `asset_class`: `"equity"` or `"fx"`, to override auto-detection.

It raises `ValueError` when fewer than 30 bars are available. The decision is recorded to
memory, and when `config["save_reports"]` is set, `results/<SYM>/<date>/report.md` is
written.

#### `save_report(state) -> pathlib.Path`

Writes `state.to_markdown()` to `results_dir/<SYM>/<as_of>/report.md`.

## Backtesting

### `run_agent_backtest(symbol, start, end, config=None, rebalance_every=5, provider=None, llm=None, asset_class=None, on_decision=None, include_agent=True) -> ComparisonReport`

Walk-forward backtest of the agent firm plus the five baselines over `[start, end]`, with
`lookback_days` of warm-up. Memory is in-memory for the run. When `include_agent=False`,
only the baselines run (this is the `baselines` CLI command). `on_decision` is called with
each `FinalDecision`.

### `ComparisonReport`

| Member | Meaning |
|---|---|
| `instrument` | `Instrument` |
| `dates` | `pd.DatetimeIndex` of the window |
| `results` | `dict[str, quant.BacktestResult]` with keys `AgenticTrader`, `Buy&Hold`, `SMA(20/50)`, `MACD`, `KDJ+RSI`, `ZMR` |
| `decisions` | `list[FinalDecision]` from each rebalance |
| `backtest_config` | The `quant.BacktestConfig` used (costs, carry, shorting) |
| `table()` | `DataFrame` with columns CR%, AR%, Vol%, Sharpe, Sortino, MDD%, Calmar, Win%, Trades, one row per strategy |
| `equity_curves()` | `DataFrame` of equity per strategy, indexed by date |

### `backtest_config_for(ins, config, prices, provider, start) -> quant.BacktestConfig`

Builds the cost, carry and shorting model for an instrument:

- **Equity:** bps commission, slippage and borrow.
- **FX:** half-spread in pips converted to bps, plus slippage and carry.

### `baseline_weights(full, allow_short) -> dict[str, np.ndarray]`

Target weights for the five baselines over an OHLC `DataFrame`.

## Configuration

### `make_config(overrides=None, **kw) -> dict`

Returns a deep copy of `DEFAULT_CONFIG` with `overrides`, then `kw`, deep-merged in. Nested
dicts merge key by key, so `make_config(risk={"max_position": 0.5})` keeps the other risk
keys. See [architecture/overview.md](../architecture/overview.md#configuration-surface) for
the important keys, and `agentic_trader/config.py` for all of them.

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

`Instrument.parse(text, asset_class=None)` treats six letters made of two known currency
codes as FX unless `asset_class="equity"` is given. It raises `ValueError` for an unknown
asset class or a non-pair forced to FX.

## State documents (`agentic_trader.state`)

| Class | Fields |
|---|---|
| `Action` | `str` enum: `BUY` (long), `SELL` (short, or exit when shorting is not allowed), `HOLD` (flat) |
| `AnalystReport` | `analyst`, `signal` ∈ [-1, 1], `confidence` ∈ [0, 1], `summary`, `key_points`, `facts`, `source` (`rules` \| `llm`) |
| `DebateTurn` | `speaker` (`bull` \| `bear`), `round`, `argument` |
| `DebateOutcome` | `winner` (`bull` \| `bear` \| `balanced`), `score` ∈ [-1, 1], `conviction` ∈ [0, 1], `summary`, `turns`, `source` |
| `TradeProposal` | `action`, `target_weight`, `confidence`, `entry_price`, `stop_loss`, `take_profit`, `horizon_days`, `rationale`, `source` |
| `RiskView` | `stance` (`aggressive` \| `neutral` \| `conservative`), `recommended_weight`, `argument`, `round`, `source` |
| `FinalDecision` | `symbol`, `as_of`, `action`, `target_weight`, `confidence`, `stop_loss`, `take_profit`, `rationale`, `approved`, `adjustments`, `source`; `to_dict()` returns JSON-ready output |
| `TradingState` | `instrument`, `as_of`, `history`, `reports`, `debate`, `proposal`, `risk_views`, `decision`, `lessons`, `track_record`, `log`; `last_price`, `reports_digest()`, `to_markdown()` |

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
| `PortfolioManager` | `run(state, facts) -> FinalDecision`; `guardrails(w, facts) -> (w, notes)` | deep |

Helpers:

- `run_debate(state, bull, bear, facilitator, rounds)`
- `run_risk_team(state, analysts, pm, rounds)`
- `ANALYSTS` maps analyst names to classes.

**Custom analysts.** Subclass `analysts.Analyst` and set `name`, `role` and `instructions`.
Implement `gather(state, provider) -> dict` and `rules(facts, state) -> AnalystReport`. The
base `run()` handles the LLM call, validation and clipping.

## LLM (`agentic_trader.llm`)

| Name | Meaning |
|---|---|
| `LLM` | Protocol: `complete(system, prompt, *, deep: bool) -> str \| None` |
| `AnthropicLLM(config)` | Claude through the Anthropic SDK (details below) |
| `get_llm(config)` | `None` for `offline`, `AnthropicLLM` for `anthropic`; `ValueError` otherwise |
| `extract_json(text)` | The first JSON object in a reply, fenced or bare, or `None` |

`AnthropicLLM` in more detail:

- **Models:** `quick_think_llm` or `deep_think_llm`.
- **Thinking:** adaptive thinking and `output_config.effort` for every model except Haiku 4.5.
- **Refusal fallback:** the server-side fallback runs on `claude-opus-5` and `claude-fable-5-1` when `use_refusal_fallback` is set.
- **Failure handling:** it returns `None` on a refusal stop reason, or on a rate-limit, status or connection error.
- **Credentials:** read by the SDK from `ANTHROPIC_API_KEY` or an `ant auth login` profile.

## Data (`agentic_trader.data`)

### `MarketDataProvider`

| Method | Returns | Contract |
|---|---|---|
| `history(instrument, start, end)` | OHLCV `DataFrame` with a `DatetimeIndex` | Inclusive of `start` and `end` (required) |
| `news(instrument, as_of, lookback_days)` | `list[NewsItem]` | Published ≤ `as_of` |
| `social(instrument, as_of, lookback_days)` | `list[NewsItem]` | Published ≤ `as_of` |
| `fundamentals(instrument, as_of)` | `dict` | Point in time; `{}` when unknown |
| `macro(instrument, as_of)` | `dict` | For FX: `base_rate`, `quote_rate`, `rate_diff`, `base_inflation`, `quote_inflation`, `source` |

`NewsItem(published, headline, source="", summary="", sentiment=None, tags=[])`

### Implementations and helpers

| Name | Notes |
|---|---|
| `SyntheticProvider(config)` | Deterministic; seeded by `synthetic_seed` and the symbol |
| `YahooProvider(config)` | Needs `yfinance`; FRED rates when `fx_macro_source="fred"` |
| `CSVProvider(config)` | Reads `<csv_dir>/<SYMBOL>.csv` and optional `<SYMBOL>_news.csv` |
| `get_provider(config)` | Builds a provider from `config["data_provider"]` |
| `PROVIDERS` | Registry of provider names to classes |

## Memory (`agentic_trader.memory`)

### `DecisionMemory(path=None)`

A JSONL-backed log when `path` is set; in-memory otherwise.

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
| `vol_target_weight(signal, realized_vol_annual, target_vol, max_leverage)` | float |
| `position_units(equity, risk_fraction, entry, stop)` | float |
| `strat_buy_hold(close)` | weights |
| `strat_sma_cross(close, fast=20, slow=50, allow_short=False)` | weights |
| `strat_macd(close, fast=12, slow=26, signal=9, allow_short=False)` | weights |
| `strat_kdj_rsi(high, low, close, kdj_n=9, rsi_n=14, rsi_low=30.0, rsi_high=70.0, allow_short=False)` | weights |
| `strat_zmr(close, n=20, entry=1.0, exit=0.0, allow_short=False)` | weights |
| `run_backtest(prices, target_weights, config=None)` | `BacktestResult` |
| `compute_metrics(equity, positions, periods_per_year, risk_free_annual=0.0)` | `Metrics` |
| `max_drawdown(equity)` | float |

The backtest types:

| Type | Fields |
|---|---|
| `BacktestConfig` | `initial_capital`=100000, `cost_bps`=1.0, `slippage_bps`=0.0, `periods_per_year`=252, `carry_annual`=0.0, `borrow_annual`=0.0, `max_leverage`=1.0, `allow_short`=True, `risk_free_annual`=0.0 |
| `BacktestResult` | `equity`, `returns`, `positions`, `trades` (`list[Trade]`), `metrics` (`Metrics`) |
| `Metrics` | `cumulative_return`, `annualized_return`, `annualized_vol`, `sharpe`, `sortino`, `max_drawdown`, `calmar`, `win_rate`, `num_trades`, `turnover`, `periods` |
| `Trade` | `index`, `from_weight`, `to_weight`, `price` |

## CLI

```text
agentic-trader analyze   SYMBOL [--date YYYY-MM-DD] [--save] [--json] [--no-memory] [common]
agentic-trader backtest  SYMBOL --start D --end D [--every N] [--out curves.csv] [common]
agentic-trader baselines SYMBOL --start D --end D [--out curves.csv] [common]
agentic-trader info

common: [--asset-class equity|fx] [--data synthetic|yahoo|csv] [--csv-dir DIR]
        [--llm offline|anthropic] [--deep-model ID] [--quick-model ID]
        [--rounds N] [--allow-short] [-v]
```

| Flag | Effect |
|---|---|
| `--date` | Decision date for `analyze` (default: yesterday) |
| `--save` | Write `results/<SYM>/<date>/report.md` |
| `--json` | Print only `FinalDecision.to_dict()` |
| `--no-memory` | Do not read or write `results/memory.jsonl` |
| `--every N` | Rebalance every N bars (backtest only) |
| `--out` | Write equity curves to CSV |
| `--rounds N` | Set both the debate and risk-discussion rounds |
| `--allow-short` | Allow equity shorts |
| `-v` | INFO logging, including LLM fallbacks |

`python -m agentic_trader` is equivalent to `agentic-trader`.

## C++ API (`cpp/include/at/*.hpp`, namespace `at`)

`Series` is `std::vector<double>`.

| Header | Declarations |
|---|---|
| `indicators.hpp` | `sma`, `ema`, `rolling_std`, `zscore`, `rsi`, `macd → MACD{line, signal, hist}`, `bollinger → Bollinger{mid, upper, lower, percent_b}`, `atr`, `kdj → KDJ{k, d, j}`, `pct_change`, `realized_vol` |
| `risk.hpp` | `quantile`, `historical_var`, `historical_cvar`, `kelly_fraction`, `vol_target_weight`, `position_units` |
| `strategies.hpp` | `strat_buy_hold`, `strat_sma_cross`, `strat_macd`, `strat_kdj_rsi`, `strat_zmr` |
| `backtest.hpp` | `BacktestConfig`, `Trade`, `Metrics`, `BacktestResult`, `run_backtest(prices, weights, cfg)`, `compute_metrics(equity, positions, ppy, rf)`, `max_drawdown(equity)` |

Invalid inputs (non-positive windows, mismatched lengths) throw `std::invalid_argument`.
Link against the `at_core` static library from `CMakeLists.txt`.

## `at_backtest` (C++ CLI)

```text
at_backtest <prices.csv> [--fx] [--short] [--cost-bps X] [--carry X] [--ppy N]
```

The CSV needs a header with `Close` (or `Adj Close`); `High` and `Low` are optional. It
needs at least 60 rows. The tool prints CR, AR, Sharpe, MDD, win rate and trades for the
five baselines. `--fx` enables shorts and 260 periods per year.
