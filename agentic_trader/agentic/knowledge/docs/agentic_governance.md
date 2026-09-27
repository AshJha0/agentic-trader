# Agentic governance

## Roles and capabilities

Viewer may read market data and knowledge. Analyst adds analytics and model runs. Trader
adds proposing trades. Risk adds approving trades. Admin holds every capability. A tool
call is denied when the role lacks a capability the tool requires. Over HTTP the role comes
from the API key; over stdio (the MCP server) it is the operator's choice for the whole
session, because stdio carries no identity.

## Plans

A task begins with a plan: an ordered list of steps restricted to the tool catalogue and
the desk's agent stages. A model may propose a plan; unknown tools, unknown stages,
unknown step types and unknown arguments are stripped and recorded, and if nothing usable
remains the canonical plan is used. The task's symbol, date and current position are
pinned into every step that takes them. State-changing tools and duplicate steps are
dropped, and a plan may load at most 200,000 symbol-days of data across its tool steps
(`agentic.max_plan_lookback_bars`). The critic, evidence validation and finalisation steps
are appended whenever a plan omits them; they cannot be dropped or reordered. Every tool
step is checked against policy before the plan runs.

## Policy

Every tool call passes through the policy rules in a fixed order: the deny list, the role's
capabilities, the argument guards, the read-only rule, the risk level, then allow. The
argument guards run before the approval outcome, so a state-changing request with a bad
argument (a symbol outside the universe, a list of more than 60 symbols, a future date, a
weight beyond the limit, a non-finite quantity, a notional above the per-order cap) is
denied outright and is never parked for a person to approve. Only a request that passes
every guard reaches the read-only rule, which sends every state-changing tool to the
approval gateway.

## Approval

The gateway is configured (`agentic.approval`): `auto` grants every approval, `queued`
pauses the task until a person with the approve-trades capability decides, `deny` refuses
everything. The library default is `auto`; the `serve` command defaults to `queued`, and a
production service sets `queued` or `deny`. An approval is identified by the tool and its
arguments, so a different order is a different approval. Each run is driven by one thread
at a time: a decision resumes a parked run only when nobody is driving it, so two
decisions on one task cannot execute a step twice, and approving an ad-hoc request does not
start a run. The HTTP API and the MCP server build their gateway from the same setting.

## Tools

Each tool attempt runs on its own thread with a hard deadline (`agentic.tool_timeout_s`,
30 seconds). A read-only tool is retried once on a transient failure; a state-changing tool
gets exactly one attempt, and a timeout or transient failure on it is reported as outcome
unknown, not retried, for a person to reconcile. The deadline isolates a hung tool, it does
not terminate it: the abandoned worker is counted and never blocks another call.

## Evidence

Every tool call produces an evidence record with the arguments, a correlation id and a
SHA-256 digest of the payload, before any agent interprets the result. Analyst reports,
debate verdicts, proposals, risk views and the final decision are recorded as decision
evidence. A finding cites evidence ids; a finding whose ids do not resolve is dropped
before the report is written.

## Critic

The critic runs deterministic checks first: cited evidence must resolve, a model-sourced
analyst signal must not contradict its own rule-based signal by more than the divergence
threshold, the final decision must sit within the firm limits (reading the VaR tail of the
decision's own side), and protective levels must sit on the correct side of the entry. A
model critique may then run and may only lower confidence, never raise it; a malformed
critique is recorded as a failed well-formedness check and ignored.

## Audited reports

The narrative is generated from structured facts. Afterwards every number in the
narrative is checked against those facts, tolerant of rounding and percentage forms, and
every cited evidence id is checked against the store. Discrepancies are attached as
warnings rather than silently accepted.

## Services

A service records the owner of every live run (`agentic.instance_id`, by default host,
process id and a random suffix) and heartbeats it every third of the lease
(`agentic.lease_s`, 90 seconds). The startup sweep and a periodic sweep mark as failed only
records written by the same configured instance id, records whose heartbeat has expired,
or records with no owner, so a live sibling's runs survive another process's restart. The
process exposes one metrics page aggregated across its runs. Tools discovered from a remote
MCP server are classified fail-closed: without annotations a tool is state-changing, high
risk and needs the propose-trades capability, and only an operator override relaxes that.
The desk's own MCP server routes every call through the policy engine, the configured
approval gateway and the evidence store for the configured role, and a refusal carries the
policy's reason.
