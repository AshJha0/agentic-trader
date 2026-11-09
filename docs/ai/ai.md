# How the AI works: agents, the LLM, machine learning and the agentic layer

This page explains, in one place, what is "AI" in AgenticTrader and what is not. It is written
for a reader who wants to know what each agent does, when a language model is called, what
it is allowed to decide, and what stops it from doing damage. The quantitative side
(indicators, backtester, risk, alphas, statistics) has its own page:
[How the quant works](../quant/quant.md).

Related pages: [architecture](../architecture/overview.md), [diagrams](../DIAGRAMS.md)
(1 to 16 cover everything here), [threat model](../threat-model/threat-model.md),
[API](../api/api.md), and concepts 1 to 17 of [LEARN.md](../../LEARN.md).

## The short version

| Term | What it means in this project |
|---|---|
| **Agent** | A Python class with one job on the desk (an analyst, a researcher, the trader, a risk analyst, the portfolio manager). Each one gathers facts with tools, applies transparent rules, and may ask a language model to reason over the same facts |
| **LLM** | Claude, called through `agentic_trader/llm.py`. It is **off by default** (`llm_provider: "offline"`). Every published backtest number except one small experiment comes from the rules, not from a model |
| **Agentic layer** | The control plane in `agentic_trader/agentic/`: a state machine that runs a validated plan, gates every tool call by policy, records evidence, criticises the result and audits the report |
| **ML** | No model is trained or fitted by gradient descent anywhere in the repository. What is *estimated from data* is statistical: information coefficients of alphas, covariance matrices with shrinkage, a TF-IDF index for retrieval, historical VaR. They are listed below |
| **RAG** | Retrieval over the desk's own runbooks and policies with a dependency-free hashed TF-IDF index. No embedding model |

The design rule behind all of it: **the model may interpret, the code decides what is
allowed.** Data is fetched by code. Numbers are computed by code. Limits are enforced by code
after the model has spoken. The model's contribution is judgement over facts it was handed.

## 1. The agents on the desk

The desk mirrors a trading firm. One pass (`TradingGraph.propagate`) runs these stages in
order and produces one sized, explained decision for one instrument on one date.

| Stage | Agents | Model tier | Output (a structured document) |
|---|---|---|---|
| Analysts | `technical`, `fundamentals` (equity), `macro` (FX), `news`, `sentiment`; optional `alpha`, `xalpha` | quick | `AnalystReport`: signal in [−1, 1], confidence in [0, 1], summary, key points, the facts used |
| Debate | bull researcher, bear researcher, facilitator | deep | `DebateOutcome`: winner, score in [−1, 1], conviction, the turns |
| Trader | trader | deep | `TradeProposal`: action, target weight, stop, take-profit, horizon, rationale |
| Risk | aggressive, neutral and conservative risk analysts | deep | three `RiskView`s: a recommended weight and an argument each |
| Decision | portfolio manager | deep | `FinalDecision`: final weight after the firm's limits, with every adjustment listed |

The default analyst set is four per asset class: technical, fundamentals, news and sentiment
for equities; technical, macro, news and sentiment for FX (`graph.DEFAULT_ANALYSTS`).

### Every agent follows one pattern

`agents/base.py` states it, and every agent class implements it:

1. **Tools.** Deterministic data gathering and computation. The technical analyst computes
   moving averages, MACD, RSI, Bollinger %B, KDJ, ATR and returns through the quant core.
   The fundamentals analyst reads point-in-time filings. Nothing here involves a model.
2. **Rules.** A transparent rule-based judgement over those facts. It is always computed.
   It is the agent's answer in offline mode, and the fallback in every other case.
3. **LLM (optional).** When a model is configured, it receives the same facts and must
   return one JSON object. If the reply meets the contract it replaces the rule-based
   judgement; the rule-based signal is kept beside it (`rule_signal`) so the two can be
   compared later.

An analyst that has no data abstains (`self.abstain(...)`): it makes **no model call**, so a
model cannot invent a view from an empty input.

### What the rules actually do

The rules are simple on purpose, so that a decision can be read and checked.

- **Technical analyst.** Adds fixed contributions: price above or below the 50-day average
  (±0.30), the 50-day above or below the 200-day (±0.20), the sign of the MACD histogram
  (±0.15), the 20-day return scaled by its volatility (up to ±0.15), and overbought or
  oversold readings from RSI and Bollinger bands as a fade. Two further rules sit behind
  switches that are off by default (`rules.tsmom`, `rules.trend_filtered_reversal`).
- **News and sentiment analysts.** Score headlines and posts with a small finance lexicon
  (`sentiment.py`: a bag of words with negation handling, and for FX a reading of which
  currency a clause is about). Since v0.11 the news analyst's confidence follows the total
  tone the headlines carry, and it abstains when they carry almost none.
- **Debate.** The facilitator's rule is a weighted consensus: each analyst's signal weighted
  by its confidence and by a fixed role weight (technical, fundamentals and macro 1.0, news
  0.7, sentiment 0.5). Above the decision threshold (0.10) the bull side wins, below the
  negative threshold the bear side, otherwise the verdict is "balanced".
- **Trader.** Starts from a *strategic weight* (fully invested for equities, the carry-based
  weight for FX) and adds a tilt of twice the debate score when the score clears the
  threshold. Stops and targets are set from ATR. A poor recent track record on the
  instrument cuts the size by a quarter.
- **Risk team.** The neutral analyst sizes to the volatility target. The aggressive one takes
  1.25 times that. The conservative one takes half of the smaller of the proposal and the
  vol-target size, and cuts further to respect the VaR limit.
- **Portfolio manager.** Blends the three views (25% / 50% / 25%) and then applies the
  guardrails described in section 4.

## 2. The language model

### When it is called

Only when `llm_provider` is `"anthropic"` and an API key is present. Otherwise `get_llm`
returns nothing and every agent uses its rules. This is why the whole test suite, the
cookbook and every published table run without a key.

There are two tiers (`config.py`):

| Tier | Default model | Used by | Why |
|---|---|---|---|
| quick | `claude-haiku-5-5`, effort `low` | analysts | summarising tool output is a light task and there are four or more per decision |
| deep | `claude-sonnet-5-5`, effort `medium` | researchers, facilitator, trader, risk team, portfolio manager; critic, reporter and planner in the agentic layer | these weigh evidence against evidence |

`claude-opus-5-5` is the optional upgrade for the deep tier (set `deep_think_llm`); at list
price it costs twice Sonnet 5.5 per token ($4 / $20 against $2 / $10 per million input / output
tokens; Haiku 5.5 is $0.10 / $0.50). `request_shape` builds the API parameters each model
family accepts (thinking mode, effort levels), so changing the model id in the config is
enough. The desk never forces a `tool_choice`; the 5.5 families reject a forced one
(`NO_FORCED_TOOL_CHOICE`).

The system prompt goes out as one block marked for prompt caching (`cache_control`
ephemeral): it is the stable prefix of every call an agent makes. A prefix shorter than the
model's minimum cacheable length is simply not cached; the usage summary then shows no
`cache_read_tokens`.

### What it is given

A system prompt made of a fixed firm preamble (`FIRM_CONTEXT`) and the agent's role, and a
user prompt with: the instrument, the date, the facts as JSON, the earlier documents it needs
(reports, debate, proposal), and the JSON keys it must return.

Third-party text never sits among the instructions. Headlines, social posts, and anything
written from them (analyst summaries, debate turns, rationales, lessons from memory) are
placed inside an `<untrusted_data>` block, and the preamble tells the model to treat that
block as material to analyse and never to follow instructions inside it. The flag travels
with the document: a report written from headlines stays fenced wherever it is quoted next.

### What happens to its reply

Each structured reply has a JSON schema in `agentic_trader/contracts.py`. When the backend
supports it, the schema is sent as `output_config.format` (structured outputs), so the API
returns JSON of that shape. That removes the parse failure; it does not make the values
right, so the contract below stays as a second gate. A test checks every schema against the
API's schema rules and runs one recorded-shape reply per contract through both.

`Agent.ask_json` enforces a contract:

- the reply must contain one JSON object;
- every required key must be present;
- every numeric key must be a finite JSON number (not a string, not `NaN`, not a boolean).

A reply that fails is **rejected as a whole** and the rules apply. A half-parsed reply is
never coerced to zero and booked as the model's view. Values that pass are clipped to their
legal range (a signal to [−1, 1], a weight to the position cap), and price levels the model
proposes are kept only when they sit on the correct side of the entry.

`llm.complete` returns `None` on any failure (no key, network error, timeout, refusal,
unparseable output). The agent then uses its rules. **A run never fails because of the model.**

On the families in `REFUSAL_FALLBACK_FAMILIES` (Fable 5.1, Opus 5.5, Opus 5, Sonnet 5.5; Haiku
5.5 has none) a request is sent with the server-side refusal fallback (`fallbacks="default"`,
beta `server-side-fallback-2026-07-01`), so a declined request may be finished by another
model. Every call leaves evidence in `TradingState.llm_calls`: configured and served model, stop
reason, refusal category, any fallback switch, and whether the served id drifted. A served id
that is neither the configured id nor that id with a date suffix, with no fallback recorded,
is drift: counted in `usage.model_drift` and, with `llm_strict_model` on (the default), the
reply is discarded and the rules apply. `FinalDecision.models_served` lists the ids that
actually answered.

### Cost control

`BudgetedLLM` caps the number of calls and the dollar spend (`max_llm_calls`,
`max_llm_cost_usd`). In the default `hard` mode each call reserves its maximum possible cost
before it is sent, so parallel workers cannot overshoot the cap, and a retry must be admitted
by the budget like a new call. The input side of a reservation is the actual prompt: counted by
the free `count_tokens` endpoint when an API key is set, otherwise estimated locally on the high
side ((chars / 3 + 64) × 1.35). Past the cap every call returns `None` and the run finishes on
rules. `UsageTracker` records tokens and cost per model; an evaluation result carries that
summary.

### Keeping the model from remembering the answer

A model trained on data that covers the backtest period may recognise "NVDA, March 2024" and
recall what happened next. With `llm_anonymize` every prompt is rewritten (`anonymize.py`):

- the ticker becomes a neutral alias;
- every date becomes an offset from the decision day (`D0`, `D-12`);
- every price level is rebased so the last close is 100;
- only facts on an allow-list of scale-free keys (returns, ratios, rates, volatilities)
  pass through. Anything else is dropped, because an absolute number such as revenue
  identifies the company.

Prices the model returns are mapped back, and names are restored in the audit trail. The
critic, the reporter and the planner go through the same scrubbing. The threat model lists
what still leaks (distinctive statistics, company names inside real headlines).

### Checking that no agent reads the future (v0.14)

Anonymisation stops the model recognising a period. A separate question is whether the
desk's own code hands it, or the rules, anything dated after the decision day.
`leakage.future_leak_canary` answers that by experiment: it runs the offline desk twice, once
on the data and once on a `ShockedProvider` copy whose prices for one symbol are tripled from
date T and whose news and social feeds gain a headline dated T. With a `PromptRecorder` as the
backend every agent builds its prompt and the rules decide, so the prompts are compared too.
Every report, the debate, the proposal, the risk views, the decision, every prompt and the
alpha values for a date before T must be byte-identical between the two runs; any difference
is a read of the future. On synthetic AAPL and EURUSD (`tests/test_v14_leakage.py`) no output
differed before T and outputs changed on T, and an analyst patched to read one week ahead was
caught. The canary does not cover a leak inside a provider's own `news()` or `fundamentals()`:
`ShockedProvider` passes fundamentals through unchanged and only adds one item to news, so a
provider that returned future items itself would look the same in both runs.

### Reproducibility of prompts

`prompts.py` hashes every agent's system prompt and the source code that builds its user
prompt into one bundle hash, stored in each evaluation result. Two runs with the same hash
used the same wording. `calibration.py` measures what a backtest cannot: how much the
model's answer varies when asked the same question several times (dispersion), how much it
leans on the position it is told it already holds (anchoring), and how the answer moves
between model versions (drift).

### What has been measured with the model

One experiment, in v0.5.1: five stocks, one quarter, anonymised prompts, about $4 of calls.
The LLM desk had the same Sharpe ratio as the rules with less than half the exposure. That
is one small sample, and it was produced under the engine before the v0.8 corrections. No
multi-year LLM backtest has been run. Every other number in the project is the rule-based
desk. See [the evaluation](../evaluation/evaluation.md#the-llm-desk-v051-the-first-measured-result).
The v0.16 local-model results (red-team, text analysts, planner survival) and the pending P2
study rows are collected, each with its evidence class, in
[what the model adds](../evaluation/what_the_model_adds.md); what in the path is real,
simulated or absent is in the [live-readiness statement](../evaluation/live_readiness.md).

## 3. Memory and reflection

`memory.py` logs every final decision. Once the decision's horizon has passed, the realised
outcome is attached with a short lesson, and later decisions on the same instrument receive
those lessons and a hit rate. Three properties matter:

- outcomes are valued on the price series handed to the desk at the current date, which
  stops at that date, so a backtest cannot see the future through memory;
- the log on disk is append-only and safe for several processes;
- lessons quote earlier rationales, which may have been model-written from third-party
  text, so they are shown to the model inside the untrusted fence.

This is the only way the desk "learns" from experience, and it is bookkeeping, not training.

## 4. Hard limits after the model

Whatever the portfolio manager (rules or model) decides, `PortfolioManager.guardrails` runs
afterwards, in code:

1. no short position where shorting is not allowed;
2. a short is capped at `risk.max_short_notional` of capital when that is set (v0.14; default `None`);
3. the weight is capped at the maximum position;
4. the position's 1-day 95% historical VaR must be within the limit, or the weight is scaled down;
5. in a multi-sleeve `scan`, the whole book's 1-day 95% VaR must be within `risk.max_book_var_95`
   (on by default at 5% since v0.14, forecast by filtered historical simulation);
6. a weight below the minimum trade size becomes flat.

Then the no-trade band keeps the current position when the new target is close to it, but
only if the current position would itself pass every limit. Each adjustment is written into
the decision, so the audit trail shows what the model wanted and what the firm allowed.

## 5. The agentic layer

The desk above can be called directly. The agentic layer runs the same stages the way a
controlled system would. **Agents never control the loop.**

| Part | Module | What it does |
|---|---|---|
| Harness | `agentic/harness.py` | A state machine: CREATED → PLANNING → VALIDATING_PLAN → EXECUTING (⇄ AWAITING_APPROVAL) → CRITIQUING → VALIDATING_EVIDENCE → FINALISING → COMPLETED, with FAILED and CANCELLED reachable from any live state |
| Tools | `agentic/tools.py`, `servers.py` | Every capability is a registered Python function with a JSON schema derived from its signature. 16 tools on 5 servers (market data, quant, knowledge, portfolio, execution). The same definition serves in-process calls, the planner's catalogue and the MCP server |
| Policy | `agentic/policy.py` | Ordered rules decide ALLOW, DENY or REQUIRE_APPROVAL for each call and role: deny list, required capabilities, argument guards, read-only, risk level, then allow. The rule that decided is named in the decision |
| Evidence | `agentic/evidence.py` | Every tool call, successful or not, leaves a record with a SHA-256 digest of its payload, before any agent interprets it |
| Planner | `agentic/planner.py` | The canonical plan, or a plan the model proposes. Either way the validator makes it safe |
| Critic | `agentic/critic.py` | Deterministic checks on the finished decision, then an optional model critique |
| Reporter | `agentic/reporter.py` | Builds the report and audits it |
| Knowledge | `agentic/rag.py` | Retrieval over the desk's runbooks and policies |
| Store, tracing | `agentic/store.py`, `tracing.py` | Every state transition persisted to SQLite when configured; spans and counters for each run |
| Interfaces | `agentic/api.py`, `mcp_server.py` | An HTTP API with roles, approvals and a bounded task pool; an MCP server over stdio |

### Plans a model may propose, and why that is safe

With a model, the planner can ask for a plan as JSON. The validator then:

- drops any step whose type, tool or stage is not in the catalogue;
- drops unknown arguments and pins `symbol` and `as_of` to the task's own, so a plan cannot
  look at another instrument or another date;
- enforces stage order (debate needs analysts, the trader needs the debate, risk needs the
  trader) and inserts a missing stage;
- always appends the governance steps (critic, validate, finalise), last and in order;
- caps the number of steps and the amount of history the plan may load.

If nothing usable remains, the canonical plan runs. A model can therefore reorder and add
read-only research steps. It cannot skip the critic, reach another symbol or remove a limit.

### Approvals

A tool that changes state (submitting an order ticket) is never read-only and is rated high
risk, so policy returns REQUIRE_APPROVAL. The harness parks the run in AWAITING_APPROVAL and
resumes from the same step when a person decides. A plan is single-use, a state-changing
tool is never retried, and one approval permits at most one side effect. The framework never
connects to a broker: the "order" is a ticket.

### The critic can only lower confidence

Seven deterministic checks run on every decision: cited evidence resolves; a model-written
analyst signal does not diverge from the rule signal on the same facts beyond a threshold;
analysts do not contradict each other without the verdict saying so; firm limits hold;
protective levels are on the right side; the direction matches the debate unless an
adjustment explains it; single-source findings are capped at 0.6 confidence. A failed check
lowers confidence. Nothing in the critic, including its optional model critique, can raise it.

### Audited reports

The report's narrative is a template, or a model given only the structured facts. Then two
audits run: every number in the narrative must match a fact (allowing rounding, sign and
percentage forms), and every evidence id must resolve. A mismatch is attached to the report
as a warning. A model-written report cannot quietly introduce a number.

## 6. Retrieval (RAG)

The knowledge base is the desk's own Markdown runbooks and policies, split by heading into
chunks. Each chunk is embedded as a hashed TF-IDF vector: words and word pairs are hashed
into a fixed number of buckets, weighted by term frequency and inverse document frequency,
and normalised, so similarity is a cosine. There is no model download and the results are
deterministic. Passages reached through the `knowledge.search` tool become DOCUMENT evidence
and are shown to the trader and the portfolio manager as firm policy.

## 7. Where statistics are estimated from data (the "ML" in the project)

Nothing is trained with a learning algorithm. These are the places where a quantity is
estimated from data and then used:

| What | Where | How it is used |
|---|---|---|
| Information coefficient of each alpha | `alpha.py`, `xalpha.py`, `leakage.py` | Estimated on purged walk-forward folds since v0.14. The alpha analysts combine signals weighted by IC, and only signals whose fold t-statistic clears the gate. Otherwise they abstain |
| Covariance with EWMA weights and Ledoit-Wolf shrinkage | `portfolio.py` | Risk parity, minimum variance and mean-variance weights |
| Historical VaR and CVaR; EWMA volatility and FHS VaR (v0.14) | `quant`, `risk_model.py`, `agents/risk.py` | Position limit (historical); book limit (EWMA by default, `config.DEFAULT_VAR_METHOD`) |
| TF-IDF document frequencies | `agentic/rag.py` | Retrieval |
| Hit rate of past decisions | `memory.py` | The trader's size cut |
| Bootstrap distributions | `stats.py` | Every interval and p-value in the evaluation |

The alpha analysts are off by default. They were measured on the design period and did not
improve the desk, which the evaluation reports.

## 8. What the AI does not do

- It does not fetch data. Tools do, under policy.
- It does not compute indicators, risk numbers or backtests. The quant core does.
- It does not set or relax a limit. The guardrails run after it.
- It does not place orders. Nothing connects to a broker.
- It does not produce the published results. Those are the rule-based desk, with one
  labelled exception.
- It has not been shown to add return. The honest standing result of the project is that the
  rule-based desk has no measurable edge over a volatility-targeted holding of the same
  instruments, and the one LLM measurement is too small to say more.

## 9. Try it

```bash
agentic-trader analyze NVDA --date 2024-03-01            # one decision, rules only, no key needed
agentic-trader task EURUSD --date 2024-03-01             # the same through the harness: plan, evidence, critic, audited report
agentic-trader tools                                     # the tool catalogue with annotations
agentic-trader analyze NVDA --date 2024-03-01 --llm anthropic --anonymize --max-llm-cost 1   # with the model, capped at $1
```

Cookbook recipes 1 to 8 (decisions), 17 to 19 and 36 (the model and its budget), 39 to 50
(the agentic layer) and 68 to 70 (repeated runs, calibration, the prompt hash) show each
piece in a few lines.

## 10. A local model and the LLM study (v0.14, plan items 2.1-2.2): ready but unrun

**The idea.** A model running on the same machine costs nothing per call and sends nothing
off the host, which makes a full study of where a model helps the desk affordable.

**Precisely.** `llm_provider = "local"` selects `local_llm.LocalLLM`, which posts to Ollama's
`/api/chat` at `local_llm_url` (default `http://127.0.0.1:11434`) with `local_llm_model`,
`local_llm_timeout_s` (120) and `local_llm_seed`; temperature is 0. A structured reply sends
the contract's JSON schema in the request's `format` field, and the agent's contract check
still runs afterwards. Anonymisation, evidence (`last_call`) and `max_llm_calls` apply as for
Claude; `estimate_cost` is 0, so only the call cap binds. A timeout, refused connection, HTTP
error or unreadable body returns `None` and the rules answer, with no retry.

`scripts/llm_study.py` defines eight cells (v0.16 added `local_analysts`): `rules`, `local_all`, `local_text`, `local_pm`, `local_analysts`,
`no_debate`, `debate_1`, `neutral_risk`. `--describe` lists them, `--dry-run` counts calls
and prompt tokens without a model, `--live` runs them on a local model and refuses if Ollama
does not answer.

**Status (updated v0.16).** OD-6 was decided on 2026-11-08: a 7-8B 4-bit model on the
15.6 GB machine is acceptable. The model in use is `qwen2.5:7b-instruct` on CPU through Ollama. It has
answered desk prompts in v0.15 (text analysts, injection compliance); the v0.16 study cells
(`local_analysts`, then `local_all`, plus `rules`) are pending: filled when the run finishes. An eighth cell, `local_analysts`,
was added in v0.16 and registered in `evaluation.TRIALS` before any run.

**Example: what the study would cost on Claude.** The dry run for 15 names x 40 dates x 2
seeds, priced at Claude list prices: `local_all` makes 16,800 calls, estimate $214.82,
ceiling $1,992.26. The estimate assumes 400 output tokens per quick call and 1,500 per deep
call; the ceiling assumes every reply runs to `max_tokens`. On a local model the same study
costs $0, which is why it is planned there.

### 10.1 The v0.16 study tools (plan items 2.3-2.8)

**The idea.** Before trusting a model's view, check three things: that it cannot see through
the anonymisation, that it gives the same answer to the same question, and that it uses only the
facts it was given. Then compare desks, and look at the holdout once.

**Precisely.**

| Item | Tool | Measures | Result |
|---|---|---|---|
| 2.3, 2.5 | `scripts/llm_study.py --first-pass --live` / `--report` | Sharpe minus vol-target control (block bootstrap), fallback share vs 10% cap, fallback by regime and date (chi-square) | pending: filled when the run finishes |
| 2.4 | `scripts/v16_local_study.py recall` | ticker hit rate vs 1/15, month vs 1/72; leaking keys by ablation | pending: filled when the run finishes |
| 2.6 | `scripts/v16_local_study.py calibration`, `drift` | dispersion (n=5, temperature 0.7), anchoring slope on `rsi14`, drift on 20 states | pending: filled when the run finishes |
| 2.7 | `scripts/v16_eval.py run/check/judge/agreement` | used facts, invented no numbers, respected fence; judge kappa vs human labels | pending: filled when the run finishes |
| 2.8 | `docs/evaluation/v16_preregistration_DRAFT.md` | design bar and one holdout look | draft, unsigned |

Evidence class for every row: tool built and tested offline against fakes and fixtures
(`tests/test_v16_*.py`); no model result yet.

Every one of the seven model cells in `scripts/llm_study.py` is registered in
`evaluation.TRIALS` before it is run (PLAN 6.1), so the deflated Sharpe counts all of them;
`stats.selection_report(..., n_trials=evaluation.registered_trial_count())` applies the count
when only some cells have a measured Sharpe. Results land in
[what the model adds](../evaluation/what_the_model_adds.md); the study design is
[diagram 40](../DIAGRAMS.md#40-the-llm-study-cells-trials-and-the-rules-control-v016).

**Example.** If the recall audit found 20 ticker hits in 200 prompts, the rate 0.10 would be
compared with chance 1/15 = 0.067 by an exact one-sided binomial test (p = 0.046); a key
whose removal loses those hits would be added to the anonymiser's drop list. The numbers here
are illustrative, not a result.

## 11. Text, research retrieval and an auditable agent (v0.15, plan items 3.1-3.9, 4.1-4.6, 4.8, 4.9)

**Plain idea.** The desk can now read filing text and central-bank statements, but every
piece of that text is treated as untrusted, retrieval is measured before an analyst may use it,
and each agent run can be recorded and replayed to check it gives the same decision.

**What exists.**

- *Filing text (3.1).* Sections of 10-K, 10-Q and 8-K filings, dated by SEC acceptance time,
  each wrapped in an `<untrusted_data>` fence before it reaches a prompt.
- *Research retrieval (3.4-3.7).* A point-in-time corpus; hashed TF-IDF by default, hybrid
  TF-IDF + BM25 by reciprocal-rank fusion, optional local embeddings (`[rag]`, untested).
  Passages go to the model as `document` blocks with citations enabled, and an audit rejects a
  claim whose quoted span is not in the cited passage. On 100 questions over a 34-passage
  invented corpus: TF-IDF recall@5 0.990, MRR 0.954; hybrid 0.990, 0.961; the 0.8 gate passes.
  Real filings are untested.
- *Text analysts (3.8).* Fundamentals-text (claims must cite passages) and macro-text
  (hawkish/dovish shift). Since v0.15.1 they are wired into the desk and off by default:
  `text_analysts: ["fundamentals_text", "macro_text"]` adds their reports before the debate,
  on both the graph and the agent-harness path. They read only text visible at the as-of day
  at 20:00 UTC, and research passages only through the 0.8 retrieval gate. The Claude variants
  are dry-run only.
- *Runbook RAG (3.9).* Kept: removing it changed 0 of 9 decisions on synthetic data (rules path),
  so it neither helps nor harms there.
- *Governance (4.1-4.3).* Outcome join and per-role hit rates (n = 0 real TaskRuns so far);
  planner survival: canonical 100%, rule planner 100%, synthetic model-plan fixtures 95.1%
  (1547/1626), which tests the validator, not a model; a governed memory tool.
- *Injection red team (4.4).* 150 snippets: 150/150 fenced, rules signal equal to the lexicon
  score 150/150, 6/150 direction flips from the words "buy" and "sell" in the attack text. Model
  compliance not run. A leak of `_`-prefixed facts into `Analyst.prompt` was found and fixed.
- *Approvals and tools (4.5, 4.6).* Signed N-of-M approvals (opt-in; shared-secret HMAC is the
  residual risk). Deferred tool loading on MCP and HTTP: the model sees names and loads schemas by
  search.
- *Replay and SLOs (4.8, 4.9).* `task --record` / `replay`; per-stage SLOs; optional OTel export;
  golden transcripts on three frozen states.

**Example.** `agentic-trader task AAPL 2024-03-01 --record` then `agentic-trader replay <id>`
prints `MATCH` when the decision and end state are reproduced from the recording
([recipe 110](../../COOKBOOK.md#110-record-a-task-and-replay-it-offline)).
