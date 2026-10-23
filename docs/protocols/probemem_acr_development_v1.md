# ProbeMem-ACR Deterministic Development v1

## Population

Exactly 100 initial units use seeds 1100--1199. A seed receives exactly one of
the five registered faults using `(seed - 1100) % 5`, producing 20 units per
condition. Initial rollout, registered probe, and paired verification use
independent namespaces 8301, 8302, and 8303.

Only failed initial rollouts are operational. Both candidates start from
independent resets of the same task seed and share the paired verification
random stream. Candidate ordering cannot share environment state or advance
the other candidate's random stream.

## Chronology

For episode t, standardization and retrieval use unique episodes strictly less
than t. All method predictions are persisted before either candidate outcome
is executed. Only after both fresh outcomes are written are the two development
counterfactual records made available to episode t+1.

## Estimator

The feature order is the existing `INTERVENTION_APPLICABILITY_FEATURES` tuple.
Missing or non-finite values fail closed. Population standard deviation is
computed once per unique prior episode; values at or below `1e-12` use scale
1.0. Distance is standardized RMS.

For each action and outcome class, use the nearest five records, weight each by
`1/(1+distance)`, add Dirichlet prior one to each class, and normalize. The
predicted class is the largest posterior; any maximum tie predicts
INCONCLUSIVE. Action utility is `P(A)+0.5P(I)`. Each action needs at least three
total historical records. Equal action utilities abstain.

Progress is the distance-weighted mean of retrieved observed progress, where
observed progress is failed-initial final distance minus verification final
distance.

## Frozen baselines and evaluator

Baselines are always compensation, always retry, state-only nearest accepted
retrieval, the exact fixed v2 coverage-aware 13-record snapshot, and the frozen
single-feature selector. The coverage baseline never appends new stream data.

Status utility is ACCEPTED=1, INCONCLUSIVE=0.5, REJECTED=0. Oracle ordering is
status utility, then greater progress, then fewer verification steps; complete
ties remain ties. Exclusive recovery means exactly one ACCEPTED action. Harmful
transfer means selecting a non-ACCEPTED action when the other is ACCEPTED.

## Promotion

Integrity requires at least 40 operational cases, at least 12 exclusive cases,
and zero chronology, Oracle-leakage, or budget violations. In addition, ACR
must improve decisive accuracy over state-only retrieval by at least ten
percentage points and three cases, or reduce harmful transfer against the
strongest memory baseline by at least 30 percent and two cases. Accepted
recovery may trail the strongest fixed action by at most one case.

Abstentions are incorrect in full decisive accuracy. Conditional accuracy and
coverage are also reported. Main paired differences use 10,000 episode-level
bootstrap resamples with RNG seed 9301.
