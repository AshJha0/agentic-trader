# Changelog

## v0.7.0 — Unreleased

A pass through the whole codebase against its own highest-quality bar: risk aggregated
across the book instead of only per-instrument, two textbook tests of whether the risk
model's own coverage claim is true, multiple-comparison correction on the cross-instrument
bootstrap, a stratified variant of it for correlated clusters, solver convergence reported
rather than assumed, a CLI split into a package, and a locked dependency set to tell
dependency drift apart from a real result change.

### Risk
- **Book-level VaR** (`portfolio.book_var_95`, `portfolio.book_var_scale`, `state.Book`).
  Per-instrument VaR caps do not see correlation across sleeves; `max_book_var_95` (off by
  default) aggregates the whole book's historical VaR and scales a proposed weight down
  (never up) to respect it, by grid search over the position size rather than a closed-form
  or bisected solve, since a new position could be a partial hedge rather than added risk.
  `TradingGraph.scan()` builds the `Book` from the watchlist's own return history when the
  cap is configured; `propagate()` alone never builds one.
- **VaR coverage backtesting** (`stats.rolling_var_forecast`, `stats.var_backtest`,
  `agentic-trader stats --var-backtest`). Kupiec (1995) unconditional-coverage and
  Christoffersen (1998) independence likelihood-ratio tests of a walk-forward historical-VaR
  forecast against realized returns, closed-form against the standard normal CDF (no scipy
  dependency). Run against the 15-sleeve core portfolio's holdout returns: neither test
  rejects at either a 120-day or 250-day window — the desk's own risk model is
  well-calibrated on this data (see
  [the evaluation's VaR coverage section](docs/evaluation/evaluation.md#var-coverage-is-the-desks-risk-model-calibrated)
  and [LEARN.md #34](LEARN.md#34-is-the-risk-model-telling-the-truth-var-coverage-backtesting)).

### Execution
- **Execution-algorithm-aware impact cost** (`algo.algo_cost_ratio`,
  `costs.execution_algo` / `--execution-algo {twap,vwap,ac}`, `costs.ac_kappa` /
  `--ac-kappa`). The daily backtester's square-root impact formula
  (`backtest.impact_coefficients`) implicitly assumed a trade is worked as VWAP -- matching
  participation to the volume curve, which minimises impact cost for a fixed order size, by
  the same convexity argument that already justifies VWAP as the execution simulator's
  default. TWAP (ignores the curve) or Almgren-Chriss (front-loads for urgency, `ac_kappa`)
  now scale the day's impact by that schedule's own cost relative to VWAP on the same
  volume curve, so a trade's simulated cost depends on how it would be worked, not only on
  its size. Off by default (unset == VWAP-equivalent == the existing formula exactly), so
  every previously published impact number is unchanged; measured on the core universe's
  $1B holdout portfolio, TWAP pays 2.51% of equity to impact over the period against VWAP's
  2.37%, and an aggressively front-loaded Almgren-Chriss (kappa=5) pays 3.14% (see
  [the evaluation's execution-algorithm section](docs/evaluation/evaluation.md#execution-algorithm-aware-impact-v07)).

### Evaluation
- **Benjamini-Hochberg FDR correction** (`stats.benjamini_hochberg`). The cross-instrument
  bootstrap's `p` was reported per baseline with no correction for testing several baselines
  at once; `EvaluationResult.paired_table(fdr_q=0.05)` now flags `significant` at the
  FDR-corrected threshold, not the raw `p < 0.05`.
- **Stratified bootstrap** (`stats.paired_bootstrap(groups=...)`). Resamples within each
  asset-class/universe group rather than pooling, so correlated clusters (e.g. the FX
  majors) do not masquerade as independent draws; `EvaluationResult.paired(stratify=True)`
  is the default when the rows carry more than one group.
- **Deflated-Sharpe caveat** made explicit in `selection_report`'s own output
  (`DEFLATED_SHARPE_CAVEAT`), not only in the surrounding prose.
- **Significance-gated diagnostic column** (`alpha.significance_gated_series`,
  `xalpha.significance_gated_scores`) added to the alpha and cross-sectional alpha reports:
  the same per-bar t-stat gate the analysts apply, exposed as its own row so a reader can see
  what passes the gate without re-deriving it from the `ic` column by hand.
- **Solver convergence reported, not assumed** (`portfolio.Convergence`,
  `PortfolioWeights.converged`). `min_variance_weights` / `mean_variance_weights` can now
  report whether their iterative projection actually converged within the iteration budget;
  `construct()` logs a warning and carries the flag through when it did not.
- **Per-job timing** (`EvaluationResult.slowest`). `evaluate()` now times every backtest job
  and `agentic-trader evaluate` prints the slowest, so a hung or unusually slow (period,
  symbol) is visible without instrumenting a re-run.

### Engineering
- **`agentic_trader/cli.py` split into a package** (`agentic_trader/cli/`: `common.py`,
  `decisions.py`, `research.py`, `evaluate.py`, `services.py`, `parser.py`, `__init__.py`),
  one module per concern instead of one 700-line file. `main`, `build_parser`,
  `load_dotenv` and `_config` remain importable from `agentic_trader.cli` exactly as before;
  the `agentic-trader` console script is unchanged.
- **`requirements-lock.txt`**: the exact dependency versions each published number was
  measured with, so a re-run that differs can rule out dependency drift before suspecting
  data drift or a real code change (see Reproducing in
  [the evaluation](docs/evaluation/evaluation.md#reproducing)).
- **Coverage reporting in CI** (`pytest-cov`, `--cov-report=xml`/`term-missing`, uploaded as
  a CI artifact) — report-only, not a merge gate. 94% overall on the numpy backend; weakest
  are `data/yahoo.py` (50%, mostly network-dependent branches) and `llm.py` (75%, the live
  Anthropic call path).
- 319 tests (up from 280), including a new `tests/test_v07.py` covering every item above.

## v0.6.0 — 2026-09-27

Point-in-time filings for the idle half of the analyst team, statistical power across the
universe, a calibration harness for the model's judgement, pinned prompts, a cross-sectional
analyst measured under the protocol, fuzzing of the agentic layer, a bounded task pool with
multi-process serving, the documentation checked in CI, and one configuration knob for the
alpha window. The measured results of every data and rule change are in
[docs/evaluation](docs/evaluation/evaluation.md).

### Data
- **SEC EDGAR point-in-time fundamentals and filing news** (`data/edgar.py`). Free and
  keyless; the SEC requires a contact e-mail in the User-Agent (`EDGAR_USER_AGENT` in
  `.env`), without which EDGAR is skipped with one warning. Every XBRL fact carries the date
  it was *filed*, so a fact exists at `as_of` iff `filed <= as_of`, and a restated value never
  replaces the first print. Quarterly flows are rebuilt from the reported spans (direct
  quarters, year-to-date differencing, Q4 from the 10-K, 12/16-week fiscal calendars such as
  Costco's and PepsiCo's) and summed to trailing-twelve-month growth, margin, EPS and P/E,
  leverage and FCF yield; EPS surprise and insider direction stay `None` because EDGAR has no
  consensus data; funds and index ETFs (SIC 6221, no company facts) return nothing. The news
  feed is the filing stream itself: 8-K item codes mapped to headlines with a conservative
  tone, periodic and ownership filings, insider Form 4 counts; the thousands of routine
  prospectus supplements banks file are excluded. Predecessor filers are mapped
  (`edgar_ciks`; Exxon's 2026 holding-company reorganisation is shipped). Coverage was
  checked for every equity in the 60-name universe at two dates. The Yahoo provider uses it
  for every historical date; `--no-edgar` and `--edgar-cache` on the CLI. Social media has no
  free point-in-time archive and that analyst still abstains on real data.
- `alpha_lookback_days` (900) is the one knob for the alpha library's window — the alpha
  analysts and the `quant.alpha` / `quant.xalpha` tools — next to `lookback_days` (400) for
  everything else; every desk tool's `lookback_days` argument now defaults to the configured
  value instead of a hard-coded 400 or 900.

### Evaluation
- **Cross-instrument bootstrap.** `stats.paired_bootstrap` resamples instruments (pairs
  kept together) for the mean difference between two strategies; `EvaluationResult.paired`
  and `paired_table` give the 95% interval and two-sided `p` per period and baseline, and
  `agentic-trader evaluate` prints them. The published tables now say whether an edge across
  the universe is distinguishable from the luck of which instruments were drawn.
- **Repeated runs.** `evaluate(repeats=N)` / `--repeats N` runs the agent N times per
  (period, symbol), tags rows with `run`, and `run_dispersion` reports the across-run
  spread — the model's own variance, which any single-run difference has to clear.
- **Prompt registry** (`prompts.py`). A SHA-256 hash of every agent's system prompt and
  prompt-building code, bundled into one hash recorded in every evaluation and calibration
  result.
- **Calibration harness** (`calibration.py`, `agentic-trader calibrate`). One frozen state,
  `n` runs per anchor: dispersion of the target weight and action agreement, the anchoring
  slope of the target on the position the desk is told it holds, and drift against a stored
  report on the same state.
- **Cross-sectional alpha analyst** (`xalpha`): the v0.5 cross-sectional research consumed
  by an analyst at last — z-scored against a peer universe on every date (`xalpha_universe`,
  `--xalpha-universe core|extended|all|SYM,...`), significance-gated exactly like the
  time-series alpha analyst, cached per (universe, date). Measured under the protocol on top
  of EDGAR: core design -0.01 [-0.02, 0.00] of per-instrument
  Sharpe, core holdout 0.00, extended holdout -0.01 [-0.01, 0.00],
  reserve +0.01 / -0.03 — **off by default**: it spoke on 2.6% of sampled decisions (never on
  FX) because no alpha clears the cross-sectional significance gate on most dates.
- **The multi-year LLM harness**: model tiers, repeats and prompt hashes on the core universe
  over design and holdout, staged with a dollar cap per stage -- built and budgeted, **not
  yet run**; the evaluation says so explicitly rather than leaving it implied.

### Engineering
- **Agentic-layer fuzzing** (`tests/test_fuzz_agentic.py`): hypothesis properties over
  `coerce_arguments` on random schemas and JSON, `validate_plan` on random plans (the result
  always ends with governance, pins the task's symbol and date, schedules no state change),
  `PolicyEngine.evaluate` (always a decision; never ALLOW for a denied, unauthorised or
  state-changing request), `extract_json` and `untrusted_block`.
- **Bounded task pool and multi-process serving.** `create_app(workers, queue_limit)` runs
  tasks on a thread pool per process and answers `503` + `Retry-After` beyond
  `agentic.queue_limit` in-flight tasks; `/health` reports in-flight, running and queued.
  `serve --processes N` starts uvicorn worker processes from an app factory over a shared task
  store (required: `multiprocess_options` refuses without one); every process serves every
  record, cancel and approvals must reach the owning process (`409` elsewhere).
- **Docs checked in CI**: a `docs` job runs every offline cookbook recipe
  (`scripts/run_cookbook.py --offline`), renders every Mermaid diagram with mermaid-cli
  (`scripts/check_mermaid.py`) and resolves every internal link (`scripts/check_links.py`).
- **Landing page**: what changed in this release at the top; the older result tables below
  the fold.

### Fixed
- **Split basis in the EDGAR per-share ratios** (found by the release review): P/E and FCF
  yield divided a split-adjusted Yahoo close by as-first-printed EPS and share counts, so every
  date before a stock split was off by the split factor (AAPL 2019: P/E 6 instead of 25; NVDA
  2020: 2 instead of 85), and a trailing year that straddled a split mixed share units. The
  fundamentals now take the close *as traded* (from a second, unadjusted Yahoo download with
  the split table) and rebase every EPS and share-count print to the as-of basis before mixing
  quarters; the EDGAR-on tables in the evaluation were re-run on the fix.
- EDGAR: year-over-year revenue growth is only reported when the two trailing years are
  exactly a year apart; the earliest print of a span wins whatever tag it was filed under; a
  missing older submissions page loses its filings, not the ticker; a 404 is never written to
  the disk cache; cached endpoint files older than `edgar_cache_max_age_days` (7) are
  re-fetched so a reused cache cannot hide new filings from a live decision.
- Multi-process serving: a record another process wrote after this one started is loaded
  from the store on demand (`GET /tasks`, `/tasks/{id}`, `/health` and the cancel `409` all
  see it); the interrupted-run sweep runs once in the parent so a worker restart cannot fail
  its siblings' live runs; the configuration is validated before any worker forks; approvals
  resume on the task pool rather than the request thread; a queued task can be cancelled
  before it starts; stopping the server cancels the queue instead of draining it.
- `coerce_arguments` rejects non-finite numbers with `ValueError` (an infinite integer used to
  escape as `OverflowError`); the plan cap only ever drops tool calls, never the analysts or
  the debate / trader / risk stages; `untrusted_block` neutralises tags split across lines or
  left unterminated; the cross-sectional cache is per provider and locked; the calibration
  drift compares at an anchor both reports sampled; baseline rows survive a failed first
  repeat and `summary()` counts instruments once under repeats; `scripts/check_links.py`
  slugs headings the way GitHub does.
- `sma` on both backends now sums each window directly (as `rolling_std` already did)
  instead of carrying a running sum: the C++ boundary fuzzer found a window `[1e-38, 0]`
  after a `1.0` where the running sum left cancellation noise the flatness floor could not
  see, so `zscore` answered +1 on one backend and 0 on the other. The published tables were
  re-run on the fixed code; 19 of 1,680 rows moved, all but a few at the last displayed
  digit (the regression check in the evaluation lists the largest).
- `YahooProvider.history` extends every download to today: a walk-forward caller asks for
  a window ending at each successive as-of date, and each step used to be a new download
  once the requested end passed the cached range (found when the cross-sectional analyst
  fetched 45 peers per decision date). The point-in-time cut is still applied by
  `clip_history` at the requested end.
- The cross-sectional analyst computes only the IC it needs instead of the full
  `xalpha_report` (decay curves, quantile spreads and correlations cost six times the IC
  itself), and the desk tools' `lookback_days` arguments no longer carry hard-coded windows.

## v0.5.1 — 2026-09-26

The first measured LLM results, and the evaluation protocol's first use for a rule change.

### LLM evaluation (first ever)
- **The LLM desk measured for the first time**, lean by design: AAPL, NVDA, MSFT, META,
  GOOGL over Q1 2024, a decision every 10 bars, one debate round, `claude-opus-5` at medium
  effort with `claude-haiku-4-5` analysts, anonymised prompts, a 400-call cap, against the
  rule-based desk on identical bars. 271 calls, 0 refusals, 0 fallbacks, 0 errors, $4.12.
  **Same Sharpe as the rules (2.19 vs 2.19)**, less than half the exposure (23% vs 57%),
  return (6.9% vs 15.5%) and drawdown (2.2% vs 5.6%) on every name: the model sized down
  citing the abstaining analysts. A single quarter shows what it does, not whether it has an
  edge; the multi-year run with the full analyst team is a matter of spend. Every
  "not evaluated" caveat in the docs is replaced by this result and its limits.

### Rules
- **FX carry-neutral strategic weight** (`rules.fx_carry_neutral`, on by default). The FX
  analogue of the equity strategic weight: `clip(rate_diff% / 2, ±0.5)` from the macro
  analyst's point-in-time policy-rate differential, so the desk holds the higher-yielding
  currency unless convinced otherwise. Chosen on the core FX pairs' design period only
  (mean Sharpe −0.03 → +0.11, monotonic across five settings), then judged on data no choice
  had touched, where it improved every slice: extended crosses design −0.24 → −0.15, holdout
  +0.12 → +0.31, reserve −0.63 → +0.22; core reserve −0.58 → −0.10. It does not make the desk
  beat buy & hold on crosses. `RULES_V03` / `--rules v03` reproduces the previous rule set;
  the published tables are re-run under the new default and the v0.3-rule tables are kept as
  the record. Re-run headline numbers: core holdout mean Sharpe 0.44 → 0.46, extended holdout
  0.37 → 0.42, 15-sleeve portfolio holdout 1.14 → 1.16 (design 1.50 → 1.54); equities unchanged.

### Fixed
- `UsageTracker` cost lookup now matches a served model id with a date suffix
  (`claude-haiku-4-5-20251001`) to its family's list price instead of reporting `n/a`.

## v0.5.0 — 2026-09-26

A wider, fresher evaluation; execution-aware backtests; cross-sectional alphas; cross-asset
risk budgets; ALFRED vintages; a persistent task store; a dollar LLM budget; TLS and
deployment guards; property-based fuzzing of the C++ boundary; and the alpha-analyst fixes.

### Evaluation
- **Universe widened from 15 to 60 instruments.** The 15 *core* instruments (every rule
  choice through v0.4 was made on them) are joined by 45 *extended* ones that no choice ever
  consulted: 26 equities across sectors and styles (UNH, V, MA, PG, HD, COST, WMT, KO, PEP,
  CVX, LLY, ABBV, MRK, BAC, GS, CAT, BA, BRK-B, QQQ, IWM, XLF, XLE, XLV, XLU, EEM, EFA), 9
  rates / credit / commodity / real-estate ETFs (TLT, IEF, LQD, HYG, GLD, SLV, USO, DBC, VNQ)
  and 10 FX crosses whose both legs have FRED policy-rate series (NZDUSD, USDCHF, EURGBP,
  EURJPY, GBPJPY, AUDJPY, EURCHF, AUDNZD, CADJPY, EURAUD). `UNIVERSES`, `universe_group()`,
  a `universe` column in every result row, `summary(universe=)`, `head_to_head(universe=)`
  and `evaluate --universe core|extended|all`.
- **A fresh holdout for the next rule change.** The 2022–2026 holdout has been seen, so
  v0.5 defines what "unseen" means from here: the extended universe over *every* period,
  plus a `reserve` period (2026-07-01 → 2026-09-25) that no number in the documentation
  consults. The protocol is written down in the evaluation.
- **Execution-aware backtests.** `costs.impact_coeff` (default 0) charges square-root market
  impact in the backtester — the execution simulator's model, applied per trade to the agent
  *and* every baseline: a trade of `|dw|` costs `|dw|^1.5 · K_t` of equity with
  `K_t = coeff · daily_vol · sqrt(capital / (price · ADV))`. `Impact%` is reported per
  strategy; `--impact` and `--capital` on the backtest, portfolio and evaluation commands.
  The published tables include the core universe at three account sizes.
- **Alpha analyst.** Two bugs fixed (see below); measured a third time and still off by default.

### Research
- **Cross-sectional alphas** (`xalpha.py`): the same signals standardised across the names of
  a group every day (z-score or rank, equities and FX separately), evaluated with per-date
  Spearman IC, an IC information ratio, a t-statistic that accounts for overlapping horizons,
  the share of positive days, top-minus-bottom quantile spreads and breadth. `xalpha_report`,
  `xalpha_snapshot`, the `quant.xalpha` tool (16 tools now) and `agentic-trader xalpha`.
- **Cross-asset risk budgets** (`portfolio.construct(groups=, group_budgets=)`): the chosen
  scheme allocates within each asset class, then risk parity with the budgets allocates
  across classes from the full covariance; `group_risk` reports budget vs realised risk
  share. `run_portfolio_backtest(class_budgets=)` and `portfolio --class-budgets equity=0.6,fx=0.4`.
- **ALFRED vintages** (`fred_vintages`, `--fred-vintages`): revised series (CPI) are read from
  the ALFRED vintage current at each date, so inflation enters the backtest as first
  published. Monthly vintage sampling (one download per series per month, cached in memory
  and optionally on disk with `fred_cache_dir`). Off by default; policy rates are never
  revised and are unaffected.

### Agentic layer and services
- **Persistent task store** (`agentic/store.py`, `agentic.task_db`, `serve --task-db`): every
  run is written to SQLite at each state transition; a new process serves old records
  through the same API routes (`GET /tasks`, `/tasks/{id}`, `/report`, `/trace`,
  `/evidence`); records left mid-flight by a crash are marked FAILED "process restarted",
  never silently resumed.
- **Dollar LLM budget** (`max_llm_cost_usd`, `--max-llm-cost`): `BudgetedLLM` now caps
  estimated spend as well as calls (list prices, cache-aware); the overshoot is at most one call.
- **TLS and deployment guards** (`serve --ssl-cert/--ssl-key`, `serve_options`): binding a
  non-loopback interface with the shipped development API keys is refused unless
  `--allow-dev-keys`; plain HTTP off loopback logs a warning. `make_config` now *replaces*
  `agentic.api_keys` instead of merging into the dev keys (a real footgun: adding a real key
  used to leave every dev key live).
- **`.env` loading.** The CLI reads a project-local `.env` (`KEY=VALUE`, git-ignored) without
  overriding the environment; `scripts/set_api_key.ps1` stores the key as a Windows user
  variable with hidden input.

### Quant core
- `BacktestInputs.impact` / `BacktestResult.impact_paid` in C++, the numpy twin and the
  bindings; `run_backtest(impact=)`.
- **Property-based fuzzing of the Python ↔ C++ boundary** (`tests/test_fuzz.py`, hypothesis):
  every quant entry point on NaN / ±inf / empty / huge inputs must either return a
  well-formed result or raise `ValueError`, and the two backends must agree on sane inputs.
  It found and fixed five divergences: `quantile(x, NaN)`, `max_drawdown` with NaN (numpy
  did not skip it), `kdj` and `atr` windows containing NaN (`std::max` silently skips NaN,
  numpy propagates it — both now treat a missing bar as a missing range), `zscore` on a
  flat window (cancellation noise gave ±1; both now floor the spread), and a
  `compute_metrics` overflow on the numpy side. Non-finite prices are now rejected by both.

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

### Tests and docs
- **Tests:** 199 → **240** pytest tests (v0.5 features 18, fuzz 21 property tests, impact 3)
  + 14 C++ test groups; hypothesis added to the `dev` and `all` extras.
- **Docs:** LEARN (30 concepts), COOKBOOK (64 recipes), DIAGRAMS (27), architecture,
  specification, threat model (36 threats), API, evaluation (60-instrument tables, impact
  sweep, the fresh-holdout protocol) and the landing page updated.

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
