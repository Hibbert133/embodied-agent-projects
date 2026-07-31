# ProbeMem Coverage-Aware Verified Memory Development v1

## Question

Can an accepted-only episodic memory avoid the dogmatic errors observed in raw
nearest-reference retrieval by abstaining outside historical coverage or when
nearby verified episodes recommend conflicting skills?

This is a Phase-C development extension, not principle memory or held-out
evaluation.

## Frozen memory gate

The immutable 13-record accepted-only snapshot is the only retrieval source.
All normalization and coverage statistics are computed from that snapshot
without query outcomes:

1. standardize 13 Agent-visible features using snapshot population standard deviation;
2. compute each historical record's leave-one-out nearest distance;
3. freeze the coverage radius at the nearest-rank 90th percentile;
4. retrieve the three nearest verified episodes;
5. use memory only when the query is within coverage and all three skills agree;
6. otherwise `ABSTAIN`;
7. also `ABSTAIN` unless 500 fresh-verification steps remain reserved.

The gate may select only a registered discrete intervention. It cannot alter
continuous parameters or inspect perturbation truth, candidate outcomes, or
counterfactual labels.

## Fresh development stream

- Seeds 980--1059 are a new development extension.
- Held-out seeds 900--979 remain untouched.
- Registered condition: `fault_05`.
- Stop at 20 paired operational cases or 80 initial units.
- Stopping depends only on paired executability, never outcome.

Paired candidates are executed for evaluator comparison under common random
numbers. The memory gate is evaluated as if only its selected candidate were
online; abstention executes neither candidate online.

## Gate and claim boundary

The registered gate requires at least five memory-use decisions, at least 75%
accepted verification among uses, wrong-memory application at most 20%, zero
leakage, and zero budget overrun. A failed result is retained without changing
coverage quantile, neighbor count, agreement, features, or seed stream.

Passing would support only a development coverage-aware episodic retrieval
candidate. It would not promote Phase D principles, prove long-term
self-improvement, or authorize held-out tuning.
