# Card: VaR models

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** default. **Code:** `agentic_trader/agents/risk.py` (per-instrument 250-day
historical VaR), `agentic_trader/risk_model.py` (`ewma_vol`, `var_forecast` with methods
including EWMA and filtered historical simulation).

## Purpose
Scale a decision down when its 95% one-day VaR breaches `max_var_95`, and, when on, the book's
VaR breaches `max_book_var_95`.

## Inputs
Each instrument's daily returns; for the book, the proposed weights and the joint return history.

## Validation evidence
- Per-instrument 250-day historical VaR against next-day returns over the holdout: Kupiec
  rejects at 5% on 2 of 15 (AAPL, AUDUSD), every breach rate is above 5%, Christoffersen
  independence rejects on 6 of 15 (real-rules; `docs/evaluation/evaluation.md`, summary).
- Book VaR default switched to EWMA by owner decision on 2026-11-07 (design 13/15 passing vs
  FHS 10/15) (real-rules; `config.py` comment on `book_var_method`, PLAN log 2026-11-08).
- FHS passes Kupiec and independence on 8 of 8 synthetic GARCH seeds (fixture; PLAN log
  2026-11-07).

## Limitations
Historical VaR reacts slowly, hence the clustered breaches. Book VaR was off in every published
run; its coverage on real data is untested (`evaluation.md`).

## Monitoring
`agentic-trader stats --var-backtest` (Kupiec, Christoffersen).

## Status
Default for per-instrument sizing; book VaR available, off by default.
