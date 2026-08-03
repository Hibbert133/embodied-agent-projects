# Conditional Retry Identifiability Audit v1

## Provenance

This audit reads immutable development run
`acr_feedback_sufficiency_20260803T031147Z_dc82fef58e26`, manifest
`e7ee616e070af571479838f8719be1ff0e6da0e348026d463035e709af4e237a`.
It uses no new environment interaction and no API calls. Paired second outcomes
are evaluator-only counterfactual data.

## Why state stratification matters

A marginal score can look predictive because some initial task states are
easier than others. That does not show that the realized first retry contains
information about the next independently seeded retry. This audit therefore
compares accepted and non-accepted second outcomes only within the same initial
state.

## Results

The population contains 39 non-accepted first-retry branches from 22 initial
states. The independent paired retry was accepted in 24 branches and not
accepted in 15. Nine states contained both outcome classes, yielding 14
positive-negative within-state pairs.

| Registered score | Marginal ROC AUC | Within-state AUC | One-sided permutation p |
|---|---:|---:|---:|
| First observed progress | 0.494 | 0.500 | 0.589 |
| Negative first final distance | 0.539 | 0.500 | 0.590 |
| Categorical status | 0.517 | 0.500 | 0.662 |

No registered feedback signal ranks the independent retry outcome after fixed
initial-state differences are controlled. The effective within-state sample is
small, so this does not prove a universal null effect; it establishes that the
current data do not support a selective online rule.

## Research consequence

The simulator's retry random streams are independent across fresh resets. A
single realized retry can reveal that attempt's outcome, but the current scalar
feedback does not predict the next random realization. This explains why the
development status rule did not replicate and why successive threshold tests
failed.

Further work should introduce a causally persistent latent execution context
whose effect can be learned across attempts, or collect repeated evidence that
estimates an outcome distribution while charging its interaction cost. It
should not fit another threshold on these branches. GLM, Memory, validation,
and held-out execution remain blocked.
