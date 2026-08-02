# ProbeMem-ACR Resonance-Triggered Second Verification Development v1

Status: frozen before execution. This is a new development-only protocol and
does not alter any earlier ACR protocol or artifact.

## Question

After a fixed stochastic retry has been freshly verified, can its Agent-visible
status justify one additional recovery attempt and determine whether to repeat
retry or switch to bounded planar compensation? This tests causal use of fresh
verification feedback, not learned memory, LLM reasoning, or step-level control.

## Population and chronology

The campaign scans seeds 2850--3049 under registered condition `fault_05` and
stops after 30 cases whose initial rollout failed, compensation was constructible
from registered-probe evidence, and the first retry was not `ACCEPTED`. Seeds
3050--3099 and 3100--3199 are reserved and must not be executed.

For each eligible initial failure the immutable order is:

1. initial rollout (at most 500 steps);
2. registered diagnostic probe (at most 64 steps);
3. fixed retry fresh verification (at most 500 steps);
4. if retry is non-accepted, evaluator-only paired second candidates from
   independent resets and the same second-verification random stream.

The first verification stream is independent of initial, probe, and second
verification streams. The two second candidates share the paired stream and
cannot affect each other's state. The stopping rule may read the first status,
which is online causal feedback, but cannot read either second outcome.

## Frozen methods

`single_retry` stops after the first verification. `repeat_retry` always repeats
retry after non-acceptance. `switch_compensation` always switches.
`status_conditioned` repeats after `INCONCLUSIVE` and switches after `REJECTED`.
`rejection_abstain` repeats after `INCONCLUSIVE` and abstains after `REJECTED`.
`oracle_second` is evaluator-only and chooses by status utility, then progress,
then lower interaction cost.

No method may request attempt 3. Online cost is capped at 1564 steps. Paired
development collection may consume 2064 because it executes both evaluator-only
second candidates; this is not deployable Agent experience.

## Evaluation and promotion

Report full-stream accepted recovery, incremental recovery beyond the first
retry, second-attempt count/rate, environment steps, harmful second selection,
missed recoverable abstention, first-status strata, and paired bootstrap
confidence intervals.

Integrity requires at least 30 second-decision cases and zero chronology,
Oracle-leakage, namespace, and budget violations. Promotion requires either:

* status-conditioned recovery exceeds the stronger always-repeat/always-switch
  policy by at least two cases; or
* rejection-abstain recovery is within one case of that fixed policy while reducing
  second attempts by at least 25% and strictly reducing total steps.

Failure is preserved. This protocol cannot authorize GLM, memory principles,
validation, held-out execution, or online-learning claims.
