# Changelog

## Unreleased

### Fixed
- `AlphaAnalyst` now weights only alphas whose IC clears significance (`|t(IC)| >= 2`,
  n >= 30) and abstains when none qualify, instead of weighting every alpha by `max(0, IC)`.
- Fixed a real inconsistency: under the agentic harness, `AlphaAnalyst` silently reused the
  `quant.alpha` tool's raw (equal-weighted, ungated) "combined" value instead of applying its
  own significance gate. Both invocation paths now share one function,
  `alpha.significant_alpha_signal`, so the analyst can no longer disagree with itself
  depending on how it is called.
- Fixed a window mismatch: the analyst reused the desk's general ~400-day lookback, too
  short for a 273-day signal like `tsmom_12_1` to ever gather enough points to be judged
  significant. It now fetches its own 900-day window, matching the `quant.alpha` tool.
- Net effect, re-measured on the design period: "+ alpha analyst" moved from mean Sharpe 0.60
  (v0.4.0) to 0.65 (essentially tied with the 0.65 default) with a higher median Sharpe (0.62
  vs 0.55) and a better FX median, at the cost of two fewer instruments beating buy & hold
  and ~8% more trades. Given this is the third combination-logic variant measured on the same
  data, a closer-to-parity result is treated as noise, not a green light: the alpha analyst
  **stays off by default**. See
  [docs/evaluation/evaluation.md](docs/evaluation/evaluation.md#the-v04-alpha-analyst-design-period-check).

## v0.4.0 — 2026-09-26

The agentic layer, the quant research layer, and a rewrite of the documentation.

### Agentic layer (`agentic_trader.agentic`)
- **Domain model.** Frozen dataclasses for `Task`, `Plan`, `PlanStep`, `ToolDescriptor`,
  `ToolRequest`/`ToolResult`, `Evidence` (six types, SHA-256 digests), `Finding`,
  `PolicyDecision`, roles and capabilities, and the task state machine with its legal
  transitions.
- **Tools.** A `ToolRegistry` derives JSON schemas from Python signatures. The
  `ToolExecutor` runs every call through the policy engine, with a per-call timeout,
  bounded retry on transient errors, argument coercion, tracing and an evidence record for
  every call, successful or not.
- **Tool servers.** 15 tools on 5 servers: `market_data` (history, news, social,
  fundamentals, macro), `quant` (technical, risk, alpha, baselines), `knowledge` (search,
  list_documents), `portfolio` (position, construct) and `execution` (plan; `submit_order`,
  which is state-changing and always needs approval). `RecordingProvider` routes the
  analysts' data access through these tools.
- **Policy engine.** Ordered rules (deny list, required capabilities, read-only, argument
  guards, risk level) returning ALLOW / DENY / REQUIRE_APPROVAL with the rule that fired;
  five roles; auto, queued and deny approval gateways.
- **Planner.** A canonical plan per asset class and an optional model-proposed plan. The
  validator strips unknown tools, stages and arguments, pins the symbol and date, repairs
  stage order, refuses state-changing tools in plans, and appends the governance steps.
- **Harness.** `AgentHarness` runs a plan through an explicit state machine with parallel
  tool batches, AWAITING_APPROVAL pause and resume, cooperative cancellation, and the
  governance steps (critic, evidence validation, audited report) that cannot be skipped.
- **Critic.** Seven deterministic checks (evidence resolves, model-vs-rules divergence,
  contradictions, firm limits, protective levels, direction vs verdict, single-evidence
  cap) and an optional model critique that can only lower confidence.
- **Audited reports.** A number audit (every figure in the narrative must trace to the
  structured facts, tolerant of rounding and percentage forms) and an evidence-id audit;
  discrepancies become warnings.
- **Knowledge base.** 11 runbooks and policies (59 chunks) with a dependency-free hashed
  TF-IDF embedder; retrieved passages are DOCUMENT evidence and are shown to the trader and PM.
- **Observability.** Spans with parent ids, JSON-lines logging and Prometheus text metrics.
- **MCP server.** The catalogue as a real MCP stdio server (official SDK 2.x), plus a client
  that turns a remote server's tools into a local registry so policy and evidence apply unchanged.
- **HTTP API.** FastAPI gateway with API-key roles: tasks (202 accepted, background run),
  reports (JSON or markdown), traces, evidence, cancel, approvals, tools, health, metrics.
- **CLI.** `task`, `tools`, `serve`, `mcp`.

### Quant research layer
- **Alpha library** (`alpha.py`): nine signals (12-1 momentum, vol-adjusted 20-day
  momentum, 5-day reversal, 52-week high, Donchian, MACD, RSI, low-vol, FX carry) with IC,
  IC t-stat, decay, hit rate, tercile spread, autocorrelation and correlations; combination;
  an `AlphaAnalyst` agent (off by default, see the evaluation).
- **Execution algorithms** (`algo.py`): TWAP, VWAP, POV and Almgren-Chriss schedules; an
  intraday simulator (Brownian-bridge bars from a daily bar, half-spread and square-root
  impact, implementation shortfall and slippage vs VWAP); decision → parent order planning.
- **Portfolio construction** (`portfolio.py`): EWMA and Ledoit-Wolf covariance; equal,
  inverse-vol, risk parity, minimum variance and mean-variance weights with caps; risk
  contributions and diversification ratio; `run_portfolio_backtest(weighting=...)` with
  trailing (no look-ahead) covariance.
- **Statistics** (`stats.py`): block-bootstrap Sharpe CI, probabilistic and deflated Sharpe
  ratios, minimum track record, and a selection report for a chosen variant.
- **C++ core:** `rolling_max`, `rolling_min`, `spearman`, `almgren_chriss`; `sma` no longer
  returns all-NaN after a leading NaN (a bug the alpha library exposed).
- **CLI.** `alpha`, `execute`, `stats`, `portfolio --weighting`.

### Evaluation
- The evaluation period formerly labelled after an external publication is now `q1_2024`.
- Adding the alpha analyst was measured on the design period (mean Sharpe 0.65 → 0.60,
  median 0.55 → 0.60): noise, so it stays off by default.
- Deflated Sharpe ratio reported for the v0.3 rule choice (16 variants).

### Changed
- References to an external research paper and repository were removed from the code and
  documentation; the design is described on its own terms.
- Approval identity is the tool and its arguments within a task, so a request re-submitted
  after approval is recognised.
- `TradingGraph` is split into stages (`prepare`, `run_analyst`, `run_debate`, `run_trader`,
  `run_risk`, `record`) that the harness reuses; `propagate` is unchanged.
- LLM usage and cost accounting (`UsageTracker`), anonymised prompts (`llm_anonymize`) and
  parallel evaluation (`evaluate(workers=)`) from the pending LLM-evaluation work are included.

### Tests and docs
- **Tests:** 116 → **197** pytest tests (agentic 30, adversarial 15, services 7 incl. a real
  MCP stdio round trip and the FastAPI client, quant research 18, LLM evaluation 11).
- **Docs:** LEARN (26 concepts), COOKBOOK (56 recipes), DIAGRAMS (24), architecture,
  specification, threat model (32 threats), API and evaluation rewritten; landing page updated.

## v0.3.0 — 2026-09-25

Hardening, real-life workflows and an honest real-price evaluation.

### Evaluation
- **New protocol on real prices.** The universe is 15 instruments (10 equities, 5 FX pairs)
  and there are three periods:
  - a 2016–2021 **design** period, the only data used for choices;
  - a 2022–2026 **holdout**, run once with frozen rules;
  - a Q1 2024 reference window.

  The protocol is available as `evaluate()` and `agentic-trader evaluate`.
- **Volatility-targeted buy & hold baseline**, the fair control for a risk-managed strategy.
  **Sharpe t-statistic** and **average exposure** are added to every result.
- **16-variant design-period ablation**, published in full.
- **Findings.** Out of sample the agents do not beat buy & hold on Sharpe per instrument, and
  take about half the drawdown. As a 15-sleeve portfolio they beat plain buy & hold (Sharpe
  1.14 vs 1.06) but not the vol-targeted control (1.24). See `docs/evaluation/evaluation.md`.

### Rule changes (chosen on design data only)
- **Strategic weight plus tilt.** With no view the trader holds `risk.neutral_weight`
  (equities 1.0, FX 0.0) instead of going flat. Design equity mean Sharpe went from 0.76 to
  0.99; on the holdout it went from 0.60 to 0.63, return from 30% to 47%, and trades halved.
- **No-trade band** (`risk.rebalance_band` 0.10) around the current position. It is applied
  only when that position still passes every limit. It cut trades by 44% at equal Sharpe.
- **Research switches, off by default** because they measured as noise: 12-1 month
  time-series momentum, trend-filtered reversals, and abstention from the consensus.
- `RULES_V02` / `--rules v02` reproduces the v0.2 rules exactly (tested against the
  published AAPL decision).

### Engine (C++ and numpy twin)
- `run_backtest_ex` adds per-bar carry, **intraday stop and take-profit fills** (at the
  level, or at the open on a gap; stop first when both trade; re-arm at the next
  rebalance), exit costs, and validation of lengths and prices.
- Randomised C++ vs numpy cross-checks of the extended backtester.

### Real-life workflows
- **Portfolio context.** `propagate(current_weight=)`; `analyze --position`.
- **Watchlists.** `TradingGraph.scan()` / `agentic-trader scan`, with positions and CSV/JSON
  export. A bad symbol becomes an error row.
- **Multi-asset portfolios.** `run_portfolio_backtest()` / `agentic-trader portfolio` (equal-capital
  sleeves with equity and FX calendars aligned).
- **Stops in backtests.** `backtest.use_stops` / `--stops on`.

### Data
- **Point-in-time FX macro from FRED** (`data/fred.py`). Values are publication-lagged and
  staleness-checked, and carry is accrued per bar. On real data, today's illustrative
  static rates are never used for old dates.
- `clean_ohlcv` normalises every provider's output: sort, dedupe, drop bad closes, fill and
  widen OHLC, strip time zones.
- **Yahoo performance.** Coverage-cached downloads, and news is no longer requested for
  dates Yahoo cannot serve. Real-data backtests are about 8× faster.

### Safety and robustness
- **Prompt-injection containment.** Headlines and posts reach the model only inside
  `<untrusted_data>` blocks that cannot be escaped.
- **LLM cost and failure handling.** `max_llm_calls` sets a hard budget (`BudgetedLLM`);
  requests time out; an analyst with no data abstains and makes no model call.
- **Model-supplied levels.** Stops and targets on the wrong side of the entry are replaced,
  and the levels are rebuilt when the PM flips direction.
- **Input guards.** Stale-data refusal (`max_data_staleness_days`); strict symbol parsing (a
  mistyped pair like `EUR/XYZ` no longer becomes an equity); non-finite position guard.
- **Memory.** Writes are atomic, and a corrupt log line is skipped.
- **CLI.** Friendly errors (exit status 2, no traceback).
- **`at_backtest`.** Skips invalid rows instead of crashing.
- `.env` files are git-ignored.

### Tests and docs
- **Tests.** 18 → **116** pytest tests; 7 → **13** C++ test groups (34 checks).
- **Docs.**
  - `LEARN.md` now has 18 concepts, `COOKBOOK.md` 38 recipes (all runnable ones executed),
    and `DIAGRAMS.md` 16 diagrams, each parsed with Mermaid 11.
  - Architecture, specification, threat model (20 threats), API reference, evaluation and
    the landing page were rewritten.

## v0.2.0 — 2026-09-25

### Added
- **Documentation site**, published with GitHub Pages from `docs/` at
  https://ashjha0.github.io/agentic-trader/. The landing page shows measured figures, an
  honesty note, the architectural boundary, component cards, a sample decision and a
  real-price backtest.
- `LEARN.md`: a guided tour through 13 concepts, each with implementation pointers, real
  numbers and questions.
- `COOKBOOK.md`: 25 recipes; all 22 Python recipes are executed when the docs are checked.
- `docs/architecture/overview.md`, `docs/DIAGRAMS.md` (10 Mermaid diagrams),
  `docs/SPECIFICATION.md` (requirements with status),
  `docs/threat-model/threat-model.md`, `docs/evaluation/evaluation.md`, `docs/api/api.md`,
  `docs/INDEX.md` and `docs/GITHUB_PAGES.md`.
- An evaluation on **real Q1 2024 prices** (Yahoo) for AAPL, NVDA, MSFT, META, GOOGL, EURUSD,
  USDJPY and GBPUSD with the rule-based agents, next to the synthetic results.
- GitHub Actions CI (#1): pytest on Python 3.10–3.14, and a C++ build with ctest and pytest
  on the C++ backend on Linux, Windows and macOS.

### Changed
- `examples/compare_baselines.py` now covers all eight evaluation instruments over the
  documented window (2024-01-02 → 2024-03-28).

## v0.1.0 — 2026-09-25

First release.

- **Agents.** A multi-agent trading firm for equities and FX:
  - analysts: technical, fundamentals or macro/rates, news, sentiment;
  - a bull/bear debate with a facilitator;
  - a trader;
  - an aggressive/neutral/conservative risk team;
  - a portfolio manager with hard limits.
- **LLMs.** Claude through the Anthropic SDK with quick and deep tiers, an offline
  rule-based mode, and a rule-based fallback on any LLM failure.
- **C++17 quant core.** Indicators, risk, rule-based baselines and a backtester, exposed via
  pybind11, with a numpy twin.
- **Data.** Synthetic, Yahoo/FRED and CSV providers with point-in-time guards; decision
  memory with reflection.
- **Tools.** Walk-forward backtesting against the baselines, the `agentic-trader` CLI,
  examples, and the pytest and ctest suites.
