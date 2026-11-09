# Card: qwen2.5:7b-instruct (local)

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** research, the P2 study model. **Code:** `agentic_trader/local_llm.py` (Ollama
`/api/chat`, temperature 0, JSON-schema constrained decoding).

## Purpose
A $0 open-weight model that lets the LLM roles be measured on this machine. It is a floor: a
7B 4-bit model says nothing about frontier models (`what_the_model_adds.md`, evidence classes).

## Inputs
Prompts from the LLM roles (see [llm_roles.md](llm_roles.md)). The server must be on a
loopback address: since v0.17 `LocalLLM` refuses any other `local_llm_url` unless
`allow_remote_llm: true`, and records `llm_host` and `remote_llm_allowed` with every call.

## Validation evidence
- See the planner, red-team and text-analyst rows on [llm_roles.md](llm_roles.md) (real-local).
- Recall audit (does the model remember what happened next?): the review of 2026-11-09 found
  the audit answers AAPL on 129 of 138 items regardless of the question, so its verdict
  measures option order, not memory (Appendix C, N1). No valid memorisation result exists.

## Limitations
- Quantised weights on CPU; one seed per run in most studies.
- Training-data cut-off is after every study date (review N9).
- Model digest is not pinned per run yet (review N5).

## Monitoring
`model_drift` counter (served name differs from configured), `empty`, `timeouts`, `errors`
(`LocalUsageTracker`).

## Status
Research only. Do not cite a result from this model as evidence about LLMs in general.
