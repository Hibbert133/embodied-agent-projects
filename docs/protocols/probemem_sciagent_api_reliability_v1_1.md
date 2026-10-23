# ProbeMem-SciAgent API Reliability v1.1

Status: `SHADOW_FROZEN_BEFORE_EXECUTION`

## Question

This development-only gate asks whether a certificate-bearing structured-output
contract can make the online GLM interface valid, evidence-grounded, idempotent,
and fail-closed before any model decision is permitted to execute. It does not
test robot recovery, memory benefit, principles, or online learning.

SciAgent v1's blocked credential preflight and all earlier negative results are
immutable. No v1 seed was consumed. This successor uses fresh seeds 5850--5899;
5900--5999 remain reserved.

## Innovations

Every response contains a normal `SciAgentDecision` plus a deterministic
`DecisionGroundingCertificate`. The certificate must bind the selected mode and
skill to the current evidence ID, enumerate only allowlisted memory/probe IDs,
name one registered grounding claim, and identify the alternative skill when a
skill is proposed. The host, not the model, validates every binding.

Before environment collection the endpoint must pass one synthetic ABSTAIN
health-check. Requests are keyed by a canonical SHA-256 fingerprint; an exact
read-only duplicate is served from the in-process response cache without a new
API call. Two consecutive logical failures open a circuit breaker and all later
requests fail closed without consuming API budget.

## Population and calls

After a valid health-check, scan seeds 5850--5899 in ascending order until eight
failed initial rollouts have valid 64-step repeated-probe evidence. The GLM sees
only compact Agent-visible evidence and an empty memory snapshot. It may propose
direct action, one registered micro-probe, or abstention, but no proposal is
executed.

The immutable budget is nine primary calls (one health-check plus eight cases),
one global schema repair, ten total calls, zero transport retries. Missing
credentials or failed health-check stops before any fresh seed is consumed.

## Gate and claim boundary

Promotion requires a valid health-check, eight operational payloads, at least
seven valid grounded certificates, grounded-output rate at least 0.875, at most
one fail-closed output, at most one repair, and zero leakage, unknown-ID,
continuous-action, execution, memory-write, or budget violations.

Passing authorizes only a separately frozen online-execution protocol. Failure
is preserved without prompt repair, schema relaxation, seed extension, model
replacement, or threshold tuning. No recovery-success statement is permitted.
