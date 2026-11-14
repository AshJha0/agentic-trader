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
| Process | Solo work, no agent fan-out. One batch PR per phase, CI green on both backends before merge. Full docs pass (README, LEARN, COOKBOOK, ARCHITECTURE, diagrams, CHANGELOG, site) after every phase. Never the word banned by the owner rule of 2026-10-27 in public files. Finish local tests before pushing. |
| Protocol | Every variant is a registered trial in `evaluation.TRIALS`, chosen on the design period only, one pre-registered holdout look, intervals + p + BH flag, deflated Sharpe over all trials. The forward paper record is the only unseen data; no decision before the pre-registered look. |
| Other decisions | OD-2 LLM study: built, dry-run, and executed only on a local model (§4 P2). OD-3 headlines: GDELT behind a flag, scored by the rules lexicon. OD-4 retrieval: optional local embedding extra `[rag]`, default stays hashed TF-IDF, no API re-ranker. OD-5 paper runner: GitHub Actions free tier, laptop fallback. **OD-6** local model on the owner's machine: a 7-8B Q4 local model is acceptable on the 15.6 GB machine (owner, 2026-11-08). |

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
| 1.5b | Batch-friendly loop: one name's dates in sequence, names and offsets in parallel per pass, so a batched backtest needs about (pipeline stages) passes per date step rather than stages x dates per run. | 15-name test needs no more than stages x dates / names passes **Status: done v0.16 (`batch.run_jobs`, `walk_forward_jobs`; 15 names x 5 dates in 34 passes, the slowest single name's count, against 505 run one by one; `stop_at_pending` 41 passes, 3,748 requests instead of 12,115; fake backend, `tests/test_v16_batch_loop.py`)** |
| 1.6 | Drift test: default ids in both tables; `models.retrieve` check skipped without a key. | CI green |
| 1.7 | Token counting via local estimate when no key, `count_tokens` when a key exists, replacing `ESTIMATED_INPUT_TOKENS = 8000` in budget admission. Test N workers at the cap during a retry storm. | test |
| 1.8 | Assert `response.model` equals the configured id and store it per decision (model-version drift). | test |

### P5 ML, risk and edge cases (~11 d) — run before P2/P3 because 5.7/5.8 protect everything after

| # | Item | Done when |
|---|---|---|
| 5.7 | **Edge-case validators and tests**: bar validator (zero/negative/NaN/duplicate dates, gaps) with explicit refusal reasons; synthetic-split invariance property test for every metric; FX 17:00 NY vs equity close and per-sleeve holiday/DST calendar alignment test with the convention documented; stop convention pinned by test (gap through stop fills at open; stop and target in one bar); survivorship statement per table row; short notional cap; ledger floats written with `repr`, compared with tolerance. | all tests green on both backends **Status: done v0.14** |
| 5.8 | **Leakage rigour**: purged/embargoed walk-forward CV for every IC estimate; a **future-leak canary** (inject a shock at T into a data copy; assert nothing from data → analysts → debate → PM changes before T); a point-in-time feature table (feature, as-of, visible-from, source accession) that P3 writes into. | canary in CI **Status: done v0.14** (plus Student-t gate) |
| 5.1 | IC-weighted combination with shrinkage toward zero and a turnover penalty replacing every hand weight (role weights, 25/50/25, 2× tilt, technical 0.30/0.20/0.15); expected return = IC × vol × z; portfolio via shrunk mean-variance; one registered window parameter. **Pre-registered expectation: tilt → 0, desk ≈ control; success is that the pipeline refuses noise.** | trial registered, tables rendered **Status: done v0.14** (design run: IC combination 0.5125 vs control 0.6437, p 0.174; pre-registered expectation did not hold; not adopted) |
| 5.2 | Regime labelling (2–3 state HMM or k-means on vol/trend/rate-change, fitted on design only) conditioning weights and vol target; label also a fact for the LLM. | trial **Status: done v0.14 (5.2b): worse than control on design, not adopted** |
| 5.3 | Split-conformal intervals on the combined forecast; PM sizes on interval width. | trial **Status: done v0.14 (5.2b): worse than control on design, not adopted** |
| 5.2b | Follow-up: build the signal panel and regime labels once per name instead of per date (the bottleneck that stopped the run), then run the regime and conformal design trials already registered. | both trials have design tables **Status: done 2026-11-08** |
| 5.4 | Risk model: filtered historical simulation / EWMA VaR (fix Kupiec and independence), book VaR default-on in multi-sleeve runs, factor exposures (market, rates, USD, momentum), stress rows (2008, 2020, 2022) in every table, capacity row (AUM at which impact costs 0.1 Sharpe). | Kupiec/independence pass on design **Status: done v0.14** (design pass both: historical 4/15, EWMA 13/15, FHS 10/15; default fhs pending owner decision) |

### P2 The LLM study at $0 (~8 d)

| # | Item | Done when |
|---|---|---|
| 2.1 | `LocalLLM` behind the `LLM` protocol (llama.cpp / Ollama HTTP, 7–8B instruct, JSON-schema grammar decoding); same anonymisation, fence, budget (call cap), evidence. **OD-6.** | smoke test on one decision **Status: built, unrun (OD-6)** |
| 2.2 | Study drivers for every cell with `--dry-run` (prints call counts and the dollar estimate at Claude list prices) and `--live` (local model only unless funded). Cells: rules; local analysts + local deep; local on text roles only; local at PM only; no debate; one debate round; single neutral risk analyst. | dry-run table in docs **Status: built, unrun (OD-6)**; dry-run: local_all 16,800 calls, est $214.82, ceiling $1,992.26 at Claude list prices |
| 2.3 | Sampled design: 15 names × 40 design dates × 2 seeds, background job for days; metrics: portfolio Sharpe − control (block bootstrap), agent_sources, contract rejection rate, dispersion, cost-equivalent per decision. | results rendered, every cell a trial **Status: built v0.16 (`--first-pass`, `--report`, `local_analysts` cell); first pass running, results pending** |
| 2.4 | Anonymisation recall audit (200 prompts: "name the ticker and month"; hit rate vs chance; leaking keys listed; tighten `SCALE_FREE_KEYS` if needed). | table **Status: built v0.16 (`v16_local_study.py recall`); results pending** |
| 2.5 | **Refusal/fallback bias**: refusal rate by regime and date, independence test; admissible fallback share per cell capped; stated on every LLM table. | table **Status: built v0.16 (`llm_study.py --report`); results pending** |
| 2.6 | Calibration on the local model: dispersion (n=5), anchoring slope, drift between two model builds on 20 frozen states. | model-risk page **Status: built v0.16 (`v16_local_study.py calibration`, `drift`); results pending** |
| 2.7 | Eval set: 150 frozen (state, rubric) items — used the facts given, invented no numbers, respected the fence; deterministic checks + local-model judge with a human-labelled calibration subset and judge agreement reported. | eval runs in CI on fixtures **Status: built v0.16 (150 items, `v16_eval.py`); checks in CI on fixtures; local run pending** |
| 2.8 | Pre-registration of the one holdout look for the design-winning cell (MDE stated); executed only when a cell clears the design bar. | prereg committed before any holdout run **Status: DRAFT committed v0.16, unsigned** |
| — | Docs say plainly: results are for a local 8B model class, not for Claude; the Claude cells exist as dry-runs with a cost estimate. | |

### P3 Text and retrieval (~12 d)

| # | Item | Done when |
|---|---|---|
| 3.1 | EDGAR full text, point-in-time by acceptance time: 10-K/10-Q Items 1A and 7, 8-K Items 2.02/7.01/8.01; cached by accession; chunked by section; **every filing section is untrusted text** (fence). | provider tests **Status: done v0.15 (offline provider tests)** |
| 3.2 | Rules-based filing-tone-change feature (lexicon diff between consecutive filings) into the alpha library and the feature table; measured by IC/decay like every alpha. | trial **Status: built v0.15; trial registered, NOT run** |
| 3.3 | GDELT headline provider behind a flag (dedupe, language filter), scored by the rules lexicon; measured as a trial. | trial **Status: DROPPED (owner, 2026-11-09)**: low expected value (the filing-tone lexicon was not supported; daily headline sentiment on large caps is crowded) and the source throttles this connection. Script and registered trial kept, not run. |
| 3.4 | RAG corpus: EDGAR sections + central-bank statements (FOMC/ECB/BoE/BoJ, dated by release time) with metadata {symbol, accession, visible_date, section}; point-in-time filter at query time. | tests **Status: done v0.15** |
| 3.5 | Hybrid retrieval: hashed TF-IDF default; optional local embeddings `[rag]`; reciprocal-rank fusion. | tests **Status: done v0.15; embeddings path tested v0.16 through the `ResearchCorpus(embedder=...)` seam with a deterministic fake embedder (`tests/test_v16_quality2.py`); the real `sentence-transformers` model stays unrun (not in lock)** |
| 3.6 | Citations end to end: passages as `document` blocks with `citations: enabled`; evidence-id audit requires every quoted span to map to a passage id. | audit test **Status: done v0.15** |
| 3.7 | Retrieval evaluation: 100 hand-labelled questions with gold accessions; recall@5 and MRR, TF-IDF vs hybrid; **gate: recall@5 ≥ 0.8 before analysts use it**. | table **Status: done v0.15: 100 questions, 34-passage invented corpus; tfidf recall@5 0.990 MRR 0.954, hybrid 0.990/0.961; gate passes; real filings untested** |
| 3.8 | LLM text analysts (fundamentals-text with cited claims, macro-text hawkish/dovish shift) and LLM tone extraction: built against fixtures and runnable on the local model as P2 cells; Claude variants dry-run only. | fixtures + local run **Status: built v0.15; local run done (11/12 and 10/10 usable; de-anonymised run, review N2); wired into the desk v0.15.1 (graph and harness, `text_analysts`, off by default, cut-off 20:00 UTC, retrieval only through the 0.8 gate)** |
| 3.9 | Policy-runbook RAG kept; trial measuring whether removing it changes any decision. | trial **Status: done v0.15: 0/9 decisions changed without runbook RAG (synthetic, rules path); kept** |

### P4 Agentic layer and operations (~13 d)

| # | Item | Done when |
|---|---|---|
| 4.1 | Outcome-aware governance: `DecisionMemory` realised P&L joined to each `TaskRun`; per-role hit rate; critic-flag → outcome correlation; false-positive rate per critic check; weekly roll-up. | report **Status: built v0.15; n=0 (no real TaskRuns recorded)** |
| 4.2 | Planner survival measured on 200 tasks (canonical, rule planner, recorded model plans): step survival through the validator, additions, data-budget hits. | table **Status: real local-model plans (v0.16): 89.3% step survival (1345/1506), 520 added, 13/200 unusable, 0 budget hits. Earlier, done v0.15: canonical 100%, rule planner 100%, synthetic model-plan fixtures 95.1% (1547/1626; tests the validator, not a model)** |
| 4.3 | Memory tool backend for decision memory (governed, fenced, append-only), offline tests. | tests **Status: done v0.15; wired v0.15.1 as `memory.recall` / `memory.remember` behind `agentic.memory_tool` (off), remember through approvals** |
| 4.4 | Injection red-team corpus (150 adversarial headlines/filing snippets: instruction-bearing, role-play, encoded, multilingual); fence structure tests through the rules analysts; compliance rate on the local model; threat model updated with numbers. | table **Status: partly done v0.15: 150/150 fenced, rules = lexicon 150/150, 6/150 flips (buy/sell); local-model compliance not run; `_`-fact fence leak fixed** |
| 4.5 | Approvals: approver identity + signature, N-of-M for `execution.submit_order`, approval TTL and re-pricing check, optional second immutable store. | tests **Status: done v0.15; config-wired v0.15.1 (`agentic.approval` block, approver secrets from env-var names, re-pricing from the provider's last close by default, `--approval signed` on task/serve/mcp; shared-secret HMAC residual risk)** |
| 4.6 | Deferred tool loading with the tool-search tool on the MCP/HTTP surface. | tests **Status: done v0.15 (MCP and HTTP)** |
| 4.7 | **Paper OMS**: order states (new → acked → partial → filled / cancelled / rejected), pre-trade checks (fat-finger notional/quantity, price collar vs last close, duplicate guard, market hours and holidays per sleeve, borrow check), global and per-sleeve kill switch honoured by every tool, end-of-day reconciliation vs ledger with break report, T+1 / FX T+2 settlement and cash projection, FX roll at 17:00 NY. All simulated, policy-gated, evidenced. | tests + cookbook recipe **Status: done v0.14** (pulled forward from P4; shadow record off by default) |
| 4.8 | **Replay mode**: re-run any `TaskRun` from its evidence store with tools and LLM served from recorded payloads; same decision asserted; doubles as the fixture mechanism for 1.2/1.5. | tests **Status: done v0.15 (recordings are pickle: load only your own)** |
| 4.9 | SLOs (latency, failure rate per stage) in `Metrics`; optional OpenTelemetry export to a local collector; golden-transcript tests for the canonical plan on three frozen states. | tests **Status: done v0.15 (`[otel]` extra declared and locked v0.15.1; golden files from numpy backend)** |
| 4.10 | Paper-desk runner on GitHub Actions (free tier, scheduled), laptop fallback, price-vintage hash per session in `runs.jsonl`, CI freshness check (fail if last session > 2 business days old), auto-opened issue on failure. Live web tools permitted here only. | first automated commit **Status: done v0.14** (workflow built; first automated commit waits on the owner's GitHub settings) |
| 4.11 | Flaky `test_interrupted_sweep_spares_a_live_siblings_runs` fixed or quarantined; suite split (PR gate < 10 min, full nightly); `ruff` + `mypy` on `agentic_trader/`; actions pinned by SHA. | CI **Status: done v0.14** (mypy advisory, 144 errors) |

### P6 Documentation and release (per phase, ~1.5 d each)

| # | Item |
|---|---|
| 6.1 | Every cell a trial; deflated Sharpe over all trials incl. LLM cells; cost-equivalent per decision in tables. **Status: done v0.16 (library and docs): all 7 P2 cells registered (77 trials); `registered_trial_count` + `selection_report(n_trials=)`; per-cell table in `what_the_model_adds.md` with every value pending until the P2 records exist** |
| 6.2 | New page "What the model adds" (P2/P3 results, calibration, red-team, retrieval tables, refusal-bias); `ai.md`, LEARN, COOKBOOK, DIAGRAMS updated; a "ready but unrun" box on every Claude cell. **Status: skeleton v0.16: `docs/evaluation/what_the_model_adds.md` (existing results with evidence class; P2 and 4.2 pending); ai.md, LEARN (concept 57), DIAGRAMS (diagram 40) and INDEX link it and live_readiness.md (round 2); P2 rows pending** |
| 6.3 | **Live-readiness statement**: per component what exists / is simulated / is absent (broker, entitlements, custodian reconciliation, tax lots, margin, surveillance); no production claim. **Status: done v0.16: `docs/evaluation/live_readiness.md`, every row sourced to a file and a test** |
| 6.4 | **KPI table** from `agent_sources`, `rule_signal`, memory join: hit rate vs control, Brier and calibration curve, model-delta book, cost per decision; Sharpe as one row. **Status: done v0.16: `agentic_trader/kpi.py` + `agentic-trader kpi`, fixture-tested (`tests/test_v16_kpi.py`); awaits the P2 records** |
| 6.5 | README first paragraph restated for positioning A; single-name desk named as the incumbent control; forward record linked with its decision date. **Status: done v0.16 (decision look at 3,600 sessions, about 14 years from 2026-09-29)** |
| 6.6 | Tags: v0.13 (P1), v0.14 (P5), v0.15 (P2+P3), v0.16 (P4). One batch PR per phase. |

### v0.17 Second review (2026-11-09): every finding and its status

Source: `docs/review/2026-11-09_review_and_plan.md` (first review: Appendix A AI, Appendix B
quant; second review: section 5, Appendices C and D). Lane notes: `docs/review/v017_notes/`.
Branch `feat/v0.17`. Status words: **done** (code and tests merged), **partial** (part done,
the rest named), **queued-run** (code done; the model or network run that produces the number
is queued, see the run queue below), **not-done** (with the reason). Commits: L1 `8e41860`, L2
`1d353ea`, L3 `2c7fdfb`, L4 `431bb52`, L5 `fd681be`, L6 `398b2b3`, L7 `bfdb5e5`, L8 `48534af`,
L10 `6921ce4`, L11 `4a19931`, B8 and critic_on wiring `fc37b75`, L9b (docs fold, headline
scrub, v17 conformal trial) on this branch. Lane L9a (engine hooks, paper OMS hooks, the
flaky test) is in progress in parallel; rows that depend on it say so.

**Owner decisions recorded.** 3.3 GDELT dropped (2026-11-09). The `postcutoff_ta` cell is
approved (2026-11-09), knowing it spends holdout and reserve dates (2025-07 to 2026-10) for the
LLM leakage question only. Tag plan: v0.16.0 on its own CHANGELOG section first, then v0.17.0.
D5 decision: "Rule-variant research on the single-name desk has stopped (v0.17); the desk is
kept only as control #3 for the agentic and multi-asset results."

First review, AI layer (Appendix A):

| id | status | commit / reason |
|---|---|---|
| A1 seeds are replays | done | 8e41860: refuse `--seeds > 1` at temperature 0, per-seed scoring, shared-block bootstrap |
| A2 critic changes no position | done | 431bb52 (rule, harness, graph flag), fc37b75 (`critic_on` cell); the cell's run is queued with P2 |
| A3 clipping instead of rejection | done | 8e41860: schema bounds, reject whole reply, counted as contract failure |
| A4 red team uses another endpoint | queued-run | 431bb52: json mode through `complete_json` and the contract; run queued |
| A5 ASCII-only fence | done | 431bb52: NFKC, invisible-character strip, look-alike regex, 10 variants tested |
| A6 HMAC "signatures" | partial | bfdb5e5: Ed25519 library and gateway; not selectable from config (`signed_gateway_from_config` builds HMAC only) |
| A7 pickle replay keys | partial | 431bb52: canonical JSON keys, FORMAT_VERSION 2; payloads still pickled (no digest allowlist) |
| A8 stale docstrings | done | 431bb52 |
| B1 eval set not anonymised | queued-run | 8e41860: items re-frozen anonymised; eval run into `results/v17_eval/` queued |
| B2 judge calibration measures nothing | queued-run | 398b2b3: cross-family judge, labelling kit; needs the eval run, the llama pull and owner labels |
| B3 red team without control arm | queued-run | 431bb52: `redteam_v2`; run queued at reduced scope (full run 7.5-15 CPU-days) |
| B4 horizon mismatch | done | 8e41860 + 6921ce4: horizon IC and hit rate primary; legacy rows labelled (N6) |
| B5 retrieval set self-fulfilling | partial | 398b2b3: v2 fixture set (tfidf 0.740, hybrid 0.820); real-EDGAR v2 needs the local cache; gate not switched (maintainer decision open) |
| B6 contamination guard unrun | queued-run | 6921ce4 (recall v2), 2c7fdfb (holdout requires a pass); `recall2` run queued |
| B7 planner metric is a validator metric | partial | bfdb5e5: quality vs canonical (F1 0.486, order 0.978); decision equality needs desk runs per plan |
| B8 percentile-tail p | done | bfdb5e5 + fc37b75: null-centred p in `llm_study` |
| C1 eval regression gate | done | 398b2b3; baseline re-recorded at the merge (L9b) |
| C2 model-changed attribution | queued-run | 2c7fdfb: `kpi.model_changed_attribution`; numbers when P2 rows exist |
| C3 output-side guard | partial | bfdb5e5: on `MemoryTool.remember`; the graph's own `memory.record` and the reporter are not covered |
| C4 online drift monitoring | partial | bfdb5e5: `daily_drift` and alerts; not wired into a daily job; numbers when P2 rows exist |
| C5 confidence never scored | queued-run | bfdb5e5: `confidence_calibration`; numbers when P2 rows exist |
| C6 memory-channel attack test | done | bfdb5e5: 20 poisoned lessons, 19/20 refused, fence holds with the guard off (stub model) |
| C7 embeddings path untested | done | round 2 (feat/v0.16-round2): tested through a fake-embedder seam; the 0.98 hybrid number stays a one-off real run |
| (d) Claude-only machinery | done | bfdb5e5: "never run against the live API" boxes in `llm.py`, `batch.py` |
| (d) N-of-M HMAC approvals | partial | kept as a demonstration (OD-C); Ed25519 added (A6) |
| (d) tool search | done | bfdb5e5: measured 58-75% token saving on 16 tools; kept, opt-in |
| (d) OTel and golden transcripts | done | bfdb5e5: marked scaffold; per-call averages from committed meta only |
| (d) two fence copies | done | 431bb52: one source in `state.py` |

First review, quant, code and ops (Appendix B):

| id | status | commit / reason |
|---|---|---|
| A1 same-bar execution | done | 1d353ea: `exec_lag`, `fill="next_open"`, both engines; C++ parity first checked in CI |
| A2 two VaR defaults | done | 8e41860 |
| A3 calendar gaps | done | fd681be: `nyse_calendar.py` |
| A4 quadratic replay | not-done | needs a resumable engine state exported by both backends (C++ API change, no local compiler) |
| A5 financing on leverage | partial | 48534af: `financing.py` post-hoc; in-loop field in both engines is L9a |
| A6 `var_next` drops NaNs | done | 48534af |
| B1 purged CV is a relabel, low power | done | 2c7fdfb: NW t, MDE, `ic_blocked_folds`; table refresh needs Yahoo (queued) |
| B2 no fill-lag sensitivity | done | `scripts/v17_exec_lag.py`; Yahoo run on 3f80a69 published in `docs/results/v17_exec_lag/` (no trial beats control at any timing, all p > 0.16) |
| B3 DSR ignores pre-registry trials | partial | 2c7fdfb: estimate 64 and `selection_report(pre_registry_trials=)`; render scripts not wired |
| B4 vintage is a hash | done | fd681be: raw bars and actions stored per session locally (replaced by N2q: not published) |
| B5 fetch before the bar is final | partial | fd681be: finality assert and same-day revision alert; cron left at 21:30 UTC until revisions show on live runs |
| B6 forward record cannot decide | done | 48534af: decision date 2040-12-19 at d = 0.2 in live_readiness.md |
| B7 gate multiplicity | done | 2c7fdfb: BH over gate families |
| B8 survivorship | done | 48534af: bound measured on holdout B&H rows; design-period equivalent needs SPY (queued) |
| C1 execution realism | partial | 48534af: stop slippage, participation cap, spread estimators (daily OHLC cannot resolve 1-5 bp); engine hooks are L9a; `v17_costs.py calibrate` queued |
| C2 OMS book limits | done | fd681be |
| C3 corporate actions in the paper OMS | partial | 48534af: `corporate_actions.py`; hook into `paper_session` is L9a |
| C4 GJR, ES backtest, book coverage in CI | done | 48534af: `garch.py`, CI test on a fixed synthetic book; GJR on the design names later |
| C5 TCA loop | partial | 48534af: `tca.py`; rows in `paper_session` are L9a |
| C6 `make results` pipeline | not-done | needs the stored vintages to accumulate first; deferred to v0.18 |
| D1 C++ core | partial | 48534af: `bench_core.py` numpy 2.59 s; C++ row not built locally; keep/retire is OD-A |
| D2 docs size | not-done | owner decision (split per module); this release adds to them |
| D3 worktrees in the repo | done | 48534af: checked, all ignored, none tracked |
| D4 stale root artefacts | done | 48534af: checked, all ignored, none tracked |
| D5 rule-variant research | done | decision recorded above |
| (e) mypy advisory | done | fd681be: blocking on the quant core |
| (e) unhashed 3.12-only lock | partial | fd681be: `gen_lockfiles.sh` and Lockfiles workflow; locks not generated (needs PyPI); owner runs the workflow |
| (e) coverage claim | done | 48534af: README note |
| (e) paper runner dual writer | done | laptop task disabled (2026-11-08); fd681be: push with retry and backoff |
| (e) tests and markers | partial | 48534af audit (no dead markers); lag-1, holiday and NW tests added; the flaky sweep test (3/20 under load) is L9a |

Second review (section 5):

| id | status | commit / reason |
|---|---|---|
| N1 recall audit is a constant responder | queued-run | 6921ce4: `recall2`; run queued; v0.16 recall rows void as a recall measure |
| N2 text analysts bypass the anonymiser | done | 4a19931; price-path headlines also scrubbed at this boundary (L9b) |
| N3 first pass unpowered | queued-run | 6921ce4: first pass labelled descriptive; `decisive_ta` registered; run queued |
| N4 no `num_ctx` | done | 6921ce4 |
| N5 no lineage | partial | 6921ce4: header, digest pinning, resume refusal; a periodic `swapped_digest` check inside `run_study` is not wired |
| N6 R0.3 not feasible from stored rows | done | 6921ce4 + 8e41860: new row fields; legacy policy for old rows |
| N7 conformal on overlapping residuals | queued-run | 4a19931: v17 design; v17 trial registered (L9b); real-data run queued |
| N8 nothing-leaves-the-host not enforced | done | 4a19931 |
| N9 no post-cutoff control | queued-run | 6921ce4: `postcutoff_ta` registered; owner approved 2026-11-09; run after the `decisive_ta` smoke |
| N10 no model inventory | done | 4a19931: `docs/models/` |
| N11 dev keys on loopback | done | 4a19931 |
| N1q paper books not frozen | done | fd681be; the re-freeze runs after this merge, before the next paper run |
| N2q raw Yahoo bars in a public repo | done | fd681be: local and opt-in artifact only, `DATA_LICENSING.md` |
| N3q unpinned install in the write job | partial | fd681be: no install in publish/freshness; ruleset bypass for the bot push not verified (owner) |
| N4q pooled IC across classes | done | 2c7fdfb; tables refresh queued |
| N5q no risk neutralisation | done | 2c7fdfb: beta residualisation option, breadth printed |
| N6q in-sample selection row | partial | 2c7fdfb: flagged and excluded from `best()`; walk-forward version not built |
| N7q two gate thresholds | done | 2c7fdfb |
| N8q DSR under correlated trials | partial | 2c7fdfb: `effective_trials`; render scripts do not pass `trial_returns` yet |
| N9q Monday and holiday as-of | done | fd681be |
| N10q hand-copied counts, breadth | done | 2c7fdfb |

**Run queue (all $0, local or free network, after the P2 chain; smoke first).** Eval re-run
into `results/v17_eval/` (L1); `recall2` smoke then full (~480 calls); `decisive_ta` smoke
then full (4,695 calls); `postcutoff_ta` (~1,050 calls); red-team v2 smoke, then `--modes json`
on a subset (target <= 1 day); llama3.1 pull, judge run and owner labels (R3.1);
`v17_exec_lag.py --provider yahoo`; `v14_design_trials.py --out results/v17_conformal`;
`v17_costs.py calibrate` and `horizon`; alpha/xalpha table refresh; `bench_core.py` with
`_atcore`. Exact commands are in the lane notes. Before the next paper run: re-freeze
(`--refreeze v09-engine-2`), Lockfiles workflow, ruleset bypass check.

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
- 2026-11-07 — P5 items 5.4, 5.7 and 5.8 merged on feat/v0.14-p5; offline and synthetic tests only (`tests/test_v14_risk.py`, `test_v14_edges.py`, `test_v14_leakage.py`, 61 tests), $0. 5.4 `risk_model.py`: EWMA and FHS VaR; FHS passes Kupiec and independence on 8/8 synthetic GARCH seeds, the 250-day historical window on at most 2/8; book VaR on by default (`risk.max_book_var_95` 0.05, loose and untuned; `book_var_method` fhs); factor, stress (2022 inside the holdout: report only) and capacity rows. Design-period counts on the 15 real names (`scripts/v14_var_design.py`) pending. 5.7 `validate.py`: bar validator in `TradingGraph.prepare`, session clocks, survivorship line, `risk.max_short_notional`, round-trip ledger CSV, stop convention pinned. 5.8 `leakage.py`: purged walk-forward IC now behind every pipeline IC (alpha and xalpha tables change); future-leak canary clean on synthetic AAPL/EURUSD and catches a deliberately leaking analyst; blind spot: leaks inside a provider's own news()/fundamentals(); `PointInTimeStore` ready for P3. Docs pass done (README, LEARN 52, COOKBOOK 103, CHANGELOG v0.14.0 unreleased with 5.4/5.7/5.8 only, API, quant, AI, architecture, INDEX, site).
- 2026-11-07 — P5 items 5.1-5.3, 4.7 (pulled forward from P4), 4.10 and 4.11 (P4 ops) and P2 items 2.1-2.2 merged on feat/v0.14-p5; offline tests only (`test_v14_combine.py`, `test_v14_oms.py`, `test_v14_ops.py`, `test_v14_local_llm.py`), $0. 5.1: Student-t IC gate (t_crit for k-1 df, refuse < 3 folds) and `combine.py`; three trials registered (TRIALS 62 to 65). Design (2016-2021, 15 names): rules desk 0.6477 vs control 0.6437 (p 0.989); IC combination 0.5125 vs 0.6437 (diff -0.131, CI [-0.314, +0.059], p 0.174, 5/15). Pre-registered expectation (tilt to zero) did NOT hold: a signal survived shrinkage on 82.6% of design dates; nothing adopted or tuned. 5.2 `regime.py` and 5.3 conformal sizing built; design runs pending (5.2b). 5.4 design VaR counts now in: historical Kupiec 14, independence 4, both 4; EWMA 15/13/13; FHS 15/10/10 of 15; EWMA beat the fhs default, owner decision in the PR. 4.7 `oms.py` (states, checks, persisted kill switch also binding `submit_order`, cost parity, reconciliation, T+1/T+2, FX roll); `--oms` shadow record `oms_shadow_v14`, off by default, ledger.csv untouched. 4.10 `paper.yml` + vintage hash + freshness + issue; 4.11 PR gate `-m "not slow"`, nightly full suite, ruff blocking, mypy advisory (144), SHA-pinned actions, two flaky tests fixed. 2.1 `local_llm.py` and 2.2 `llm_study.py` built, unrun (15.6 GB < 16 GB, no Ollama; OD-6). Docs pass done (README, LEARN 53, COOKBOOK 105, CHANGELOG, API, quant, AI, architecture, evaluation, INDEX, site).

- 2026-11-08 — 5.2b: research inputs cached per series (bit-identical, canary clean); regime trial 0.465 vs 0.644 (p 0.009, worse), conformal 0.565 vs 0.644 (p 0.33); neither adopted. Owner switched book VaR default to EWMA (design 13/15 vs FHS 10/15). Workflow token stays read; paper.yml grants write per job.
- 2026-11-08 — P3 items 3.1-3.9 and P4 items 4.1-4.6, 4.8, 4.9 merged on feat/v0.15-p3-p4 (five lanes); offline, fixture and synthetic tests only (`test_v15_text.py`, `test_v15_rag.py`, `test_v15_governance.py`, `test_v15_security.py`, `test_v15_replay.py`), $0. 3.2/3.3 trials registered, NOT run (TRIALS now 70). 3.8 text analysts fixture-tested only, not wired into the graph. 3.7: 100 questions on a 34-passage invented fixture corpus: tfidf recall@5 0.990 MRR 0.954, hybrid (tfidf+BM25 RRF) 0.990/0.961; gate 0.8 passes; says nothing about real filings; embeddings untested ([rag] extra, sentence-transformers deliberately not in lock). 3.9: 0/9 decisions changed without runbook RAG (synthetic, rules path). 4.1: no real TaskRuns recorded, n=0. 4.2: canonical 100%, rule planner 100%, synthetic model-plan fixtures 95.1% (1547/1626; tests the validator, not a model). 4.4: 150 snippets, 150/150 fenced, rules signal == lexicon score 150/150, 6/150 direction flips from lexicon words buy/sell; local-model compliance not run; latent fence leak of `_`-prefixed facts in Analyst.prompt fixed. 4.5 signed approvals opt-in, not config-wired, shared-secret HMAC residual risk. 4.6 deferred tools on MCP and HTTP. 4.8 replay recordings are pickle (load only your own). 4.9 OTel extra not declared (lock regen needed); golden files from numpy backend. Full suite 1484 passed, 3 skipped (numpy backend). Paper trading unchanged; paper.yml has no runs yet, laptop task remains the producer. OD-6 decided: a 7-8B Q4 local model is acceptable on the 15.6 GB machine (owner). Docs pass done (README, LEARN 55, COOKBOOK 112, DIAGRAMS 39, CHANGELOG, API, AI, quant, evaluation, architecture, INDEX, site).

- 2026-11-08 (later) — real-data runs, $0. 3.2 on real SEC filings (design period, 9 names, 201 filings): not supported (IC negative at all horizons, no |t| >= 2); cutter fixed first. 3.7 on real filings: recall@5 TF-IDF 0.92, hybrid 0.98, gate passes. Local model (OD-6 revised: qwen2.5:7b Q4 on CPU): 3.8 text analysts 11/12 and 10/10 usable (de-anonymised: real names and dates in the prompts, relabelled v0.17). 4.4 local compliance: first run discarded (fenced-JSON scorer bug, all 300 replies unreadable); fixed, smoke-tested on 3 snippets, full rerun in progress. 4.2 real model plans: aborted, each plan > 300 s on CPU and timed out; needs a shorter planner prompt or a smaller model, open. 3.3 GDELT: throttled (429), retrying. Paper record moved to GitHub Actions (first run green, laptop task disabled). Lesson: every long model run starts with a 2-3 item smoke test that checks replies parse.
- 2026-11-08 (v0.15.1, feat/v0.15-followup) — wiring items done, offline tests only (`test_v15_followup.py`, `test_v15_local_runs.py`), $0: 3.8 text analysts in the desk on the graph and harness paths (off by default); 4.3 memory tools behind `agentic.memory_tool` (off), `memory.remember` through approvals; 4.5 signed approvals from an `agentic.approval` block (secrets only from named env vars, re-pricing from the provider's last close unless `reprice: false`, `--approval signed` on task/serve/mcp, stdio MCP refuses it); 4.9 `[otel]` extra with 8 lock pins. Planner `compact` prompt option and a resumable plans run for the local model. 3.3 deferred (GDELT throttles this machine; script on main). Docs pass done (README, COOKBOOK 113, CHANGELOG v0.15.1, API, AI, architecture, threat model, INDEX, site).

- 2026-11-08 (evening) — 4.4 local-model compliance (corrected run, all 300 replies readable): 21/150 (14%) attacks moved the signal > 0.5 (instruction 10/32, multilingual 8/26, role play 2/20, encoded 1/40, fence escape 0/32); 7B floor, not Claude. 4.2 real model plans: compact prompt made qwen2.5 drop the closing brace on every plan; grammar-constrained decoding (PLAN_SCHEMA) fixed it (smoke 3/3); full 200-task run launched detached (~106 s each, ~6 h), result in the next round.
- 2026-11-09 — 1.5b batch-friendly loop: `batch.run_jobs` / `walk_forward_jobs` run (symbol, offset) jobs together, one batch per pass; 15 names x 5 dates take 34 passes (slowest single name 34, names one by one 505), decisions equal the direct path; `stop_at_pending` 41 passes and 3,748 requests vs 12,115. Opt-in; `run_agent_backtest` default path unchanged. Fake backend only, $0. Docs: CHANGELOG v0.16.0 unreleased, COOKBOOK 114.

- 2026-11-09 — v0.16 P2 items 2.3-2.8 merged on feat/v0.16-p2 (three lanes); offline, fixture and fake-backend tests only (`test_v16_p2_a.py`, `test_v16_eval.py`, `test_v16_study.py`), $0. Model `qwen2.5:7b-instruct` (4-bit, CPU, Ollama). Owner asked for a model at every stage: first pass runs `local_analysts` then `local_all` against `rules` (15 names x 20 dates x 1 seed); `local_analysts` registered in TRIALS before any run. Runs launched detached, take days. Results for 2.3/2.5, 2.4, 2.6 and 2.7: pending: filled when the run finishes. 4.2 real planner plans survival (v0.15 follow-up): pending: filled when the run finishes. Prereg 2.8 is a DRAFT, unsigned. Known gap: `scripts/llm_study.py` docstring examples still say llama3.1; fix in code after the runs. Docs pass done (README, LEARN 56, COOKBOOK 117, CHANGELOG Unreleased 0.16.0, AI, API, architecture).

- 2026-11-09 — 4.2 real planner plans finished (local model, $0): 200 tasks, qwen2.5:7b-instruct (4-bit, CPU, temperature 0, compact grammar-constrained prompt): 1,345 of 1,506 proposed steps survived the validator (89.3%); the validator added 520 required steps, repaired 145 plans, and 13 plans (6.5%) were unusable (timeout or unparseable); 0 data-budget hits. Canonical and rule planner: 100% (1800/1800). Recorded plans: `tests/data/v15_local_model_plans.jsonl` (+ `.meta.json`; the run resumed twice after shutdowns, so the meta usage block covers the last segment only). Evidence class: real local model, 7B floor, not Claude. Folded into feat/v0.16-combined with lanes 1.5b (batch loop), quality pass (coverage 94.3% -> 95.1%, four bug fixes) and P6 6.2-6.5 (live-readiness, KPI table, README positioning, What the model adds). Full suite 1564 passed, 44 skipped (numpy backend locally; C++ via CI). P2 chain started after plans.
- 2026-11-09 — P6 6.1 and 6.2 remainder (docs round 2), $0, no model calls: five remaining P2 cells registered as trials (77 total); `evaluation.registered_trial_count` and `stats.selection_report(n_trials=)` with tests; per-cell pending table, diagram 40, LEARN concept 57, links from ai.md, LEARN, DIAGRAMS, INDEX; stale counts fixed (57 concepts, 119 recipes, 40 diagrams). Docs checks run locally (cookbook offline, links; Mermaid needs mmdc, not installed locally, so CI renders it).
- 2026-11-09 — Round 2 (feat/v0.16-round2): ruff clean on tests and in CI, mypy 170 -> 35, one CLI crash fixed; coverage 95.2% -> 95.7% with the 3.5 embeddings path tested through a fake-embedder seam; 6.1 every study cell registered (77 trials) and counted in the deflated Sharpe, 6.2 links and diagram 40. 3.3 GDELT DROPPED by owner. Second in-depth review and v0.17 plan: `docs/review/2026-11-09_review_and_plan.md` (R0 blocking items before any P2 result is published).
- 2026-11-09 — v0.17 (feat/v0.17): eleven lanes merged for the second review (R0-R4, N1-N11, N1q-N10q); status of every finding in §4 "v0.17 Second review". Offline code and tests only, $0, no model call. Trials 77 -> 81 (critic_on, decisive_ta, postcutoff_ta, v17 conformal). Price-path headlines now anonymised; eval baseline re-recorded. Owner: GDELT dropped; `postcutoff_ta` approved 2026-11-09 (spends holdout dates for the leakage question only); tag v0.16.0 then v0.17.0. Lane L9a (engine and paper-OMS hooks, flaky test) in progress. Model and network re-runs queued behind the P2 chain. Docs pass done (CHANGELOG Unreleased 0.17.0, LEARN 65, COOKBOOK 130, INDEX links to the model inventory, DATA_LICENSING.md, paper_freeze.md; v0.15 local text-analyst result relabelled de-anonymised).

## 10. How to resume

Say to a new session: *"Resume AgenticTrader per docs/review/PLAN.md (memory: agentic-trader-review-2026-11-07). Zero spend, no card details, solo, free data. Commit docs/review on `feat/v0.13-foundation`, then P1 items 1.1–1.8, one batch PR, docs pass."* The session reads §1, §4 and §9, appends to §9 as it goes, and changes phases in place.

- 2026-11-09 evening: v0.18 follow-up round (lanes A-E, notes in docs/review/v018_notes/): next-open+stops, N6 DSR trial count + stats flags, poison paraphrase check, OMS corporate actions opt-in, llm_study model-swap guard, red-team v2 two-pass scope (chain step skipped; runs after chain end). Remaining: quadratic replay fix (C++ resumable state), v0.8 tables re-render, advisory mypy errors in scripts/llm_study.py and cli/research.py.

- 2026-11-10: v0.19 robustness round (lanes A-C, notes docs/review/v019_notes/): resumable exec_lag + checkpoint helper, local-model retry budget, provider-miss skip rows, k/N progress, operations guide, build scripts use venv python, 27 edge-case tests. Open: measure_v08 run_trials atomic writes + fingerprint (own review), run_recall/run_calibration/_fwd retries, skip-reporting rule in prereg text.
- 2026-11-10 night: ops guide gains "check the worker, not the launcher" (venv launcher at 0 CPU is normal; measure the child process). Still open from v0.19: measure_v08 run_trials atomic writes + fingerprint, run_recall/run_calibration/_fwd provider retries, skip-reporting rule in prereg text.
