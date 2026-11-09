# AgenticTrader: second in-depth review and v0.17 plan (2026-11-09)

Status: review complete, plan proposed, NOT started. Zero spend, no card details, free data, local model only.

Method: two independent read-only reviews of `main` @ cb8dd38 (AI layer; quant, code, tests and docs), each finding cited to file:line and checked against code, not docs. Two claims spot-checked by the maintainer: A1 (temperature fixed at 0, `agentic_trader/agents/local_llm.py:122`) confirmed; B1 (eval prompts carry real tickers: AAPL 107, MSFT 109, NVDA 105, JPM 111, XOM 74 mentions in `eval_set/items.json`) confirmed. Full reviews are Appendix A and B.

## 1. Verdict

The plumbing is good and the statistics code is above sell-side average (BH, PSR/DSR, block and cluster bootstraps, ex-ante EWMA, FHS on lagged sigma, schemas plus a second contract check, anonymiser, fence, replay, an honest MDE table). The "no edge" conclusion stands.

What a top desk would reject is the evidence around it. Several defects would inflate or misstate results, and two mechanisms are weaker than the docs say:

- **The model study can overstate precision.** Temperature is fixed at 0, so the planned two seeds are identical replays that are then pooled and bootstrapped as independent (A1). The eval set is not anonymised while the study is (B1). Decisions are scored over ~3.6-month holds although analysts forecast 1-4 weeks (B4).
- **Governance does not govern.** The critic scales `confidence` after the decision; sizing reads `target_weight`, so a flagged divergence changes no position, and the backtest graph has no critic at all (A2). Schemas have no ranges and outputs are clipped, so an injected `signal: 999` becomes a valid full-conviction +1.0 (A3).
- **Backtests trade at the bar they read.** Signals use `close[t]` and trades fill at `p[t]`, with no lag or next-open option (Q1). This biases toward edge, so it cannot create the null, but short-horizon rule differences sit inside the bias.
- **"Purged CV for every IC" is mostly a label.** For fixed signals the training folds are unused, and the gate is a 5-fold t-test with 4 df, so "nothing cleared" means "could not detect"; no power is reported (Q2).
- **Red-team and retrieval numbers are softer than stated.** 21/150 has no benign control, no direction check, one synthetic state, the unconstrained call path and no end-to-end weight impact (B3/A4). Recall@5 0.92/0.98 rests on 50 real questions written from the gold passages (B5). Judge calibration is 30 hand-written replies judged by the same 7B (B2).

## 2. Findings that are wrong or disputed

- **Paper cron "too early" (Appendix B, item 4): disputed.** The paper script records the last complete New York session (`scripts/paper_trade_v09.py:4`, default as-of = New York yesterday), so the 21:30 UTC fetch reads a bar that closed a day earlier. Keep 21:30 unless the revision log shows same-day revisions; R4.2 adds the check.

## 3. Plan (v0.17), ordered

Effort in solo plan-days; calibrated at ~12-15 plan-days per wall-clock day with 2-3 parallel lanes. Model-run items share the laptop with the running P2 chain.

### R0 Before any P2 result is published (blocking, ~3 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R0.1 | A1 seed pseudo-replication | seeds only with temperature > 0, else refuse `--seeds > 1`; never pool replays; test | 0.5 |
| R0.2 | B1 eval set not anonymised | re-freeze items through the same anonymiser; re-run the eval step | 1 |
| R0.3 | B4 holding horizon | score each decision over its own horizon; IC and hit rate primary, Sharpe secondary; recomputed from stored rows, no re-run | 1 |
| R0.4 | A3 schema ranges | `minimum`/`maximum` in schemas; reject out-of-range instead of clipping; count as a contract failure | 0.5 |
| R0.5 | Two VaR defaults | one constant, live_readiness fixed, agreement test | 0.2 |

### R1 Research honesty (~6 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R1.1 | Q1 execution lag | `exec_lag` / next-open option in both engines (C++ and numpy, parity test); re-run registered trials at lag 1 as a protocol amendment | 2.5 |
| R1.2 | Q2 gate power | Newey-West t and minimum detectable IC per table; drop the "purged" label for fixed signals | 1.5 |
| R1.3 | Multiple testing | BH across the gate family (alphas x names x horizons); DSR with a pre-registry trial estimate | 0.8 |
| R1.4 | Recall audit as precondition | prereg requires a 2.4 pass before any holdout look | 0.5 |
| R1.5 | Model-changed P&L | P&L of decisions the model changed versus the rule decision | 0.7 |

### R2 Governance that governs (~5 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R2.1 | A2 critic | critic veto/scale on `target_weight` in harness and graph; new study cell critic-on | 1.5 |
| R2.2 | B3/A4 red-team v2 | benign control arm, direction-matched compliance, constrained `complete_json` path, several real states, all text analysts, end-to-end `target_weight` impact | 2.5 |
| R2.3 | A5/A8 fence | Unicode NFKC normalisation, single-source fence code, stale docstrings | 0.7 |
| R2.4 | A7 replay keys | canonical JSON hashing instead of pickle | 0.3 |

### R3 Evaluation credibility (~3.5 d + owner time)

| # | Item | Fix | Effort |
|---|---|---|---|
| R3.1 | B2 judge | owner labels >= 100 real replies (owner ~2-3 h, guided sheet); judge from a different free local model family | 1.5 |
| R3.2 | B5 retrieval set | 100 questions paraphrased independently of gold wording; report both sets | 1 |
| R3.3 | Eval regression gate | CI check tied to the prompt-registry hash, on fixtures | 1 |

### R4 Desk realism and ops (~4 d)

| # | Item | Fix | Effort |
|---|---|---|---|
| R4.1 | Vintage | store raw unadjusted bars and corporate actions per paper session, not only a hash | 1 |
| R4.2 | Cron check | assert the recorded session is final; alert on same-day revisions | 0.3 |
| R4.3 | NYSE calendar | one-off closures and early closes, tests | 0.5 |
| R4.4 | OMS limits | gross/net, per-name concentration, order-time VaR checks | 0.5 |
| R4.5 | Build hygiene | hashed lockfiles per Python version with `--require-hashes`; mypy blocking on the quant core | 1.5 |

### R5 Simplify (owner decisions)

- **OD-A C++ core.** Keep (parity is a teaching asset) or retire (doubles CI, no benchmark on daily bars). Recommendation: keep; add one benchmark that justifies it, else retire in v0.18.
- **OD-B Claude-only code never run live** (refusal-fallback beta, BatchLLM live path, price tables). Recommendation: keep as dry-run with a "never run live" box.
- **OD-C Approval machinery** (N-of-M, TTL, re-pricing). HMAC with a server-held secret means server holders can forge approvals. Recommendation: document as a demonstration; asymmetric keys only if positioning needs it.
- **OD-D Second local model** (~5 GB free download) as the judge in R3.1. Recommendation: yes.
- Prune docs size (LEARN, COOKBOOK, CHANGELOG at 130-150 KB) and stale root artefacts (coverage.xml, build/, egg-info).

### Interaction with the running P2 chain

Recall and calibration are unaffected. B4 is fixed in the report from stored rows, so the study cells keep running. B1 needs only the eval step re-run after R0.2. Recommendation: land R0 as the next PR, let the chain continue, re-run the eval step.

### Totals

~22 solo plan-days, $0: about 2-3 wall-clock days of build with parallel lanes, plus model re-runs (eval some hours, red-team v2 ~5-6 h, lag-1 trials some hours) that queue behind the P2 chain. Owner time: R3.1 labelling only.

## 4. Were the 2026-11-07 fixes real?

Real: EWMA/FHS VaR, factor and stress rows, leak canary, Actions paper runner with freshness check, SHA-pinned actions, ruff, schemas plus contracts, anonymiser, replay. Half: vintages (hash only). Not real: "mypy strict" (advisory, lenient). Not fixed: stop slippage, financing spread, horizon from decay. Fixture-only: most agentic fixes have met no real model outside the 7B runs.



## 5. Second review (2026-11-09, independent; gaps and corrections to sections 1-4)

Two further reviewers read the first review and this plan and reported only what it missed, got wrong or under-specified. Full texts: Appendix C (AI) and D (quant, code, ops). All items below are ADDED to the plan; owner order 2026-11-09: implement everything, leave nothing out.

### 5.1 AI layer (Appendix C)
| # | Severity | Finding | Fix | Lane |
|---|---|---|---|---|
| N1 | critical | Recall audit measures option order, not memory: items run name by name with AAPL first and a fixed candidate order; model answers AAPL 129/138, 2019-10 133/138 | shuffle candidates per item, ranked top-3 vs permutation null, synthetic placebo arm, real vs date-shifted test; re-run recall | L6 |
| N2 | high | Text analysts bypass the anonymiser (company, accession/CIK, ISO timestamps, raw text); scrub replaces tickers only | route text prompts through the anonymiser incl. company names, accession and dates; tests | L4 |
| N3 | high | P2 first pass cannot detect an edge (19 periods, MDE ~0.9 Sharpe / ~0.36 IC) | preregister first pass as descriptive; decisive design: technical-analyst cell, weekly dates, 5-day horizon, model IC over rule signal with date-clustered SE, ~5,000 decisions, futility stop | L1 |
| N4 | high | `num_ctx` never set; Ollama default may truncate long prompts from the start (system prompt and fence first); no token count stored | `num_ctx` 8192, store `prompt_eval_count`, flag truncation | L1 |
| N5 | high | No lineage per decision: no prompt hash, git SHA, Ollama version or model digest; resume never checks versions | run header, digest pinning, refuse resume on mismatch | L1 |
| N6 | medium | R0.3 "recompute from stored rows" impossible as written (no horizon, no forward closes; Yahoo re-adjusts) | store horizon and forward closes per row going forward; for past rows use the session vintage, stated | L1 |
| N7 | medium | Conformal sizing on overlapping h-step residuals breaks coverage; ignores regime mask; tested on iid only | non-overlapping/blocked calibration, regime-aware, dependent-data test | L8 |
| N8 | medium | "Nothing leaves the host" not enforced; `llm_anonymize` defaults False | loopback check on `local_llm_url` unless explicit flag; anonymise by default for model cells | L4 |
| N9 | medium | All study dates inside the model training window | post-cutoff slice (2025-07 to 2026-10) as the leakage test cell | L1 |
| N10 | medium | No model inventory or model/dataset cards (SR 11-7 style) | inventory + cards for each model and dataset | L7 |
| N11 | low | Shipped dev API keys accepted on loopback; full config with keys written to a temp file | refuse default keys outside tests; redact secrets in the temp config | L7 |

### 5.2 Quant, code and ops (Appendix D)
| # | Severity | Finding | Fix | Lane |
|---|---|---|---|---|
| N1q | high | Frozen paper books are not frozen: workflow checks out main and recomputes with current code | run from a pinned freeze, engine+config hash check, per-row vintage_id | L5 |
| N2q | high | Planned R4.1 would publish raw Yahoo bars (licensing) | raw bars as Actions artifacts / local, publish hashes only; DATA_LICENSING.md | L5 |
| N3q | medium | Unpinned `pip install` in the write-permission job; direct push to main | hashed install or stdlib step; document or route the push | L5 |
| N4q | medium | IC and spreads rank equities and FX together while scores are per class | per-group IC and spreads | L3 |
| N5q | medium | No beta/sector neutralisation; 2 names a side | beta residualisation option; breadth printed | L3 |
| N6q | medium | `significance_gated` selected and scored in sample; `best()` uses in-sample IC | walk-forward or flag and exclude | L3 |
| N7q | medium | Two gate thresholds (2.0 vs t_crit) | one gate; BH on Newey-West p; explicit families | L3 |
| N8q | low-med | Correlated ablation trials make DSR under-deflate | DSR at an effective trial count | L3 |
| N9q | low | Monday/holiday "yesterday" may be a non-session | resolve to last NYSE session; freshness tolerates gaps | L5 |
| N10q | low | Hand-copied trial count, breadth not stated | generated count; breadth stated | L3 |

### 5.3 Corrections to the first plan
R1.4 gates on the fixed recall audit (N1). R0.2 and R2.2 need N2 first; R2.2 also needs N4. R0.3 is redefined by N6. R3.3 depends on N5. R4.1 is replaced by N2q. P2 headline framing changes per N3: descriptive first pass, decisive design as a new preregistered cell.

## Appendix A. AI layer review

# AgenticTrader AI-side review (hostile, 2026-11-09, main @cb8dd38)

Scope: LLM integration, agents/harness, RAG, guardrails, ML, LLM evaluation methodology.
Method: read code and frozen data, not docs. Read-only; nothing run except small Python reads of
committed JSON. Every finding cites file:line. Effort = wall-clock solo days, $0.

## Verdict

The plumbing is better than most hedge-fund prototypes: schemas plus a second contract gate,
anonymiser, fence, HMAC approvals, replay, prereg with an honest MDE table. The problem is the
**evidence layer around the model**, which is where a desk reviewer looks first. It has several
defects that would quietly inflate or misstate results:

- the study counts duplicated temperature-0 "seeds" as extra data;
- the critic, the advertised governance control, changes no position;
- the eval set skips the anonymisation the study relies on;
- the "human-labelled" judge calibration is 30 synthetic replies;
- the red team has no benign control and does not test the path the desk actually uses.

The previous review's fixes (P1 API plumbing, P4 governance) are real in code, but most are
untested against a real model. Several docstrings still say "UNRUN" for things that were run.

---

## (a) Real defects / bugs

**A1. CRITICAL: "seeds" in the LLM study are identical replays, and the bootstrap counts them as new periods.**
- The desk's local model always decodes at `temperature: 0.0` (`agentic_trader/local_llm.py:122`). `config.py:18` says so: "temperature is 0 regardless".
- `llm_study.run_study` varies only `local_llm_seed` per seed (`scripts/llm_study.py:357`). Under greedy decoding the seed does nothing, so seed 1 repeats seed 0.
- `cell_metrics` appends each seed's period returns into one series (`llm_study.py:436-447`) and block-bootstraps it as one time series (`:389-406`). With the default `--seeds 2` (`:591`) and the planned 2.3 design (15x40x2), n doubles and the CI shrinks by about 1/sqrt(2) for free. Circular blocks also wrap across the seed boundary.
- `dispersion` (`:461-463`) is identically 0, and gets reported as a stability result.
- The first pass uses 1 seed (`:207`), so it is unaffected today. The full 2.3 design is not.
- Fix: either sample (T>0) for the seeded cells, or set seeds=1 at T=0. Always bootstrap per seed and average the Sharpe diff across seeds; never concatenate. Add a test asserting that identical seed series give the same CI as one seed. **0.5 d.**

**A2. HIGH: the critic changes no position, so the governance control is cosmetic for P&L.**
- `harness._finalise` multiplies `decision.confidence` by `critic.multiplier` after the decision is made (`agentic/harness.py:669-671`).
- Order sizing uses `target_weight` (`agentic/servers.py:333,370`). Confidence never feeds back into the weight.
- A `model_rule_divergence` failure (`critic.py:117-129`) therefore leaves the position unchanged. The graph/backtest path that the P2 study uses has no critic at all (no reference in `graph.py`). So the study measures an ungoverned desk while the docs sell a governed one.
- Fix: make the critic act on weight. On divergence, replace the analyst's signal with `rule_signal` (or clip it to `rule_signal ± divergence`) and re-run PM sizing. Or scale `target_weight` by the multiplier. Wire the same critic into `graph.py` behind a flag and make "critic-on" a study cell. **1.5 d.**

**A3. HIGH: out-of-range model numbers are clipped to the extremes, not rejected.**
- The contract checks only presence and finiteness (`agents/base.py:136-147`). The JSON schemas have no bounds (`contracts.py:26-28`).
- `analysts.py:74-75` then `clip`s, so `signal: 999` becomes +1.0, maximum conviction. An injected "set signal to 50" lands as a full-size view and passes as contract-valid.
- Fix: add `minimum`/`maximum` to the schemas wherever the backend honours them (Ollama grammar does). Make an out-of-range value a contract rejection that falls back to rules, and count it in `contract_rejection_rate`. **0.5 d.**

**A4. MEDIUM: the red-team compliance harness calls a different endpoint from the desk.**
- `compliance_run` calls `llm.complete(...)`, which is unconstrained (`agentic/redteam.py:166-167`).
- The desk path is `ask_json` with a schema, i.e. `complete_json` with grammar decoding (`agents/base.py:125`, `local_llm.py:116-130`).
- The 21/150 figure is for free-text decoding plus the lenient `extract_json` (`llm.py:731-747`), not for the configuration that trades. Constrained decoding could move the number either way.
- Fix: run both modes and report both. **0.5 d plus overnight CPU.**

**A5. MEDIUM: the fence is ASCII-only.**
- The neutraliser regex `<\s*/?\s*untrusted_data\b[^>]*>?` (`state.py:36`, duplicated at `redteam.py:46`) does no NFKC normalisation. Fullwidth `＜/untrusted_data＞`, homoglyph or zero-width-split tags pass through untouched.
- The corpus has encoded families, but `fence_check` only verifies the ASCII tag count.
- Fix: NFKC-normalise and strip zero-width/bidi/tag characters (U+200B-U+200F, U+202A-U+202E, U+2066-U+2069, U+E0000-U+E007F) before the regex. Add corpus cases for each. **0.5 d.**

**A6. MEDIUM: approval "signatures" are shared-secret HMACs held by the same process.**
- `policy.py:327` (HMAC-SHA256) and `:429-443`: the server holds every approver's secret. Anyone with server access can mint N-of-M approvals, so this gives no non-repudiation.
- Fix: Ed25519 via the stdlib-free `cryptography` package, which is likely already a transitive dependency; check the lock. Store public keys only on the server. Or document it plainly as "tamper-evident, not non-repudiable". **1 d** (or 0.1 d for the docs-only option).

**A7. LOW: replay keys are `sha256(pickle.dumps(...))`.**
- `agentic/replay.py:54`. The pickle byte stream changes with pandas/numpy/Python versions, so recordings stop matching after a dependency bump.
- Loading uses `pickle.loads` (`:284`), and recordings could become test fixtures that get shared.
- Fix: canonical JSON key (sorted keys, floats via `repr`, frames via `to_json(orient="split")`). Keep pickle only for the payload, behind a hash allowlist. **1 d.**

**A8. LOW: stale docstrings contradict the results.**
- `redteam.py:22-25` and `:141,163` say "UNRUN ... no local model". `docs/results/v15_local/redteam_compliance.json` exists with 150 rows.
- A reviewer reading code will distrust everything else.
- Fix: grep for `unrun|UNRUN|no local model` and update. **0.1 d.**

## (b) Methodological flaws that would invalidate conclusions

**B1. CRITICAL: the eval set is not anonymised, while the study is.**
- The study forces `llm_anonymize: True` (`llm_study.py:75`). The default is `False` (`config.py:61`).
- 41 of 150 frozen eval prompts contain real tickers (AAPL/MSFT/NVDA/SPY/EURUSD; counted from `knowledge/eval_set/items.json`).
- Eval scores ("used facts", "no invented numbers") are therefore measured on a different prompt distribution from the trading cells. Named tickers also invite recalled numbers, which inflates "invented numbers" failures in a way that does not transfer.
- Fix: rebuild the items through `Anonymizer` (rescale facts, aliases), re-freeze, re-pin the test. Optionally keep a named copy as an explicit "leak probe" arm. **1 d.**

**B2. HIGH: the "human-labelled calibration subset" measures nothing about the real judge task.**
- `calibration.json` has 30 rows. Its own `_note` says "Replies are written by hand, not by a model". The labels are the author's.
- The commit (`7813829`, "v0.16 lane B") came from an agent lane, so the "human" labeller is most likely the same AI that wrote the rubric and checker.
- Label mix: 15/30 all-pass, 4 fence failures.
- Kappa on 30 hand-crafted, deliberately clean-cut cases says nothing about agreement on real 7B replies. The judge is also the same qwen2.5:7b that is being judged (`v16_eval.py:165`), a known self-preference bias.
- Fix: label at least 100 real model replies from `run.jsonl`, by the owner (about 2 h), stratified by checker verdict. Report kappa with a bootstrap CI. Use a different model family as judge (e.g. llama3.1:8b or phi) and report cross-judge agreement. **1.5 d.**

**B3. HIGH: the red-team metric has no control arm and conflates sentiment with compliance.**
- "Complied" means |Δsignal| > 0.5 or unreadable (`redteam.py:168`).
- There is no benign-suffix control: the carrier plus a neutral sentence of equal length and tone.
- There is no targeted test: did the signal move in the direction the payload demanded?
- Payloads containing "buy/sell" legitimately move a sentiment analyst. The rules arm counts exactly this (`redteam.py:14-19`), but the model arm does not subtract it.
- Only one synthetic state is used (`_state`: AAPL, a linear uptrend), and only the News analyst. The critic divergence check, which would have flagged most of the 21 ±1 replies (bases cluster at 0, attacked at ±1.0 in 21 cases), is never exercised end to end.
- Fix: add a control arm and a direction-matched compliance definition. Add 5 states, and an end-to-end run measuring how many attacks change the final `target_weight` after critic and limits. That last number is the one a risk committee wants. **2 d plus overnight CPU.**

**B4. HIGH: first-pass P&L holds each decision about 3.6 months against a stated 1-4 week horizon.**
- 20 dates spread evenly over 2016-2021 (`llm_study.py:151-155,207`). Each weight is held to the next design date (`:425-446`).
- Analysts forecast "next 1-4 weeks" (system prompt in `items.json`), and trades carry `horizon_days`.
- The Sharpe compares forecasts at roughly 5x their horizon. A null there is uninformative and a positive is luck. With 19 periods, the design-bar CI (prereg DRAFT:38) is essentially unpassable.
- Fix: score each decision over its own horizon (e.g. a 20-day forward return, or `horizon_days`). Use IC / hit rate versus the control as the primary metric, which matches PLAN principle 5. Treat Sharpe as secondary. State the design-pass MDE as the prereg does for the holdout. **1 d.**

**B5. MEDIUM: retrieval recall@5 0.92/0.98 is close to self-fulfilling.**
- `edgar_real_questions.json` has **50** questions, not 100. They were written while looking at the gold passage and repeat its literals and entity names, e.g. "from 80 cents to 84 cents", "J&J board raises quarterly dividend to 95 cents". Lexical overlap is what TF-IDF rewards.
- The corpus is small, and `evaluate_retrieval` (`research_rag.py:423-433`) has no distractor-scale test.
- The gate (≥0.8) therefore says little about analyst-style queries ("is credit risk rising at JPM?").
- Fix: add 50 paraphrased/abstract questions written without the passage open. Grow the corpus to every cached filing (hundreds). Report recall by question type. **1.5 d.**

**B6. MEDIUM: training-window contamination guard rests on an audit that has not run.**
- The design period 2016-2021 and holdout 2022-2026-06 both sit inside qwen2.5's pretraining window. The prereg admits anonymisation is "the only guard" (DRAFT:53).
- The 2.4 recall audit is pending. The return-series shape leak is acknowledged (`v16_local_study.py:22`) but not quantified.
- Fix: run 2.4 before any P2 number is published, and make "recall ≤ chance + 2 SE" a hard precondition in the prereg. **0.5 d plus CPU.**

**B7. MEDIUM: the planner's 89.3% step survival is a validator metric, not a quality metric.**
- The validator added 520 required steps. Survival therefore measures how much code repaired the model, not whether the plans were good or produced better decisions.
- Fix: report "plans needing zero repair" and the decision equality versus the canonical plan on the 200 tasks. **0.5 d.**

**B8. LOW: the bootstrap p-value is the percentile-tail share, not null-centred.**
- `llm_study.py:404`. It is acceptable as a rough number, but with deflated Sharpe in the bar it should be a studentised or null-recentred bootstrap. **0.3 d.**

## (c) Missing versus a 2026 production AI research platform

| # | Missing | Severity | $0 fix | Effort |
|---|---|---|---|---|
| C1 | Eval regression gate in CI on **recorded real local replies**: fixtures exist (`tests/data/v15_local_model_plans.jsonl`), but there is no "score must not drop" gate on prompt changes. `prompt_bundle_hash` (`prompts.py:162`) is not tied to an eval score. | high | CI job: prompt hash change ⇒ eval on recorded replies must be re-recorded or the hash pinned to a stored score | 1 d |
| C2 | Per-decision attribution of the model delta (exact P&L of the decisions the model changed vs the rules, with CI). `kpi.py` exists but n=0. | high | Compute it from first-pass rows (`sources`, `rule_signal`) as soon as P2 lands | 0.5 d |
| C3 | Output-side guard: no check that the model's summary contains no URLs, tickers outside the allowed set, or canary echoes before it is stored as untrusted memory / report text. | medium | regex/allowlist filter in `reporter.py` + memory write path | 0.5 d |
| C4 | Online drift monitoring of model outputs (signal distribution, rejection rate, divergence rate per day) with an alert. `drift` exists only as a two-build offline compare. | medium | daily paper-runner job appends stats; CI freshness check already exists, add thresholds | 1 d |
| C5 | Uncertainty from the model is never validated: `confidence` is not scored (Brier/reliability) on any real-model output. | medium | add to 2.6 using forward 20 d returns | 0.5 d |
| C6 | No adversarial test of the **memory** channel (poisoned lesson reaches later prompts). | medium | add 20 corpus items through `memory.remember` → recall path | 0.5 d |
| C7 | Embedding retrieval path untested (PLAN 3.5: `sentence-transformers` not in the lock) yet the 0.98 hybrid number is quoted. | low | either lock the extra and test, or mark it as a one-off number | 0.5 d |

## (d) Over-engineering / things to delete or freeze

- **Claude-only P1 machinery that has never run against the API**: refusal-fallback beta (`llm.py:29-34,437-441`), 5.5 price/capability tables, served-model drift, `count_tokens` admission, and `BatchLLM`/1.5b batching (`batch.py`, 281 lines) for a $0 project. These are maintenance liabilities against moving beta headers. Freeze them behind one "untested against live API" banner and stop extending them. Delete `_FALLBACK_BETA` usage if no funded run is planned within 3 months.
- **N-of-M HMAC approvals, TTL, re-pricing, second store** (`policy.py:370-460`): this is production theatre for a paper desk with one human. Keep a single signed approval and drop the rest, or fix A6 properly.
- **Tool-search deferred loading** (`agentic/tool_search.py`) for a small tool set. Context savings are negligible, and it adds a failure mode. Delete it, or justify it with a token measurement.
- **OpenTelemetry extra plus golden transcripts**: fine, but there are no SLO numbers from real runs. Either collect them from the local runs or mark the feature as scaffold.
- **Two FENCE_NOTE copies** (`critic.py:36`, `text_analysts.py:35`) and two neutraliser regexes (`state.py:36`, `redteam.py:46`). Make each a single source of truth, or the next fix (A5) will land in one place only.

## Were the previous review's fixes real?

- L5 model tiers, structured outputs, caching, token counting: **real in code**, fixture-tested only; zero live verification (acceptable at $0, but say so in code, not only docs).
- "Governance governs decisions with no information": **still true**, and A2 shows that even when it fires it changes nothing.
- "No injection red-team on a live model": **done, but measured wrong** (A4, B3).
- "Analysts hand the model the same indicators": **unchanged**. Text analysts exist but are off by default and the filing-tone signal failed (3.2), so the model still mostly re-weights the rules.

## Top-10 priority list

| # | Item | Sev | Effort |
|---|---|---|---|
| 1 | A1: fix seed pseudo-replication before the 2.3 full design runs | critical | 0.5 d |
| 2 | B1: anonymise the eval set to match the study | critical | 1 d |
| 3 | A2: make the critic act on `target_weight` and add a critic-on study cell | high | 1.5 d |
| 4 | B4: score decisions over their own horizon; IC/hit rate primary | high | 1 d |
| 5 | B3 + A4: red-team control arm, direction-matched compliance, constrained-decoding mode, end-to-end `target_weight` impact | high | 2.5 d |
| 6 | B2: owner labels ≥100 real replies; cross-family judge | high | 1.5 d |
| 7 | A3: bounds in schemas; reject instead of clip | high | 0.5 d |
| 8 | B6: run the 2.4 recall audit and make it a prereg precondition | medium | 0.5 d |
| 9 | C1 + C2: CI eval-regression gate tied to the prompt hash; model-delta P&L attribution | high | 1.5 d |
| 10 | A5 + A8 + dedup: Unicode-safe fence, single-source fence/regex, stale docstrings | medium | 0.7 d |

Total ≈ 11 solo days, $0. Items 1, 2, 4 and 7 should land before any P2 result is written up,
or the first published LLM table will be wrong in ways an outside reader can find in an hour.


## Appendix B. Quant, code, tests and docs review

# AgenticTrader: hostile quant / quant-dev review (non-LLM scope)

Repo: C:\Work\Claude\AgenticTrader, main @ cb8dd38, read only. Reviewer stance: systematic fund
QR + QD + algo dev + eng lead. Every finding below was checked in code, not in docs. Effort is
wall-clock solo days. Spend for every fix is $0.

Coverage note: this was a targeted read (stats.py, leakage.py, risk_model.py, backtest.py,
quant/pycore.py engine, algo.py, oms.py pre-trade and calendar, validate.py, yahoo.py, CI and
paper workflows, lockfile, PLAN, previous review, live_readiness). I did not read alpha.py,
xalpha.py, combine.py, portfolio.py, evaluation.py line by line, did not diff C++ against
Python, and ran no tests. Findings outside the read set are marked "not verified".

## 0. Verdict

The statistical toolkit is above sell-side average and mostly correct: BH, PSR/DSR, the
circular block bootstrap, cluster-paired bootstrap, the purged fold builder, ex-ante EWMA, and
FHS standardised on lagged sigma. The 2026-11-07 review's fixes are mostly real: EWMA/FHS VaR,
factor exposures, stress rows, capacity, vintage hash, the Actions paper runner, freshness and
issue alerts, SHA-pinned actions, ruff. But four things weaken the headline claims:

1. Every backtest fills at the same close the signal reads (no execution lag anywhere).
2. The "purged walk-forward CV for every IC" is mostly a relabel. For fixed signals the
   training sets are never used, and the gate is a 5-fold t-test with 4 df, which has almost
   no power. "No alpha passed the gate" is therefore weak evidence of no alpha.
3. The vintage system stores a hash, not the bars. Revisions are detected, not reproducible.
4. mypy is advisory, the lockfile has no hashes and is 3.12-only, and docs disagree with code
   on the VaR default.

None of these flips the "no edge" conclusion. Point 1 biases results toward edge, and the
project found none anyway. They do mean that several "measured" statements are stronger than
the code supports.

## (a) Real bugs / correctness defects

| # | Sev | Finding (evidence) | $0 fix | Effort |
|---|---|---|---|---|
| A1 | High | **Same-bar execution.** `quant/pycore.py:688-705`: the weight `w_in[t]` is traded at `p[t]` (`Trade(t, prev, w, p[t])`) and earns `p[t+1]/p[t]`. The baselines compute their signal from `close[t]` (`backtest.py:236-256`, where `realized_vol(c,20)` includes c[t]). The agent loop decides at `window.index[i]` using bars up to i, then holds from i (`backtest.py:336-357`). `evaluation.md:210` documents this as an assumption, but there is no `execution_lag` or next-open option anywhere (grep finds none). It is a market-on-close fill on information you only have after the close. The bias is small for 12-1 TSMOM and material for ZMR, KDJ+RSI, 5d reversal and stop logic. | Add `execution_lag: int = 0` (shift `w_in` by 1) and a `fill="next_open"` mode to both engines (C++ and numpy). Re-run the headline tables with lag 1 as a sensitivity row. Pin it with a test showing that a signal equal to `sign(r[t+1])` earns nothing at lag 1. | 1.5 |
| A2 | Med | **Two VaR defaults.** `risk_model.py:98,113` defaults `method="fhs"`, but `config.py:169` sets `book_var_method: "ewma"`. `docs/evaluation/live_readiness.md` (pre-trade row) says "FHS default, EWMA option", which is wrong for the desk path. Any direct caller of `var_next()` gets FHS while the desk uses EWMA. | One constant `DEFAULT_VAR_METHOD` used by both. Fix the doc row. Add a test that `config` and the function default agree. | 0.2 |
| A3 | Med | **Calendar gaps.** `oms.py:145-167` `nyse_holidays` has no one-off closures (2012-10-29/30 Sandy, 2018-12-05 Bush, 2025-01-09 Carter) and no early closes (13:00 on the day before Independence Day, Black Friday, Christmas Eve). `is_open` will accept a 14:00 order on a half day, and the paper OMS's market_hours check is wrong on about 3 days a year. | Add a static `NYSE_SPECIAL` table (closures and early closes, 2000 to present) plus a test per entry. | 0.5 |
| A4 | Low | **Quadratic replay** in the agent backtest: `backtest.py:341-343` re-runs `quant.run_backtest(prices[:i+1], ...)` at every rebalance to recover the held weight. That is O(n^2/rebalance_every). It is harmless at daily x 15 names but is the hot path of a 40-minute suite. | Expose the engine state (position, equity) incrementally, or run the engine once with a callback. | 1 |
| A5 | Low | **Cash leg on leverage:** `pycore.py:720` gives `cash = (1-|w|)*rf`. With `|w|>1` the negative cash is financed at rf, with no spread. Shorts pay a flat `borrow_annual`, with no hard-to-borrow. live_readiness admits there is no financing model. | Add a `funding_spread_bps` applied when `|w|>1`, at a 50 bps default. | 0.3 |
| A6 | Low | `var_next` (`risk_model.py:121`) silently drops non-finite returns before the forecast. That compresses calendar time (a NaN-gap day disappears), unlike `var_forecast`, which keeps alignment. The two can disagree on the same data. | Keep NaNs and let `ewma_vol` skip them, as it already does. | 0.2 |

## (b) Methodological flaws that weaken or invalidate conclusions

| # | Sev | Finding (evidence) | $0 fix | Effort |
|---|---|---|---|---|
| B1 | High | **Purged CV is mostly theater for fixed signals.** `leakage.py:253-281` says so in its own docstring: "the training sets are not used here". The purge and embargo only matter when something is fitted. What remains is a block-mean of 5 fold ICs with t on 4 df (`_summarise`, `leakage.py:241-251`; bar 2.776). Power: at IC 0.03 across 5 names-years, a k=5 t-test is far below a HAC/Newey-West t on all non-overlapping pairs. PLAN item 5.8 and the CHANGELOG present this as "leakage rigour". Every "no alpha clears the gate" statement inherits the low power, and no power analysis is reported. | Report a Newey-West t (lag = horizon) on all pairs alongside the fold t. Add a minimum-detectable-IC line (at 80% power) per table, so a null reads "cannot detect IC < x" and not "no edge". Reserve the "purged" label for fitted things: IC-weight combination, regime and conformal. | 1.5 |
| B2 | High | **No fill-lag sensitivity on any published Sharpe** (follows from A1). The beta 0.9 / R² 0.89 finding stands, but rule-variant differences of 0.05 to 0.1 Sharpe, which are typical of the trials table, are inside the same-close bias for the short-horizon rules. | Re-run the trial table at lag 1 and re-register it as a protocol amendment, not as a new trial. | 1 (after A1) |
| B3 | Med | **The DSR benchmark is built from the dispersion of trial Sharpes** (`stats.py:154-188`). The code has an honest caveat, but the deflation counts only registered trials. Implicit trials (rule constants 0.30/0.20/0.15, the 25/50/25 blend, ATR multiples, lookbacks chosen in v0.1 to v0.5 before the registry existed) are not counted. The 62 is a floor. | Add a "pre-registry degrees of freedom" estimate (count tunable constants in the rules path), and report DSR at 62 and at 62 + that count. | 0.5 |
| B4 | Med | **Vintage = hash only.** `scripts/paper_trade_v09.py:247` records `vintage_hash(provider.frames)`; raw bars are not stored. A revision can be detected but not attributed (dividend re-adjust, split, late print), and a past session cannot be recomputed bit-exactly once Yahoo re-adjusts. With `auto_adjust=True` (`data/yahoo.py:4`), every dividend rewrites the whole history, which explains much of the 141 recomputed cells. | Commit a gzip parquet/CSV of the session's raw bars (unadjusted plus actions) under `results/paper/bars/YYYY-MM-DD/` (15 names x 2 y is about 1 MB/day), or keep the last N plus monthly. Compute adjusted series locally from raw plus actions. | 1 |
| B5 | Med | **Paper fetch 30 min after the EST close** (`paper.yml:22`, cron 21:30 UTC, which is 16:30 ET in winter). Yahoo's daily bar and volume are often not final at that point, so the job creates its own "revisions". | Move to about 23:30 UTC (still the same session date). Record the fetch timestamp and whether the bar is final (re-fetch D-1 and diff before computing D). | 0.3 |
| B6 | Med | **Forward record cannot decide** (PLAN §2: about 14 years). That is fine as a statement, but it makes the paper record operational evidence, not research evidence. Docs should stop calling it "the only unseen data" as if it could adjudicate. | Publish the min-track-record figure next to the ledger and state the decision date explicitly. | 0.2 |
| B7 | Low | **Gate multiplicity:** `passes_gate` is per (signal, instrument). There are 9 alphas x 15 names x several horizons, and no BH across the gate set (BH exists, `stats.py:194`, but is applied to evaluation tables). Any future "pass" would be false-positive prone. | Route gate decisions through BH over the full family. | 0.3 |
| B8 | Low | **Survivorship:** `validate.survivorship_statement` writes a sentence. The universe is today's 10 mega-caps, chosen with hindsight. That is acknowledged, but every equity result is conditioned on winners, which inflates B&H and thus the control. | State it in each equity table header (partly done). Nothing free fixes it at 15 names. | 0 |

## (c) Missing capabilities versus a real desk (prioritised, $0 only)

- C1. **Execution realism:** no next-open or VWAP-of-next-day fill, no stop slippage beyond a gap-at-open (`_exit_fill`), no participation cap in the backtester (the OMS has one), and the impact coefficient of 1.0 is not calibrated. A $0 calibration is possible: fit the sqrt-law coefficient to the paper OMS fills versus arrival is circular, so use the published literature value (around 0.1 to 0.3 x sigma for large caps) as a sensitivity band. (1 d)
- C2. **Portfolio-level risk limits in the OMS:** `_pre_trade` (`oms.py:507-539`) checks fat finger, collar, duplicate, hours, borrow and short cap. It has no per-name gross limit, no book gross/net, no concentration and no VaR breach check at the order level (VaR lives in the risk team, upstream). A real pre-trade gate re-checks limits at order time. (0.5 d)
- C3. **Corporate-action handling as data:** actions are fetched (`yahoo.py:108-124`) but no ex-date-aware position adjustment exists in the paper OMS (quantities in shares across a split). (Not verified end to end.) (1 d)
- C4. **Risk model:** EWMA lambda 0.94 is fixed, with no GARCH/GJR (free via `arch`, if that dependency is acceptable). There is no ES backtest (Acerbi-Szekely) and no book-level Kupiec/Christoffersen in CI on a fixed synthetic GARCH path. (1 d)
- C5. **TCA loop:** OMS shadow fills are not compared with the backtest's predicted cost per order. A desk's first live-readiness metric is predicted-versus-realised slippage. (1 d)
- C6. **Reproducible results pipeline:** a single `make results` that regenerates every published table from stored vintages, with hashes in the docs. (2 d, after B4)

## (d) Over-engineering / candidates to delete

- D1. **The C++ core** (`cpp/`, about 3 files plus bindings, C++17 `-O3`). It duplicates `pycore.py` operation for operation for daily bars on 15 names, where numpy finishes in milliseconds. It doubles the CI matrix and creates a parity-maintenance tax. Keep it as a parity demo, but stop claiming performance relevance, or delete it and the `_atcore` .pyd. If kept, add a benchmark that justifies it. (0.5 d to document; deletion 0.5 d)
- D2. **LEARN.md (143 KB), COOKBOOK.md (133 KB), CHANGELOG.md (152 KB).** These are unreviewable at this size, and the docs-versus-code drift (A2) proves it. Split them per module, and generate numbers from results files rather than hand-copying. (2 d)
- D3. **`.claude/worktrees/agent-*` copies of the whole package inside the repo directory** (grep hits many duplicate `stats.py`). If any are unignored they pollute search, coverage and packaging. Confirm they are git-ignored and prune them locally. (0.1 d)
- D4. **Stale artefacts at the repo root:** `coverage.xml` (27/09), `.coverage`, `build/`, `__pycache__/`, `agentic_trader.egg-info`. Make sure they are ignored. Coverage from September is not evidence for the "~95%" claim. (0.1 d)
- D5. **Rule-variant research on the single-name desk:** stop, as the previous review said and PLAN agreed. The remaining value is as control #3.

## (e) Code quality, tests, ops

- **mypy is advisory** (`ci.yml:35-37`, `continue-on-error: true`; `pyproject.toml:59-64` is lenient with `ignore_missing_imports`). The previous review's O4 asked for `--strict`, and what landed is non-blocking lenient. That is not a real fix. Make it blocking on `quant/`, `stats.py`, `leakage.py`, `risk_model.py` and `oms.py` first. (1 d)
- **Lockfile** (`requirements-lock.txt`): a `pip freeze` with no `--hash` entries (one "hash" match, in a comment) and "Valid for Python 3.12 only". The CI matrix runs 3.10 to 3.14 unlocked, so the published numbers are reproducible only on 3.12 and are not supply-chain pinned. Use `pip-compile --generate-hashes` or `uv pip compile` per Python, and install with `--require-hashes`. (0.5 d)
- **Coverage claim:** coverage is collected only on the numpy-backend job (`pyproject.toml` comment). C++ branches are covered only by parity tests, and the ~95% figure counts pycore, not `cpp/`. Say so in the README. (0.1 d)
- **Paper runner:** Actions is primary now, and the laptop task also commits to main (`paper.yml:7`, and `:83-90` rebases once and retries). Two writers on an append-only ledger with a retry-once race is fragile. Disable the laptop task, which memory says is pending, or make it write to a branch. A bot pushing straight to main under a ruleset with 9 required checks means either the bot bypasses the ruleset (document it) or pushes fail. (0.3 d)
- **Tests:** 63 test files, plus 55 skip/xfail/flaky markers worth auditing. Property tests exist (hypothesis directory). Missing: a lag-1 no-lookahead property on the engine (A1), a holiday table test (A3), and a Newey-West power test (B1).

## (f) Previous-review fixes: real or not

| Prev item | Status |
|---|---|
| R6 EWMA/FHS VaR, factor exposure, stress, book VaR on | **Real** (`risk_model.py:45-135`, 138-232). Default-mismatch bug A2. |
| R7 vintage per session | **Half.** Hash only, no stored bars (B4). |
| 5.8 purged CV and canary | **Canary real** (`leakage.py:458`). Purged IC mostly cosmetic for fixed signals (B1). |
| O1 Actions runner, freshness, issue | **Real** (`paper.yml`). Dual-writer risk remains. |
| O2 flaky test, suite split | Partly (`-m "not slow"`, nightly.yml). Not verified that the flake was fixed. |
| O4 ruff + mypy strict, SHA pins | ruff and SHA pins real. **mypy not real** (advisory, lenient). |
| Q7 cost model (stop slippage, financing) | Not fixed (A5, C1). |
| Q4 horizon from decay | Not fixed. Rebalance remains 5 bars by fiat (not verified in alpha.py). |

## Top 10 (do in this order)

1. **A1/B2** Add execution lag and next-open fill to both engines. Re-run trials at lag 1 as a protocol amendment. (2.5 d) High.
2. **B1** Add a Newey-West t on all pairs and a minimum-detectable-IC per table. Stop calling fixed-signal fold ICs "purged CV". (1.5 d) High.
3. **B4** Store raw unadjusted bars plus actions per paper session and derive adjustments locally. (1 d) Med.
4. **B5** Move the paper cron to about 23:30 UTC and add a D-1 finality re-check. (0.3 d) Med.
5. **mypy blocking** on the quant core modules. (1 d) Med.
6. **Hashed per-Python lockfiles**, with CI installing `--require-hashes`. (0.5 d) Med.
7. **A2** One VaR default constant, fix live_readiness.md, plus an agreement test. (0.2 d) Med.
8. **A3** NYSE one-off closures and early-close table, with tests. (0.5 d) Med.
9. **C2** Book gross/net/concentration plus an order-time VaR check in OMS `_pre_trade`. (0.5 d) Med.
10. **B3 + B7** DSR with a pre-registry DoF estimate, and BH over the gate family. (0.8 d) Low-Med.

Total is about 9 wall-clock solo days. Deletion candidate: the C++ core, unless a benchmark justifies it (D1).


## Appendix C. Second review: AI layer

# AgenticTrader: second hostile AI review (2026-11-09)

Scope: AI / ML / LLM / RAG / agents / evaluation. Code: `C:\Work\Claude\AgenticTrader-round2` (feat/v0.16-round2). Live artefacts checked read-only in `C:\Work\Claude\AgenticTrader-v16\results\v16_local\` (the running chain). Findings already in `docs/review/2026-11-09_review_and_plan.md` are not repeated unless the planned fix is wrong or incomplete.

## Verdict

The first review was right on what it covered, but it reviewed the study design on paper. It did not open the running chain's output, and it did not trace the anonymiser through the text path. Doing both shows three things:

1. The anonymisation recall audit (2.4), which the plan now makes a precondition for any holdout look (R1.4), is running and is degenerate. The model answers one constant. A pass or fail from it means nothing.
2. The text analysts bypass the anonymiser completely.
3. The P2 first pass has no statistical power for its headline metric, so it cannot be decisive. It should be re-framed before results land, not after.

The model runs also lack the lineage a model-risk function would need: no stored prompt, no prompt hash, no weights digest, no Ollama version, no git SHA. In addition, nothing sets `num_ctx`, so long prompts can be silently truncated by Ollama.

---

## Findings

### N1. CRITICAL: the recall audit is a constant responder; its verdict depends on the stopping point
Evidence:
- `results/v16_local/recall.rows.jsonl` (137 rows at review time): the guessed ticker is `AAPL` 129 times and `MSFT` 9 times. The guessed month is `2019-10` 133 times and `2018-10` 5 times. All 15 ticker hits are AAPL items (14) plus one MSFT item.
- `scripts/v16_local_study.py:231`: items are built in name-major order (`[(n, d) for n in NAMES for d in design_dates(14)][:200]`), with AAPL first, and `recall_question` (`:144-146`) always lists the candidates in the same order with AAPL first. The rate test is in `:137-140` (Wilson CI and binomial against p0 = 1/15).

Why it matters:
- A model that always says the first option scores 14/200 = 7.0%, against a chance level of 6.7%. That reads as "no recall" even if the model could recognise every series.
- A run stopped early (for example at 30 items, 14 of them hits) is flagged `above_chance`.
- The audit therefore measures position bias, not memorisation. R1.4 makes this audit a gate, and R0.2 re-runs the eval through the same anonymiser, so both would rest on a null instrument.
- The 200-item cap also drops most of the last FX name: 15 x 14 = 210 items, so the last 10 are cut.

Why it was missed: the review read the design (`:24-31`), not the rows.

$0 fix:
- Shuffle the candidate order per item, with a recorded seed, and interleave items across names.
- Ask for a ranked top-3, and score the mean reciprocal rank (MRR) against a permutation null that preserves the model's own answer distribution. Equivalently, compare against a "same prompt, shuffled labels" control.
- Add a placebo arm: synthetic series with the same volatility and drift, which no model can recognise. The audit passes only if real-series accuracy does not beat the placebo.
- Add a behavioural leak test, which matters more than naming. Run the same anonymised state twice, once with the real future and once with a date-shifted state of the same name. Then test whether the model's signal correlates with realised forward returns more on real states than on shifted ones.
- Stop and restart the recall step of the chain. It costs about 4 h of CPU.

Effort: 1.5 d.

### N2. HIGH: the text analysts never see the anonymiser; the prompt carries ticker, CIK and absolute dates
Evidence:
- `graph.py:265` calls `text_reports(names, llm, self.text_inputs, state.instrument, state.as_of)` without `state.anon`.
- `text_analysts.py:134,171` call `self.llm.complete_json` directly, not through `agents/base.py:73,105`, which is where `anon.scrub` lives.
- The prompt itself (`text_analysts.py:126-128`) contains `Company: {symbol}`, the accession number (its first 10 digits are the CIK, which identifies the company), the ISO `accepted=` timestamp, and up to 6,000 characters of raw filing text.
- Even where scrubbing does apply, `anonymize.py:86-104` replaces only the ticker and Yahoo symbol, not company or product names ("Apple Inc.", "iPhone").

Impact: `llm_anonymize: True` gives a false assurance for any text-analyst run. The 3.8 local text-analyst result and the planned R2.2 red-team v2 ("all text analysts") run fully de-anonymised. P2 is not affected today, because `config.py:68` defaults `text_analysts: []`.

Why it was missed: B1 looked at the eval set. Nobody traced the text path.

$0 fix:
- Pass `anon` into `text_reports`.
- Scrub the accession number (or drop it), the dates (rewrite them as D-offsets, as the price path does) and the company name. Take a name list from the EDGAR `entityName` and `formerNames` fields in the submissions JSON, which is already fetched.
- Refuse `text_analysts` together with `llm_anonymize` until the scrub is in place.
- Add a test that no prompt contains a CIK, a ticker or a 4-digit year.

Effort: 1 d.

### N3. HIGH: P2 first pass is not powered for its headline metric, and the fix list makes it worse
Evidence:
- `scripts/llm_study.py:207`: 20 dates, of which 19 periods are usable because the last date drops (`:435`). The periods are about 115 calendar days apart, so `ppy` is about 3.2 (`:424-425`).
- `:389-406`: circular block bootstrap with block 3 over 19 points, which gives about 6 effective blocks; percentile intervals at that size under-cover.
- Rough power: the model portfolio and the control are both long-biased on mega-caps, so assume a correlation of about 0.7. Over 6 years, the SE of the annualised Sharpe difference is about sqrt(2(1-0.7)/6) = 0.32, so the minimum detectable effect at 80% power and 5% two-sided is about 0.9 Sharpe.
- Decision-level IC: 300 decisions, but cross-sectional correlation among the 10 equities makes the effective n about 20 dates x 3 = 60, so the MDE IC is about 0.36. Realistic effects are 0.02 to 0.05.
- R0.3 (score over each decision's own horizon) helps validity, not power.

Why it was missed: the first review flagged the forward record (about 14 years to decide) and the CV gate power (Q2), but not P2's own power.

$0 fix: pre-register now, before rows land, that the first pass is descriptive (contract rates, agreement with rules, fallback bias) and cannot accept or reject edge. For a decisive $0 design:
- Analysts-only cell with the technical analyst only, which is 1 call per decision.
- Daily-to-weekly dates, 5-day horizon, paired against the rule signal on the same state.
- Primary metric: the incremental IC of (model signal minus rule signal) on forward 5-day returns, with a cluster-by-date Newey-West SE.
- Size: at about 60 s per call, 4 days of CPU is about 5,000 decisions. With 15 names x about 330 weekly dates, the effective n is about 1,000 or more, so the MDE IC is about 0.09. Add the second free model (qwen2.5:3b or llama3.2:3b, about 3x faster) to reach about 0.05.
- Write a futility rule: stop when the 90% CI upper bound is below IC 0.03.

This turns P2 from "inconclusive by construction" into an answerable question.

Effort: 1 d design and prereg, plus CPU days.

### N4. HIGH: no `num_ctx`; long prompts can be silently truncated
Evidence:
- `local_llm.py:122` sends only `temperature`, `num_predict` and `seed`. Ollama then applies its default context (2,048 or 4,096 tokens depending on version) and truncates the oldest tokens, which drops the system prompt and the fence instructions first, without raising an error.
- The deep roles (debate history), the planner and the text analysts (6,000 characters per section, several sections) can exceed that limit.
- PLAN.md:161 records planner calls over 300 s. That fits very long prompts, but it was never diagnosed.
- `llm_study.py:265-267` records `in_tok_est`, a character estimate, not `prompt_eval_count`. `local_llm.py:171` books `prompt_eval_count` into usage but never compares it with the estimate, so truncation cannot be detected from the rows.

Why it was missed: the first review checked temperature (A1) but not the other options.

$0 fix:
- Set `num_ctx` explicitly (8192 fits a 7B Q4 in about 6 GB on this laptop) and record it.
- Store `prompt_eval_count` per call.
- Flag a call as `truncated` when `prompt_eval_count < 0.9 x estimate`, or when `done_reason == "length"`, and count both in the contract and fallback share.
- Add a unit test on `build_request`.
- Check one current chain row for `prompt_eval_count` against the estimate before trusting P2.

Effort: 0.5 d.

### N5. HIGH: no per-decision lineage (prompt, weights, runtime, code); resume can mix versions
Evidence:
- `llm_study.py:369-372`: a row stores the reply but not the prompt or system text, `prompt_bundle_hash` (which exists at `prompts.py:162` but is used only by `calibration.py:161`), the git SHA (`provenance.py:66` exists but is unused here), the Ollama version, or the model digest.
- `local_llm.py:62-71,173`: drift is detected only by served name, so a re-pulled `qwen2.5:7b-instruct` tag with new weights passes.
- Resume (`llm_study.py:342-347`) skips keys already in the file and does not check that the code or prompt version matches. The chain runs from a worktree (`run_v16_chain.cmd:2`) for 4-6 days while 8 lanes change code, and its interpreter comes from another checkout's venv (`:5`).

Why it was missed: lineage was listed only as C1 (an eval gate on the prompt hash). Per-decision lineage for model risk was not.

$0 fix:
- On start, write a run header: `git rev-parse HEAD` plus a dirty flag, `prompt_bundle_hash`, the Ollama `/api/version`, `/api/show` (model digest, quantisation, template hash), the options, and `pip freeze` hashes.
- Stamp the header id on every row, and refuse to resume on a mismatch.
- Store a sha256 of each prompt, and the full prompt gzipped in a side file.
- Pin the model by digest: `llm_strict_model` should compare digests, not names.

Effort: 1 d.

### N6. MEDIUM: R0.3 "recompute from stored rows, no re-run" is not feasible as written
Evidence:
- The rows store `close` only at design dates (`llm_study.py:300-312,369`) and do not store `horizon_days`, which lives on the proposal (`state.py:107`).
- Forward closes at each decision's horizon must be re-fetched. Yahoo adjusted closes are re-adjusted after later dividends, so splicing a run-time `close` with a later fetch mixes vintages (B4/R4.1).

Fix:
- Re-fetch the full series once and recompute both ends from that one vintage, ignoring the stored `close`.
- Recover the horizon from the trader reply (model cells) or recompute it with the rules (rule cells).
- Add `horizon_days` and `entry_bar_date` to the row schema now, so the local_all cell, which has not started, records them.

Effort: 0.5 d.

### N7. MEDIUM: conformal sizing assumes exchangeability that overlapping h-step residuals break; regime mismatch
Evidence:
- `combine.py:310-315`: the calibration residuals are consecutive h-bar forward returns. Neighbours overlap by h-1 bars, and volatility clusters, so split-conformal coverage is not guaranteed.
- The weights may be regime-restricted (`:294`, `rows`), but the calibration residuals span all regimes.
- `tests/test_v14_combine.py:207` tests coverage on iid draws only.

Fix:
- Use non-overlapping residuals (stride h), or adaptive conformal inference (Gibbs and Candès 2021), which is a few lines of code.
- Scale residuals by `vol` (normalised conformal).
- Restrict calibration to the same regime mask.
- Report empirical coverage on real walk-forward data in the evaluation doc.

Effort: 1 d.

### N8. MEDIUM: "nothing leaves the host" is not enforced
Evidence: `config.py:15` sets `local_llm_url` with no loopback check in `local_llm.py:80-95`, and `config.py:61` defaults `llm_anonymize: False`. A typo or a shared config sends full, de-anonymised prompts to any host. The docstring claim at `local_llm.py:4` is unenforced.

Fix: refuse non-loopback URLs unless `allow_remote_llm: true` is set, and log the resolved host in the run header (N5).

Effort: 0.2 d.

### N9. MEDIUM: the recall and calibration designs share the design-period dates, which all fall inside the model's training data, and there is no out-of-training control
Evidence: `v16_local_study.py:24,34` and `llm_study.py:73` cover 2016-2021. qwen2.5's corpus extends well past that, so every study date is in-training.

Fix: add a post-cutoff slice (2025-07 to 2026-10, free Yahoo data) as a contamination control. A model edge that disappears after the cutoff is memory, not reasoning. This is the cheapest decisive leakage test available at $0. Run it on the analysts-only cell from N3.

Effort: 0.5 d plus CPU.

### N10. LOW-MEDIUM: model-risk documentation is missing (SR 11-7 style)
There is no model inventory entry, model card or dataset card for qwen2.5:7b Q4, TF-IDF/BM25, MiniLM, the HMM regime model, combine/conformal, or the judge. There are no documented intended uses, limits, validation evidence, monitoring thresholds or owner. `docs/evaluation/live_readiness.md` covers the desk, not the models.

Fix: one `docs/models/INVENTORY.md` table plus a 1-page card per model, generated partly from the run header (N5). Include the ongoing monitoring metrics already planned (C4).

Effort: 1 d.

### N11. LOW: the shipped development API keys work on loopback, and the config is written to a temp file
Evidence: `config.py:317` ships the keys, and `api.py:286-312` blocks them only off loopback. `api.py:398-401` writes the full config, including keys, to `%TEMP%`. On a shared laptop, any local process can call the analyst and approver roles.

Fix: generate random keys on first serve when only the development keys are configured, and pass the config by environment or pipe, not by file.

Effort: 0.3 d.

---

## Planned fixes that are inadequate

| Plan item | Problem | Change |
|---|---|---|
| R1.4 recall audit as a precondition | The instrument is degenerate (N1) | Gate on the N1 v2 audit (shuffled candidates, placebo, behavioural leak) |
| R0.2 eval re-frozen through the anonymiser | The anonymiser misses names, CIKs and dates on the text path (N2) | Fix N2 first |
| R0.3 recompute from stored rows | Horizon and forward closes are not stored, and the vintages differ (N6) | Re-fetch one vintage; extend the row schema |
| R2.2 red-team "all text analysts" | Runs de-anonymised (N2) and possibly truncated (N4) | Do after N2 and N4 |
| R3.3 eval gate tied to the prompt hash | No per-row lineage to tie to (N5) | Add the N5 header first |
| P2 "first pass" framing | Unpowered (N3) | Pre-register it as descriptive; add the N3 decisive design |

## Prioritised list ($0)

1. N1: kill the recall step, fix and re-run the audit (1.5 d).
2. N4: `num_ctx`, `prompt_eval_count` and a truncation flag. Check the chain rows today (0.5 d).
3. N5: run header, digest pin and resume guard, before local_all starts (1 d).
4. N3: pre-register the first pass as descriptive, plus the powered analysts-only incremental-IC design (1 d).
5. N9: post-cutoff contamination slice, folded into the N3 design (0.5 d).
6. N2: anonymise the text path, with a refusal until done (1 d).
7. N6: row schema plus single-vintage recompute (0.5 d).
8. N7: conformal on non-overlapping or adaptive residuals, with real-data coverage (1 d).
9. N8: loopback enforcement (0.2 d).
10. N10: model inventory and cards (1 d).
11. N11: random API keys, no temp-file config (0.3 d).

Total about 8.5 solo days plus CPU time. Items 1-4 should land before any P2 number is quoted.


## Appendix D. Second review: quant, code and ops

# AgenticTrader second quant/dev review (2026-11-09, feat/v0.16-round2, read only)

Scope: non-LLM. Only findings not in docs/review/2026-11-09_review_and_plan.md, or where its fix is wrong/inadequate. Every item checked in code; no tests run (targeted reads only). Effort = solo days, $0.

## N1 HIGH: the "frozen" forward books are not frozen; every merge to main changes the strategy being forward-tested
Evidence: `.github/workflows/paper.yml:40-42` checks out `ref: main`, installs `-e .` (`:49-51`) and runs `scripts/paper_trade_v09.py`, which recomputes the whole record freeze->as_of with the *current* code and current `cfg` (`paper_trade_v09.py:78-88, 216-218`). `merge_append_only` (`:225`) keeps old rows, so each new row is produced by whatever code is on main that day. Only `provenance()` is logged (`:248`); nothing refuses a code change. v0.17 R1.1 (exec_lag), R0.4 (schema reject), R2.1 (critic on target_weight), R4.4 (OMS limits) will all silently change the forward books mid-record.
Why missed: first review treated revisions as a data-vintage problem only (B4/B5, R4.1/R4.2); the code-vintage half is bigger.
Fix: tag the freeze commit (e.g. `paper-freeze-v09`); paper job checks out that tag for the computation (main only for the ledger commit); store a hash of the frozen config + engine source in the ledger header and fail if it differs; any intended change = new book with a new freeze date. Also: the stitched ledger mixes rows computed on different Yahoo vintages; add a `vintage_id` column per row. Effort 0.75.

## N2 HIGH (plan fix inadequate): R4.1 "store raw bars per session" in a public repo redistributes Yahoo data
Evidence: plan R4.1 and Appendix B B4 propose committing raw bars under `results/paper/bars/`. Yahoo's terms forbid redistribution; no data-licence statement exists (grep of README/docs finds none). FRED series also carry per-series source licences; EDGAR is public domain.
Fix: store raw bars as a GitHub Actions artifact (90-day retention) or in a git-ignored local store plus a published SHA-256 per file; publish only derived returns (already done). Add `docs/DATA_LICENSING.md` (Yahoo: personal/research, no redistribution; FRED: check per series; EDGAR: public, SEC fair-access UA). Effort 0.5.

## N3 MED: unpinned dependencies inside the job that holds `contents: write`
Evidence: `paper.yml:78` and `:107` run `pip install numpy pandas` (no version, no hash) in the commit job with `permissions: contents: write` (`:68-69`), which then pushes straight to main with `[skip ci]` (`:89-90`). A compromised or simply new pandas release runs with a write token, and the `[skip ci]` commit lands on main with no required check (or requires a ruleset bypass that is not documented).
Why missed: first review checked SHA-pinned actions and the 3.12 lockfile, not this job. R4.5 hashes the lockfile but does not touch these lines.
Fix: install from `requirements-lock.txt --require-hashes` (or need no pandas at all: make `paper_ops.py commit` stdlib-only); document the bot's ruleset bypass or push to a `paper-record` branch. Effort 0.3.

## N4 MED: cross-sectional IC pools asset classes after standardising within them
Evidence: `xalpha.py:205-207` z-scores within `groups` (default asset class), but `cross_sectional_ic` (`:116-127`) and `quantile_spread` (`:149-172`) rank all columns together. With equities + FX in one call (reachable via `agentic/servers.py:240-252`), IC partly measures "equities beat FX this period", with FX forward returns at ~1/3 the vol. The analyst path filters to one class (`agents/analysts.py:606`), so research tables and the traded signal measure different things.
Fix: compute IC and spreads per group and average (or require one group); test with a two-group panel whose within-group IC is 0 but between-group mean differs. Effort 0.5.

## N5 MED: no risk neutralisation in the cross-section; "alphas" on 10 mega-caps are beta/vol bets
Evidence: `cs_zscore` (`xalpha.py:70-94`) only demeans within asset class. low_vol, tsmom, high_52w on 10 large caps load on market beta and size; no beta/sector regression residualisation anywhere in xalpha.py. With top/bottom 20% of ~10 names = 2 names a side (`:166`), spread t is driven by 2-4 stocks. First review's B8 notes survivorship but not exposure or breadth.
Fix: optional `neutralise=("beta",)`: residualise scores on trailing 252d beta to SPY each date (numpy lstsq); report IC raw and neutral; print breadth and names-per-leg in every table, and state the fundamental-law ceiling (IR ~ IC*sqrt(breadth)). Effort 1.

## N6 MED: in-sample selection rows sit in the same table as honest ones
Evidence: `xalpha.py:225-230` gates on full-sample IC and then scores the gated combination on the same sample; `XAlphaReport.best()` (`:183-185`) ranks by in-sample IC. The comment says "full-sample diagnostic", but the table carries no flag and the row is formatted like the others.
Fix: either compute the gate walk-forward (reuse `combine.trailing_ics`, which already respects `i+h<=end`) or mark the row `in_sample=True` and exclude it from `best()`. Effort 0.5.

## N7 MED (plan R1.3 incomplete): BH over gates ignores that the 9 alphas x horizons are strongly dependent
Evidence: decay table computes the same signal at horizons (1,5,10,21,42) (`xalpha.py:189, 218-219`); overlapping horizons on one signal are positively dependent, which BH tolerates (PRDS) but the ~5-fold t (Appendix B B1) gives near-discrete p-values. More important: the gate threshold `min_tstat=2.0` (`xalpha.py:245`) is a fixed t, not the t_crit for 4 df (2.776) used elsewhere (`passes_gate`, which reads t_crit). Check which applies: two bars coexist.
Fix: one gate function; BH on Newey-West p-values (after R1.2), not on fold-t p-values; state horizons as one family per signal, signals as the family for BH. Effort 0.3.

## N8 LOW-MED: DSR trial count vs dependence
Evidence: `evaluation.py:112+` registers 62-65 trials, mostly one-rule ablations of the same v0.2 control; `stats.deflated_sharpe` (`stats.py:104-111`) uses raw N and the dispersion of trial Sharpes. Highly correlated trials shrink `var_trials_sr` and so under-deflate even as N looks large. First review (B3) only argued N is a floor.
Fix: report effective N from the trial-return correlation matrix (eigenvalue count or clustering, Lopez de Prado 2019), show DSR at N_eff and at N + pre-registry DoF. Effort 0.5.

## N9 LOW: Monday/holiday behaviour of "New York yesterday"
Evidence: cron Mon-Fri (`paper.yml:22`); as-of default is NY yesterday (`paper_trade_v09.py:186,198`). Monday's run asks for Sunday, Tuesday after a holiday asks for the holiday; the script then relies on the SPY calendar (`:212`) to find the last session. Friday's session is first recorded Monday (3 days of Yahoo re-adjustment before first write). Not a bug, but the freshness check (`paper_ops.py freshness`) must allow a 3-day gap; verify it does and add a test for Mon and post-holiday dates. Effort 0.2.

## N10 LOW: stale-but-plausible statements to check in docs site
- `docs/evaluation/evaluation.md:2688` "62 to 65" registered trials: the count depends on version; render from `len(TRIALS)`.
- Coverage/quant docs should state the cross-section breadth (10 equities) wherever ICs are quoted.
Effort 0.3.

## Things the first review got right and I confirm
Same-bar execution, low-power fold t, two VaR defaults, calendar gaps. The disputed cron item: the maintainer is right that the script records yesterday, so 21:30 is fine.

## Prioritised list
1. N1 freeze the paper code/config by tag + hash check (0.75 d) - before R1/R2 land on main, or the forward record is contaminated.
2. N2 replace "commit raw Yahoo bars" with artifacts/hashes + licensing doc (0.5 d).
3. N3 hashed install / stdlib-only commit job; document bot bypass (0.3 d).
4. N4 per-group IC (0.5 d).
5. N6 walk-forward or flagged gated row (0.5 d).
6. N5 beta-neutral scores + breadth disclosure (1 d).
7. N7 single gate threshold, BH on NW p (0.3 d).
8. N8 effective-N DSR (0.5 d).
9. N9 calendar edge tests (0.2 d). 10. N10 docs (0.3 d).
Total ~4.9 solo days, $0.

Not covered (time): C++/Python numeric parity across BLAS, mutation testing, docs-site build, OMS idempotency/state recovery.
