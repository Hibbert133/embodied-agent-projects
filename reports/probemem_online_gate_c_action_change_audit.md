# ProbeMem-Online Gate C Action-Change Causal Audit

## Scope

This audit uses only immutable artifacts from
`probemem_online_gate_c_20260803T095434Z_f346d23912a9`. It performs no new
environment rollout, GLM call, prompt change, memory update, or threshold fit.
For every changed action, it reconstructs the action-conditioned memory that
was available strictly before the current episode. Segment and matched outcome
fields are attached afterwards as evaluator-only annotations.

## Population

The full resonance Agent changed 12 of 60 Stateless GLM actions. Every change
was:

```text
INDEPENDENT_STOCHASTIC_RETRY -> BOUNDED_PLANAR_COMPENSATION
```

The matched effects were four helpful, three harmful, and five status ties.
Chronology violations were zero.

| Episode | Segment (evaluator only) | Effect | Variance score | Distance from frozen threshold | GLM memory margin |
|---:|---|---|---:|---:|---:|
| 28 | bias-dominant | helpful | 0.054 | 0.061 | 0.57 |
| 29 | bias-dominant | tie | 0.026 | 0.090 | 0.62 |
| 32 | bias-dominant | tie | 0.033 | 0.082 | 0.41 |
| 36 | bias-dominant | helpful | 0.043 | 0.073 | 0.51 |
| 39 | bias-dominant | helpful | 0.034 | 0.082 | 0.54 |
| 41 | bias-dominant | helpful | 0.140 | 0.025 | 0.49 |
| 46 | noise-dominant | tie | 0.478 | 0.362 | 0.27 |
| 51 | noise-dominant | tie | 0.391 | 0.275 | 0.37 |
| 53 | noise-dominant | harmful | 0.707 | 0.591 | 0.44 |
| 57 | noise-dominant | tie | 0.384 | 0.268 | 0.17 |
| 76 | mixed | harmful | 0.267 | 0.152 | 0.37 |
| 79 | mixed | harmful | 0.250 | 0.135 | 0.22 |

The frozen variance threshold is `0.11560838098372882`; scores above it select
retry and scores below it select compensation.

## What the helpful changes mean

Three of four helpful memory changes (episodes 28, 36, and 39) occurred far on
the compensation side of the frozen rule. These changes corrected Stateless
GLM disagreement but did not add capability beyond the deterministic physical
rule. Episode 41 is the only helpful change that overrode the deterministic
rule, and it is also the closest helpful case to the frozen boundary.

Therefore the observed `4 helpful` count overstates the incremental value of
Memory relative to the strongest deterministic baseline. The development run
contains one promising boundary override, not four demonstrated Memory gains.

## Why the harmful changes occurred

All harmful changes occurred on the retry side of the frozen rule and were not
close to the threshold. Their variance scores were 0.707, 0.267, and 0.250.
They appeared after the bias-dominant segment: one in noise-dominant and two in
mixed cases.

The retrieved action summaries nevertheless favored compensation:

| Episode | Comp global/recent accept | Retry global/recent accept | Comp contradictions | Retry contradictions |
|---:|---:|---:|---:|---:|
| 53 | 0.69 / 1.00 | 0.62 / 0.63 | 1 | 3 |
| 76 | 0.72 / 0.83 | 0.50 / 0.46 | 1 | 4 |
| 79 | 0.69 / 0.70 | 0.49 / 0.48 | 1 | 4 |

The GLM explicitly cited this apparent compensation support. It treated high
recent compensation success, moderate directional agreement, and low residual
as sufficient to override high response variance. Fresh verification rejected
all three compensation choices while the unselected retry was accepted.

This identifies a concrete failure mechanism:

```text
earlier compensation success
-> action-conditioned summaries favor compensation
-> GLM interprets partial directional structure as applicability
-> Memory overrides a high-confidence variance rule
-> harmful transfer after regime composition changes
```

Global/recent agreement alone would not block these errors: both scopes favored
compensation in every harmful case. A deterministic ambiguity guard is needed
before Memory is allowed to influence action.

## Feature contrast

Descriptively, helpful cases had lower median `estimated_bias_std_norm` (0.048)
and higher median `repeat_response_consistency` (0.747) than harmful cases
(0.267 and 0.474). Harmful cases also had greater initial progress and smaller
final distance. These groups contain only four and three cases, respectively;
the differences are diagnostic observations, not fitted decision features.

The GLM confidence margin did not reliably identify harm. Its median selected-
action probability margin was 0.525 for helpful changes and 0.370 for harmful
changes, while one harmful override still had a margin of 0.44. Model-reported
confidence therefore cannot be used as the sole override gate.

## Falsifiable successor hypothesis

The audit supports testing a narrower architecture:

```text
high-confidence frozen variance rule
        -> execute deterministic action without an API call

measurement-ambiguous variance evidence
        -> call GLM with action-conditioned Memory
        -> allow override only when global and recent summaries agree
        -> otherwise fall back to the deterministic rule or abstain
```

The ambiguity definition must be frozen without using these 12 matched
outcomes. No threshold is selected by this audit. A new development protocol
must use fresh seeds and must compare API cost as well as recovery and harmful
override rate.

## Claim boundary

This post-hoc development audit localizes a failure mechanism. It does not
establish that an ambiguity-gated GLM improves recovery, identify a deployable
band, validate Memory, or authorize validation, held-out execution, principle
generation, or prompt retuning.

Machine-readable records are stored under
`outputs/probemem_online/causal_audits/gate_c_action_changes_v1/`.
