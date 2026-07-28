# Day 3 GLM-5.1 Recovery Pilot

## Status

This is a single-seed integration pilot, not a statistically supported comparison.
All numbers below were read from the real CSV, audit JSONL, and schema-v2 trajectories
generated on 2026-07-28. No result was manually edited.

## Setup

- Task: MetaWorld `push-v3`
- Seed: 148
- Hidden experimental perturbation: single-axis `+x` bias, magnitude `0.145`
- Planner: `glm-5.1` through an Anthropic-compatible ModelArts endpoint
- Prompt: `push-recovery-v1`
- Total rollout budget: 5
- Maximum steps per rollout: 500
- Candidate corrections: fixed x/y offsets from the approved discrete grid
- Planner input: schema-v2 Agent-visible evidence only

## Real Results

| Trial | Correction | Success | Steps | Return | Final object-goal distance (m) | Progress to goal (m) | Clipped-step fraction |
|---:|---|:---:|---:|---:|---:|---:|---:|
| 1 | none | no | 500 | 127.7693 | 0.246488 | 0.023273 | 10.0% |
| 2 | +x 0.145 | no | 500 | 48.5347 | 0.269777 | -0.000016 | 0.0% |
| 3 | +x 0.060 | no | 500 | 49.1041 | 0.269756 | 0.000004 | 0.0% |
| 4 | +x 0.020 | no | 500 | 168.1286 | 0.222284 | 0.047477 | 8.0% |
| 5 | +x 0.040 | no | 500 | 106.8983 | 0.444517 | -0.174756 | 13.8% |

Overall success was false after 5 trials and 2500 environment steps. Trial 4 was the
best attempted correction by final distance, improving from 0.246488 m to 0.222284 m,
but it did not recover the task. Trial 5 then degraded substantially.

The four model calls used 14,757 input tokens and 13,279 output tokens. Mean observed
latency was 102.46 seconds per call. No monetary cost is reported because a verified
provider price was not recorded with this run.

## Interpretation

The planner made evidence-responsive decisions: after large positive corrections
prevented the gripper from approaching the object, it reduced the magnitude to 0.02,
then tested the intermediate 0.04 level. This demonstrates a functioning rollout-level
observe-propose-test loop.

However, the planner inferred the wrong correction direction. The hidden audit bias was
positive x, while every proposed correction was also positive x. This is a legitimate
failure under the leakage-free Agent View, not an execution error. It also exposes a
design limitation: a constant correction is active during both the approach and push
phases. Larger corrections can prevent contact before their effect on pushing can be
evaluated.

## Integrity Checks

- All 5 JSONL files use schema version 2.
- All 2500 transitions passed Agent View projection and state-continuity validation.
- No injected bias field, perturbed action, executed action, or clipping field was sent
  to the planner.
- Oracle-only clipping statistics were calculated after the experiment for audit.
- The environment completed normally; the failure was not caused by an exception.

## Limitations and Next Experiment

- One seed cannot support a performance claim or comparison with random/rule baselines.
- The prompt may encourage reasoning from mean action without enough system-identification
  evidence to determine the sign of an unknown control bias.
- Constant whole-rollout compensation confounds approach-phase and push-phase effects.
- The next controlled ablation should compare whole-rollout correction with a
  contact/progress-gated correction using the same seeds and budget. This is an Agent
  action-timing interface, not failure diagnosis, memory, RL, or policy training.

## Representative Videos

The video rerun is recorded separately from the timing pilot because rendering changes
wall-clock time. Its real per-trial CSV and audit log are stored as
`outputs/recovery/glm51_seed148_video_retry.csv` and
`outputs/recovery/glm51_seed148_video_retry_audit.jsonl`.

Two cases were selected by fixed rules rather than visual preference:

- `glm51_seed148_initial_failure.mp4`: initial uncorrected trial;
- `glm51_seed148_best_attempt_x_positive_0.02_failure.mp4`: recovery trial with
  the minimum final object-goal distance.

Both cases are failures. The manifest preserves their seed, correction, result, distance,
selection rule, and source CSV.
