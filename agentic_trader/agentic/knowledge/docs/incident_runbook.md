# Incident runbook

## Stale or missing price feed

Symptom: a decision is refused with a message that the latest bar is older than the
staleness limit, or that fewer than 30 bars are available. Action: do not override the
guard. Check the data provider, confirm the instrument is still listed, and re-run once
fresh bars arrive. Watchlist scans continue past the failing symbol and record the error.

## Language model outage or rate limiting

Symptom: agents report their source as rules although the model is configured, and the
usage summary shows errors. Action: no intervention is needed for correctness; every agent
falls back to its rule-based reasoning and the decision remains bounded by firm limits.
Investigate the API status, then re-run if model reasoning is required.

## Call budget exhausted

Symptom: a warning that the call budget was reached; later agents use rules. Action: raise
the budget deliberately or accept the rule-based remainder. Never remove the budget for
backtests.

## Corrupt decision memory

Symptom: a warning that memory lines were skipped. Action: the run continues without the
unreadable entries. Inspect the JSONL file, restore from the last good copy if the lost
lessons matter, and check for a process that was killed mid-write (writes are atomic, so
this usually indicates a hand edit).

## Suspicious headlines

Symptom: a headline that reads like an instruction to the model. Action: nothing is
required; third-party text reaches the model only inside untrusted-data blocks and the
limits apply after the model. Record the headline for the threat-model log.

## Policy denial

Symptom: a tool call denied by the policy engine, with the rule named. Action: check the
role and the arguments. A denial for an out-of-universe symbol or a future date is
correct behaviour. Grant a capability only through the role configuration, never by
disabling the rule.

## Approval pending

Symptom: a task in the awaiting-approval state. Action: a person with the approve-trades
capability reviews the request in the approvals queue and approves or rejects it; the task
then resumes or fails. Do not auto-approve in production.
