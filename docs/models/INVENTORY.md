# Model and dataset inventory

This is the list of every model the desk can run and every dataset it reads, with a card for
each. It follows the shape of a bank's model inventory (US Federal Reserve SR 11-7, "Guidance
on Model Risk Management", 2011): what the model is for, what goes in, what evidence says it
works, where it breaks, how it is watched, and whether it is in use.

The plain idea: before anyone trusts a number the desk produces, they should be able to find,
in one place, which model produced it and how much that model has been tested. A model with
no card is a model nobody has reviewed.

Every evidence statement on a card carries one of the classes used in
[what_the_model_adds.md](../evaluation/what_the_model_adds.md):

- **real-local**: measured on real inputs with the local model (qwen2.5:7b, 4-bit, CPU).
- **real-rules**: measured on real data, no model involved.
- **fixture**: measured on invented or synthetic data; tests the machinery, not the model.
- **pending**: built, not yet measured.

"Status" means: **default** (on in the shipped config), **research** (available behind a
config switch, not adopted), **planned** (not built or not run), **retired**.

Owner for every row is the repository maintainer; there is no second line of review yet
(the review of 2026-11-09, section 5.1 N10, records that gap).

## Models

| Model | Kind | Card | Status | Strongest evidence (class) |
|---|---|---|---|---|
| Rule-based analysts (technical, fundamentals, macro, news, sentiment, alpha, cross-sectional alpha) | hand-set rules | [rules_analysts.md](rules_analysts.md) | default | design and holdout Sharpe tables, `docs/evaluation/evaluation.md` (real-rules) |
| LLM roles (analysts, bull/bear, facilitator, trader, risk, PM, planner, text analysts, judge) | prompted LLM | [llm_roles.md](llm_roles.md) | research | planner survival 89.3%, red-team 21/150 (real-local) |
| qwen2.5:7b-instruct, 4-bit, via Ollama | open-weight LLM | [qwen2_5_local.md](qwen2_5_local.md) | research (P2 study model) | as above; recall audit disputed (review N1) |
| llama3.1 8B as judge | open-weight LLM | [judge_llama3_1.md](judge_llama3_1.md) | planned (owner decision OD-D) | none (pending) |
| Retrieval: TF-IDF, BM25 hybrid, MiniLM embeddings | retrieval | [retrieval.md](retrieval.md) | research (gated) | recall@5 0.92 TF-IDF, 0.98 hybrid on real filings (real-rules) |
| IC-weighted signal combination | statistical | [combination.md](combination.md) | research | design 0.5125 vs control 0.6437, p 0.174; not adopted (real-rules) |
| HMM regime label and regime conditioning | statistical | [regime_hmm.md](regime_hmm.md) | research | design 0.465 vs control 0.644, p 0.009, worse (real-rules) |
| Split-conformal interval sizing | statistical | [conformal.md](conformal.md) | research | design 0.565 vs control 0.644, p 0.33 (real-rules); v0.17 design unrun |
| VaR: per-instrument historical, book EWMA / FHS | risk | [var_models.md](var_models.md) | default | Kupiec rejects 2/15, independence rejects 6/15 (real-rules) |

## Datasets

| Dataset | Card | Point in time | Licence |
|---|---|---|---|
| Yahoo Finance prices and headlines | [data_yahoo.md](data_yahoo.md) | partly (adjusted closes re-adjust) | see `DATA_LICENSING.md` |
| FRED / ALFRED macro series | [data_fred_alfred.md](data_fred_alfred.md) | yes with vintages on | see `DATA_LICENSING.md` |
| SEC EDGAR filings, XBRL facts, submissions | [data_edgar.md](data_edgar.md) | yes (acceptance time) | see `DATA_LICENSING.md` |
| Test fixtures and synthetic series | [data_fixtures.md](data_fixtures.md) | by construction | repository licence |

`DATA_LICENSING.md` (repository root) is the single place for terms of use; the cards only
point to it. If it is missing in your checkout, it has not been merged yet; do not infer
licence terms from these cards.

## Worked example

Question: "Can I quote the conformal-sized desk's Sharpe as an improvement?" Open
[conformal.md](conformal.md). Status is research, the only measured result is a design-period Sharpe of 0.565
against 0.644 for the control (real-rules, design period, not significant), and the v0.17 calibration fix has
not been re-run. Answer: no; the measured effect is negative and the current code is a
different design from the one measured.

## Keeping this current

A new model or dataset gets a row and a card in the same pull request that adds it. A card's
"Evidence" section names the file or result that backs each number; a number with no source is
removed, not kept. When the run header from review item N5 lands, the model, digest and code
version fields on the LLM cards should be filled from it rather than by hand.
