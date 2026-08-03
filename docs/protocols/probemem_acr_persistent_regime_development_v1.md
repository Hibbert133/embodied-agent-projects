# Persistent Execution-Regime Development v1

## Motivation

The independent-noise experiments showed that one stochastic retry does not
predict the next realization. This protocol changes the causal question without
changing the task or low-level policy: can Agent-visible evidence distinguish
intervention utility when an execution property persists across attempts?

## Population

Fifty fresh task seeds `3900--3949` are crossed with two existing registered
conditions: `fault_01` stable x bias and `fault_05` calibrated stochastic noise.
This creates exactly 100 initial units. Condition identity and parameters persist
through initial rollout, registered probe, and paired verification. Initial,
probe, and verification random namespaces remain independent. Seeds 3950--3999
are reserved and held-out seeds 3100--3199 remain untouched.

## Frozen Agent decision

Failed initial rollouts receive the existing 64-step repeated symmetric probe.
The decision uses only `consistency.estimated_bias_std_norm` and the historical
registered outcome-classifier threshold `0.11560838098372882`, imported without
retuning:

```text
score > threshold  -> INDEPENDENT_STOCHASTIC_RETRY
otherwise          -> BOUNDED_PLANAR_COMPENSATION
```

Both candidate verifications are evaluator-only paired counterfactuals and
start from independent resets with the same task seed and paired perturbation
stream. The Agent decision is persisted before either outcome exists.

## Gate and claim boundary

The run requires at least 30 operational failures, at least 10 per condition,
and at least 12 exclusive-recovery cases. Promotion requires at least 75%
selection accuracy on exclusive cases, no more than one accepted case below the
strongest fixed candidate, and no greater harmful-selection count.

Passing establishes only that a persistent-regime benchmark has identifiable
action utility and authorizes a fresh development GLM action-selection ablation.
It is not a GLM, memory, validation, held-out, or generalization result. Failure
is preserved without threshold tuning.
