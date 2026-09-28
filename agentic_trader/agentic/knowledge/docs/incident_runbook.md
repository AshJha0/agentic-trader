# Incident runbook

## Stale or missing price feed

Symptom: a decision is refused with a message that the latest bar is older than the
staleness limit, or that fewer than 30 bars are available. Action: do not override the
guard. Check the data provider, confirm the instrument is still listed, and re-run once
fresh bars arrive. Watchlist scans continue past the failing symbol and record the error.
A Yahoo request for today returns yesterday's bar by design; a bar dated D is served once
it is D+1 on the New York calendar, whatever the host's timezone, and an empty download is
refused rather than served as an empty history.

## Language model outage or rate limiting

Symptom: agents report their source as rules although the model is configured, and the
usage summary shows errors or timeouts. Action: no intervention is needed for correctness;
every agent falls back to its rule-based reasoning and the decision remains bounded by firm
limits. A timed-out request is billed at its estimated maximum once per attempt, so the
usage summary overstates rather than understates spend. A rate limit or overload is retried
after the wait the server asked for (its retry-after header, honoured up to 60 seconds),
otherwise after the configured backoff. Investigate the API status, then re-run if model
reasoning is required.

## Call or spend budget exhausted

Symptom: a warning that the call budget or the spend budget was reached, followed by
"agents fall back to rules"; later agents use rules. The spend budget reserves each call's
cost before it is dispatched and counts calls in flight against the cap. In the default
hard mode (`llm_budget_mode`) the reservation is the most the call can cost, a full
maximum-length reply, which is also what a timed-out attempt is billed at, so spend never
exceeds the cap, the run stops at the cap rather than one call per worker past it, and a
small cap admits fewer concurrent calls than its balance suggests; a cap that cannot afford
one such call refuses that tier before any spend. In estimate mode the reservation is a
realistic reply, more calls run at once, and spend can exceed the cap by what replies run
over the reserve. "Exhausted" means the next deep-tier call would be refused (its
reservation, on top of what is spent and reserved, reaches the cap); the quick tier can
still be served while its smaller reservation fits. A warning that the budget "cannot be
enforced" because a model id has no list price means the budget treated itself as
exhausted; add the price or change the model. Action: raise the budget deliberately, or
switch to estimate mode knowing the cap is then soft, or accept the rule-based remainder.
Never remove the budget for backtests.

## Corrupt decision memory

Symptom: a warning that a memory line was unreadable and skipped. Action: the run continues
without the unreadable entries. The log is append-only and each line is written and synced
in one call under a file lock, so a torn last line indicates a process killed mid-write and
anything else a hand edit. Inspect the JSONL file and restore from the last good copy if
the lost lessons matter. Entries written before v0.8 carry no provider: they are never
valued, and any named provider's visit expires them once twice their horizon has elapsed;
regenerate lessons that matter under the named provider.

## Suspicious headlines

Symptom: a headline that reads like an instruction to the model. Action: nothing is
required; third-party text reaches the model only inside untrusted-data blocks, as do the
digests, lessons, debate turns, verdicts and rationales written from it, in the critic's
and the reporter's prompts too, and the limits apply after the model. Findings built on
such text carry an untrusted flag in the task record. Record the headline for the
threat-model log.

## Policy denial

Symptom: a tool call denied by the policy engine, with the rule named. Action: check the
role and the arguments. A denial for an out-of-universe symbol, a future date, a list of
more than 60 symbols or an order above the per-order notional cap is correct behaviour,
and it happens before any approval is requested. Grant a capability only through the role
configuration, never by disabling the rule.

## Approval pending

Symptom: a task in the awaiting-approval state. Action: a person with the approve-trades
capability reviews the request in the approvals queue and approves or rejects it; the
response says whether the task was resumed, and the task then resumes or fails. The
approvals queue answers 409 when the service is not in queued mode, and deciding an
approval whose run has since finished or been cancelled is refused with 409 (its requests
were withdrawn with the run); once the run has been evicted the id answers 404. Do not
auto-approve in production.

## Tool timed out or outcome unknown

Symptom: a step failed with "timed out" or "outcome unknown, not retried". Action: for a
read-only tool the executor already retried once; check the provider. For a state-changing
tool (an order ticket) the call was made exactly once and its result is unknown: reconcile
the ticket against the order management system before re-submitting. The timed-out worker
is abandoned, not killed, and counted in `tool_calls_abandoned_total`; a hung remote tool
holds one thread until it returns. A call to a remote MCP server that passes its deadline
(`agentic.tool_timeout_s` by default) only receives the protocol's cancellation notice: the
remote tool may still finish and land its ticket, so reconcile through the remote desk's
position report, which lists pending tickets.

## Book VaR could not be evaluated

Symptom: a decision flattened with a note that the book VaR could not be evaluated, or a
scan warning that a held symbol has fewer than 20 bars of book history. Action: this is the
check failing closed. Supply history for the held symbol, or accept the flat decision; do
not remove the book cap to make the note go away.

## Runs failed after a restart, or a sibling's runs marked failed

Symptom: records marked "process restarted". Action: a live run is failed only after its
heartbeat lease (`agentic.lease_s`, 90 seconds, at least one) has expired, or when it has
no owner. The configured `agentic.instance_id` never widens the sweep: a crashed process's
in-flight records, under any instance id, stay non-terminal until the lease passes and are
then failed by whichever live instance sweeps next, and a live sibling sharing the id
keeps its runs because it keeps heartbeating them. A sweep that races the owner finishing
a run leaves the finished state in place. Approvals queued in memory do not survive a
restart; their task is failed.

## Metrics and shutdown

`/metrics` is one exposition per process, aggregated across runs; its histograms are
bounded (count, sum, min, max and cumulative counts over fixed buckets, never the
observations) and its counters render exactly. `/health` reports the approval mode and the
instance id. A harness with a task store runs a heartbeat thread; call `harness.close()`
on shutdown so it stops before the store is closed.
