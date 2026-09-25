# Architecture overview

agentic-trader models a trading firm as a fixed pipeline of specialised agents that share
one structured state. This document covers the components, the data flow, the key design
decisions and the extension points. Diagrams are in [../DIAGRAMS.md](../DIAGRAMS.md).

## Components

| Layer | Module | Responsibility |
|---|---|---|
| Orchestration | `agentic_trader/graph.py` | `TradingGraph.propagate(symbol, as_of)`: loads point-in-time data, runs every stage, records memory, optionally saves the report |
| Shared state | `agentic_trader/state.py` | Typed documents: `AnalystReport`, `DebateTurn`, `DebateOutcome`, `TradeProposal`, `RiskView`, `FinalDecision`, and the `TradingState` that holds them |
| Agents | `agentic_trader/agents/` | `analysts.py` (5 analysts), `researchers.py` (bull, bear, facilitator), `trader.py`, `risk.py` (3 risk analysts, portfolio manager) |
| LLM | `agentic_trader/llm.py` | `LLM` protocol, `AnthropicLLM` (quick and deep tiers), JSON extraction; `None` means offline |
| Quant facade | `agentic_trader/quant/__init__.py` | One API; dispatches to the C++ extension `_atcore` when present, otherwise to `pycore.py` |
| C++ core | `cpp/` | Indicators, risk, strategies, backtester and metrics; pybind11 bindings; `at_backtest` CLI; ctest suite |
| Data | `agentic_trader/data/` | `MarketDataProvider` interface; `SyntheticProvider`, `YahooProvider` (with FRED), `CSVProvider` |
| Memory | `agentic_trader/memory.py` | Decision log, horizon-based outcome resolution, lessons, track record |
| Backtest | `agentic_trader/backtest.py` | Walk-forward agent backtest plus the five baselines; `ComparisonReport` |
| Instruments | `agentic_trader/instruments.py` | `Instrument.parse` for equity and FX symbols; pip size, periods per year, Yahoo symbol |
| Config | `agentic_trader/config.py` | `DEFAULT_CONFIG` and `make_config` (deep merge) |
| Interface | `agentic_trader/cli.py` | `agentic-trader analyze / backtest / baselines / info` |

## One decision, step by step

1. **Resolve the instrument.** `Instrument.parse("EUR/USD")` gives an FX instrument
   (base EUR, quote USD, pip 0.0001, 260 periods per year). `"AAPL"` gives an equity (252).
2. **Load data up to `as_of`.** `provider.history(ins, as_of - lookback_days, as_of)`. The
   graph filters the frame to `<= as_of` again, whatever the provider returned. It needs at
   least 30 bars.
3. **Consult memory.** `memory.resolve()` attaches outcomes to past decisions whose horizon
   has elapsed by `as_of`. `lessons()` and `track_record()` go into the state.
4. **Analyst team.** Four analysts are chosen by asset class: equity gets technical,
   fundamentals, news and sentiment; FX gets technical, macro, news and sentiment. Each runs
   `gather()` (tools), then `rules()` (rule-based report), then an optional LLM call. The
   result is an `AnalystReport` with a signal in [-1, 1], a confidence in [0, 1], a summary,
   key points and the raw facts.
5. **Research debate.** Bull and bear speak alternately for `max_debate_rounds`. The
   facilitator computes the weighted consensus
   `Σ wᵢ·confᵢ·signalᵢ / Σ wᵢ·confᵢ` (with role weights from `analyst_weights`) and names
   the winner using `decision_threshold`. With an LLM it returns a JSON verdict instead.
6. **Trader.** The target weight is `clip(2·score)` when |score| exceeds the threshold. Stops
   are at `stop_atr_mult × ATR14` and targets at `take_profit_atr_mult × ATR14`. The size is
   cut by 25% if the instrument's hit rate over at least 5 resolved calls is below 40%.
   Equity weights are floored at 0 unless shorting is allowed.
7. **Risk team.** A shared fact sheet is computed: 20-day realised volatility, 1-day
   historical VaR95 and CVaR95 over 250 days, and drawdown from the 60-day high. Each
   analyst sizes from it:
   - aggressive: `max(1.25·|w|, |vol-target w|)`
   - neutral: the volatility-targeted weight
   - conservative: `½·min(|w|, |vol-target w|)`, then capped by VaR

   In later rounds, each view moves 25% toward the others.
8. **Portfolio manager.** Blends the latest views 25/50/25, or takes the LLM's weight. It
   then applies the guardrails in order: shorting policy, max position, VaR cap, minimum
   trade size. Each adjustment is recorded. `approved` is true when the final direction
   matches the trader's.
9. **Record.** The decision is logged to memory with the trader's horizon. If
   `save_reports` is set, `results/<SYM>/<date>/report.md` is written.

## Design decisions

**Tools, then rules, then LLM.** Every agent does all numeric work itself before any model
is involved, and always has a rule-based answer. This gives three properties:

- the pipeline is fully functional and deterministic offline;
- an LLM failure degrades to a sensible answer instead of an exception;
- the rule-based output is a baseline for judging what the LLM adds.

**Structured state over chat history.** Following the paper, agents read concise typed
documents (`reports_digest()`), not an ever-growing transcript. Natural language exists only
inside the two debates, and even there it is stored as structured turns.

**Guardrails after the model.** LLM output is clipped to valid ranges, and the portfolio
manager's firm limits run after the model's decision, so no prompt or model error can
produce an oversized or forbidden position.

**C++ with a numpy twin.** The C++ core is the performance path and the reference for
numerical conventions:

- warm-up values are NaN;
- rolling statistics use the population estimator;
- RSI and ATR use Wilder smoothing;
- EMA is seeded with an SMA.

`pycore.py` mirrors it exactly, and CI cross-checks the two, so the package works without a
compiler and a C++ regression cannot pass silently.

**Explicit timing convention.** The weight decided at the close of bar *t* earns the return
from *t* to *t + 1*. Weights set on the final bar earn nothing, and a unit test checks this.
The same rule holds for the agent backtest (decided at the rebalance close, held to the next
rebalance) and the baselines.

**One model per asset class, shared machinery.** Equity and FX differ only where finance
says they should:

- value analyst: fundamentals for equities, macro/rates for FX;
- headline orientation: FX scores from the base currency's point of view;
- shorting default: off for equities, on for FX;
- cost model: bps plus borrow for equities, pips plus carry for FX;
- periods per year: 252 vs 260.

## Configuration surface

See `config.py` for the full dictionary. The most important keys:

| Key | Default | Effect |
|---|---|---|
| `llm_provider` | `offline` | `anthropic` enables Claude |
| `deep_think_llm` / `quick_think_llm` | `claude-opus-5` / `claude-haiku-4-5` | Model per tier |
| `deep_effort` / `quick_effort` | `high` / `low` | Adaptive-thinking effort |
| `max_debate_rounds` / `max_risk_discuss_rounds` | 2 / 1 | Debate lengths |
| `analyst_weights` | technical 1, fundamentals 1, macro 1, news 0.7, sentiment 0.5 | Consensus weights |
| `decision_threshold` | 0.10 | Minimum \|score\| for a directional view |
| `risk.max_position` | 1.0 | Cap on \|weight\| |
| `risk.target_vol` | 0.15 | Neutral analyst's volatility target |
| `risk.max_var_95` | 0.02 | Cap on the position's 1-day VaR95 |
| `risk.min_trade_weight` | 0.05 | Smaller targets become flat |
| `risk.allow_short_equity` / `allow_short_fx` | False / True | Shorting policy |
| `costs.*` | 1 bps + 1 bps slippage + 1% borrow; FX 0.8 pip spread + 0.2 bps | Backtest costs |
| `fx_policy_rates` / `fx_inflation` | Illustrative levels | FX macro inputs (`fx_macro_source="fred"` to fetch rates) |

## Extension points

| To add | Do this |
|---|---|
| A data source (Reddit, StockTwits, a news API) | Subclass `MarketDataProvider`, implement the methods it can serve, return only data available at `as_of`, and register it in `data/__init__.py:PROVIDERS` |
| An analyst | Subclass `Analyst` with `name`, `role`, `instructions`, `gather()` and `rules()`, then add it to `ANALYSTS`. List it in `config["analysts"]` or `DEFAULT_ANALYSTS` |
| An LLM provider | Implement `complete(system, prompt, *, deep) -> str | None` and pass `llm=` to `TradingGraph` |
| A quant routine | Implement it in `cpp/`, bind it in `module.cpp`, mirror it in `pycore.py`, export it in `quant/__init__.py`, and add it to the cross-check test |
| A baseline | Add it to `strategies.hpp/.cpp` and `pycore.py`, then to `backtest.baseline_weights()` |
| A firm limit | Extend `PortfolioManager.guardrails()`. It runs after any model output |
