# Live-readiness statement (PLAN 6.3)

**AgenticTrader is not a production trading system and makes no claim to be one.** It never
connects to a broker. This page says, component by component, what exists in the repository,
what exists only as a simulation, and what is absent, so that nobody has to infer it from the
code.

How to read the table. *Exists* means the code runs on real inputs the way a desk would use it
(still on free daily data). *Simulated* means the logic is there but it acts on a paper book
or a fixture, never on an external system. *Absent* means there is no code; anything a real
desk needs here would be new work. Every row names the file that implements it and a test
that exercises it; a row with no test says so.

Worked example: an order. `oms.py` takes it through new, acked, partial, filled, runs the
pre-trade checks and reconciles it at end of day against the ledger (simulated, tested in
`tests/test_v14_oms.py`). Nothing leaves the process: there is no broker adapter, so the
"broker" row below is absent, and the reconciliation is against our own ledger, not against a
custodian statement.

| Component | Status | What there is | Source | Test |
|---|---|---|---|---|
| Broker / execution venue | **Absent** | No broker, FIX or exchange adapter. Fills are modelled with the backtester's cost model at a participation cap. | `agentic_trader/oms.py` (fill model only) | `tests/test_v14_oms.py::test_fill_cost_matches_the_backtester_on_a_toy_order` |
| Order management (OMS) | **Simulated** | Order states and legal transitions, idempotent client order id, fat-finger, collar, duplicate and borrow checks, market hours and NYSE holidays, T+1 / FX T+2 settlement, cash projection, FX roll at 17:00 NY. Shadow record `oms_shadow_v14`, off by default. | `agentic_trader/oms.py` | `tests/test_v14_oms.py` (state machine, checks, settlement, roll) |
| Kill switch | **Simulated** | Global and per-sleeve, persisted, honoured by the OMS and by the agentic `submit_order` tool. | `agentic_trader/oms.py`, `agentic_trader/agentic/tools.py` | `tests/test_v14_oms.py::test_kill_switch_blocks_every_path_and_persists`, `::test_kill_switch_blocks_the_agentic_submit_order_tool` |
| Pre-trade risk | **Simulated** | Book VaR limit (EWMA default since the owner decision of 2026-11-07, `config.DEFAULT_VAR_METHOD`, shared with `risk_model.var_forecast`/`var_next`; FHS and historical options), short-notional cap, position limits in the risk team. Limits are loose and untuned (PLAN §9, 2026-11-07). | `agentic_trader/risk_model.py`, `agentic_trader/validate.py` | `tests/test_v14_risk.py::test_book_var_default_on_and_ewma`, `tests/test_v17_r0_var.py`, `tests/test_v14_oms.py::test_duplicate_guard_and_short_notional_cap` |
| Approvals / four-eyes | **Simulated** | Approval gateway; signed approvals with N-of-M quorum, TTL and re-pricing check, from the `agentic.approval` block. Shared-secret HMAC is a residual risk (CHANGELOG v0.15.1). | `agentic_trader/agentic/governance.py`, `agentic_trader/agentic/harness.py` | `tests/test_v14_oms.py::test_approval_gateway_gates_orders`, `tests/test_v15_followup.py` |
| Entitlements (who may see or do what) | **Simulated, partial** | Tool-level policy: every data access and action is a catalogued tool call checked by a policy and evidenced. There are no user accounts, roles, data-vendor licences or market-data entitlements. | `agentic_trader/agentic/policy.py`, `agentic_trader/agentic/tools.py` | `tests/test_agentic.py`, `tests/test_v15_security.py` |
| Custodian reconciliation | **Absent** | End-of-day reconciliation exists only between the paper OMS and the paper ledger (quantity, cash and price breaks). No custodian or prime-broker statement is read. | `agentic_trader/oms.py` (internal reconciliation) | `tests/test_v14_oms.py::test_reconciliation_detects_qty_cash_and_price_breaks` (internal only) |
| Tax lots | **Absent** | Positions are net weights; no lot tracking, no FIFO/HIFO, no wash-sale logic. | none | none |
| Margin and financing | **Absent** | No margin model, no haircut, no financing charge beyond the FX carry in the backtester; shorts are capped by notional, not by margin. | none (carry: `agentic_trader/backtest.py`) | none |
| Trade surveillance | **Absent** | No market-abuse, wash-trade or spoofing surveillance. The governance report audits the agent's evidence trail, which is a different thing. | none | none |
| Data vintages | **Exists** | Each paper session records a `price_vintage` hash of the bars it read in `results/paper/runs.jsonl`; recomputations that differ are logged to `revisions.csv`, never absorbed; FRED series read first-published values. | `scripts/paper_trade_v09.py`, `agentic_trader/data/` | `tests/test_v14_ops.py::test_vintage_hash_is_stable_and_moves_with_any_price`, `tests/test_v05.py::test_fred_vintages_read_first_published_values` |
| Point-in-time data and leakage | **Exists** | Purged walk-forward IC, a future-leak canary, a point-in-time feature store. Blind spot: leaks inside a provider's own news or fundamentals (PLAN §9). | `agentic_trader/leakage.py` | `tests/test_v14_leakage.py` |
| Forward paper record | **Exists (paper)** | Daily scheduled run on GitHub Actions, append-only ledger, freshness check, issue on failure. Paper only. | `.github/workflows/paper.yml`, `scripts/paper_trade_v09.py` | `tests/test_v09_paper.py`, `tests/test_v14_ops.py::test_freshness_rule_skips_without_a_record_and_fails_past_two_business_days` |
| Model drift and refusals | **Exists** | Served-model drift is counted and can be refused; a refusal is evidenced as missing data. | `agentic_trader/llm.py` | `tests/test_v13_foundation.py::test_drift_is_rejected_when_strict_and_always_counted` |

What would have to change before any of this touched money: a broker adapter behind the OMS,
reconciliation against an external statement, tax lots, margin, surveillance and real
entitlements, each with its own tests, and an independent review. None of it is planned in
`docs/review/PLAN.md`.
