# ProbeMem-ACR Resonance Validation v1

Status: frozen before execution. This independently validates the attempt-level
status rule produced by development run
`acr_resonance_20260802T142610Z_af2acb3b380b`.

## Frozen rule

```text
ACCEPTED     -> STOP_SUCCESS
INCONCLUSIVE -> REPEAT_STOCHASTIC_RETRY
REJECTED     -> SWITCH_TO_BOUNDED_COMPENSATION
```

The status definition, interventions, fault, probe, budgets, and rule cannot be
changed after validation outcomes are observed.

## Population

The immutable population contains exactly 150 initial units in this order:
3050--3099 followed by 3200--3299. All units run; there is no early stopping.
Seeds 3100--3199 remain untouched held-out data.

Eligibility is established before any verification outcome: the initial
rollout failed and bounded compensation is constructible from Agent-visible
registered-probe evidence. Initial successes and ineligible failures remain in
the audit. Validation is complete only with at least 60 eligible first attempts
and 25 second-decision cases; otherwise it is `INCOMPLETE_FOR_VALIDATION` and
cannot be repaired by replacing or adding seeds.

## Execution and information boundary

Every eligible case executes a fixed retry. `ACCEPTED` stops. After a non-
accepted result, evaluator collection runs repeat-retry and switch-compensation
from independent resets of the same task initialization with the same paired
second-verification stream. Candidate order cannot alter state or randomness.

Agent methods see only causal first-verification feedback. They cannot see the
unselected outcome, Oracle winner, perturbation truth, future episode, or
evaluator labels. Online execution permits two recovery verifications and 1564
steps; paired evaluator collection permits 2064 steps.

## Evaluation and promotion

Compare one retry, always repeat, always switch, frozen status conditioning,
rejection-abstain, and per-case Oracle. Report recovery, incremental recovery,
harmful selection, attempts, final distance, environment steps, recovery per
additional 100 steps, status strata, paired win/tie/loss, and paired-bootstrap
confidence intervals.

The strongest fixed baseline is selected by recovery, then fewer harmful
selections, fewer steps, and method name. All integrity counters must be zero.
Status conditioning must have recovery no lower and harmful selections no
higher. If recovery ties, it must strictly improve total steps, second attempts,
or harmful selections.

The run is immutable regardless of outcome. Only promotion may authorize a
separately frozen GLM development protocol. This validation cannot call an API,
write memory, promote principles, execute held-out seeds, or claim online
learning.
