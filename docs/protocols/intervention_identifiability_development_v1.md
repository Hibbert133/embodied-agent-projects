# Intervention Identifiability Development Protocol v1

## Motivation

The frozen P1 experiment showed that a registered probe can change mechanism
belief and the subsequent intervention without improving fresh verification.
The next question is therefore narrower than designing another Agent:

> Is the evaluator mechanism class itself sufficient to identify which bounded
> intervention has higher utility on a particular failed rollout?

This is a development-only falsification study. It does not alter the immutable
seeds 330--339 artifacts, fit a new held-out rule, or promote the project to
Verified Episodic Memory.

## Population

The collection uses ten previously unused development seeds, 400--409, under
the same five registered execution conditions. All 50 initial rollout units are
retained for audit. Only failed initial rollouts are in the operational
intervention population.

## Paired candidate audit

Every operational unit receives the same registered 64-step diagnostic probe.
The evaluator then executes exactly two bounded candidates:

1. `probe_grounded_compensation`, parameterized only by the Agent-visible probe;
2. `stochastic_retry`, with zero deterministic correction.

Both candidates share task initialization and the same independent verification
perturbation seed. No candidate-specific probe is allowed. Candidate outcomes
are evaluator-only counterfactuals and cannot enter StructuredEvidenceState.

Candidate utility is ordered before execution as follows:

1. `ACCEPTED > INCONCLUSIVE > REJECTED`;
2. if both are accepted, fewer verification steps wins, followed by lower final
   object-goal distance;
3. if both fail with the same status, lower final object-goal distance wins,
   followed by fewer steps.

An exact equality is retained as a tie rather than broken by candidate name.

## Measurements

The audit reports recovery and final-distance outcomes, the empirical best
candidate, agreement of evaluator/passive/post-probe mechanism beliefs with
candidate utility, and belief/intervention/outcome changes. Results are also
stratified by registered condition and mechanism.

The outcome-derived best candidate is post-hoc Oracle audit. It must not enter
Agent View, probe selection, intervention selection, GLM payloads, or future
retrieval signatures.

## Interpretation boundary

This study diagnoses whether the P1 abstraction is adequate. It does not claim
that the Agent can predict intervention utility. If the same mechanism class
contains contradictory best interventions, future work must model
action-conditional utility on a new development split before any new held-out
test. Negative and ambiguous results are retained.
