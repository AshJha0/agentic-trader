# Lane C: governance leftovers (v0.18)

Source: `docs/review/v017_notes/LEFTOVERS.md`, L7 and L5.

| Item | State at f0838f1 | Done here |
|---|---|---|
| 1. `signed_gateway_from_config` Ed25519 `public_keys` | Already shipped in v0.17 (`harness.py`), with in-memory key tests in `tests/test_v17_integration.py` (good keys, mixed HMAC + Ed25519, bad hex, wrong length) | Nothing; closed |
| 2. `graph.py` memory record through the output guard | Already shipped: `TradingGraph._guarded_summary` redacts before `memory.record` (`memory_output_guard`, default on); covered in `tests/test_v17_integration.py` | Nothing; closed |
| 3. Paraphrase poison miss (1/20) | Open | `output_guard.poison_match`: word-bigram shingle containment (stop words and numbers dropped, threshold 0.75) against ten generic steering phrases in `KNOWN_POISON`; reason `poison-like text`. No new dependency, no model |
| 4. Paper OMS C3 ex-date hook + per-name limit 1.0 | Hook existed but ran whenever the provider had action tables; `max_name_concentration` default 1.0 already in `OMS_DEFAULTS` with a test | Hook now behind `paper_session(..., corporate_actions=False)` and `scripts/paper_trade_v09.py --oms-corporate-actions` (off by default) |

## Poison corpus result

Existing 20-line corpus (`tests/test_v17_ai_rest.py::POISON`): 19/20 refused before, 20/20 after
(miss rate 5 % -> 0 %). The phrases in `KNOWN_POISON` are generic, not copies of the corpus, but
one of them was written knowing the missed line, so 0/20 is an in-sample figure, not a measured
out-of-sample rate. Evidence class: rule-based, unit-tested on hand-written cases. Four ordinary
decision summaries that share words with the phrases ("target weight ... within risk limits",
"approval was granted") pass, as tested; the false-refusal rate on real model replies is not measured.

## Engine hash

Unchanged. The freeze covers `backtest, config, algo, portfolio, graph, validate, instruments,
quant/*, agents/*` plus config keys; this lane touches `oms.py`, `agentic/output_guard.py` and
`scripts/paper_trade_v09.py` only, and adds no config key. No refreeze needed for lane C.

## Open

- Behaviour change: before this lane an `--oms` run with a provider that has action tables applied
  actions; now it needs `--oms-corporate-actions`. Nothing scheduled used it (the paper workflow
  does not pass `--oms`); say so in the CHANGELOG at combine.
- A larger, held-out poison corpus (and real model summaries for false refusals) is still needed
  before quoting any miss rate beyond this corpus.
