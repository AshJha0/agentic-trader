# Threat model

agentic-trader turns untrusted inputs (market data, news, social posts, macro series, model
output, plans, API requests, remote tools) into position sizes, evidence and reports. This
document lists what must be protected, where the trust boundaries are, and which control and
test handle each threat. Where a threat is only partly mitigated, it says so.

## Assets

| Asset | Why it matters |
|---|---|
| Final position size and direction | The only output that moves (simulated) capital |
| Evidence and audit trail | A report is only worth what its evidence proves; tampering makes every claim unverifiable |
| Backtest and evaluation integrity | Look-ahead, leakage or selective reporting makes every number meaningless |
| Numerical correctness of the quant core | Every agent's facts, every alpha, every metric depends on it |
| API credentials and spend | An `ANTHROPIC_API_KEY` or OAuth profile grants paid model access; an API key grants a role |
| Decision memory | Feeds lessons and a track record into later decisions |
| The knowledge base | Retrieved passages shape the trader's and risk team's prompts |

## Trust boundaries

1. **Data providers → tools → agents.** Prices, headlines, social posts, fundamentals and
   FRED series come from outside. Headlines and posts are free text written by third parties.
   Under the harness, every access is a tool call.
2. **Agents → LLM → agents.** Prompts leave the process; model replies (analyst views, plans,
   critiques, narratives) are untrusted text.
3. **Planner → harness.** A plan is a request, not an instruction; the validator and the policy
   engine decide what runs.
4. **Tool executor → policy → gateway.** The last point before a tool runs, and the only place
   a state change can be approved.
5. **Portfolio manager → critic → report.** Code overrides everything upstream; the critic can
   only lower confidence; the audits check the narrative.
6. **Python → C++.** Array data crosses into native code through pybind11.
7. **Client → HTTP API / MCP → harness.** Symbols, dates, positions, questions and approvals
   arrive over a socket or a pipe, with a role attached.
8. **Remote MCP servers → registry.** Tools discovered from another process carry their own
   descriptions and results.

## Threats, controls, tests

### Data and time

| # | Threat | Control | Test / evidence | Residual risk |
|---|---|---|---|---|
| T1 | **Look-ahead bias**: a provider returns bars after `as_of` | The provider contract, plus the graph re-clipping history to `<= as_of` regardless of provider | `test_propagate_offline` | None known for prices |
| T2 | **Leakage through fundamentals**: a current snapshot used for a past date | `YahooProvider.fundamentals` returns nothing when `as_of` is more than 7 days before today; synthetic fundamentals publish with a 30-day lag | `test_synthetic_fundamentals_respect_publication_lag` | CSV users must supply point-in-time data themselves |
| T3 | **Leakage through news**: headlines after `as_of` | Every provider filters by date, and `NewsAnalyst` and `SentimentAnalyst` filter `published <= as_of` again; Yahoo news is not requested for dates it cannot serve | `test_synthetic_news_never_after_as_of`, `test_csv_news_filters_dates_and_blank_rows` | Timestamps are at day granularity: news published after the close on `as_of` is visible to that day's decision |
| T4 | **Leakage through memory**: using outcomes not yet known | `resolve()` only settles entries whose horizon has elapsed by `as_of`; `lessons()` and `track_record()` only return entries resolved on or before `as_of` | `test_memory_resolves_only_past` | None known |
| T5 | **Execution-timing bias**: earning the return of the bar that produced the signal | The weight at bar *t* earns the return from *t* to *t + 1*; the last bar earns nothing. The FX spread is converted at the window's first price | `test_no_lookahead_timing` | None known |
| T6 | **Look-ahead in alphas or covariance** | Every alpha uses only bars up to *t* (rolling windows, lagged returns); covariance is estimated from trailing returns at each rebalance; the alpha report aligns signal at *t* with the return from *t* to *t + h* | `test_alpha_signals_are_bounded_point_in_time_and_complete`, `test_construct_end_to_end`, `test_portfolio_backtest_weighting_schemes` | The design period was used to judge the alpha analyst, so it is in-sample for that choice |
| T7 | **Decisions on stale data**: a dead feed, a delisting or an outage leaves the last bar weeks old | `prepare` refuses when the last bar is more than `max_data_staleness_days` (7) before `as_of`; weekends and holidays pass | `test_stale_data_is_refused`, `test_weekend_as_of_uses_friday_close` | A feed that keeps publishing wrong but fresh prices is not detected |
| T8 | **Wrong instrument**: a mistyped pair silently becoming an equity ticker, or garbage symbols reaching a provider | `Instrument.parse` treats "/" and "=X" as FX intent and rejects invalid pairs; equity tickers must match a strict pattern; `agentic.symbol_universe` restricts tool calls to a list | `test_instrument_parsing_rejects_bad_symbols`, `test_policy_rules_in_order` | A valid but unintended ticker (a typo that is another real company) cannot be detected without a universe |
| T9 | **Macro look-ahead or stale macro** | `data/fred.py` shifts every observation by its publication lag and treats values older than their maximum age as unavailable; on real data the static table is used only within 180 days of today | `test_fred_publication_lag`, `test_fred_staleness`, `test_fx_macro_modes` | FRED serves the latest vintage: revised CPI can differ from first publication |
| T10 | **Messy input files**: unsorted rows, duplicate dates, blank or zero closes, highs below closes, time zones | `clean_ohlcv` normalises every provider's output | `test_clean_ohlcv_repairs_messy_input`, `test_csv_lowercase_adj_close_unsorted` | Split or dividend errors in user files are not detected |
| T11 | **Corrupt decision memory** from a crash mid-write or a hand edit | Writes go to a temporary file and are then renamed; unreadable lines are skipped with a warning and counted | `test_memory_survives_corrupt_lines_and_writes_atomically` | Skipped entries are lost to reflection |

### Models and prompts

| # | Threat | Control | Test / evidence | Residual risk |
|---|---|---|---|---|
| T12 | **Prompt injection via news, social text or retrieved passages** | Third-party text reaches the model only inside `<untrusted_data>` blocks; tag open/close attempts inside the text are neutralised; model output is clipped and coerced; firm limits run after the model; the critic flags a model view that diverges from the rule view by more than `critic_divergence` | `test_untrusted_block_cannot_be_closed_from_inside`, `test_headlines_reach_the_model_only_inside_the_block`, `test_injected_model_cannot_breach_limits`, `test_injected_headline_is_fenced_and_bounded`, `test_critic_flags_divergence_wrong_side_levels_and_limits` | **Partial.** Injected text can still bias a direction *within* the limits; the critic lowers confidence but does not veto |
| T13 | **Malformed or hostile LLM output**: prose, broken JSON, missing keys, `inf`, `nan`, strings, wrong-side stops, absurd horizons | `extract_json` accepts only a JSON object; missing keys fall back to rules; `clip()` coerces or defaults non-finite values; `sane_levels` replaces wrong-side stops and targets; horizons are clipped to 1–90 days | `test_llm_garbage_falls_back_to_rules`, `test_injected_model_cannot_breach_limits`, `test_sane_levels` | None known |
| T14 | **Model refusal, timeout or API failure** mid-pipeline | A refusal and typed SDK errors return `None`, and the agent uses its rule-based result; requests time out after `llm_timeout_s` | Code review; `test_llm_garbage_falls_back_to_rules` | Degraded (rule-based) reasoning for that step, visible as `source = "rules"` |
| T15 | **Cost runaway** from many LLM calls | `max_llm_calls` and `max_llm_cost_usd` wrap any model in `BudgetedLLM` (a call count does not bound a bill: an Opus call is ~15 Haiku calls); `UsageTracker` records tokens and estimated cost per run; the dollar cap is checked before each call so the overshoot is at most one call; abstaining analysts make no call; offline is the default | `test_budgeted_llm_caps_calls_and_falls_back`, `test_dollar_budget_caps_spend`, `test_usage_tracker_prices_by_serving_model`, `test_budget_is_thread_safe` | The caps are per graph, not per account; the dollar figure uses list prices |
| T16 | **Sensitive prompt content**: symbols, positions or dates leaving the process | `llm_anonymize` replaces instruments, names and dates with placeholders before the call and maps them back after | `test_anonymized_prompts_leak_no_name_date_or_price`, `test_anonymizer_fx_pair_and_codes` | Free text (headlines) can still identify the instrument; anonymisation is off by default |
| T17 | **A rogue plan**: the model asks for tools that do not exist, another symbol or date, a state change, or drops the governance steps | `validate_plan` strips unknown tools, pins the task's symbol and date, coerces arguments against the schema, and appends the critic, evidence validation and finalisation steps; every tool step is then pre-checked against policy | `test_validate_plan_strips_repairs_pins_and_appends_governance`, `test_rogue_plan_is_repaired_not_executed`, `test_governance_cannot_be_skipped` | A plan that omits useful steps degrades quality, not safety |
| T18 | **A critic or narrative that inflates confidence** | The model critique's multiplier is clipped to at most 1 and its concerns are appended, never removed; the deterministic checks run regardless | `test_llm_critique_can_only_lower_confidence`, `test_critic_cannot_raise_confidence` | A model critique that is too lenient adds nothing; the deterministic checks are the floor |
| T19 | **A fabricated narrative**: numbers or evidence ids that are not in the facts | `number_audit` accepts only numbers that match a fact when the fact is rounded to the displayed precision (counts included); `evidence_audit` rejects unknown ids; failed audits are attached to the report | `test_number_and_evidence_audits`, `test_report_flags_fabricated_numbers_and_ids_from_a_model`, `test_fabricated_narrative_is_audited` | A narrative can omit facts; the audits check what is said, not what is left out |
| T20 | **Knowledge-base poisoning**: a hostile document steering the trader | The knowledge directory ships with the package and is loaded from disk, never the network; `knowledge.list_documents` shows what was loaded; the trader and risk prompts take at most three passages truncated to 400 characters, labelled as retrieved policy; the firm limits and the critic run after the model | `test_knowledge_base_retrieval`; code review of `policy_passages` | **Partial.** Passages are presented as firm policy to follow, so anyone who can write to the docs directory can bias a direction within the limits. Keep the directory read-only in deployment |

### Tools, policy and services

| # | Threat | Control | Test / evidence | Residual risk |
|---|---|---|---|---|
| T21 | **Approval bypass**: a state-changing tool runs without a human | `read_only_rule` returns REQUIRE_APPROVAL for every non-read-only tool before any allow rule; the `deny` gateway refuses everything; `QueuedApprovalGateway` pauses the task in AWAITING_APPROVAL; the approval identity is the tool and its arguments, so a different order is a different approval | `test_policy_rules_in_order`, `test_queued_gateway_round_trip_and_deny_gateway`, `test_harness_awaits_approval_then_resumes_or_cancels`, `test_rejected_approval_fails_the_step_but_finishes_the_task` | With `approval: auto` (the default for research) approvals are granted automatically; production deployments must set `queued` |
| T22 | **Privilege escalation**: a viewer proposing trades, an analyst approving | Roles map to capabilities; `capability_rule` denies a tool whose required capabilities the role lacks; the HTTP API maps API keys to roles and checks capabilities per route | `test_role_escalation_is_denied`, `test_harness_refuses_role_without_capability`, `test_api_auth_roles_and_task_lifecycle` | There is no key rotation; see T33 for the development keys |
| T23 | **Hostile tool arguments**: huge strings or arrays, extra fields, bad dates, a symbol outside the universe, a position beyond the limit | `coerce_arguments` bounds strings (2000 chars) and arrays (1000 items), rejects extra fields and bad types; `argument_guard_rule` checks symbols, dates and weights | `test_hostile_arguments_are_refused`, `test_schema_from_signature_and_coercion`, `test_policy_rules_in_order` | None known |
| T24 | **Tool hangs and retries as denial of service** | Each call runs with `tool_timeout_s` (30) and at most `max_attempts` (2) with backoff; a failure becomes FAILED evidence and the step fails, not the process | `test_executor_retries_transient_errors_and_times_out`, `test_executor_records_evidence_for_success_and_failure` | A slow provider still costs the timeout per step |
| T25 | **Untrusted remote MCP tools**: another process's tool descriptions or results | Remote descriptors are registered with `register_descriptor` and go through the same policy, coercion and evidence path as local tools; results are data, not instructions | `test_mcp_stdio_round_trip_and_remote_registry` | A remote tool's payload is trusted as data for that tool; there is no signature on results |
| T26 | **Evidence tampering** after the fact | `Evidence.resolve` re-hashes the payload and compares it to the stored digest; findings citing unresolved ids are dropped | `test_evidence_store_resolves_and_detects_tampering`, `test_unresolvable_evidence_is_dropped` | The persistent task store (T34) keeps evidence *summaries* (id, type, digest prefix), not payloads: an archived record can be read but its evidence cannot be re-verified |

### Engineering and reporting

| # | Threat | Control | Test / evidence | Residual risk |
|---|---|---|---|---|
| T27 | **Oversized or forbidden positions** from rule or model bugs | Firm limits in `PortfolioManager.guardrails`; the no-trade band only keeps a legal position; the backtester clips to `max_leverage` and to `>= 0` when shorting is disallowed; the critic's `firm_limits` check is an error | `test_guardrail_order_and_zero_var`, `test_no_trade_band_keeps_position_only_when_legal`, C++ `test_short_clip` | None known |
| T28 | **Silent numerical divergence** between the C++ and Python backends | The numpy twin mirrors the C++ conventions; CI asserts the active backend and cross-checks indicators, strategies, rolling extremes, Spearman, Almgren-Chriss and randomised extended backtests | `test_cpp_matches_python_reference`, `test_cpp_matches_python_extended_backtest`, `test_new_core_functions_match_numpy` | None known |
| T29 | **Native-code memory errors or silent garbage** from hostile arrays | Every optional per-bar array is length-checked; non-positive windows and non-positive, NaN or infinite prices are rejected with `std::invalid_argument`; list conversion at the boundary means C++ never sees raw numpy memory; `tests/test_fuzz.py` fuzzes every quant entry point with hypothesis (NaN, ±inf, empty, subnormal, 1e300) and asserts either a well-formed result or `ValueError`, plus C++/numpy agreement on sane inputs. Its first run found five divergences (NaN in `quantile`, `max_drawdown`, `kdj`, `atr`; flat-window `zscore`), all fixed | `test_extra_length_mismatch_rejected`, `test_non_positive_or_nan_prices_rejected`, `tests/test_fuzz.py` (21 properties), C++ `test_carry_series_and_validation`, `test_impact_cost` | Agreement is only asserted for \|x\| ≤ 1e6: beyond ~2^53 the running-window and cumulative-sum formulations lose precision differently (a float64 property, not a bug) |
| T30 | **Credential exposure** | Model credentials are read only by the Anthropic SDK; API keys are compared, never logged; nothing writes keys to reports or evidence; `results/`, `.venv/` and `.env` files are git-ignored | Code review | Users must keep keys out of committed config |
| T31 | **Overstated results** in documentation | Every figure on the site comes from a recorded run; evaluation tables are generated from saved JSON; LLM-mode results are explicitly not claimed; the alpha-analyst negative result and the DSR caveats are published | [GITHUB_PAGES.md](../GITHUB_PAGES.md) "keeping the page honest" | Figures go stale if code changes without re-measuring |
| T32 | **Overfitting the evaluation** | Choices are made on the 2016–2021 design period of the core universe only, the holdout was run once with frozen rules, the full ablation is published, `RULES_V02` keeps the before state reproducible, the deflated Sharpe ratio is reported for the number of variants tried, and (v0.5) the 45-instrument extended universe and the reserve period are declared as the unseen data for the next change *before* there is one | [evaluation.md](../evaluation/evaluation.md#the-next-rule-change-what-counts-as-unseen) | The 2022–2026 holdout has been seen; the reserve period is short until it grows |
| T33 | **Development API keys in production**: the shipped `dev-*` keys left live on a reachable host | `serve` refuses to bind a non-loopback interface while any shipped or `dev-` key is configured unless `allow_dev_keys` is passed explicitly; `make_config` *replaces* `agentic.api_keys` instead of deep-merging an override into the dev keys (a real footgun: adding a real key used to leave every dev key active) | `test_serve_options_guard_deployment`, `test_serve_cli_plumbs_tls_and_store` | A user who passes `allow_dev_keys` has been told; nothing stops a reverse proxy from exposing a loopback bind |
| T34 | **Task records lost or misrepresented across restarts**: an in-flight decision vanishes or appears to be still running | `TaskStore` writes every run at each state transition; on startup any record in a non-terminal state is marked FAILED with the reason `process restarted` and is served read-only; the API reports archived and live counts separately and refuses to cancel an archived task | `test_task_store_persists_and_archives`, `test_api_serves_archived_tasks` | SQLite is single-host; a run is at most one transition behind at a crash; approvals queued in memory do not survive (their task is failed) |
| T35 | **Plain-text API keys on the wire** | `serve --ssl-cert/--ssl-key` enables TLS in uvicorn; both files must exist; binding off loopback without TLS logs a warning | `test_serve_options_guard_deployment` | Certificate management (rotation, trust) is the operator's; the warning is a warning |
| T36 | **Look-ahead through data revisions**: a macro value used as it was later revised, not as first published | `fred_vintages` reads revised series from the ALFRED vintage current at each date; vintages are sampled monthly so a value becomes visible at the first vintage after its publication, the conservative side; policy rates are never revised and bypass vintages | `test_fred_vintages_read_first_published_values`, `test_default_client_per_setting` | Off by default (the published FX runs carry a small CPI revision leak); Yahoo total-return prices are themselves the latest adjustment history |

## Out of scope

- Live trading, order routing and broker credentials: `execution.submit_order` records an
  order request as evidence and does nothing else.
- Market-abuse surveillance.
- Multi-tenant isolation: one harness serves one desk. The HTTP API authenticates by key but
  every key sees the same tasks.
- Multi-process workers and a shared queue: the task store persists records, it does not
  distribute work.
