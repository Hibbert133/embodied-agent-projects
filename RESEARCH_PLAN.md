# Active-Evidence Embodied Research Agent — Research Plan

## Objective

Study whether an embodied agent can behave like a researcher after failure: estimate
uncertainty, decide what evidence is missing, design a bounded diagnostic probe,
revise a falsifiable mechanism hypothesis, propose a corrective intervention,
verify it on a fresh rollout, and retain only verified experience.

## Completed foundations

- MetaWorld 3.1.1 `push-v3` rollout, video, JSONL, and CSV pipeline.
- Masked scale/noise/bias perturbations with reproducible random generators.
- Schema-v2 causal transitions and leakage-safe Agent/Oracle views.
- Task-progress and clipping metrics grounded in installed MetaWorld source.
- Directional probes, bounded intervention skills, deterministic/online controls,
  paired stochastic evaluation, and preserved negative results.

## Phase A — Research architecture

**Current phase.** Establish explicit contracts for uncertainty, probe authorization,
hypothesis revision, intervention, verification, and verified-only memory. Reframe
documentation around active evidence acquisition without adding new algorithms.

Acceptance: compatible interfaces, strict causal boundary, complete lifecycle tests,
research-first README, architecture review, and unchanged baseline commands.

## Phase B — Uncertainty-aware evidence allocation

Compare never-probe, always-probe, fixed-budget, and uncertainty-gated strategies.
Primary metrics: hypothesis calibration, evidence steps, verification success, and
total interaction cost. Repeated stochastic candidate evaluation must use common
random numbers for comparison and independent streams for final verification.

## Phase C — Probe selection

Evaluate which bounded probe best distinguishes competing hypotheses. Begin with
existing directional probes; add repeated-action or contact probes only when a
specific ambiguity and measurable information-gain hypothesis justify them.

## Phase D — Hypothesis-grounded intervention and verification

Require every intervention to name its supporting hypothesis, predicted effect,
budget, and acceptance criterion. Compare deterministic and online diagnostic agents
against simple rules and Oracle audit upper bounds on frozen splits.

## Phase E — Verified experience

After Phases B–D pass held-out gates, test whether retrieving only accepted
hypothesis-intervention experiences reduces future evidence cost. Do not store or
reuse unverified conclusions.

## Phase F — Paper-style evaluation

Report frozen tuning/validation/held-out splits, uncertainty calibration, diagnostic
accuracy, evidence efficiency, verification success, rollout improvement, API cost,
ablations, confidence intervals, counterexamples, figures, videos, and manifests.

## Current exclusions

No reinforcement learning, behavior cloning, VLA training, new robot tasks, complex
policy learning, or operational memory is approved during Phase A.
