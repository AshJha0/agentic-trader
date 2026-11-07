> **Superseded 2026-11-07 by [PLAN.md](PLAN.md), the single living plan. Kept as the record of how the plan was reached.**

# AgenticTrader: in-depth review and improvement plan (2026-11-07)

Reviewer stance: the bar is a tier-1 systematic desk, HFT firm or bank quant group deciding
whether this could ever run money, and whether its AI/agentic layer is anything more than a
veneer. Read against `main` at `2a0c6da` (v0.12.0 + paper-record PRs #17/#18), the published
site, the forward paper record (30 sessions) and the prior review digests. Everything here is
verified against the code unless marked *(not re-measured)*.

## 0. Verdict in five lines

1. **As engineering and as science it is unusually honest and well above the open-source
   norm**: pre-registration, a trials registry (62), deflated Sharpe, BH correction, cluster
   bootstraps, append-only forward ledger, provenance stamps, retracted claims, 879 tests on
   two backends, a real threat model. Very few public "AI trading" repos do any of this.
2. **As a trading product it has no edge and the project itself proves it.** Four research
   rounds (v0.9–v0.12), 62 registered trials, and the desk never beats a one-line control
   (buy-and-hold scaled to 15% vol). Attribution: beta 0.9, R² 0.89 to the control, tilt
   Sharpe −0.17 / −0.61. The 30-session forward record is −1.11% vs −1.09% for the control.
3. **The "agentic / LLM / AI" layer is almost entirely untested as a source of value.** Every
   published number is the rules. The one LLM run (v0.5.1, $4, 5 stocks, one quarter) was
   on a superseded engine. The harness, planner, critic, RAG, MCP and policy engine are
   governance plumbing around a decision whose information content is ~zero.
4. **The alpha problem is structural, not a tuning problem.** The signal set (SMA/MACD/RSI/
   Bollinger/KDJ on daily single-name bars, a lexicon over a few headlines, four-quarter
   EDGAR ratios) is textbook retail technical analysis. No hedge fund expects it to carry
   information after costs on 15 liquid names; the project's own IC tables confirm it.
5. **Therefore the plan is not "more rules".** It is: (a) stop spending research effort on
   the single-name desk; (b) decide what the project *is* (an agentic-governance reference
   implementation with a measured LLM study, or an attempt at a real multi-asset systematic
   book); (c) run the one experiment the project exists for and has never run (the LLM desk,
   properly); (d) rebuild the alpha pipeline the way a desk would (breadth, cross-section,
   point-in-time features, combination by fitted IC) if, and only if, (b) chooses "book".

## 1. Business and positioning

**What it is today.** A research/education framework with a public negative result. The
README says so in paragraph one. The documentation site is the strongest asset: `ai.md`,
`quant.md`, LEARN (50), COOKBOOK (100), DIAGRAMS (38), threat model (40 threats).

**Brutal points**

- B1. *There is no customer and no monetisable claim.* It is not investment advice, has no
  broker, no live orders, no edge. The two credible "products" are (i) a reference
  implementation for agentic governance in finance (policy-gated tools, evidence, audited
  reports, MCP) and (ii) a portfolio/credibility piece for the owner. Neither is stated as
  the goal; the README leads with "agentic trading desk", which sets a bar the results fail.
- B2. *The headline results are negative and will remain so* under the current design. A
  hiring manager at a systematic fund will read "below buy & hold, no edge over vol-target,
  four rounds, nothing adopted" and conclude the signal design was wrong from the start,
  not that the researcher was careful. The honesty is a strength; the absence of a
  positive, defensible contribution is the weakness.
- B3. *The forward record cannot decide anything for 14 years* (3,600 sessions by the
  owner's own pre-registration). That is a correct calculation and a strategically useless
  test. A desk would never run a 15-name daily book to a 14-year decision.
- B4. *Operational fragility of the record*: the paper job died for a week (missing Python),
  10 sessions were back-filled from later data, and `revisions.csv` holds 1,232 data-vintage
  differences from Yahoo. A public "append-only ledger" that depends on one laptop and a free
  revisable feed is not an audit trail a bank would accept.

**What to do (business)**

- Re-position. Choose explicitly, in the README's first paragraph, between:
  **A. "A reference architecture for governed LLM agents in trading, with a measured study of
  what the model adds"** (the realistic, differentiating option), or
  **B. "A systematic multi-asset research platform with a forward record"** (requires the
  alpha rebuild in §5 and 2–3 years before it says anything).
  My recommendation: **A, with the §5 rebuild run as a research programme under A's
  governance**, so the positive contribution is the *method and the measured LLM result*,
  not a Sharpe.
- Freeze the single-name technical desk as "the incumbent/control" and stop publishing new
  variants of it. Every further trial on it is a negative result the registry already predicts.

## 2. AI / LLM layer

Code read: `llm.py`, `agents/base.py` (via prompts.py), `agents/analysts.py`, `trader.py`,
`risk.py`, `researchers.py`, `anonymize.py` (via docs), `calibration.py`, `prompts.py`.

**What is good (and genuinely rare)**

- Model may interpret, code decides: rules always computed, JSON contract enforced, reply
  rejected as a whole on failure, values clipped, protective levels sanity-checked
  (`sane_levels`), firm limits after the model. This is the correct architecture.
- `<untrusted_data>` fence travelling with derived documents; anonymisation (ticker alias,
  relative dates, rebased prices, scale-free allow-list) against training-set recall.
- Budget admission in `hard` mode including retries; prompt bundle hash; calibration harness
  (dispersion, anchoring, drift). `MODEL_CAPABILITIES`/`request_shape` per family.

**Brutal points**

- L1. **The LLM has never been evaluated.** One $4 run, 271 calls, five mega-caps, Q1 2024,
  one debate round, engine since corrected. Everything the project says about "the LLM
  desk" rests on that. The multi-year harness exists and is unexecuted. For a project whose
  name is *Agentic*Trader this is the single largest gap.
- L2. **The LLM is asked the wrong question.** Analysts receive the same 20 indicator
  values the rules use and are asked for a signal in [−1, 1]. There is no information in
  the prompt the rules do not already use (by design, to be auditable), so the best the
  model can do is re-weight the rules. The v0.5.1 result (same Sharpe, half the exposure,
  "sized down citing abstaining analysts") is exactly that: a conservative re-weighting.
  A model adds value only where it has information or judgement the rules lack: *text*
  (filings, transcripts, news), *cross-sectional context*, *regime labelling*,
  *hypothesis generation*. Only the news/sentiment analysts give it text, and that text is
  (i) absent in backtests older than 30 days (`NEWS_HORIZON_DAYS`: Yahoo news is
  current-only, so historical news = EDGAR filing titles), (ii) scored by a bag-of-words
  lexicon, (iii) weighted 0.7/0.5 in the consensus. So in every historical run the "news"
  and "sentiment" the LLM would reason over is either filing boilerplate or nothing.
- L3. **The debate is theatre in offline mode and unmeasured in LLM mode.** Rules-mode
  bull/bear "arguments" are templated strings; the facilitator's verdict is a weighted
  mean (`consensus_score`) with fixed role weights 1.0/1.0/1.0/0.7/0.5 chosen by hand and
  never fitted or ablated as weights. Two debate rounds, three risk stances blended
  25/50/25: all hand-set, none measured for marginal value (ablation of the debate stage
  itself — plan: analysts → trader directly — is not in the trials registry).
- L4. **No anonymisation leak audit.** The threat model lists what leaks (distinctive
  statistics, names inside headlines) but there is no test that *measures* recall: e.g.
  ask the model to name the ticker/date from an anonymised prompt over N samples and
  report the hit rate. Without it the anonymised backtest's validity is asserted.
- L5. **Default tiers are stale/odd**: `deep_think_llm: claude-opus-5` at effort `high`
  for *every* deep role, `quick: claude-haiku-4-5`. Opus 5.5 and Sonnet 5.5 exist, are
  cheaper per token (Opus 5.5 is $4/$20 vs $5/$25 in the project's own table) and the
  reasoning roles do not need `high` effort for a 16k-token JSON. No cost/quality tier study
  exists; the harness supports it (staged, dollar-capped) but was never run.
- L6. **No structured outputs / tool-use API.** Replies are parsed with `extract_json` from
  free text, then contract-checked. The Messages API supports forced tool use with a JSON
  schema, which removes the parse failure mode and lets the rejection rate be ~0 instead of
  a measured-then-fallback path. Prompt caching is priced in the table (0.1x) but the fixed
  `FIRM_CONTEXT` + role preamble is not marked as a cache breakpoint (verify in
  `AnthropicLLM`; *not confirmed in this read*).
- L7. **Calibration harness unexecuted on the real model.** Dispersion/anchoring/drift are
  exactly what a model-risk committee asks for; there is no published number.

**Fixes (AI/LLM)**

- A1. **Run the LLM study (the project's defining experiment), staged and capped:**
  Stage 0: anonymisation recall audit (200 prompts, Haiku + Opus 5.5, report hit rate).
  Stage 1: tier × role grid on the design period, 15 core names, every 5 bars, 3 seeds:
  {rules} vs {Haiku analysts + Sonnet 5.5 deep} vs {Haiku + Opus 5.5} vs {all Sonnet 5.5};
  record agent_sources, rejection rate, cost, dispersion. Budget cap ~$150–300 (owner
  launches; see memory on spend). Success metric: desk − vol-target control, block bootstrap,
  on design; then one pre-registered holdout look.
  Stage 2: ablations — no debate; debate 1 round; risk team single neutral analyst; LLM only
  on text roles. Register every cell in `TRIALS`.
- A2. **Give the model information the rules do not have**: full EDGAR filing sections
  (MD&A, risk factors, point-in-time by acceptance time — the plumbing exists), earnings-call
  transcripts if a free point-in-time source is found, FOMC statements/minutes for FX macro.
  The analyst's task becomes *extraction + judgement over text*, which is what LLMs are for,
  and the rules keep the numeric side. Measure as A1 cells.
- A3. Replace free-text JSON with forced tool-use schemas; add cache breakpoints on the
  fixed prefix; retire `claude-opus-5` defaults in favour of `claude-sonnet-5-5` (quick+deep
  default) and `claude-opus-5-5` (deep, optional); keep `MODEL_CAPABILITIES` current.
- A4. Publish the calibration numbers (dispersion, anchoring slope, drift) from Stage 1.

## 3. Agentic layer (harness, planner, policy, critic, RAG, MCP)

Code read: `agentic/harness.py`, `planner.py`, `critic.py`, `servers.py`, `rag.py`, `policy.py`
(docs), `tools.py` (docs).

**Good**: explicit state machine with lease/heartbeat and single-driver lock; plan
validation that pins symbol/as_of, clips universe and data budget; governance steps always
appended; evidence SHA-256 per call; single-use plans; approval gateway for state-changing
tools; critic can only lower confidence; number and evidence-id audits of the report.

**Brutal points**

- G1. **Governance with nothing to govern.** The policy engine, evidence store and critic
  are correct but the decisions they wrap carry no information; the critic's seven checks
  (divergence from rules, limits, level sanity, verdict consistency) are consistency checks,
  not quality checks. Nothing in the layer measures whether a run's *conclusion* was right.
- G2. **RAG is a hashed TF-IDF over a handful of in-repo runbooks**, returning 3 passages the
  trader/PM quote as "policy". It is honest ("no embedding model") but it is not RAG in the
  sense a desk means (retrieval over filings, research, transcripts with citations). It
  retrieves firm policy, not market information. Its contribution to any decision is
  unmeasured and almost certainly nil.
- G3. **The model-proposed plan path is unexercised.** `make_plan` accepts an LLM plan,
  validates it, falls back to canonical. There is no measurement of how often a model plan
  survives validation, what it adds, or how much `max_plan_lookback_bars` protects against.
- G4. **No red-team evidence for the prompt-injection fence.** Threat model says the fence
  "cannot be escaped"; tests check structure, not a model's behaviour under adversarial
  headlines. A bank's model-risk team would want an injection corpus run against the live
  model with the refusal/compliance rate reported.
- G5. **MCP server exposes `execution.submit_order`** (ticketed, approval-gated, simulate
  only). Fine, but the approval queue is in-process/persisted locally; there is no
  identity on the approver, no two-person rule, no immutable external log. For "the way an
  enterprise system would" this is a gap worth naming in the threat model's status column.

**Fixes (agentic)**

- B1'. Add *outcome-aware* governance: after each decision's horizon, join the memory's
  realised P&L to the run record; report per-role hit rates and critic-flag → outcome
  correlation. The critic then has a measured false-positive rate.
- B2'. Make RAG about markets: index point-in-time EDGAR sections (already fetched) and
  macro releases, chunk by section, return citations with accession number + visible date;
  keep the hashed TF-IDF as the default and allow an optional embedding backend behind the
  same `KnowledgeBase` interface. Measure A2 through it.
- B3'. Injection red-team: 100 adversarial headlines (instruction-bearing, role-play, encoded)
  through the news analyst on the live model; publish compliance rate; make it a CI job
  gated on a key being present.
- B4'. Approver identity + signed approval records; document the two-person rule as a
  configuration; mark G5 in the threat model.

## 4. Quant research, alpha and signal

Code read: `alpha.py`, `xalpha.py`, `analysts.py` rules, `trader.py`, `risk.py`,
`portfolio.py`, `stats.py`, `backtest.py` header, `evaluation.py` trials, v09/v12 docs.

**Good**: IC with overlap-aware t, decay, tercile spread vs base rate, Fama-MacBeth per-date
IC for cross-section, Ledoit-Wolf shrinkage, risk parity/min-var/mean-var, block bootstrap,
BH, DSR/PSR/min track record, Kupiec/Christoffersen VaR tests, realistic controls (vol-target
B&H, TSMOM L/S, carry) costed identically. The statistics are better than most sell-side
research.

**Brutal points**

- Q1. **The alpha library is nine daily technical indicators** (`ALPHAS`): tsmom, 20d mom,
  5d reversal, 52w high, Donchian, MACD/ATR, RSI, low-vol, carry. On 10 mega-cap equities
  and 5 G10 pairs. Every one is public since the 1990s, crowded, and on this universe has
  IC ≈ 0 after costs — which the repo's own alpha tables show. There is no fundamental
  alpha (value, quality, accruals, revisions), no event alpha (earnings surprise, PEAD,
  filing tone change), no flow/positioning (CFTC COT for FX), no macro factor (rates
  surprises, term-structure for carry), no volatility-surface signal, no cross-asset lead-lag.
- Q2. **Breadth is 15.** Cross-sectional work (`xalpha`) over 10 stocks or 5 pairs is noise;
  the v0.6 result (−0.01) is the expected outcome. A desk tests cross-sectional signals on
  hundreds to thousands of names. Equities need a point-in-time universe (e.g. a
  survivorship-free S&P 500 constituent history) — Yahoo cannot supply it; the project has
  (correctly, per owner decision) refused paid data, which caps what can be learnt.
- Q3. **Signal combination is hand-weighted** (role weights, 25/50/25 risk blend, 2× tilt,
  0.30/0.20/0.15 technical contributions). No signal is weighted by its fitted IC, no
  shrinkage toward zero, no regime conditioning, no turnover penalty in the combination.
  `combine()` is an equal-weight mean. This is the opposite of how any quant desk combines.
- Q4. **Horizon mismatch**: analysts forecast "1–4 weeks", rebalance is every 5 bars, stops
  are ATR-based intraday-style levels, tsmom is 12-month. The signal, holding period and
  exit logic are not derived from one measured decay curve.
- Q5. **The rules desk is a worse vol-target control** (beta 0.9, R² 0.89): the only
  things that moved Sharpe in four rounds were vol scaling and diversification. The project
  knows this (attribution_v09). Continuing to A/B single-name rule switches is spending
  trials on a dead design and lowering the deflated Sharpe of anything found later.
- Q6. **Data is Yahoo**: revisable (1,232 logged revisions in six weeks), dividend-adjusted
  totals, no delistings, 30-day news horizon, survivorship built in to any universe chosen
  today. Fine for education; disqualifying for a claim of edge. FRED/EDGAR are the good
  parts and under-used.
- Q7. **Cost model is linear bps + optional square-root impact with coefficient 1.0** on
  dollar ADV; borrow 1%/yr flat; FX spread not by pair/time; no funding/financing on
  leverage; no slippage model for stop fills (stop executed at the stop level?). *(not
  re-verified in C++ this read)*. For 15 liquid names at ≤$10M this is immaterial; at scale
  the impact sweep already shows SMA/MACD die, which is realistic.
- Q8. **Risk**: per-instrument 250-day historical VaR rejects Kupiec on 2/15 and
  independence on 6/15 (breaches cluster) — i.e. the risk model is mis-specified and the
  project reports it and leaves it. Book-level VaR is off by default and "untested in any
  published run". No stress tests, no factor exposure (market/size/momentum/rates/USD) on
  the book, no drawdown-control rule evaluated beyond vol targeting.

**Fixes (quant) — only if positioning B is chosen, otherwise as a bounded research track**

- R1. **Stop the single-name desk research.** Freeze it as control #3 in every table.
- R2. **Build a point-in-time, survivorship-aware equity panel from free sources**: EDGAR
  company facts (already ingested) + Yahoo prices for the *current and historical* members
  of a broad index reconstructed from EDGAR/Wikipedia filing histories (document the
  residual bias honestly), target 300–500 names from 2010. Without breadth nothing in R3
  can be tested. If this is impossible free of charge, say so and stay with positioning A.
- R3. **Add alpha families with actual priors** (each a registered trial, each with IC/decay/
  turnover on design only): PEAD/earnings surprise (EDGAR 10-Q vs prior), accruals and
  asset-growth (EDGAR facts), 12-1 cross-sectional momentum on the broad panel, idiosyncratic
  vol/low-beta, filing tone change (LLM-extracted, A2), FX: COT positioning, rate-surprise
  and term-structure carry, 1-month vs 12-month trend blend; macro ETFs: TSMOM across 20+
  futures-proxy ETFs with vol scaling (the v0.12 result on 11 ETFs is underpowered).
- R4. **Combine by fitted IC with shrinkage** (rolling IC-weighted, Grinold–Kahn style with
  a turnover penalty), expected returns = IC × vol × z-score; portfolio via the existing
  mean-variance with the shrunk covariance; no hand weights left in the path. Register the
  fitting window as the one free parameter.
- R5. **Derive horizon from decay**: holding period and rebalance cadence from the measured
  IC half-life per family; stops only where the decay study shows a convex payoff.
- R6. **Risk model upgrade**: EWMA/filtered historical simulation VaR (fix Kupiec/
  independence), book VaR on by default in multi-sleeve runs, factor exposure report
  (market, rates, USD, momentum) per book, three stress scenarios (2008, 2020, 2022) as
  standard table rows.
- R7. **Data integrity**: snapshot raw downloads with content hashes per session (the paper
  job should store its own price vintage, so revisions become diffs against a stored file,
  not against Yahoo tomorrow); publish the vintage hash in `runs.jsonl`.

## 5. Software, quant-dev and operations

**Good**: C++17 core with pybind11 and a numpy twin cross-checked and fuzzed on both; CI on
five Pythons plus a locked job; coverage uploaded; append-only logs with file locks;
MCP/HTTP interfaces; prompt hashes; 879 tests.

**Brutal points**

- S1. The paper job runs on one Windows laptop via `schtasks`, broke silently for a week,
  back-filled, and now auto-commits to `main` `[skip ci]`. No alert on failure, no
  heartbeat check in CI, no second machine, one person's credentials. A bank calls this a
  key-person and availability finding.
- S2. The numpy suite takes ~33 minutes; `test_interrupted_sweep_spares_a_live_siblings_runs`
  is known-flaky (timing window). Known-flaky tests erode the "879 green" claim.
- S3. `results/` is mostly git-ignored; the measurement record lives on one disk (stamped,
  but un-replicated). `docs/results/*` copies tables, not the per-instrument CSVs.
- S4. No type-checking gate (mypy/pyright) or lint in CI; no SBOM/pinned actions by SHA
  (actions pinned by major tag); secrets handled by `.env` (fine) but `set_api_key.ps1`
  exists in `scripts/` — check it never echoes.
- S5. `MODEL_CAPABILITIES`/`PRICES_PER_MTOK` are hand-maintained tables that will drift;
  there is no test that the configured default model is in both tables and currently served.

**Fixes (ops)**

- O1. Paper job: a GitHub Actions scheduled workflow (free) as the primary runner with the
  laptop as a fallback, both writing the same append-only ledger with vintage hashes; a
  CI check that fails if the last session is older than 2 business days; failure → GitHub
  issue auto-opened.
- O2. Quarantine or fix the flaky test; split the suite (fast PR gate < 10 min; full nightly).
- O3. Commit per-instrument CSVs for every published table under `docs/results/` (small).
- O4. Add `ruff` + `mypy --strict` on `agentic_trader/` to CI; pin actions by SHA; add a test
  that default model ids resolve in both tables.

## 6. Prioritised plan

Each item names its owner decision (OD) where one is needed; estimates are wall-clock days of
solo work at the owner's stated cadence (no agent fan-out); spend is only where the owner
launches an LLM run.

| # | Item | Why first | Effort | Spend |
|---|---|---|---|---|
| P0 | **OD-1: positioning A or B** (§1). Rewrite README/landing first paragraph accordingly; freeze the single-name desk as a control. | Everything below depends on it | 0.5 d | 0 |
| P1 | **LLM study Stage 0–1** (A1): anonymisation recall audit, tier × role grid on design, 3 seeds, calibration numbers, every cell a trial; pre-registered holdout look. | The project's defining experiment has never been run | 3 d + run time | **OD-2: ~$150–300** |
| P2 | **Text-information analysts** (A2, B2'): EDGAR sections into RAG with citations; analyst becomes extraction+judgement; measured as P1 cells. | Only place an LLM can add information | 4 d | within OD-2 |
| P3 | **Structured outputs, caching, model defaults** (A3) + model-table test (O4). | Removes a failure mode, cuts cost 30–60% before P1 | 1 d | 0 |
| P4 | **Injection red-team + outcome-aware governance** (B1', B3', B4'). | Turns the governance layer from asserted to measured | 2 d | ~$20 |
| P5 | **Ops hardening** (O1–O3): Actions runner for the paper job, vintage hashes (R7), freshness check, flaky test, suite split. | The record is the only forward evidence; it must not break again | 2 d | 0 |
| P6 | **Risk model** (R6): FHS VaR, book VaR default-on, factor exposures, stress rows. | The one measured defect the desk still carries (Kupiec/independence) | 2 d | 0 |
| P7 | **If OD-1 = B: breadth** (R2) then **alpha families** (R3) then **IC-weighted combination** (R4, R5). | The only route to an edge that is not a re-run of a known null | 10–15 d | 0 (free data only; **OD-3** if any paid feed is ever reconsidered — owner has declined) |
| P8 | Docs pass per standing instruction after each phase; CHANGELOG; trials registry; one batch PR per round. | Standing owner rules | 0.5 d/phase | 0 |

Suggested order: P0 → P3 → P1 → P5 → P4 → P2 → P6 → (P7) → P8 each round. P1 before P2 so the
"model re-weights rules" baseline is measured before text is added.

## 7. What I would not do

- Any further switch, weight or threshold variant on the single-name technical desk.
- Any claim of edge from the forward record before the pre-registered look, or shortening
  that look without a new pre-registration.
- Fine-tuning or training a model on the price history (the project's "no ML fitted"
  stance is defensible given 15 names; it stops being defensible only after R2).
- Paid data sign-ups (owner decision stands; see memory).

## 8. Owner decisions needed

- **OD-1** Positioning: A (governed-agents reference + measured LLM study) or B (systematic
  book). Recommendation: A, with P7 as an optional research programme.
- **OD-2** Approve the LLM study budget (~$150–300 across stages, hard-capped per stage, owner
  launches).
- **OD-3** Confirm free-data-only remains the constraint (it limits P7's reach; nothing in
  P1–P6 needs paid data).
