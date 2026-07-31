# Noise-Stratum Intervention Utility Development Protocol v1

## Question

The completed identifiability audit found that stable-bias failures consistently
preferred compensation, while stochastic-noise failures contained both retry-
preferred and compensation-preferred cases. This extension asks:

> Does existing Agent-visible evidence show any separability between those two
> outcome-derived utility groups inside the registered stochastic-noise stratum?

It does not design or fit a selector.

## Population and execution

- Development seeds: 410--429, disjoint from all frozen seeds 330--339 and the
  preceding development seeds 400--409.
- Registered condition: `fault_05` only, with the unchanged calibrated noise.
- Initial policy, probe, candidates, random namespaces, and utility ordering are
  unchanged from intervention-identifiability v2.
- Only failed initial rollouts form the operational population.
- `ABSTAIN` remains candidate unavailability, never an executable action.

## Evaluator label

`retry_preferred` is true only when stochastic retry strictly outranks
probe-grounded compensation under matched fresh verification. It is computed
after both candidate outcomes exist, is excluded for ties or unavailable
candidates, and is Oracle audit only.

## Preregistered Agent-visible scores

All score directions are frozen before execution:

| Score | Direction predicting retry preference |
| --- | --- |
| phase inconsistency | higher |
| temporal uncertainty | higher |
| probe estimated-bias standard-deviation norm | higher |
| probe relative bias standard deviation | higher |
| probe mean estimation residual | higher |
| one minus dominant-axis sign agreement | higher |

The analysis reports label prevalence, feature medians by label, ROC AUC, and PR
AUC. It does not choose a threshold, combine features, train a classifier, or
select favorable score direction after seeing results. Single-class labels are
reported as incomplete rather than assigned a synthetic AUC.

## Claim boundary

This is an exploratory development characterization. Even a high single-feature
AUC cannot support an online selector claim without a separately frozen rule and
new held-out evaluation. Negative separability is retained and blocks that route.
