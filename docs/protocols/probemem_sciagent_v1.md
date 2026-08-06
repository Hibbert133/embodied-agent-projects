# ProbeMem-SciAgent v1

Status: `DEMO_FROZEN_BEFORE_EXECUTION`

## Question and immutable history

This development-only stage asks whether an online recovery Agent can organize
selected-action experience into testable hypotheses, request one bounded
action-conditioned probe when evidence is insufficient, and use only
deterministically promoted scoped principles in later decisions. ProbeMem Online
v4, Verifier Demo v1, and Calibrated Verifier v2 artifacts are immutable inputs
and are not regenerated or reinterpreted.

The Demo uses fresh seeds 5300--5349 in ascending order and stops at 15 failed
operational cases or exhaustion. It is incomplete below ten. Calibration seeds
5350--5449, prospective-development seeds 5450--5649, and reserved seeds
5650--5849 are not authorized by this Demo protocol.

## Causal online order

For each failed initial rollout the host collects the frozen 64-step repeated
directional probe, builds compact Agent evidence, retrieves only earlier memory,
and persists the first GLM decision. The Agent may act, abstain, or request one
registered micro-probe. A probe request must contain a provisional skill and an
explicit evidence-gap code. After a probe, a second decision is mandatory and
cannot request another probe. The final selected action is persisted before any
candidate outcome is executed.

Fresh verification uses a reset and an independent random namespace. A paired
alternative may be collected only after the final decision for evaluator audit.
Only the selected result reaches the Agent, Experience Memory, hypothesis
updates, or principle updates. Knowledge updates occur after verification and
cannot alter the already persisted decision.

## Memory and promotion

Experience Memory stores every selected recovery outcome, including accepted,
inconclusive, and rejected outcomes. Hypotheses are non-actionable and may guide
future tests. A new post-outcome hypothesis treats its source episode as
induction evidence, not verification support.

The deterministic host promotes a hypothesis only with at least three distinct
seeds, four accepted supports, no more than one contradiction, support rate at
least 0.75, at least one matched targeted verification, and a most-recent result
other than rejected. Only ACTIVE principles are actionable. One rejected result
while an ACTIVE principle is cited restricts it; two contradictions or support
rate below 0.75 suspend it. The model cannot promote, reactivate, or retire a
principle.

## Probes and budget

`COMPENSATION_RESPONSE_PROBE` runs one 64-step registered compensated prefix.
`RETRY_REPEATABILITY_PROBE` runs three independent 64-step nominal prefixes.
All prefixes begin from matched resets and use independent perturbation streams;
they are local evidence rather than counterfactual winners. The formal recovery
resets again. Maximum case cost is 500 initial + 64 mandatory probe + 192 optional
probe + 500 verification = 1256 online environment steps.

## GLM and fail-closed behavior

The GLM receives only compact Agent-visible evidence, registered skill/probe
semantics, bounded earlier memory summaries, and remaining budget. It never sees
fault identity, perturbation parameters, the frozen deterministic threshold,
Oracle winners, unselected outcomes, or future memory. Invalid schema, timeout,
unknown IDs, continuous actions, budget exhaustion, or call exhaustion returns
ABSTAIN. The host does not silently substitute the frozen rule.

The live Demo allows at most 45 primary calls, 15 schema repairs, and 60 total
calls with no transport retry. Missing credentials block execution before any
fresh seed is consumed.

## Claims and case presentation

The Demo tests integration and information integrity, not performance or online
learning. Natural cases are never selected or extended to satisfy presentation
targets. Missing direct-action, probe, probe-change, or principle-restriction
paths may be shown only in a separately labeled synthetic integration audit and
are excluded from all research metrics.
