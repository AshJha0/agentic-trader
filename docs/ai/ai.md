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
| quick | `claude-haiku-4-5`, effort `low` | analysts | summarising tool output is a light task and there are four or more per decision |
| deep | `claude-opus-5`, effort `high` | researchers, facilitator, trader, risk team, portfolio manager; critic, reporter and planner in the agentic layer | these weigh evidence against evidence |

`request_shape` builds the API parameters each model family accepts (thinking mode, effort
levels), so changing the model id in the config is enough.

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

### Cost control

`BudgetedLLM` caps the number of calls and the dollar spend (`max_llm_calls`,
`max_llm_cost_usd`). In the default `hard` mode each call reserves its maximum possible cost
before it is sent, so parallel workers cannot overshoot the cap, and a retry must be admitted
by the budget like a new call. Past the cap every call returns `None` and the run finishes on
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
2. the weight is capped at the maximum position;
3. the position's 1-day 95% historical VaR must be within the limit, or the weight is scaled down;
4. optionally the whole book's VaR must be within its limit;
5. a weight below the minimum trade size becomes flat.

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
| Information coefficient of each alpha | `alpha.py`, `xalpha.py` | The alpha analysts combine signals weighted by IC, and only signals whose IC t-statistic is at least 2 in magnitude. Otherwise they abstain |
| Covariance with EWMA weights and Ledoit-Wolf shrinkage | `portfolio.py` | Risk parity, minimum variance and mean-variance weights |
| Historical VaR and CVaR | `quant`, `agents/risk.py` | Position and book limits |
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
