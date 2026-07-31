# Structured Evidence Schema v1

## Purpose

`StructuredEvidenceState` is the only structured state accepted by the frozen
deterministic allocation layer. It is derived from contiguous schema-v2 Agent
View transitions after an attempt completes. It contains no perception-confidence
claim and no Oracle fault information.

## Top-level provenance

| Field | Source | Unit | Available at decision time | GLM allowed |
|---|---|---:|---|---|
| `schema_version` | frozen schema constant | none | yes | yes |
| `evidence_id` | campaign-generated identifier | none | yes | yes |
| `source` | attempt type | none | yes | yes |
| `episode_id` | trajectory Agent View | none | yes | yes |
| `attempt_id` | attempt-level state machine | none | yes | yes |
| `seed` | experiment provenance | none | yes | no by default |
| `decision_required` | observed rollout success | boolean | yes | yes |
| `environment_step_cost` | transition count | steps | yes | yes |
| `parent_evidence_ids` | earlier Agent evidence | none | yes | yes |
| `historical_verified_case_count` | earlier accepted records only | count | yes | only in memory experiment |
| `missing_evidence` | unavailable registered evidence | none | yes | yes |

Seed is retained for reproducibility but is excluded from model reasoning payloads
unless a future frozen protocol demonstrates why it is needed.

## Task state

All geometry is derived from MetaWorld 3.1.1 `push-v3` observations using the
verified indices documented in `src/task_metrics.py`. Metrics use
`next_observation` and are therefore aligned to the post-action state.

| Field | Source | Unit | Available | GLM allowed |
|---|---|---:|---|---|
| `final_object_goal_distance` | final object/goal positions | metres | yes | yes |
| `minimum_gripper_object_distance` | minimum over completed transitions | metres | yes | yes |
| `object_displacement` | final versus initial object position | metres | yes | yes |
| `progress_to_goal` | initial minus final object-goal distance | metres | yes | yes |

## Temporal response

The per-axis model is
`gripper_delta = response_gain * commanded_action + estimated_drift`. It reads
only `observation`, `commanded_action`, and `next_observation`.

| Field | Source | Unit | Available | GLM allowed |
|---|---|---:|---|---|
| `response_gain_xy` | least-squares response fit | metres/action-unit | yes | yes |
| `estimated_drift_xy` | fit intercept | metres/step | yes | yes |
| `normalized_residual_xy` | fit RMSE / observed response std | ratio | yes | yes |
| `action_excitation_xy` | commanded-action std | action units | yes | yes |
| `uncertainty` | one minus mean visible fit confidence | [0,1] | yes | yes |
| `sample_count` | fitted transitions | count | yes | yes |

This uncertainty is a deterministic response-fit score, not calibrated pose or
perception uncertainty.

## Phase-conditioned response

Phases are classified from current Agent-visible geometry before each action:
near-goal if object-goal distance is at most 0.08 m, otherwise push if
gripper-object distance is at most 0.08 m, otherwise approach.

| Field | Source | Unit | Available | GLM allowed |
|---|---|---:|---|---|
| `phase_inconsistency` | eligible-sample-weighted phase residual | ratio | yes | yes, but no threshold |
| `eligible_sample_fraction` | samples in phases with at least eight transitions | ratio | yes | yes |
| `sample_counts` | phase assignment counts | count | yes | yes |
| `normalized_residual_norms` | within-phase response fit | ratio or null | yes | yes |

The frozen allocation threshold is never serialized into this state or a GLM
payload.

## Explicitly forbidden

Direct or nested occurrences of Oracle-only keys fail closed, including injected
condition/fault labels, bias axis/sign/magnitude, perturbation parameters,
perturbed/executed action, clipping fields, future verification outcomes, and
evaluator-only probe-need labels.

`repeat_consistency` is reported as missing for an initial failed rollout. It is
populated only by the registered probe in a later evidence packet; it is not
inferred from Oracle perturbation type.
