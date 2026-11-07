# AgenticTrader — consolidated improvement plan (living document)

**Status:** approved by the owner 2026-11-07, not started. This is the single plan to update.
It supersedes `2026-11-07_in_depth_review.md` (the diagnosis) and
`2026-11-07_ai_improvement_plan.md` (the first two drafts), which are kept as the record of how
the plan was reached. Update the **Progress log** (§9) as work lands; change the phases in place.

## 1. Constraints and decisions (binding)

| Rule | Value |
|---|---|
| Spend | **$0.** No API dollars, no paid data, no cloud spend, no card details anywhere. Every LLM run uses recorded fixtures or a local open-weight model. A live Claude run happens only if the owner later funds it and launches it under a hard cap. |
| Positioning (OD-1) | **A** — a reference implementation of governed LLM agents in trading, with every AI component measured. Not a systematic book; no broad-universe phase. |
| Data | Free only (Yahoo, FRED, EDGAR, GDELT). No Nasdaq Data Link / LOBSTER / vendor feeds. |
| Process | Solo work, no agent fan-out. One batch PR per phase, CI green on both backends before merge. Full docs pass (README, LEARN, COOKBOOK, ARCHITECTURE, diagrams, CHANGELOG, site) after every phase. Never the word "interview" in public files. Finish local tests before pushing. |
| Protocol | Every variant is a registered trial in `evaluation.TRIALS`, chosen on the design period only, one pre-registered holdout look, intervals + p + BH flag, deflated Sharpe over all trials. The forward paper record is the only unseen data; no decision before the pre-registered look. |
| Other decisions | OD-2 LLM study: built, dry-run, and executed only on a local model (§4 P2). OD-3 headlines: GDELT behind a flag, scored by the rules lexicon. OD-4 retrieval: optional local embedding extra `[rag]`, default stays hashed TF-IDF, no API re-ranker. OD-5 paper runner: GitHub Actions free tier, laptop fallback. **OD-6** local model on the owner's machine: yes if ≥16 GB RAM, else P2 stays unrun. |

## 2. Diagnosis in six lines (from the review)

1. Science and engineering are honest and strong: pre-registration, 62 trials, deflated Sharpe, BH, cluster bootstraps, append-only ledger, provenance, 879 tests on two backends, threat model.
2. There is no edge and the project proves it: the desk is beta 0.9 / R² 0.89 to a one-line control (buy-and-hold at 15% vol); four research rounds adopted nothing; the forward record cannot decide for ~14 years.
3. The AI/agentic layer has never been evaluated: one $4 run on a superseded engine. Analysts hand the model the same twenty indicators the rules use, so it can only re-weight the rules.
4. The alpha set is retail technicals on 15 names; more rule variants are pointless. The only lever that ever moved Sharpe was vol scaling and diversification.
5. Governance is correct but governs decisions with no information; RAG is TF-IDF over runbooks; no injection red-team or anonymisation audit on a live model; VaR fails Kupiec 2/15 and independence 6/15.
6. Operations: the paper record depends on one laptop, broke for a week, back-filled, and now auto-commits to main.

## 3. Principles

1. The model may interpret; code decides what is allowed; firm limits run after any model output.
2. Nothing in a backtest may see past the as-of date: no web tools, no live news, anonymised prompts inside the model's training window.
3. Every AI feature is measured against the vol-target control and the rules desk, with cost per decision.
4. No price-only deep learning on 15 names. Statistical learning only where the sample supports it (text over thousands of filings).
5. The right KPIs for an AI desk are *information added* (hit rate vs control, Brier/calibration of confidence, the P&L of exactly the decisions the model changed, cost per decision). Sharpe is one row, not the title.
6. A reasoned *no* to an AI feature is a result.

## 4. Phases and items

Effort = wall-clock solo days. Spend = $0 throughout. Order: **P1 → P5 → P2 → P3 → P4 → P6**.

### P1 Foundation (~5 d) — branch `feat/v0.13-foundation`

| # | Item | Done when |
|---|---|---|
| 1.1 | Model defaults `quick: claude-haiku-5-5`, `deep: claude-sonnet-5-5`, optional `claude-opus-5-5` for PM/critic; `deep_effort: medium`; `PRICES_PER_MTOK` and `MODEL_CAPABILITIES` updated (Haiku 5.5 adaptive thinking; forced `tool_choice` returns 400 on 5.5 models). | tests pin the tables; configured ids resolve in both |
| 1.2 | Structured outputs: every `ask_json` contract as a JSON schema via `output_config.format` (or `strict: true` tool with `tool_choice: auto`); contract checks kept as a second gate. Tested on recorded-response fixtures. | zero parse-failure path on fixtures |
| 1.3 | Prompt caching: `FIRM_CONTEXT` + role + instructions as the first system block with `cache_control`; `UsageTracker` records `cache_read_input_tokens`; request-shape unit test. | cost report shows cache fields |
| 1.4 | Server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`); fallback blocks and `stop_details.category` into the evidence record; `_FALLBACK_MODELS` removed. | fixture test |
| 1.5 | `BatchLLM` implementing `LLM` (Message Batches, resume by `custom_id`, idempotent writes, partial-failure handling) with a fake batch backend; graph restructured for stage-wise batching across the walk-forward. | fake-backend test runs a 3-name, 5-date walk-forward |
| 1.5b | Batch-friendly loop: one name's dates in sequence, names and offsets in parallel per pass, so a batched backtest needs about (pipeline stages) passes per date step rather than stages x dates per run. | 15-name test needs no more than stages x dates / names passes |
| 1.6 | Drift test: default ids in both tables; `models.retrieve` check skipped without a key. | CI green |
| 1.7 | Token counting via local estimate when no key, `count_tokens` when a key exists, replacing `ESTIMATED_INPUT_TOKENS = 8000` in budget admission. Test N workers at the cap during a retry storm. | test |
| 1.8 | Assert `response.model` equals the configured id and store it per decision (model-version drift). | test |

### P5 ML, risk and edge cases (~11 d) — run before P2/P3 because 5.7/5.8 protect everything after

| # | Item | Done when |
|---|---|---|
| 5.7 | **Edge-case validators and tests**: bar validator (zero/negative/NaN/duplicate dates, gaps) with explicit refusal reasons; synthetic-split invariance property test for every metric; FX 17:00 NY vs equity close and per-sleeve holiday/DST calendar alignment test with the convention documented; stop convention pinned by test (gap through stop fills at open; stop and target in one bar); survivorship statement per table row; short notional cap; ledger floats written with `repr`, compared with tolerance. | all tests green on both backends |
| 5.8 | **Leakage rigour**: purged/embargoed walk-forward CV for every IC estimate; a **future-leak canary** (inject a shock at T into a data copy; assert nothing from data → analysts → debate → PM changes before T); a point-in-time feature table (feature, as-of, visible-from, source accession) that P3 writes into. | canary in CI |
| 5.1 | IC-weighted combination with shrinkage toward zero and a turnover penalty replacing every hand weight (role weights, 25/50/25, 2× tilt, technical 0.30/0.20/0.15); expected return = IC × vol × z; portfolio via shrunk mean-variance; one registered window parameter. **Pre-registered expectation: tilt → 0, desk ≈ control; success is that the pipeline refuses noise.** | trial registered, tables rendered |
| 5.2 | Regime labelling (2–3 state HMM or k-means on vol/trend/rate-change, fitted on design only) conditioning weights and vol target; label also a fact for the LLM. | trial |
| 5.3 | Split-conformal intervals on the combined forecast; PM sizes on interval width. | trial |
| 5.4 | Risk model: filtered historical simulation / EWMA VaR (fix Kupiec and independence), book VaR default-on in multi-sleeve runs, factor exposures (market, rates, USD, momentum), stress rows (2008, 2020, 2022) in every table, capacity row (AUM at which impact costs 0.1 Sharpe). | Kupiec/independence pass on design |

### P2 The LLM study at $0 (~8 d)

| # | Item | Done when |
|---|---|---|
| 2.1 | `LocalLLM` behind the `LLM` protocol (llama.cpp / Ollama HTTP, 7–8B instruct, JSON-schema grammar decoding); same anonymisation, fence, budget (call cap), evidence. **OD-6.** | smoke test on one decision |
| 2.2 | Study drivers for every cell with `--dry-run` (prints call counts and the dollar estimate at Claude list prices) and `--live` (local model only unless funded). Cells: rules; local analysts + local deep; local on text roles only; local at PM only; no debate; one debate round; single neutral risk analyst. | dry-run table in docs |
| 2.3 | Sampled design: 15 names × 40 design dates × 2 seeds, background job for days; metrics: portfolio Sharpe − control (block bootstrap), agent_sources, contract rejection rate, dispersion, cost-equivalent per decision. | results rendered, every cell a trial |
| 2.4 | Anonymisation recall audit (200 prompts: "name the ticker and month"; hit rate vs chance; leaking keys listed; tighten `SCALE_FREE_KEYS` if needed). | table |
| 2.5 | **Refusal/fallback bias**: refusal rate by regime and date, independence test; admissible fallback share per cell capped; stated on every LLM table. | table |
| 2.6 | Calibration on the local model: dispersion (n=5), anchoring slope, drift between two model builds on 20 frozen states. | model-risk page |
| 2.7 | Eval set: 150 frozen (state, rubric) items — used the facts given, invented no numbers, respected the fence; deterministic checks + local-model judge with a human-labelled calibration subset and judge agreement reported. | eval runs in CI on fixtures |
| 2.8 | Pre-registration of the one holdout look for the design-winning cell (MDE stated); executed only when a cell clears the design bar. | prereg committed before any holdout run |
| — | Docs say plainly: results are for a local 8B model class, not for Claude; the Claude cells exist as dry-runs with a cost estimate. | |

### P3 Text and retrieval (~12 d)

| # | Item | Done when |
|---|---|---|
| 3.1 | EDGAR full text, point-in-time by acceptance time: 10-K/10-Q Items 1A and 7, 8-K Items 2.02/7.01/8.01; cached by accession; chunked by section; **every filing section is untrusted text** (fence). | provider tests |
| 3.2 | Rules-based filing-tone-change feature (lexicon diff between consecutive filings) into the alpha library and the feature table; measured by IC/decay like every alpha. | trial |
| 3.3 | GDELT headline provider behind a flag (dedupe, language filter), scored by the rules lexicon; measured as a trial. | trial |
| 3.4 | RAG corpus: EDGAR sections + central-bank statements (FOMC/ECB/BoE/BoJ, dated by release time) with metadata {symbol, accession, visible_date, section}; point-in-time filter at query time. | tests |
| 3.5 | Hybrid retrieval: hashed TF-IDF default; optional local embeddings `[rag]`; reciprocal-rank fusion. | tests |
| 3.6 | Citations end to end: passages as `document` blocks with `citations: enabled`; evidence-id audit requires every quoted span to map to a passage id. | audit test |
| 3.7 | Retrieval evaluation: 100 hand-labelled questions with gold accessions; recall@5 and MRR, TF-IDF vs hybrid; **gate: recall@5 ≥ 0.8 before analysts use it**. | table |
| 3.8 | LLM text analysts (fundamentals-text with cited claims, macro-text hawkish/dovish shift) and LLM tone extraction: built against fixtures and runnable on the local model as P2 cells; Claude variants dry-run only. | fixtures + local run |
| 3.9 | Policy-runbook RAG kept; trial measuring whether removing it changes any decision. | trial |

### P4 Agentic layer and operations (~13 d)

| # | Item | Done when |
|---|---|---|
| 4.1 | Outcome-aware governance: `DecisionMemory` realised P&L joined to each `TaskRun`; per-role hit rate; critic-flag → outcome correlation; false-positive rate per critic check; weekly roll-up. | report |
| 4.2 | Planner survival measured on 200 tasks (canonical, rule planner, recorded model plans): step survival through the validator, additions, data-budget hits. | table |
| 4.3 | Memory tool backend for decision memory (governed, fenced, append-only), offline tests. | tests |
| 4.4 | Injection red-team corpus (150 adversarial headlines/filing snippets: instruction-bearing, role-play, encoded, multilingual); fence structure tests through the rules analysts; compliance rate on the local model; threat model updated with numbers. | table |
| 4.5 | Approvals: approver identity + signature, N-of-M for `execution.submit_order`, approval TTL and re-pricing check, optional second immutable store. | tests |
| 4.6 | Deferred tool loading with the tool-search tool on the MCP/HTTP surface. | tests |
| 4.7 | **Paper OMS**: order states (new → acked → partial → filled / cancelled / rejected), pre-trade checks (fat-finger notional/quantity, price collar vs last close, duplicate guard, market hours and holidays per sleeve, borrow check), global and per-sleeve kill switch honoured by every tool, end-of-day reconciliation vs ledger with break report, T+1 / FX T+2 settlement and cash projection, FX roll at 17:00 NY. All simulated, policy-gated, evidenced. | tests + cookbook recipe |
| 4.8 | **Replay mode**: re-run any `TaskRun` from its evidence store with tools and LLM served from recorded payloads; same decision asserted; doubles as the fixture mechanism for 1.2/1.5. | tests |
| 4.9 | SLOs (latency, failure rate per stage) in `Metrics`; optional OpenTelemetry export to a local collector; golden-transcript tests for the canonical plan on three frozen states. | tests |
| 4.10 | Paper-desk runner on GitHub Actions (free tier, scheduled), laptop fallback, price-vintage hash per session in `runs.jsonl`, CI freshness check (fail if last session > 2 business days old), auto-opened issue on failure. Live web tools permitted here only. | first automated commit |
| 4.11 | Flaky `test_interrupted_sweep_spares_a_live_siblings_runs` fixed or quarantined; suite split (PR gate < 10 min, full nightly); `ruff` + `mypy` on `agentic_trader/`; actions pinned by SHA. | CI |

### P6 Documentation and release (per phase, ~1.5 d each)

| # | Item |
|---|---|
| 6.1 | Every cell a trial; deflated Sharpe over all trials incl. LLM cells; cost-equivalent per decision in tables. |
| 6.2 | New page "What the model adds" (P2/P3 results, calibration, red-team, retrieval tables, refusal-bias); `ai.md`, LEARN, COOKBOOK, DIAGRAMS updated; a "ready but unrun" box on every Claude cell. |
| 6.3 | **Live-readiness statement**: per component what exists / is simulated / is absent (broker, entitlements, custodian reconciliation, tax lots, margin, surveillance); no production claim. |
| 6.4 | **KPI table** from `agent_sources`, `rule_signal`, memory join: hit rate vs control, Brier and calibration curve, model-delta book, cost per decision; Sharpe as one row. |
| 6.5 | README first paragraph restated for positioning A; single-name desk named as the incumbent control; forward record linked with its decision date. |
| 6.6 | Tags: v0.13 (P1), v0.14 (P5), v0.15 (P2+P3), v0.16 (P4). One batch PR per phase. |

## 5. AI features: use / do not use

| Feature | Decision | Reason |
|---|---|---|
| Structured outputs, strict tools | Use | removes the parse failure mode |
| Prompt caching, token counting, Message Batches | Use | cost and reproducibility |
| Citations on `document` blocks | Use | every text claim traces to an accession |
| Memory tool (governed backend) | Use | lessons through a backend, fenced, append-only |
| Server-side refusal fallback | Use, and report it | a fallback is a mixture of decision processes; count it |
| Local open-weight model | Use | the only $0 way to run the study |
| LLM as judge | Use with human-labelled calibration subset | report judge agreement |
| Vision on chart images | No | the model has the numbers; images cost more and lose precision |
| Web search / web fetch | Live paper desk only | look-ahead poison in any backtest |
| Model-run code execution | No in the desk | unauditable code in a governed loop |
| Advisor tool, Managed Agents, message threads, compaction | No | spend, or irrelevant to short single-turn prompts |
| Fine-tuning on price history | No | 15 names; fitting noise with extra steps |

## 6. Edge-case register (tested in 5.7 / 5.8 / 2.5 / 4.5 unless noted)

Splits and dividend rebases between sessions; zero/negative/NaN/duplicate bars and gaps; FX vs equity close times, per-sleeve holidays, DST, rebalance on a one-sleeve holiday; borrow availability and recall (documented limitation + cap); gap-through-stop fills and stop+target in one bar; delistings and names absent at design start (survivorship statement); Yahoo revisions and back-filled sessions (vintage hashes, 4.10); refusal-as-missing-data bias (2.5); model version drift (1.8); injection inside EDGAR text (3.1); seed and tokenizer non-determinism (2.6); partial batches and result order (1.5); parallel workers at the budget cap (1.7); ledger float precision (5.7); stale approvals after prices move (4.5).

## 7. Totals

~50 solo wall-clock days, **$0**. At the owner's cadence of 2–3 sessions per day this is roughly 3–4 months with the local-model runs overlapping P3.

## 8. What this plan cannot fix

Free daily data on 15 names will not produce a tradable edge; a local 8B model is not evidence about frontier models; a paper OMS is not a broker; the forward record decides nothing for years. What it produces is a reference implementation whose every claim is measured, whose failure modes are enumerated and tested, and whose AI components are shown with numbers to add or not add information.

## 9. Progress log

- 2026-11-07 — review, two plan drafts, second critical review, consolidation into this file. Nothing executed. Files uncommitted.
- 2026-11-07 — P1 items 1.1 (5.5 model defaults and price table), 1.2 (structured outputs, `contracts.py`), 1.3 (prompt caching), 1.4 (refusal-fallback evidence per call), 1.6 (model-table drift test), 1.7 (token counting in budget admission) and 1.8 (served-model drift) implemented and tested offline in `tests/test_v13_foundation.py`; no live call, $0. 1.5 (BatchLLM) partly done: mechanism, store, resubmission and a fake-backend 3x5 walk-forward test pass, but passes grow as stages x dates because each prompt carries the previous held weight; full-length batching needs a loop change (open, see 1.5b). Docs pass done (README, LEARN 51, COOKBOOK 101, CHANGELOG v0.13.0 unreleased, AI, API, architecture pages).

## 10. How to resume

Say to a new session: *"Resume AgenticTrader per docs/review/PLAN.md (memory: agentic-trader-review-2026-11-07). Zero spend, no card details, solo, free data. Commit docs/review on `feat/v0.13-foundation`, then P1 items 1.1–1.8, one batch PR, docs pass."* The session reads §1, §4 and §9, appends to §9 as it goes, and changes phases in place.
