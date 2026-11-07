> **Superseded 2026-11-07 by [PLAN.md](PLAN.md), the single living plan. Kept as the record of how the plan was reached.**

# AgenticTrader: AI, ML, LLM, agentic and RAG improvement plan (2026-11-07)

Companion to [2026-11-07_in_depth_review.md](2026-11-07_in_depth_review.md). That document says
what is wrong; this one says what to build, in what order, what it costs and which decisions
are the owner's. It is a plan to execute later, not a changelog. Nothing here has been started.

Conventions. **Effort** is wall-clock days of solo work at the owner's cadence (no agent
fan-out). **Spend** is API dollars at first-party list prices (Haiku 5.5 $0.10/$0.50, Sonnet 5.5
$2/$10, Opus 5.5 $4/$20 per MTok; cache reads ~0.1x input, Batches 50% off); every LLM run is
launched by the owner under a hard `max_llm_cost_usd` cap. **OD-n** marks an owner decision.
Every measured item is a registered trial in `evaluation.TRIALS`, chosen on the design period
only, with one pre-registered holdout look; the forward paper record stays the only unseen data.

## 0. Principles that do not change

1. The model may interpret; code decides what is allowed. Rules are always computed; the firm
   limits run after any model output. (Already true; every item below keeps it.)
2. Nothing the model does in a backtest may use information after the as-of date: no web
   search, no web fetch, no live news in historical runs; anonymised prompts on any period
   inside the model's training window.
3. Every AI feature is measured against the vol-target control and the rules desk, with
   intervals, p, BH flag, cost per decision and the deflated Sharpe over all trials.
4. No price-only deep learning on 15 names. Statistical learning is admitted only where the
   sample supports it (cross-section of hundreds of names, or text features over thousands of
   filings).

## 1. Model and API hygiene (foundation; do first)

| # | Item | What changes | Effort | Spend | Decision |
|---|---|---|---|---|---|
| 1.1 | **Model defaults** | `quick_think_llm: claude-haiku-5-5`, `deep_think_llm: claude-sonnet-5-5`, optional `pm/critic: claude-opus-5-5`; `deep_effort: medium` (Opus 5.5's default; `high` only after a sweep). Retire `claude-opus-5` / `claude-haiku-4-5` defaults; keep them in the tables. Update `PRICES_PER_MTOK`, `MODEL_CAPABILITIES` (Haiku 5.5: adaptive thinking, effort; Sonnet 5.5: forced `tool_choice` returns 400). | 0.5 d | 0 | none |
| 1.2 | **Structured outputs instead of `extract_json`** | Each `ask_json` contract becomes a JSON schema passed as `output_config.format` (or `strict: true` tool with `tool_choice: auto` where a tool is natural). Contract failures drop from "measured then fallback" to schema-guaranteed. Keep the numeric/finite checks as a second gate. | 1 d | ~$2 of smoke calls | none |
| 1.3 | **Prompt caching** | `FIRM_CONTEXT` + role + instructions as the first system block with `cache_control`; facts and fenced text after. Verify `cache_read_input_tokens > 0` in `UsageTracker`; add it to the cost report. Expected 40–60% input-cost cut on the deep tier. | 0.5 d | 0 | none |
| 1.4 | **Server-side refusal fallback** | Default `fallbacks: "default"` with beta `server-side-fallback-2026-07-01` on Opus 5.5 / Sonnet 5.5; log fallback blocks and `stop_details.category` into the evidence record. Replace the hard-coded `_FALLBACK_MODELS` set. | 0.5 d | 0 | none |
| 1.5 | **Message Batches for backtests** | `BatchLLM` implementing the `LLM` protocol: queues one request per (agent, instrument, date), submits in batches, resumes from `custom_id`. Halves the cost of every historical LLM study; latency is irrelevant offline. Requires the graph to be restructured so each stage's calls for all instruments/dates can be collected before the next stage (stage-wise batching across the walk-forward). | 2 d | 0 | none |
| 1.6 | **Model-table drift test** | CI test: configured default ids exist in both tables and `client.models.retrieve` succeeds (skipped without a key); nightly job with the key. | 0.25 d | ~0 | none |
| 1.7 | **Token counting before spend** | `count_tokens` on the deep prompts once per run to replace `ESTIMATED_INPUT_TOKENS = 8000` in the budget admission; tighter caps, fewer refused calls. | 0.25 d | 0 | none |

Section total: ~5 d, <$5. Unlocks everything below at roughly a third of today's cost.

## 2. The LLM study (the project's defining, never-run experiment)

| # | Item | Design | Effort | Spend | Decision |
|---|---|---|---|---|---|
| 2.1 | **Anonymisation recall audit** | 200 anonymised analyst prompts from the design period; ask Haiku 5.5 and Opus 5.5 "name the ticker and the month" with structured output; report hit rate vs chance; list the leaking fact keys. Gate: if recall > chance on the equities, tighten `SCALE_FREE_KEYS` before 2.2. | 1 d | ~$5 | none |
| 2.2 | **Tier × role grid on design** | Core 15, 2016–2021, every 5 bars (~300 decisions/name), 3 seeds (model variance). Cells: rules; Haiku analysts + Sonnet deep; Haiku + Opus deep; all Sonnet; all Opus (one seed). Metrics: portfolio Sharpe − control with block bootstrap, agent_sources, contract rejection rate, cost/decision, dispersion. Via Batches (1.5). | 3 d + run time | **OD-2a: ~$120–250** (≈4,500 decisions × 9 calls × ~5k tokens, batch prices) | OD-2a |
| 2.3 | **Ablations** | No debate (analysts → trader); one debate round; single neutral risk analyst; LLM only on text roles (news/fundamentals/macro) with rules elsewhere; LLM only at the PM. Each a registered trial. | 1 d + run | ~$60–100 | within OD-2a |
| 2.4 | **Calibration on the live model** | `calibration.py` dispersion (n=5), anchoring slope, drift between Sonnet 5 → 5.5 on 20 frozen states. Publish as the model-risk page. | 0.5 d | ~$10 | none |
| 2.5 | **One pre-registered holdout look** | Only the design-winning cell, written down before the run, with the MDE calculation (as v09 prereg). | 0.5 d + run | ~$40–80 | OD-2b: approve the look |
| 2.6 | **Eval set for the desk** | 150 frozen (state, expected-direction-of-reasoning) items with a rubric: did the analyst use the facts given, did it invent numbers, did it respect the fence. Graded by Sonnet 5.5 as judge against the rubric + deterministic checks. Reused by every later prompt change (hill-climb safely without the backtest). | 1.5 d | ~$15 per full eval run | none |

Section total: ~8 d, **~$250–450** across stages, each stage capped. Deliverable: the first
honest, multi-year answer to "does the model add anything", with cost per decision.

## 3. Give the model information the rules do not have (text analysts)

Today the analysts receive the same twenty indicator values the rules already use, so the
model can only re-weight the rules. The one place an LLM adds *information* is text.

| # | Item | Design | Effort | Spend | Decision |
|---|---|---|---|---|---|
| 3.1 | **EDGAR full-text, point-in-time** | Extend `data/edgar.py`: fetch 10-K/10-Q Item 1A, Item 7 (MD&A), 8-K Items 2.02/7.01/8.01, visible from acceptance time (plumbing exists). Cache to disk by accession; chunk by section. | 2 d | 0 | none |
| 3.2 | **Fundamentals-text analyst** | New `AnalystReport` source: Sonnet 5.5 over the latest filing sections as `document` blocks with `citations: enabled`, structured output {signal, confidence, guidance_direction, tone_change, cited_accessions}. Every claim carries a citation; the number audit checks cited text exists. Rules keep the ratio-based fundamentals view beside it. | 2 d | ~$0.02–0.05/decision (cached prefix) | none |
| 3.3 | **Filing-tone-change feature** | Diff of tone/risk-factor language vs the prior filing, extracted once per filing (not per decision) by Haiku 5.5 in a batch → a numeric feature stored point-in-time → enters the alpha library as `filing_tone_delta` and is measured with IC/decay like every alpha. ML that is defensible: thousands of filings, one number each. | 2 d | ~$20 for the 10 core names' history; ~$200 for 300 names | OD-3a if broad universe |
| 3.4 | **Macro-text analyst (FX)** | FOMC/ECB/BoE/BoJ statements and minutes (public, dated); point-in-time by release time; Sonnet 5.5 extracts hawkish/dovish shift and surprise vs prior; feeds the macro analyst beside the FRED rate differential. | 2 d | ~$0.02/decision | none |
| 3.5 | **Historical news** | Yahoo news only covers the last 30 days, so historical "news" is EDGAR titles. Either (a) accept and document (today), (b) GDELT (free, dated, noisy) for headlines back to 2015, or (c) nothing. Recommend (b) behind a provider flag, measured as a trial. | 2 d | 0 | OD-3b |
| 3.6 | **Measure** | 3.2–3.5 as cells of §2 (design only, one holdout look). The question is specific: does text-derived information beat the same desk without it. | 1 d + run | ~$80–150 | within OD-2a |

Section total: ~11 d, ~$150–400. This is where a positive result is actually possible.

## 4. RAG that retrieves market information, not just runbooks

| # | Item | Design | Effort | Spend | Decision |
|---|---|---|---|---|---|
| 4.1 | **Corpus** | The §3 EDGAR sections and central-bank texts become `KnowledgeBase` documents with metadata {symbol, accession, visible_date, section}. Point-in-time filter at query time: nothing visible after as-of is retrievable. | 1 d | 0 | none |
| 4.2 | **Hybrid retrieval** | Keep the hashed TF-IDF (dependency-free default); add an optional dense backend behind the same interface (a local small embedding model via `sentence-transformers`, or none), reciprocal-rank fusion, and a Sonnet 5.5 re-ranker for the top 20 → 5 when the LLM is on. | 2 d | re-rank ~$0.005/query | OD-4: allow a local embedding dependency (optional extra) |
| 4.3 | **Citations end to end** | Passages returned as `document` blocks with `citations: enabled`; the reporter's evidence-id audit extended to require that every quoted text span maps to a passage id. | 1 d | 0 | none |
| 4.4 | **Retrieval evaluation** | 100 labelled questions (symbol, date, "what did the company say about X") with gold accessions; recall@5 and MRR for TF-IDF vs hybrid; published table. | 1 d | ~$5 | none |
| 4.5 | **Policy RAG stays** | The runbook index remains for the trader/PM policy passages; measure (trial) whether removing it changes any decision. | 0.25 d | 0 | none |

Section total: ~5 d, <$20.

## 5. Agentic layer upgrades

| # | Item | Design | Effort | Spend | Decision |
|---|---|---|---|---|---|
| 5.1 | **Outcome-aware governance** | Join `DecisionMemory` realised P&L to each `TaskRun`; per-role hit rate, critic-flag → outcome correlation, false-positive rate of each critic check. Reported in the audited report and in a weekly roll-up. | 1.5 d | 0 | none |
| 5.2 | **Model-proposed plans, measured** | Run the planner with Sonnet 5.5 on 200 tasks; record survival rate of each step through the validator, what it adds (tools the canonical plan lacks), and the data-budget hits. Decide from data whether to keep the path. | 1 d | ~$5 | none |
| 5.3 | **Advisor pattern for the PM** | Sonnet 5.5 executor with Opus 5.5 advisor (the API's advisor tool) on the final decision only; compare against Sonnet-alone and Opus-alone cells in §2 on cost per decision and outcome. | 1 d | within §2 | none |
| 5.4 | **Memory tool for decision memory** | Expose `DecisionMemory` lessons through the Messages API memory tool (`memory_20250818`) so the model reads/writes lessons through a governed backend instead of a pasted block; keep the fence; keep append-only storage. Measure lesson usefulness via 5.1. | 1.5 d | 0 | none |
| 5.5 | **Injection red-team** | 150 adversarial headlines/filing snippets (instruction-bearing, role-play, encoded, multilingual) through the news and text analysts on Haiku/Sonnet 5.5; report compliance rate; CI job when a key is present; threat-model status updated with numbers. | 1 d | ~$10 | none |
| 5.6 | **Approval identity and two-person rule** | Approver id + signature on `QueuedApprovalGateway` records; configurable N-of-M for `execution.submit_order`; immutable external log option (append to a second store). | 1 d | 0 | none |
| 5.7 | **Tool search and deferred loading** | On the MCP/HTTP surface, mark rarely used tools `defer_loading` with the tool-search tool so the deep-tier prompt carries only the tools a plan needs (cheaper, cleaner cache prefix). | 0.5 d | 0 | none |
| 5.8 | **Cloud runner for the paper desk** | A Managed Agents scheduled deployment (or a GitHub Actions cron as the free alternative) runs `paper_trade_v09.py`, stores the price vintage hash, commits the record; the laptop becomes the fallback. Live web tools are permitted here and only here. | 1.5 d | Actions: 0; Managed Agents: session cost ~$0.50–2/day | OD-5: Actions (free) vs Managed Agents |

Section total: ~9 d, <$30 plus OD-5.

## 6. Machine learning that is defensible on this data

| # | Item | Design | Effort | Spend | Decision |
|---|---|---|---|---|---|
| 6.1 | **IC-weighted combination with shrinkage** | Replace hand weights (role weights, 25/50/25, 2× tilt, technical 0.30/0.20/0.15) with rolling IC-weighted combination, shrunk toward zero, with a turnover penalty; expected return = IC × vol × z; portfolio through the existing shrunk mean-variance. One free parameter (window) registered. | 2 d | 0 | none |
| 6.2 | **Regime labelling** | 2–3 state HMM or k-means on (vol, trend, rate-change) features, fitted on the design period only, used to condition signal weights and the vol target; the regime label is also given to the LLM as a fact. Measured as a trial. | 1.5 d | 0 | none |
| 6.3 | **Conformal intervals on forecasts** | Split-conformal prediction intervals around the combined alpha's return forecast; the PM sizes on interval width, not point estimate; VaR consistency checked against them. | 1 d | 0 | none |
| 6.4 | **LLM-extracted text features into the IC pipeline** | From 3.3/3.4: tone delta, guidance direction, hawkishness shift as numeric alphas measured exactly like the price alphas (IC, decay, turnover). The honest way to test "does the LLM see something". | 1 d | within §3 | none |
| 6.5 | **Risk model upgrade** | Filtered historical simulation / EWMA VaR (fix the Kupiec and independence failures), book VaR on by default in multi-sleeve runs, factor exposure (market, rates, USD, momentum), three stress rows (2008, 2020, 2022) in every table. | 2 d | 0 | none |
| 6.6 | **Broad cross-section (only if OD-1 = B)** | Point-in-time, survivorship-aware 300–500 name panel from EDGAR + Yahoo (document the residual bias); cross-sectional momentum, PEAD, accruals, asset growth, low-beta, tone delta; IC-weighted long/short book. Without this breadth no cross-sectional ML is honest. | 10–15 d | 0 (free data) | OD-1, OD-3a |

Section total: ~8 d (+10–15 d for 6.6).

## 7. Evaluation, documentation and release discipline

| # | Item | Effort | Spend |
|---|---|---|---|
| 7.1 | Every LLM cell registered as a trial; deflated Sharpe over all trials including LLM cells; per-cell cost per decision in the tables. | 0.5 d | 0 |
| 7.2 | New docs page "What the model adds" with the §2/§3 results, calibration, red-team and retrieval tables; `ai.md` updated; LEARN/COOKBOOK entries for structured outputs, batches, citations, memory tool. Full docs pass per the standing instruction after each phase. | 1 d/phase | 0 |
| 7.3 | One batch PR per phase; CI green; tag at phase ends (v0.13 foundation + study, v0.14 text + RAG, v0.15 agentic + ML). | 0.5 d/phase | 0 |

## 8. Order, totals and gates

| Phase | Items | Effort | Spend | Gate to next |
|---|---|---|---|---|
| **P1 Foundation** | §1 all; 7.1 | ~5 d | <$5 | caching verified, structured outputs green, Batches smoke-tested |
| **P2 LLM study** | 2.1 → 2.2 → 2.3 → 2.4 → 2.6; then 2.5 | ~8 d | ~$250–450 (OD-2a/2b) | results published whatever they say |
| **P3 Text + RAG** | §3, §4 | ~16 d | ~$150–400 | retrieval recall@5 ≥ 0.8 on the labelled set before analysts use it |
| **P4 Agentic** | §5 | ~9 d | <$30 (+OD-5) | red-team compliance rate published; outcome join live |
| **P5 ML + risk** | 6.1–6.5 | ~8 d | 0 | risk model passes Kupiec/independence on the design period |
| **P6 Breadth (optional)** | 6.6 | 10–15 d | 0 | only if OD-1 = B |
| **Docs/release** | §7 | ~1.5 d/phase | 0 | per standing instruction |

Totals without P6: **~46 solo days, ~$450–900 API spend** (each run owner-launched and capped).
With P6: ~60 days. At the owner's cadence of 2–3 sessions per wall-clock day this is 2–4 months.

## 9. What would make this a positive contribution

If P2 shows the model adds nothing to a rules desk that itself adds nothing, that is a clean,
citable negative result about LLM trading agents, measured properly — more valuable than
another Sharpe claim. If P3 shows text-derived information moves the design-period Sharpe
against the control with an interval excluding zero, the project has a real finding and a
real forward test. Either way the architecture (governed agents, evidence, citations, batch
evaluation, pre-registration) is the asset, and §1–§5 make it current with the API.

## 10. Owner decisions — DECIDED 2026-11-07

Owner instruction: "all the decisions = you decide for me (no money to be spent, no card
details to be given)". **Zero spend is the binding constraint**: no API dollars, no paid data,
no cloud spend, no card details anywhere. Every item that needs model calls is re-planned
below to be built and tested offline (recorded fixtures, mocked client) and left *ready to
run*; it is executed only if the owner later chooses to fund it.

| Decision | Choice | Reason |
|---|---|---|
| **OD-1** Positioning | **A**: governed-agents reference implementation, with the LLM study *prepared and documented as unexecuted*. P6 (breadth) not scheduled. | The method is the contribution; B needs breadth free data cannot supply. |
| **OD-2a** LLM study budget | **$0. Stages 2.1–2.6 are built (drivers, batch client, eval set, prereg text) and smoke-tested against recorded fixtures only; nothing is sent to the API.** The docs state plainly that the study is ready and unrun. | Owner: no money. |
| **OD-2b** Holdout look | Deferred with 2.2; the pre-registration is written now so a future funded run cannot peek. | Protocol. |
| **OD-3a** Broad-universe text extraction | Not scheduled. | A, and $0. |
| **OD-3b** Historical headlines | **GDELT behind a provider flag**, measured with the rules lexicon (no model). | Free. |
| **OD-4** Embedding dependency | **Allowed as optional extra `[rag]`** (local model, no service, no key); default stays hashed TF-IDF. No re-ranker (needs API). | Free, local. |
| **OD-5** Paper-desk runner | **GitHub Actions scheduled workflow** (free tier), laptop fallback, vintage hashes. No Managed Agents. | $0. |

Standing constraints: free data only, solo work, one batch PR per round, full docs pass after
every phase, never paid extra usage on the Claude plan, **no API spend and no card details**.

### 10.1 Re-planned phases under zero spend

| Phase | What runs now ($0) | What is built but not executed |
|---|---|---|
| P1 Foundation (~5 d) | 1.1 model defaults and tables; 1.2 structured outputs with recorded-response fixtures; 1.3 caching code + a unit test on the request shape; 1.4 fallback parameter wired, tested on fixtures; 1.5 `BatchLLM` with a fake batch backend; 1.6 drift test (API part skipped without key); 1.7 token counting via a local estimate when no key. | Live smoke calls. |
| P2 LLM study (~5 d) | Drivers, cells, prereg text, calibration script, eval set and rubric, judge harness on fixtures; a `--dry-run` that prints call counts and the dollar estimate per cell. | 2.1–2.6 live runs (~$250–450 if ever funded). |
| P3 Text + RAG (~12 d) | 3.1 EDGAR full-text point-in-time fetch and cache; 3.5 GDELT provider; 4.1 corpus; 4.2 hybrid retrieval with local embeddings; 4.3 citation plumbing (passage ids in the audit); 4.4 retrieval eval (TF-IDF vs hybrid) on 100 labelled questions written by hand; a **rules-based tone-change feature** (lexicon diff between consecutive filings) into the alpha library, measured by IC/decay. | 3.2 LLM fundamentals-text analyst, 3.3 LLM tone extraction, 3.4 LLM macro-text analyst, re-ranker: built against fixtures, unrun. |
| P4 Agentic (~8 d) | 5.1 outcome-aware governance; 5.2 planner survival measured with the canonical/rule planner and recorded model plans; 5.4 memory-tool backend (offline tests); 5.5 red-team corpus built and run through the **rules** analysts (fence structure tests) — live model compliance rate unrun; 5.6 approver identity / N-of-M; 5.7 deferred tool loading; 5.8 Actions runner. | 5.3 advisor pattern; live red-team. |
| P5 ML + risk (~8 d) | All of 6.1–6.5 (no API needed). | — |
| Docs/release | Per phase; a "ready but unrun" box on every LLM table. | — |

Totals: **~38 solo days, $0.** Everything that needs model calls is one `--live` flag and an
owner-launched, capped run away.

## 12. Second review: the plan itself, against the same bar (2026-11-07, later)

The owner asked for the plan to be reviewed as critically as the project was. The findings
below are about §1–§11; each ends with the change made to the plan. Items marked **NEW** are
added to the phases in §12.9.

### 12.1 The plan still treats the single-name daily desk as the vehicle

§6.1 spends two days fitting IC weights to nine technical alphas whose measured IC is ≈ 0.
Weights fitted to noise will overfit the design period and look good there; with honest
shrinkage toward zero the tilt will shrink to nothing and the desk will converge to the
vol-target control. That is the *expected* outcome and the plan did not say so.
**Change:** 6.1 is re-stated as a pipeline demonstration whose pre-registered expectation is
"tilt → 0, desk ≈ control"; success is that the pipeline *refuses* to adopt noise, not a Sharpe.

### 12.2 Zero spend removed the defining experiment and the plan did not replace it

With OD-2a = $0, P2 builds a study nobody runs. A desk would not accept "ready but unrun" as
a result. There is a $0 route the plan missed: **a local open-weight model** behind the same
`LLM` protocol (`LocalLLM`: llama.cpp / Ollama HTTP, a 7–8B instruct model quantised to run
on the owner's machine). It is a weaker model and slow (tens of seconds per call on CPU), so
the study shrinks to a sampled design: 15 names × 40 dates × 9 calls ≈ 5,400 calls ≈ 2–4
machine-days in the background, repeated for 2 seeds. It answers the question that matters
under A — *does an LLM desk differ from, and improve on, the rules it is given* — at $0, and
it runs the anonymisation audit, the calibration harness and the injection red-team for free.
Caveats to state in the docs: result is for that model class, not for Claude; prompts tuned
for Claude may need a local variant; the structured-output guarantee becomes grammar-constrained
decoding (llama.cpp supports JSON schema grammars) or the existing contract check.
**NEW 2.7 `LocalLLM` + sampled study (3 d, $0; OD-6: owner confirms the machine may run a
background job for days and has ≥16 GB RAM; if not, 2.7 is dropped and P2 stays unrun).**

### 12.3 Edge cases the plan never named

A bank's model-validation team would list these before approving a backtest. None are in
§1–§11; several are only partly covered by the code today.

| Area | Edge case | Status in code (this read) | Change |
|---|---|---|---|
| Prices | split/dividend rebase between sessions; as-traded vs adjusted mixing | memory resolves on one series; impact uses as-traded (v0.11) | **NEW 6.7** property test: every metric invariant under a synthetic split |
| Prices | zero / negative / NaN / duplicate-date bars; gaps > N days | `max_data_staleness_days`; validation on config, not on bars | **NEW 6.7** bar validator with explicit refusal reasons |
| Calendar | FX 17:00 NY close vs equity 16:00; holidays differing by sleeve; DST; a rebalance date that is a holiday for one sleeve | portfolio joins on dates; not audited | **NEW 6.7** calendar alignment test + documented convention |
| Shorts | borrow availability / recall, hard-to-borrow cost spikes, locate | flat 1%/yr | state as a limitation; cap short notional in `risk` |
| Stops | gap through the stop (fill at open, not at the stop); stop and target hit in the same bar | C++ engine convention in `backtest.hpp` (not re-read) | **NEW 6.7** unit test pinning the convention; document it |
| Universe | ETF/stock delisting inside the period; a name that did not exist at design start (META 2012) | handled ad hoc (design_long excludes core 15) | survivorship statement per table row |
| Data vintage | Yahoo revisions (1,232 logged in six weeks); back-filled sessions after an outage | logged in `revisions.csv` | **R7** vintage hashes becomes a hard requirement in P4 |
| LLM | **refusal/fallback as missing data**: a refused call falls back to rules, so an "LLM desk" is a mixture of two decision processes; if refusals correlate with regime (bad news → refusal) the measurement is biased | `agent_sources` counts exist; no correlation test | **NEW 2.8** report refusal rate by regime/date and test independence; cap the admissible fallback share per cell |
| LLM | model version change mid-study (deprecation, silent server update) | `response.model` priced; not asserted | pin ids; assert `response.model` equals the configured id; store it per decision |
| LLM | injection *inside EDGAR text* (filings are third-party text too) | fence applies to news/social only | extend `untrusted_keys` to every filing section (P3) |
| LLM | non-determinism across seeds; tokenizer change across families | seeds in 2.2 | report dispersion per cell (2.4) |
| Batches | partial batch failure, expired items, result order | 1.5 spec | resume by `custom_id`; idempotent writes |
| Budget | parallel workers overshooting a cap during a retry storm | hard mode (v0.11) | keep; add a test for N workers at the cap |
| Ledger | 16-significant-digit rewrite trims appended floats (noted in memory) | pre-existing | fix: write with `repr`, compare with tolerance |
| Approvals | approver absent for days; stale approval executed after prices moved | queue has no TTL | **5.6** add approval TTL and re-pricing check |

### 12.4 Tradability and "real life" were not addressed

The plan improves research and governance but says nothing about what stands between this
code and a live book. Under positioning A the right deliverable is not a broker — it is an
honest *live-readiness statement* plus a **paper OMS** that the agentic layer governs, so the
reference implementation covers the whole order lifecycle, not just the decision.
**NEW 5.9 Paper OMS (3 d, $0):** order states (new → acknowledged → partially filled → filled /
cancelled / rejected), pre-trade checks (fat-finger notional and quantity limits, price collar
against last close, duplicate-order guard, market-hours and holiday check per sleeve, borrow
check for shorts), a kill switch (global and per sleeve, state in the store, honoured by every
tool), end-of-day reconciliation of positions against the ledger with a break report, T+1 /
FX T+2 settlement and cash projection, FX roll at 17:00 NY. All simulated, all policy-gated,
all evidenced — this is where `execution.submit_order` becomes meaningful.
**NEW 7.4 Live-readiness statement:** a page that lists, per component, what exists, what is
simulated and what is absent (broker, market data entitlement, reconciliation to a custodian,
tax lots, margin, compliance surveillance), with no claim that any of it is production.
**Capacity:** every published table gains a capacity row (AUM at which impact costs 0.1
Sharpe, from the existing sweep) so "profitability" is never quoted without the size it holds at.

### 12.5 Profitability KPIs are wrong for positioning A

The project quotes Sharpe as the headline. For an AI-desk reference the right KPIs are
*information added*: decision-level hit rate vs the control's implied decision, Brier score and
calibration curve of stated confidence against realised direction, information coefficient of
the LLM signal vs the rule signal on the same facts, cost per decision, fraction of decisions
the model changed and the P&L of exactly those changes (the "model delta book").
**NEW 7.5 KPI table** rendered from `agent_sources`, `rule_signal` and the memory join (5.1);
Sharpe stays as one row, not the title.

### 12.6 ML rigour gaps

No purged/embargoed walk-forward cross-validation anywhere (consecutive overlapping forward
returns leak across folds); no automated look-ahead test beyond fuzzing the signals' point-in-
time property; no feature store with per-feature availability timestamps.
**NEW 6.8 (2 d, $0):** purged k-fold with embargo for every IC estimate used in 6.1; a
**future-leak canary** — inject a synthetic shock at date T into a copy of the data and assert
no feature, signal, weight or LLM fact changes before T across the whole pipeline (data →
analysts → debate → PM); a point-in-time feature table (feature, as-of, visible-from, source
accession) that 3.x and 6.4 write into and the canary reads.

### 12.7 Agent reliability and auditability are asserted, not engineered

A bank asks for: deterministic replay of any past decision from recorded inputs; SLOs
(latency and success rate per stage); tracing a regulator can read; golden transcripts in CI.
**NEW 5.10 Replay mode (1.5 d):** re-run a `TaskRun` from its evidence store with every tool
call served from the recorded payloads and the LLM served from recorded replies; assert the
same decision; this is also the fixture mechanism 1.2/1.5 need. **NEW 5.11 (0.5 d):** per-stage
latency and failure SLOs in `Metrics`, exported through optional OpenTelemetry (local collector,
free); golden-transcript tests for the canonical plan on three frozen states.

### 12.8 Which AI features to use — and which not to

A top-firm review values a reasoned *no* as much as a yes. Verdict per feature:

| Feature | Use? | Why |
|---|---|---|
| Structured outputs / strict tools | Yes (1.2) | removes the parse failure mode |
| Prompt caching, token counting, Batches | Yes (1.3, 1.5, 1.7) | cost and reproducibility |
| Citations on documents | Yes (3.2, 4.3) | every text claim traces to an accession |
| Memory tool | Yes, governed (5.4) | lessons through a backend, still fenced and append-only |
| Server-side refusal fallback | Yes (1.4), *reported* | but see 12.3: a fallback is a mixture, so count it |
| Local open-weight model | Yes (2.7) | the only $0 way to run the study |
| Vision (chart images) | **No** | the model already has the numbers; images add cost and lose precision |
| Web search / fetch | **Live paper desk only** | look-ahead poison in any backtest |
| Code execution by the model | **No in the desk**; research-assistant only, sandboxed, never in a decision path | unmeasurable, unauditable code in a governed loop |
| Advisor tool, Managed Agents, message threads, compaction | **No** | spend, or irrelevant to short single-turn prompts |
| Fine-tuning on price history | **No** | 15 names; it would be fitting noise with extra steps |
| LLM as judge (eval set 2.6) | Yes, with human-labelled calibration set | standard practice; report judge agreement |

### 12.9 Plan changes (totals re-stated)

| Phase | Added | New effort | Spend |
|---|---|---|---|
| P1 | — (unchanged) | ~5 d | $0 |
| P2 | 2.7 LocalLLM + sampled study; 2.8 refusal-bias report | ~8 d (+3) | $0 (OD-6) |
| P3 | filings as untrusted text; feature table (6.8) consumers | ~12 d | $0 |
| P4 | 5.9 paper OMS; 5.10 replay mode; 5.11 SLOs/OTel/golden transcripts; approval TTL | ~13 d (+5) | $0 |
| P5 | 6.7 edge-case validators and tests; 6.8 purged CV + leak canary + feature table; 6.1 re-stated | ~11 d (+3) | $0 |
| Docs | 7.4 live-readiness statement; 7.5 KPI table; capacity row | +1 d | $0 |

**Total ~50 solo days, $0.** Order: P1 → P5 (6.7, 6.8 first: validators and the leak canary
protect everything after) → P2 (2.7 runs in the background for days while P3 proceeds) → P3 →
P4 → docs. OD-6 (local model on the owner's machine) is the one new decision; default = yes if
the machine has ≥16 GB RAM, else P2 stays unrun.

### 12.10 What this plan still cannot fix

Honesty requires saying it: no plan under free daily data on 15 names produces a tradable
edge; a local 8B model is not evidence about frontier models; a paper OMS is not a broker;
the forward record decides nothing for years. What the plan can produce is a reference
implementation whose every claim is measured, whose failure modes are enumerated and tested,
and whose AI components are shown — with numbers — to add or not add information. That is the
standard the best desks hold internal tools to, and it is reachable at $0.

## 11. Start of execution

First session: commit the two review documents on `feat/v0.13-foundation`, then P1 items
1.1–1.7 in that order with fixtures (no key present), tests green on both backends, docs pass,
one PR. Then P5 (pure quant, highest certainty of a measurable change) before P3/P4, unless the
owner prefers the text plumbing first.
