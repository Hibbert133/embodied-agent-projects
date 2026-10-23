# Active Diagnostic Probe Pilot

## Research question

Can a small, causally valid interaction budget identify the axis and direction
of an unknown planar execution drift, and can that evidence guide recovery more
reliably than blind whole-rollout prompt search?

This is a five-seed development pilot, not a statistical performance claim.
It does not use failure labels, injected bias parameters, perturbed actions, or
executed actions as planner inputs.

## Method

After the initial rollout fails, four independent environments reset to the same initial state.
The executor commands `+x`, `-x`, `+y`, and `-y` at magnitude 0.2 for eight
steps. Gripper displacement is measured from observations. Under the local
model `displacement = gain * command + common drift`, averaging an opposite
command pair cancels the command term and estimates drift. The recommended
correction opposes the inferred drift.

The probe budget is 32 environment steps per seed and is reported separately
from full-rollout steps. Minimum gripper-object distance was 0.184429 m and
maximum object displacement was 0.000014845 m, so these probes did not
meaningfully manipulate the object.

## Structured planner prompt

Prompt version `push-recovery-v2-causal` defines command coordinates, aligned
transition semantics, the additive-bias compensation hypothesis, evidence
priority, failure-mechanism distinctions, history checking, and a strict output
schema. It explicitly states that hidden perturbation truth is unavailable.

## Real probe evidence

Command:

```powershell
python scripts/run_active_diagnostic_probes.py --seeds 103 107 108 144 148 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --probe-magnitude 0.2 --probe-steps 8
```

All five seeds inferred `x_positive`; Oracle audit therefore records 5/5 axis
and 5/5 direction agreement for this injected condition. Confidence was about
0.745 and symmetric-pair residual about 0.000000656 for every seed. The near
identical estimates are expected because the reset hand dynamics are nearly
identical; they should not be interpreted as five independent task outcomes.

## Probe-guided recovery pilot

The deterministic estimator selected an `x_negative 0.10` correction. All five
uncorrected trials failed. With one correction trial, seeds 103, 107, 108, and
148 succeeded; seed 144 failed. Final object-goal distance changed as follows:

| Seed | Initial distance (m) | Corrected distance (m) | Corrected success |
|---:|---:|---:|:---:|
| 103 | 0.192641 | 0.048873 | yes |
| 107 | 0.083467 | 0.048914 | yes |
| 108 | 0.278269 | 0.048737 | yes |
| 144 | 0.528798 | 0.069487 | no |
| 148 | 0.246488 | 0.048523 | yes |

This gives 4/5 recovered development cases. It does not justify an 80% general
recovery claim. Seed 144 is an important counterexample: correct drift-axis
identification and substantial distance reduction did not cross the task's
success condition within 500 steps.

## Artifacts

- `outputs/active_probes/probe_transitions_agent_view.csv`
- `outputs/active_probes/probe_estimates_oracle_audit.csv`
- `outputs/active_probes/probe_rule_stratified_trials.csv`
- `outputs/active_probes/probe_rule_stratified_audit.jsonl`

Raw development trajectories are reproducible but ignored by Git to avoid
committing high-volume intermediate data.

## Limitations and next experiment

- Only one task and one injected bias condition were probed.
- Probe response estimates drift direction more reliably than exact magnitude.
- Whole-rollout constant correction can interfere with different policy phases.
- No LLM-vs-deterministic comparison has been run with this evidence yet.
- The fixed seeds were used for development and must not serve as held-out data.

The next bounded experiment should compare rule, probe-rule, GLM-5.1 with the
same probe context, and Oracle under identical seeds and explicit total
interaction/API budgets. A phase-gated correction ablation should be tested
before episodic memory or any Day 4 mechanism is introduced.

## Fixed-seed non-API ablation

A follow-up comparison used the identical development seeds and a maximum of
two full rollouts. `none` stopped after the initial failure. `probe_rule` also
used 32 diagnostic environment steps per failed episode. Results were computed
by `scripts/summarize_recovery_ablation.py` directly from trial CSV files:

| Planner | Successes | Mean final distance (m) | Mean total environment steps |
|---|---:|---:|---:|
| none | 0/5 | 0.265933 | 500.0 |
| rule | 0/5 | 0.255673 | 1000.0 |
| probe_rule | 4/5 | 0.052907 | 684.8 |
| oracle | 5/5 | 0.048171 | 566.4 |

These values show that agent-visible probing was useful on this development
set and that the original final-geometry rule did not recover within one
correction. They do not establish held-out performance or an LLM advantage.
GLM-5.1 was not run in this follow-up because no API credential was present in
the experiment process.

Representative corrected-rollout videos were selected automatically from the
real CSV rows. Seed 148 is a successful recovery, while seed 144 is the
preserved failure counterexample. Their manifest is stored at
`outputs/active_probes/representative_videos/manifest.csv`.

## Reproduction

```powershell
python scripts/run_recovery_agent.py --planner probe_rule --active-probes --seeds 103 107 108 144 148 --max-steps 500 --max-trials 2 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --output-csv outputs/active_probes/probe_rule_stratified_trials.csv --audit-jsonl outputs/active_probes/probe_rule_stratified_audit.jsonl --trajectory-dir outputs/active_probes/stratified_trajectories
python -m unittest discover -s tests -v
python -m pip check
git diff --check
```
