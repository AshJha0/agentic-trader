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
remains the canonical plan is used. The task's symbol and date are pinned into every step
that takes them, and a model-written current position is dropped whenever the run's book
holds the symbol: the book, seeded from the task's declared position and any positions map
submitted with it, is the one source of the position for the planner, the tools and the
agents. A `symbols` argument given as a single string is repaired to a one-element list
and any other shape drops the step; the list is clipped to the configured universe
(canonical spelling, duplicates removed, unparseable names dropped) and to 60 names per
call (`agentic.max_symbols_per_call`), and the step is dropped only when nothing is left.
State-changing tools and duplicate steps are dropped, and a plan may load at most 200,000
symbol-days of data across its tool steps (`agentic.max_plan_lookback_bars`). The critic,
evidence validation and finalisation steps are appended whenever a plan omits them; they
cannot be dropped or reordered. Every tool step is checked against policy before the plan
runs.

## Policy

Every tool call passes through the policy rules in a fixed order: the deny list, the role's
capabilities, the argument guards, the read-only rule, the risk level, then allow. The
argument guards run before the approval outcome, so a state-changing request with a bad
argument (a symbol outside the universe, a list of more than 60 symbols, a future date, a
weight beyond the limit, a non-finite quantity, a notional above the per-order cap, a
missing or unknown argument) is denied outright and is never parked for a person to
approve. A current position is a fact about the book, not a proposal: it must be finite
but is never capped, so a position that drift has carried past the limit can be sized
from. Only a request that passes every guard reaches the read-only rule, which sends every
state-changing tool to the approval gateway.

## Approval

The gateway is configured (`agentic.approval`): `auto` grants every approval, `queued`
pauses the task until a person with the approve-trades capability decides, `deny` refuses
everything. The library default is `auto`; the `serve` command defaults to `queued`, and a
production service sets `queued` or `deny`. An approval is identified by the tool and its
arguments, so a different order is a different approval. Each run is driven by one thread
at a time: a decision resumes a parked run only when nobody is driving it, so two
decisions on one task cannot execute a step twice, and approving an ad-hoc request does not
start a run. A decision that lands as the driver parks is not lost, and a cancel requested
while a run waits for approval cancels it instead of resuming it. When a run finishes or is
cancelled its pending approvals are withdrawn, so deciding one is refused (409); once the
run has been evicted from memory the approval id is unknown (404). The HTTP API builds its
gateway from the setting; the MCP server takes the operator's role and gateway for the
whole session (`--role`, `--approval`, defaulting to the configured setting) and refuses
`queued`, because nothing on a stdio server can decide a parked request.

## Tools

Each tool attempt runs on its own thread with a hard deadline (`agentic.tool_timeout_s`,
30 seconds). A read-only tool is retried once on a transient failure; a state-changing tool
gets exactly one attempt, and a timeout or transient failure on it is reported as outcome
unknown, not retried, for a person to reconcile. The deadline isolates a hung tool, it does
not terminate it: the abandoned worker is counted and never blocks another call. A call to
a remote MCP server has the same deadline by default (`agentic.tool_timeout_s`; an infinite
value waits without limit); when it passes, the client only sends the protocol's
cancellation notice, which is as far as the cancellation reaches: a synchronous remote tool
still finishes and may land its ticket, so the outcome is unknown and is reconciled through
the position report's pending tickets.

## Evidence

Every tool call produces an evidence record with the arguments, a correlation id and a
SHA-256 digest of the payload, before any agent interprets the result. Analyst reports,
debate verdicts, proposals, risk views and the final decision are recorded as decision
evidence. A finding cites evidence ids; a finding whose ids do not resolve is dropped
before the report is written. A finding written from third-party text (a headline, a
social post, or an analyst summary, verdict or rationale built on one) carries an
untrusted flag, in the task record and the report alike, and enters the critic's and the
reporter's prompts only inside the untrusted-data fence, as the decision rationale does
when it may quote such text.

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
process id and a random suffix) and heartbeats the runs it drives every third of the lease
(`agentic.lease_s`, 90 seconds, at least one). The startup sweep and the periodic sweep
mark as failed only records whose heartbeat lease has expired or that have no owner; the
configured instance id never widens the sweep, so a live sibling's runs survive another
process's restart, a rolling restart under a stable id does not fail its predecessor's
records at once but only once their lease has passed, and a sweep never overwrites a
record its owner finished meanwhile. Each run has its own position book, seeded from the
task and any positions map submitted with it (the API accepts one on task creation), over
which its tools run and which its tickets move. The process exposes one metrics page
aggregated across its runs, whose histograms are bounded bucket counts rather than stored
observations. Tools discovered from a remote MCP server are classified fail-closed
whatever the server claims: every discovered tool is state-changing, high risk, needs the
propose-trades capability and yields data evidence, the server's own annotations are kept
for display only, and the operator's override map is the only relaxation (for the
package's own server it defaults to the desk's own catalogue); one server session is kept
per registry. The desk's own MCP server routes every call through the policy engine, the
operator's approval gateway and the evidence store for the operator's role, caps every
ticket at the desk's per-order cap, and a refusal carries the policy's reason.
