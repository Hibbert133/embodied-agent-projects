# ProbeMem-ACR Distributional Memory Development v1

Status: `FROZEN_BEFORE_EXECUTION`

## Question

Can a chronological action-outcome posterior reduce harmful transfer relative
to accepted-only last-success memory, and can confidence-based abstention trade
recovery coverage for lower intervention risk?

The preceding utility-stability study showed that a single paired winner is an
unstable label. This protocol therefore estimates outcome distributions rather
than copying a single successful action.

## Causal replay

Collect one evaluator-only paired candidate outcome for each of 40 eligible
failed `fault_05` states from fresh seeds 2000--2099. The stopping rule sees no
candidate outcome. For each method and chronological episode `t`:

```text
decide from that method's selected outcomes at episodes < t
-> reveal only the selected current outcome
-> append only that selected outcome to that method's history
```

The unselected current candidate is evaluator-only. It is used to score harmful
transfer and missed opportunity but never enters method history.

Rejected and inconclusive executions may update Dirichlet outcome counts. They
are statistical evidence, not actionable episodic records and cannot be copied
as interventions or promoted to principles.

## Frozen methods

1. always compensation;
2. always retry;
3. accepted-only last successful selected action;
4. Dirichlet posterior-mean greedy;
5. Dirichlet posterior with abstention.

The three adaptive methods share eight fixed alternating exploration episodes.
Each action has prior `Dirichlet(1,1,1)` over accepted, inconclusive, rejected.
Utility is `P(A) + 0.5 P(I)`. The abstaining policy acts only when 20,000 frozen
posterior samples give one action at least 0.90 probability of superiority.

## Evaluation

Report full-stream and post-exploration accepted recovery, harmful transfer,
missed recoverable abstention, coverage, selected-action accepted precision,
verification and probe steps, posterior calibration, paired win/tie/loss, and
episode-clustered bootstrap intervals.

Promotion requires all integrity checks and one preregistered route: posterior
greedy gains at least three accepted cases over last-success memory without
more harmful transfer; or posterior abstention reduces harmful transfer by at
least 30% and two cases, improves covered precision by 10 points, and covers at
least 40% of post-exploration cases. Failure blocks GLM, validation, held-out,
and principle promotion.

This is paired development replay, not naturally available counterfactual
experience, policy learning, or a held-out online-deployment claim.
