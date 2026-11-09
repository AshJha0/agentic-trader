# Card: rule-based analysts

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** default. **Code:** `agentic_trader/agents/analysts.py` (`TechnicalAnalyst`,
`FundamentalsAnalyst`, `MacroAnalyst`, `NewsAnalyst`, `SentimentAnalyst`, `AlphaAnalyst`,
`XAlphaAnalyst`), with the facilitator, trader, risk and PM rules in `agents/`.

## Purpose
Turn market, macro and filing data into a signal in [-1, 1] and a confidence, without any
model. This is the desk that runs when `llm_provider` is `offline` and the fallback whenever a
model call fails or is refused.

## Inputs
Daily closes (Yahoo), FRED/ALFRED rates and inflation, EDGAR XBRL facts and filing events, the
alpha library (`alpha.py`). All are cut at the decision date (see the dataset cards).

## Validation evidence
- Design period 2016-2021 was used to choose the rules; the holdout 2022-2026 was run once with
  frozen rules. Tables: `docs/evaluation/evaluation.md`, sections "Headline results" and
  "v0.8: engine and protocol corrections" (real-rules).
- The evaluation summary itself says nothing remains unseen: the reserve period and extended
  universe were consulted for later rule changes (`evaluation.md`, summary) (real-rules).

## Limitations
- The weights inside the rules (for example the technical analyst's 0.30 / 0.20 / 0.15 / 0.15)
  were set by hand, not estimated (`combine.py` module docstring).
- The universes were chosen in 2025 with hindsight (survivors) (`evaluation.py`, comment on
  `EXTENDED_UNIVERSE`).

## Monitoring
The paper-trading runner and forward log (`results/paper/`) record each session's decisions;
review findings for v0.17 (Appendix D N1) note the forward books are not frozen across merges,
so drift in the strategy itself is not yet separated from drift in the market.

## Status
Default. Changes go through a registered trial in `evaluation.TRIALS`.
