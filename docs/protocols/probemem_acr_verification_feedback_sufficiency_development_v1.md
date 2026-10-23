# Verification Feedback Sufficiency Development Audit v1

Status: frozen before execution. This is a new development-only mechanism audit
and does not alter the failed independent validation or earlier artifacts.

## Question

Is one categorical first-retry verification status stable across independent
execution realizations of the same failed task state? If not, do the two
preregistered continuous measures—observed progress and negative final
object-goal distance—contain descriptive signal about which registered second
intervention is exclusively successful?

This audit diagnoses an evidence abstraction failure. It does not fit a rule,
select a threshold, create online memory, or support a recovery claim.

## Population and chronology

Scan fresh development seeds 3300--3499 under registered `fault_05` and stop
label-blind after 30 initial failures for which bounded compensation is
constructible from registered-probe evidence. Seeds 3500--3599 and existing
held-out seeds 3100--3199 must not be executed.

Persist initial and probe evidence before outcomes, then execute four independent
first stochastic-retry realizations. An ACCEPTED first retry ends that branch.
For each non-accepted realization, execute both evaluator-only second candidates
from independent resets. Within a realization, repeat retry and switch
compensation share the same paired verification random stream. Candidate order
cannot share simulator state. The stopping rule cannot read outcomes.

## Frozen analysis

Report per-state modal first-status share, mixed-status state fraction, status
transition counts, candidate-winner reversals, and repeat/switch acceptance by
first status. Evaluate raw ranking AUC on exclusive-recovery branches for exactly
`first_observed_progress` and negative `first_final_object_goal_distance`.
Neither orientation nor threshold may be optimized after collection.

Completion requires 30 eligible states, 30 non-accepted branches, 12 exclusive
second-recovery branches, and zero integrity violations. Instability is flagged
when mean modal share is at most 0.75 or at least 30% of states contain multiple
first statuses. A continuous signal is only a candidate for a future prospective
protocol when its raw AUC is at least 0.70 with at least 12 exclusive branches.
This never authorizes a selector, GLM, memory, validation, or held-out run.
