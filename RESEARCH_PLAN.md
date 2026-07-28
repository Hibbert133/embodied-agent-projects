# Failure-Aware Self-Improving Embodied Agent — Research Plan

## Research Objective

Build a reproducible simulation study showing how a robotic agent can use
causally available trajectory evidence to understand controlled execution
failures, choose corrective experiments under a limited interaction budget, and
eventually reuse successful recovery experience.

The project is intended for embodied-AI and robotic-agent PhD applications. Its
value should come from a precise question, clean experimental hygiene,
interpretable ablations, honest negative results, and clear visual evidence—not
from code volume.

## Phase 0 — MetaWorld Baseline

**Status: completed**

Delivered:

- Python 3.10 CPU setup for MetaWorld 3.1.1 and MuJoCo;
- reproducible `push-v3` rollout with `SawyerPushV3Policy`;
- RGB-array MP4 rendering, JSONL trajectories, and CSV evaluation;
- fixed-seed baseline evaluation and installation checks.

Acceptance evidence: working demo video, real baseline CSV/JSONL, tested setup,
and documented commands.

## Phase 1 — Controlled Failure Generation

**Status: completed**

Delivered:

- masked action scale, Gaussian noise, and full-vector action bias;
- independent seeded NumPy generators;
- default protection of the gripper dimension;
- single-axis x/y positive/negative bias sweeps;
- reliable task-progress and action-clipping metrics;
- 20-seed scans and 50-seed validation of `+x 0.145`;
- representative success, failure, and near-success cases.

Key methodological result: controlled single-axis bias is more interpretable
than scalar broadcast disturbance and supports causal failure analysis.

## Phase 2 — Failure Evidence and Diagnosis

**Status: in progress**

Completed foundations:

- schema-v2 transition alignment;
- strict leakage-safe Agent View and audit-only Oracle View;
- observation-derived gripper/object/goal positions, distances, progress, and
  lateral drift;
- compact agent-visible episode evidence.

### Active diagnostic probe pilot

Hypothesis:

> A small symmetric probing budget can identify the axis and sign of an unknown
> additive control bias from agent-visible state transitions, reducing recovery
> search relative to blind trial-and-error.

Development seeds are fixed to `103, 107, 108, 144, 148`, spanning near,
moderate, and severe failures from the real 50-seed dataset.

Probe protocol:

- run after the initial failed rollout and before the first correction;
- reset to the same seed for each probe;
- execute `+x`, `-x`, `+y`, and `-y` commands of magnitude `0.2`;
- use 8 steps per probe with zero z and gripper command;
- estimate per-axis response gain, bias vector, dominant axis, direction,
  magnitude, residual, and confidence;
- compute exclusively from `observation`, `commanded_action`, and
  `next_observation`;
- count probe steps separately from full rollout steps.

Acceptance criteria concern implementation integrity, not a forced positive
result: deterministic reproduction, no Oracle leakage, correct synthetic tests,
real probe CSV, and honest sign/magnitude accuracy on the fixed seeds.

Implemented development evidence:

- four reset-controlled world-frame probes and symmetric-pair estimator;
- separate agent-visible transition and Oracle audit tables;
- causal prompt v2 and optional probe evidence for OpenAI/Anthropic planners;
- deterministic probe-guided correction baseline;
- fixed development seeds `103, 107, 108, 144, 148` with a preserved failure
  counterexample on seed 144.
- observation-driven approach/push/near-goal phase classification;
- phase-aware correction recovered the seed-144 counterexample and reached 5/5
  on the development set, compared with 4/5 for whole-rollout correction;
- the phase schedule and thresholds are now frozen pending held-out evaluation.

This milestone is not held-out evidence and does not yet establish that an LLM
improves over deterministic probe-guided recovery.

## Phase 3 — Adaptive Recovery

**Status: partially completed**

Delivered:

- bounded rollout-level recovery loop;
- no-recovery, random, deterministic rule, LLM, and Oracle planners;
- validated structured proposals and action correction grid;
- OpenAI Responses and Anthropic-compatible Messages adapters;
- prompt/model/token/latency/response auditing;
- incremental checkpoints and optional per-trial video;
- a real GLM-5.1 seed-148 pilot.

Pilot finding: GLM-5.1 adapted correction magnitude based on evidence but chose
the wrong sign, and whole-rollout correction interfered with the approach phase.
This is integration and mechanism evidence, not a statistical claim.

### Probe-guided recovery experiment

Methods on the same five development seeds:

1. no recovery;
2. random search;
3. existing deterministic rule;
4. active probe plus deterministic correction;
5. active probe plus GLM-5.1 planner;
6. Oracle upper bound.

GLM-5.1 receives at most 3 calls per seed. Primary metrics are recovery success,
final distance, bias-sign accuracy, full-rollout steps, probe steps, total
environment interactions, and API calls. The first experiment is explicitly a
five-seed development study. A larger held-out evaluation is justified only if
the mechanism is sound.

Planned visual artifacts:

- estimated versus injected audit bias plot;
- method success/final-distance/interaction-budget figures;
- recovery curve;
- one correctly diagnosed recovery video;
- one correctly diagnosed but unrecovered counterexample;
- side-by-side initial failure and recovery video with evidence/proposal overlay.

## Phase 4 — Episodic Memory

**Status: not started**

Future question: can an agent reuse a previously successful correction for a
similar failure pattern and reduce diagnostic rollouts?

Do not implement until Phase 2 diagnosis and Phase 3 recovery have held-out
evidence. The future memory unit should store an agent-visible failure signature,
validated correction, applicability conditions, and outcome—not hidden
perturbation labels.

## Phase 5 — Paper-Style Evaluation

**Status: not started**

Future deliverables:

- frozen development and held-out seed splits;
- no-recovery, random, rule, LLM, memory, and Oracle comparisons;
- confidence intervals and interaction-budget-normalized metrics;
- diagnosis, correction, gating, and memory ablations;
- failure and counterexample analysis;
- reproducible tables, PNG figures, representative videos, and manifests;
- bilingual technical report, concise research statement summary, and CV entry.

## Current Research Boundary

The next approved work is Phase 2 active diagnostic probing and its Phase 3
probe-guided recovery comparison. Do not start episodic memory, RL, behavior
cloning, VLA training, complex policy learning, or new robot tasks during this
milestone.
