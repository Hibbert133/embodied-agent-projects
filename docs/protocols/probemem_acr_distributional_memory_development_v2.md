# ProbeMem-ACR Distributional Memory Development v2

Status: `FROZEN_BEFORE_EXECUTION`

## Rationale

Development v1 exhausted 100 preregistered initial units with 39 eligible
failed cases, one below its required operational population. That immutable
run remains `INCOMPLETE_POPULATION`; it is not extended or replayed.

V2 repeats the same deterministic scientific test with fresh seeds and a
larger initial population. It changes no estimator, exploration schedule,
abstention threshold, promotion criterion, candidate skill, or operational
target. The only design correction is population capacity.

## Population and stopping rule

- development seeds: 2200--2349;
- validation seeds 2350--2399: reserved and unauthorized;
- held-out seeds 2400--2499: reserved and unauthorized;
- target: 40 Agent-visibly eligible failed `fault_05` cases;
- maximum: 150 initial units;
- stopping rule candidate-outcome reads: forbidden.

Eligibility requires an initial failure and both registered interventions to
be constructible before either candidate outcome is executed or read.

## Frozen chronological replay

For method `m` and operational episode `t`:

```text
decide from outcomes of interventions selected by m at episodes < t
-> reveal the selected outcome at t
-> append only that outcome to m's history
```

The paired unselected candidate is evaluator-only. Rejected and inconclusive
outcomes may update the action posterior but are not actionable episodes and
cannot be copied into verified memory or promoted to principles.

The five methods, eight-episode alternating exploration, Dirichlet(1,1,1)
prior, utility `P(A) + 0.5 P(I)`, 20,000 posterior samples, 0.90 superiority
threshold, metrics, and promotion routes are identical to v1.

## Claim boundary

This is a paired development feasibility study. It cannot support an online
learning, LLM-memory, validation, held-out, or principle-learning claim. Gate
failure or another incomplete population is preserved without retuning or seed
extension.
