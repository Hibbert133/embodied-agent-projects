# ProbeMem-Online Selective Override Development v1

Status: `DEVELOPMENT_FROZEN_BEFORE_EXECUTION`

## Motivation

Gate C showed that online Memory changed 12/60 Stateless GLM actions but did
not pass its promotion gate. The post-hoc, no-rollout causal audit found that
three of four helpful changes merely restored the already-correct frozen
variance action. All three harmful changes overrode high-variance retry
decisions after action-conditioned Memory favored compensation. Global and
recent Memory agreed in those harmful cases, so Memory agreement alone is not
a sufficient applicability condition.

This successor does not modify the Gate C prompt or rerun seeds 4300--4499. It
tests whether GLM and Memory are useful only when a strong physical rule is
measurement-ambiguous.

## Research question

> Can a budgeted embodied Agent preserve a high-confidence physical recovery
> rule while invoking GLM and action-conditioned Memory only when repeated-
> probe evidence is unstable to omission of one probe repetition?

The incremental claim concerns selective decision-layer assistance, not a
general Memory or LLM advantage.

## Fresh population

The run may scan seeds 4500--4599 once and stop at 40 operational failed
initial rollouts. Seeds 4600--4699 remain reserved. The four Mixed Persistent
Regime v2 conditions and their fixed cycle are unchanged. Condition and segment
identities remain evaluator-only.

If fewer than 40 operational or fewer than 10 ambiguous cases are obtained,
the run is incomplete and cannot be extended or replaced.

## Outcome-independent ambiguity definition

The frozen variance threshold remains `0.11560838098372882`. The registered
probe produces four independent Agent-visible bias estimates.

For each case, the host computes:

1. the registered score from all four repetitions;
2. four leave-one-repeat-out scores using the unchanged consistency function;
3. the frozen-rule action for every score.

The case is high confidence only when the full score and all four leave-one-out
scores select the same action. It is ambiguous when any leave-one-out action
differs. This is a measurement-stability definition, not a numeric band fitted
from the 12 Gate C matched outcomes. Missing or invalid repetitions fail closed
to the deterministic rule and are logged.

## Selective decision structure

```text
high-confidence frozen variance rule
        -> execute frozen deterministic action; no API call

ambiguous repeated-probe evidence
        -> call constrained GLM
        -> retrieve compensation and retry histories separately
        -> require global and recent action preference to agree
        -> allow a GLM override only when it matches that preference
        -> otherwise deterministic fallback or registered abstention
```

Global/recent agreement is defined without a new margin threshold: the sign of
`P_comp(ACCEPTED) - P_retry(ACCEPTED)` must be nonzero and identical for the
global and recent summaries. The summaries use the already registered memory
implementation. No nearest historical action is copied.

The primary operational policy uses deterministic fallback. A separately
reported abstention variant measures risk/cost tradeoff and is not substituted
after outcomes are observed.

## Methods

1. Frozen variance rule.
2. Ambiguity-gated Stateless GLM.
3. Ambiguity-gated action-conditioned Memory with deterministic fallback.
4. The same Memory gate with abstention on conflict.
5. Evaluator-only per-case Oracle.

All operational methods share initial state, repeated probe, registered skills,
and matched verification namespaces. Paired unselected outcomes are evaluator-
only and never enter Memory or a GLM payload. Episode `t` sees only selected
outcomes appended after episodes `< t`.

## Metrics

Report accepted recovery, helpful/harmful/tied overrides, override precision,
ambiguity rate, GLM call rate, API calls avoided, latency, tokens, abstention,
environment steps, post-shift recovery, and paired bootstrap intervals.

API efficiency is evaluated against calling all three registered GLM variants
(stateless, Memory fallback, and Memory abstention) on every operational case.
Warm-up and schema repair calls are reported separately.

## Promotion gate

Integrity requires zero chronology, Oracle leakage, budget, future-memory,
counterfactual-write, invalid-ID, and invalid-skill violations. Population
requires at least 40 operational and 10 ambiguous cases.

The primary selective-memory method must:

* make at least three more helpful than harmful overrides;
* recover at least as many cases as the frozen variance rule;
* reduce calls by at least 50% relative to two all-case GLM methods;
* have no more harmful than helpful overrides.

Failure is preserved without changing ambiguity semantics, the prompt, Memory
summaries, seeds, or gate. Passing authorizes only a separately reviewed next
development question; it does not authorize validation, held-out execution, or
principle generation.

## Claim boundary

The Gate C action-change audit is post-hoc mechanism localization. It does not
select a threshold or count as evidence for this method. This protocol is a
fresh development test of selective API and Memory use above a fixed physical
rule. It cannot establish cross-task generalization, policy learning, or a
general online LLM advantage.
