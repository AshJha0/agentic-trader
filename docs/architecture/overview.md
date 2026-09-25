# Architecture overview

agentic-trader models a trading firm as a fixed pipeline of specialised agents that share
one structured state. This document covers the components, the flow of one decision, the
backtesting and evaluation layers, the design decisions and the extension points. Diagrams
are in [../DIAGRAMS.md](../DIAGRAMS.md).

## Components

| Layer | Module | Responsibility |
|---|---|---|
| Orchestration | `graph.py` | `TradingGraph.propagate(symbol, as_of, current_weight=None)` runs one decision. `scan(symbols, as_of, positions)` runs a watchlist. Both load point-in-time data, refuse stale or short history, record memory, and optionally save the report |
| Shared state | `state.py` | Typed documents: `AnalystReport` (with `abstained`), `DebateTurn`, `DebateOutcome`, `TradeProposal`, `RiskView`, `FinalDecision`, and the `TradingState` that holds them plus `current_weight` |
| Agents | `agents/` | `analysts.py` (5 analysts), `researchers.py` (bull, bear, facilitator, consensus), `trader.py` (strategic weight and tilt, protective levels), `risk.py` (3 risk analysts, portfolio manager, limits, no-trade band), `base.py` (LLM plumbing, untrusted-text blocks) |
| LLM | `llm.py` | `LLM` protocol; `AnthropicLLM` (quick and deep tiers, timeout, refusal fallback); `BudgetedLLM` (hard call cap); JSON extraction. `None` means offline |
| Quant facade | `quant/__init__.py` | One API; dispatches to the C++ extension `_atcore` when present, else to `pycore.py`. `run_backtest` takes optional per-bar carry, OHLC, stop/take levels and a rebalance mask |
| C++ core | `cpp/` | Indicators, risk, strategies, backtester (`run_backtest_ex`: carry series, intraday stops with gap fills), metrics including exposure and the Sharpe t-stat; pybind11 bindings; `at_backtest` CLI; ctest suite |
| Data | `data/` | `MarketDataProvider` interface and `clean_ohlcv`; `SyntheticProvider`, `YahooProvider`, `CSVProvider`; `fred.py` (point-in-time rates and CPI with publication lags and staleness); `fx_macro` and `carry_series` |
| Memory | `memory.py` | Decision log with atomic writes and corrupt-line tolerance, horizon-based outcome resolution, lessons, track record |
| Backtest | `backtest.py` | `run_agent_backtest` (walk-forward with position context, stops and carry), the paper's five baselines plus vol-targeted buy & hold, `run_portfolio_backtest` (equal-capital sleeves) |
| Evaluation | `evaluation.py` | `evaluate(symbols, periods, config)` over the design / holdout / paper protocol: summaries, head-to-head counts, JSON round-trip, failures recorded |
| Instruments | `instruments.py` | `Instrument.parse` with strict validation (FX intent from "/" or "=X"; ticker character rules); pip size, periods per year, Yahoo symbol |
| Config | `config.py` | `DEFAULT_CONFIG`, `make_config` (deep merge), `RULES_V02` (reproduces the v0.2 rules) |
| Interface | `cli.py` | `agentic-trader analyze / scan / backtest / baselines / portfolio / evaluate / info`. Bad input gives exit status 2 and a one-line error |

## One decision, step by step

1. **Resolve the instrument.** `Instrument.parse("EUR/USD")` gives an FX instrument
   (base EUR, quote USD, pip 0.0001, 260 periods per year). `"AAPL"` gives an equity (252).
   A mistyped pair (`"EUR/XYZ"`) or an invalid ticker is refused.
2. **Load data up to `as_of`.** The provider returns cleaned OHLCV (sorted, deduplicated,
   bad closes dropped, impossible bars widened). The graph filters to `<= as_of` again and
   refuses to decide in two cases:
   - fewer than 30 bars are available;
   - the last bar is more than `max_data_staleness_days` (7) old, as with a dead feed or a
     delisting.
3. **Consult memory.** `resolve()` attaches outcomes to past decisions whose horizon has
   elapsed by `as_of`. `lessons()` and `track_record()` go into the state, along with
   `current_weight`.
4. **Analyst team.** Four analysts are chosen by asset class: equity gets technical,
   fundamentals, news and sentiment; FX gets technical, macro, news and sentiment. Each runs
   `gather()` (tools), then `rules()` (the rule-based report, or an **abstention** when there
   is no data). Only then, and only if it didn't abstain, does it make an optional LLM call.
   Third-party text reaches the model only inside `<untrusted_data>` blocks.
5. **Research debate.** Bull and bear speak alternately for `max_debate_rounds`. The
   facilitator computes the weighted consensus `Σ wᵢ·confᵢ·signalᵢ / Σ wᵢ·confᵢ` and names
   the winner using `decision_threshold`. Abstaining analysts are skipped when
   `rules.abstain_without_data` is set. With an LLM, the facilitator returns a JSON verdict.
6. **Trader.** It sets the target weight:
   - `neutral + 2·score` when |score| exceeds the threshold, else `neutral`. The neutral
     (strategic) weight comes from `risk.neutral_weight`: 1.0 for equities, 0.0 for FX.
   - Equity weights are floored at 0 unless shorting is allowed.
   - Stops go at `stop_atr_mult × ATR14` and targets at `take_profit_atr_mult × ATR14`.
     Model-supplied levels on the wrong side of the entry are replaced.
   - The size is cut by 25% if the instrument's hit rate over at least 5 resolved calls is
     below 40%.
7. **Risk team.** A shared fact sheet is computed:
   - 20-day realised volatility;
   - 1-day historical VaR95 and CVaR95 over 250 days;
   - drawdown from the 60-day high;
   - ATR14;
   - the current position.

   Each analyst sizes from it:
   - aggressive: `max(1.25·|w|, |vol-target w|)`;
   - neutral: the volatility-targeted weight;
   - conservative: `½·min(|w|, |vol-target w|)`, capped by VaR.

   In later rounds, each view moves 25% toward the others.
8. **Portfolio manager.** Blends the latest views 25/50/25, or takes the LLM's weight. Then:
   - it applies the **firm limits** in order: shorting policy, max position, VaR cap,
     minimum trade size;
   - it applies the **no-trade band**: it keeps the current position if the target is
     within `rebalance_band`, and only if that position passes every limit today;
   - it rebuilds the protective levels for the final direction.

   Every adjustment is recorded. `approved` is true when the final direction matches the
   trader's.
9. **Record.** The decision is logged to memory atomically. If `save_reports` is set,
   `results/<SYM>/<date>/report.md` is written.

## Backtesting and evaluation

**Walk-forward** (`run_agent_backtest`). The graph runs at every `rebalance_every`-th bar
with data up to that close and **the position it currently holds**. Each decision's weight
and stop/take levels are held until the next rebalance. The C++ engine then applies:

- **Costs:** commission and slippage per unit of turnover, with the FX spread converted to
  bps at the window's first price.
- **Financing:** per-bar carry from point-in-time rates for FX, and a borrow fee on equity
  shorts.
- **Stops (optional):** intraday stops and targets that fill at the level, or at the open
  on a gap; the stop is assumed first when both trade; the position re-arms at the next
  rebalance.

The six baselines run on the same bars, costs and carry: the paper's five plus
**volatility-targeted buy & hold**.

**Portfolio** (`run_portfolio_backtest`). One sleeve per symbol with equal capital. Sleeve
returns are averaged daily, with equity and FX calendars aligned (a missing bar counts as a
0 return).

**Evaluation** (`evaluate`). Runs every (period, symbol) pair. It reports:

- per-strategy aggregates and head-to-head Sharpe counts;
- failures as data rather than exceptions;
- results as JSON that round-trips.

The default protocol is **design** 2016–2021 (every choice), **holdout** 2022–2026 (run
once) and the paper's **Q1 2024** window. See [../evaluation/evaluation.md](../evaluation/evaluation.md).

## Design decisions

**Tools, then rules, then LLM.** Every agent does its numeric work before any model is
involved, and always has a rule-based answer. This gives three properties:

- the pipeline is deterministic offline;
- an LLM failure degrades to a sensible answer, never an exception;
- the rule-based firm is the control for measuring what the LLM adds.

**Structured state over chat history.** Following the paper, agents read concise typed
documents, not an ever-growing transcript. Natural language exists only inside the two
debates, and even there it is stored as structured turns.

**Guardrails after the model; injection contained before it.** Third-party text is fenced
in `<untrusted_data>` blocks that can't be closed from inside. Model output is clipped and
coerced. The portfolio manager's firm limits run after any model decision, so no prompt can
produce an oversized or forbidden position.

**A benchmark, then tilts.** With no view, the firm holds the strategic weight rather than
cash. This is how real mandates work, and it is the only v0.3 change that measurably helped
on design data. It works through exposure to the equity premium, not better forecasting,
and the evaluation says so.

**Point-in-time or nothing.** On real data, FX macro inputs come from FRED as they were known
on each date: publication-lagged, staleness-checked, and never replaced by today's
illustrative table for old dates. Yahoo news and fundamentals are refused for dates they
can't serve, which also removed a network call per historical decision (backtests ran about
8× faster).

**C++ with a numpy twin.** The C++ core is the performance path and the reference for
numerical conventions:

- warm-up values are NaN;
- rolling statistics use the population estimator;
- RSI and ATR use Wilder smoothing;
- EMA is seeded with an SMA;
- stops fill as in diagram 10.

`pycore.py` mirrors it exactly, and randomised CI tests cross-check the two.

**Explicit timing convention.** The weight decided at the close of bar *t* earns the return
from *t* to *t + 1*. Weights set on the final bar earn nothing, and a unit test checks this.

**Honest evaluation by construction.** `RULES_V02` keeps the old behaviour reproducible, so
every change has a before and after. Choices are made on the design period, and the holdout
runs once.

## Configuration surface

See `config.py` for the full dictionary. The most important keys:

| Key | Default | Effect |
|---|---|---|
| `llm_provider` | `offline` | `anthropic` enables Claude |
| `deep_think_llm` / `quick_think_llm` | `claude-opus-5` / `claude-haiku-4-5` | Model per tier |
| `deep_effort` / `quick_effort` | `high` / `low` | Adaptive-thinking effort |
| `llm_timeout_s` / `max_llm_calls` | 300 / None | Request timeout; hard call cap per graph |
| `max_debate_rounds` / `max_risk_discuss_rounds` | 2 / 1 | Debate lengths |
| `analyst_weights` | technical 1, fundamentals 1, macro 1, news 0.7, sentiment 0.5 | Consensus weights |
| `decision_threshold` | 0.10 | Minimum \|score\| for a directional view |
| `rules.tsmom` / `trend_filtered_reversal` / `abstain_without_data` | all False | Research switches; measured as noise on design data |
| `risk.neutral_weight` | equity 1.0, fx 0.0 | Strategic weight held with no view |
| `risk.rebalance_band` | 0.10 | No-trade band around the current position |
| `risk.max_position` / `max_var_95` / `min_trade_weight` | 1.0 / 0.02 / 0.05 | Firm limits |
| `risk.allow_short_equity` / `allow_short_fx` | False / True | Shorting policy |
| `risk.stop_atr_mult` / `take_profit_atr_mult` | 2.0 / 3.0 | Protective levels |
| `backtest.use_stops` | False | Enforce the levels intraday in backtests |
| `costs.*` | 1 bps + 1 bps slippage + 1% borrow; FX 0.8-pip spread + 0.2 bps | Backtest costs |
| `fx_macro_source` | `auto` | Static table for synthetic data, point-in-time FRED for real data |
| `max_data_staleness_days` | 7 | Refuse to decide on a feed older than this |

## Extension points

| To add | Do this |
|---|---|
| A data source (Reddit, StockTwits, a news API) | Subclass `MarketDataProvider`, call `super().__init__(config)`, implement the methods it can serve and return only data available at `as_of` (pass prices through `clean_ohlcv`). Register it in `data/__init__.py:PROVIDERS` |
| An analyst | Subclass `Analyst` with `name`, `role`, `instructions`, `gather()` and `rules()`; list free-text fact keys in `untrusted_keys`; return `self.abstain(...)` when there is no data; add it to `ANALYSTS` |
| An LLM provider | Implement `complete(system, prompt, *, deep) -> str | None` and pass `llm=` to `TradingGraph`. `max_llm_calls` wraps it automatically |
| A quant routine | Implement it in `cpp/`, bind it in `module.cpp`, mirror it in `pycore.py`, export it in `quant/__init__.py`, and add a cross-check test |
| A baseline | Add it to `backtest.baseline_weights()` (and to C++ if it is a reusable strategy) |
| A firm limit | Extend `PortfolioManager.guardrails()`. It runs after any model output, and the no-trade band respects it automatically |
| A rule change | Put it behind a `config["rules"]` switch, run it through `evaluate` on the design period, then judge it on the holdout |
