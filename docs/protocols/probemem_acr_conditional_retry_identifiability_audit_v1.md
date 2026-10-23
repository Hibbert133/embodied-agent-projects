# Conditional Retry Identifiability Audit v1

## Question

The earlier feedback-sufficiency audit reported a marginal progress AUC on
evaluator-only exclusive branches. That statistic may reflect differences in
fixed task-state difficulty rather than information carried by the realized
first retry. This audit asks:

> Within the same initial state, does better first-retry feedback predict that
> an independently seeded second retry will be accepted?

It reads the immutable repeated-realization development run and performs no new
rollout. The second-retry outcome remains evaluator-only.

## Frozen analysis

The population contains non-accepted first-retry branches with a complete paired
stochastic-retry outcome. Scores are oriented before analysis: higher first
progress, lower first final distance, and `INCONCLUSIVE` rather than `REJECTED`
mean greater predicted retry value.

Conditional AUC compares every positive-negative branch pair only when both
belong to the same `episode_id`. States without both outcome classes contribute
no conditional pair. A 10,000-resample, fixed-seed, one-sided permutation test
shuffles labels within state, preserving state membership and prevalence.

## Boundary

This is a causal-structure audit, not a selector. It cannot choose a threshold,
add a feature after seeing results, claim online learning, call an LLM, write
memory, or authorize validation/held-out execution. If marginal signal vanishes
after state stratification, the correct interpretation is that single-attempt
feedback does not predict the independent random realization under this
protocol.
