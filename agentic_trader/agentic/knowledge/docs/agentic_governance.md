# Agentic governance

## Roles and capabilities

Viewer may read market data and knowledge. Analyst adds analytics and model runs. Trader
adds proposing trades. Risk adds approving trades. Admin holds every capability. A tool
call is denied when the role lacks a capability the tool requires.

## Plans

A task begins with a plan: an ordered list of steps restricted to the tool catalogue and
the desk's agent stages. A model may propose a plan; unknown tools, unknown stages,
unknown step types and unknown arguments are stripped and recorded, and if nothing usable
remains the canonical plan is used. The critic, evidence validation and finalisation steps
are appended whenever a plan omits them; they cannot be dropped or reordered.

## Evidence

Every tool call produces an evidence record with the arguments, a correlation id and a
SHA-256 digest of the payload, before any agent interprets the result. Analyst reports,
debate verdicts, proposals, risk views and the final decision are recorded as decision
evidence. A finding cites evidence ids; a finding whose ids do not resolve is dropped
before the report is written.

## Critic

The critic runs deterministic checks first: cited evidence must resolve, a model-sourced
analyst signal must not contradict its own rule-based signal by more than the divergence
threshold, the final decision must sit within the firm limits, and protective levels must
sit on the correct side of the entry. A model critique may then run and may only lower
confidence, never raise it.

## Audited reports

The narrative is generated from structured facts. Afterwards every number in the
narrative is checked against those facts, tolerant of rounding and percentage forms, and
every cited evidence id is checked against the store. Discrepancies are attached as
warnings rather than silently accepted.
