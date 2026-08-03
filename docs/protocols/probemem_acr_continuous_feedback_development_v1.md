# Prospective Continuous Verification Feedback Development v1

Status: frozen before execution. This protocol follows the feedback-sufficiency
audit but does not reuse its outcomes for threshold fitting.

## Question and frozen rule

Can a physical no-progress boundary prospectively allocate the second recovery
action better than fixed second-action policies?

```text
first retry ACCEPTED          -> STOP_SUCCESS
first observed progress > 0   -> REPEAT_STOCHASTIC_RETRY
first observed progress <= 0  -> SWITCH_TO_BOUNDED_COMPENSATION
```

The threshold is exactly zero metres. It represents forward versus absent or
negative task progress and was not selected by optimizing the preceding audit.
It cannot be changed after execution.

## Population and execution

Scan fresh seeds 3500--3799 under `fault_05` and stop after 30 non-accepted
first retries. The previously reserved 3500--3599 block is explicitly reassigned
to this new versioned development protocol. Seeds 3800--3899 and held-out seeds
3100--3199 remain untouched.

Every eligible case executes the same initial rollout, registered probe, and
first retry. Non-accepted cases receive evaluator-only paired repeat and switch
rollouts using identical random streams and independent resets. Agent decisions
are persisted before paired outcomes. Maximum deployable flow is one initial,
one probe, one first verification, and one optional second verification.

## Evaluation and boundary

Compare one retry, always-repeat, always-switch, the historical frozen status
rule, the zero-progress rule, and evaluator-only Oracle. Report accepted
recovery, harmful selection, attempts, environment steps, distance, paired
win/tie/loss, and 10,000-sample paired bootstrap intervals.

Completion requires 30 second-decision cases and zero violations. Promotion
requires recovery not below the strongest fixed policy and harmful selections
not above it; a recovery tie additionally requires strictly lower cost or harm.
Failure is retained. This is development evidence only and cannot authorize GLM,
memory, validation, held-out execution, or an online-learning claim.
