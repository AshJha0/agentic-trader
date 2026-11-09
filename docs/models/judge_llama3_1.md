# Card: llama3.1 8B as judge (planned)

Back to the [inventory](INVENTORY.md). Evidence classes are defined there.

**Status:** planned (owner decision OD-D in `docs/review/2026-11-09_review_and_plan.md`,
section 3 R5; plan row R3.1).

## Purpose
Score the desk's free-text replies with a model from a different family than the one being
judged. Today the judge is the same qwen2.5:7b that writes the replies, a known self-preference
bias (review Appendix A, B2).

## Inputs
Replies from the LLM roles, a rubric, and an owner-labelled calibration set of at least 100
real replies (plan R3.1).

## Validation evidence
None yet (pending). The current judge calibration is 30 hand-written replies judged by the same
7B, which the review says measures nothing about the real task (Appendix A, B2).

## Limitations
Not downloaded (about 5 GB) and not run. Agreement with the owner's labels is the acceptance
test; no threshold has been registered.

## Monitoring
Planned: agreement (Cohen's kappa) against owner labels, re-checked when the judged model
changes.

## Status
Planned. Nothing in the repository calls it.
