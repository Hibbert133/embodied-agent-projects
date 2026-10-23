# ProbeMem Verifier Demo v1

Status: `DEMO_FROZEN_BEFORE_EXECUTION`

## Question and claim boundary

This engineering/research feasibility demo asks whether a history-aware
verifier can be admitted selectively and override the frozen repeated-probe
variance rule only under conservative, preregistered evidence conditions. It
is not a validation, held-out, statistical-superiority, policy-learning, or
general memory-improvement experiment.

The frozen variance rule, registered repeated probe, compact evidence,
registered skill semantics, action-conditioned memory, skill implementations,
and fresh verification are reused without retuning.

## Fresh population

The run may scan seeds 4700--4749 exactly once, in ascending order, and stops
after 30 operational failed initial rollouts or all 50 units. Seeds 4750--4799
remain reserved. The registered regime assignment cycles A, B, C, D and is
evaluator-only. Every eligible failure is retained; no outcome-dependent case
filtering or seed replacement is permitted.

Fewer than 20 operational cases is `INCOMPLETE_POPULATION`. Eight exclusive-
recovery cases is a descriptive target, not a stopping or exclusion rule.

## Frozen methods

The deterministic proposal uses threshold `0.11560838098372882` and confidence
margin `abs(score - threshold)`. The admission gate calls the verifier when the
margin is at most `0.05`, global and recent memory preferences conflict with
positive coverage, or the nearest action-conditioned record is also in the
recent window and has a rejected outcome.

The deterministic verifier evaluates compensation and retry separately with a
Beta(1,1) prior. Accepted contributes one success, rejected one failure, and
inconclusive contributes one half to both. Candidate status is accepted at
probability at least 0.70, rejected at probability at most 0.30, and otherwise
inconclusive. Candidate confidence is its predicted acceptance probability.

An alternative overrides the frozen default only when all are true:

* its probability is greater by at least 0.15;
* its nearest-history coverage is at least three records;
* its rejected fraction is at most 0.30;
* global and recent preferences are non-tied and both prefer the alternative;
* its verifier confidence is at least 0.70.

Otherwise the method executes the frozen default. Invalid evidence, memory,
IDs, verifier output, timeout, or unavailable GLM fails closed to that default.

Methods are Frozen Deterministic, Always-on Verifier, Budgeted Verifier, and an
Evaluator-only Oracle. The registered run uses the deterministic verifier. A
GLM verifier is an optional interface smoke only and is not called in the
registered run.

## Chronology and paired evaluation

All operational methods share initial evidence, repeated probe evidence, and a
paired evaluator candidate collection. Every method writes its final selection
before either candidate outcome is collected. Each method owns a separate
chronological memory and appends only its selected action outcome after fresh
verification. The alternative paired outcome is evaluator-only and can never
enter an Agent payload or operational memory. Oracle never retrieves or writes
memory.

Successful initial rollouts require no decision. Failures for which both
registered candidates are not constructible are retained in the population
ledger as ineligible rather than silently omitted.

## Integrity and success

Integrity requires zero chronology, Oracle leakage, future-memory,
counterfactual-write, budget, invalid-ID, and invalid-skill violations. The
Budgeted Verifier call rate must be at most 50%. In addition, either:

1. Budgeted recovery is at least Frozen recovery and helpful overrides exceed
   harmful overrides; or
2. Budgeted recovery is no more than one case below Always-on recovery while
   reducing verifier calls by at least 50%.

No override, excess harmful overrides, gate failure, or incomplete population
is retained and reported without modifying thresholds or reusing these seeds.
