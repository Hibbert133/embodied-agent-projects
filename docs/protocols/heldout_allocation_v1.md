# Held-Out Budgeted Allocation Protocol v1

## Executable source

The executable configuration is
`configs/autoresearch/heldout_allocation_v1.json`. This document explains its
semantics. The config takes precedence if prose and executable values disagree;
such a disagreement is a protocol defect and blocks the run.

This protocol is distinct from the historical seeds 310--319 ambiguity held-out
study under `configs/benchmarks/`. Existing results are retained and are not
overwritten or relabeled.

## Population

The full collection population contains:

```text
10 seeds (330--339) x 5 conditions x 1 initial rollout = 50 units
```

It is used for data-integrity audit, condition/mechanism strata, full-population
diagnosis metrics, and leakage audit.

The operational decision population contains failed initial rollouts with
`decision_required == true`. Version 1 has no successful-but-uncertain trigger.
It is the primary population for probe request rate, probe-need ROC/PR AUC,
evidence efficiency, unnecessary-probe rate, probe cost, and promotion.

A successful initial rollout records:

```text
decision_required = false
evidence_decision = CONTINUE
adaptation_cost = 0
```

This is not counted as a successful active-allocation decision.

## Registered conditions

| ID | Perturbation | Evaluator mechanism | Intervention family |
|---|---|---|---|
| `fault_01` | bias `[0.145, 0, 0, 0]` | `stable_bias` | bounded x compensation |
| `fault_02` | bias `[-0.18, 0, 0, 0]` | `stable_bias` | bounded x compensation |
| `fault_03` | bias `[0, -0.198, 0, 0]` | `stable_bias` | bounded y compensation |
| `fault_04` | bias `[0.14, -0.14, 0, 0]` | `stable_bias` | bounded planar compensation |
| `fault_05` | calibrated Gaussian noise | `stochastic_noise` | independent-seed stochastic retry |

There is no clean condition in this mechanism benchmark. `insufficient_evidence`
is an Agent belief outcome, not an injected mechanism. Primary diagnosis is at
mechanism level; condition-level results are audit strata only.

## Evidence decision and budget

The fixed allocation score is phase inconsistency. A diagnostic probe is
requested when the score meets the frozen allocation threshold, subject to the
budget invariant. This allocation threshold is distinct from the older repeated-
probe outcome classifier threshold:

- allocation threshold: `0.91612970415368`;
- probe outcome classifier threshold: `0.11560838098372882`.

The probe is allowed only when:

```text
remaining_budget >= 64 + 500
```

Each case has a 1064-step maximum: 500 initial, 64 probe, and 500 verification.
Attempt 0 is the initial rollout, attempt 1 is the optional probe, and attempt 2
is the single verification. Attempt 3 or later is invalid in version 1.

Record total, remaining, reserved-probe, reserved-verification, and consumed
budgets plus any rejection reason. Early termination is charged at actual steps,
but authorization reserves the maximum valid downstream budget.

## Evaluator-only labels

`diagnostic_probe_needed` is true only when the passive mechanism decision is
incorrect and the registered-probe mechanism decision is correct. It measures
probe necessity for mechanism correctness, not all possible improvements in a
continuous drift estimate.

`decision_probe_needed`, used in P1 rather than this allocation promotion, is true
only when the probe changes the intervention and the active intervention obtains
a strictly better matched fresh-verification status than the passive intervention.
The order is `ACCEPTED > INCONCLUSIVE > REJECTED`; equal status is not improvement.

Both labels are post-hoc Oracle audit fields computed only after the required
counterfactuals finish. They cannot enter Agent evidence, decision rules, GLM
payloads, threshold fitting, or memory signatures.

Report positive prevalence, positive/negative counts, ROC AUC, PR AUC, score
distributions, and mechanism-stratified prevalence. If the operational population
contains one label class, both AUCs are `N/A` and the status is
`INCOMPLETE_FOR_PROBE_NEED_EVALUATION`.

## Matching

Matching is used only for paired cost/intervention analyses, not to define the
full or operational population AUC.

The frozen rule selects failed bias and noise cases, assigns every failed noise
case to a unique failed bias case, standardizes the exact passive feature vector
`[episode_return, final_object_goal_distance, progress_to_goal]` over the candidate
pool, and minimizes global one-to-one Euclidean cost. Probe evidence is excluded.
Equal-cost assignments use lexicographic bias `case_id` order.

The number of pairs is determined by actual failed noise cases and is not forced
to five. No valid assignment means an incomplete experiment; no seed replacement
or matching relaxation is permitted. The manifest records the matching version,
implementation Git blob hash, source features, and selected case IDs.

## Methods and metrics

Compare Passive, seeded Random-probe with probability 0.60, Always-probe, the
global temporal gate, the frozen phase-conditioned gate, and Oracle audit.

Physical interaction cost is initial + probe + verification environment steps.
Evidence efficiency is improvement in correct diagnoses over Passive divided by
probe steps. Passive zero-probe efficiency is `N/A`.

Record decision-layer latency with a monotonic high-resolution clock, excluding
environment execution: evidence-state build, evidence decision, belief update,
intervention selection, optional memory retrieval, and total Agent decision time.
Warm-up is separate. Report median, p90, and maximum; deterministic and GLM latency
are never combined.

Report full and operational sample sizes, Wilson intervals, mechanism strata,
10,000 fixed-seed stratified paired-bootstrap intervals, paired diagnosis
win/tie/loss, and cost win/tie/loss where diagnosis outcomes tie.

## Promotion and stop conditions

On the operational population, promotion requires:

- accuracy at least 90% of Always-probe accuracy;
- request rate at most 60%;
- probe-need ROC AUC at least 0.75 with both label classes present;
- probe cost below Always-probe;
- no mechanism-stratum, paired-bootstrap, or win/tie/loss contradiction to the
  claimed accuracy/cost tradeoff;
- no Agent/Oracle leakage.

Failure or incomplete status is preserved. Thresholds, features, labels, matching,
seeds, and promotion criteria are never retuned on this run.

## Immutable execution manifest

The implementation and config are committed before execution. From a clean tree,
generate a canonical manifest containing the source commit, config SHA-256,
thresholds, seeds, condition/matching/probe versions and blob hashes, evidence
schema, Python/MetaWorld/MuJoCo/dependency versions, platform, and UTC timestamp.

The SHA-256 of canonical manifest content is the manifest ID. The run directory is
new and content-addressed; existing runs are never overwritten. Every CSV, JSON,
and JSONL references the run ID, manifest ID, and source commit. Any code, config,
or environment change requires a new manifest and run ID.
