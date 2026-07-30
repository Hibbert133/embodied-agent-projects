# Experiment Plan

## Objective

Test whether active evidence acquisition improves diagnosis and intervention under
a fixed interaction budget, especially when one passive rollout is compatible with
multiple failure mechanisms.

Experiments must separate three claims:

1. a probe can provide additional evidence;
2. the Agent can decide when that evidence is needed;
3. the new evidence changes diagnosis or intervention in a way that improves fresh
   verification outcomes.

Successful task completion alone does not establish any of these claims.

## Baseline agents

| Baseline | Evidence behavior | Purpose |
|---|---|---|
| Passive | Diagnose and intervene from the failed rollout only | Measures whether probes are needed at all |
| Always-probe | Execute the full registered probe after every failure | Robust evidence upper-cost baseline |
| Random-probe | Request a probe with an independent seeded random decision | Controls for probe frequency without reasoning |
| Frozen threshold gate | Probe only when a tuning-selected uncertainty threshold is crossed | Transparent evidence-allocation baseline |
| Oracle audit | Use injected labels or counterfactual outcomes after execution | Evaluation upper bound; never an Agent |

Existing online-model adapters may be reported as an optional historical comparison,
but they are not the central method and are not required for the next experiment.
No new LLM implementation is part of this plan.

## Failure types

### Implemented experimental conditions

- single-axis positive and negative action bias on x or y;
- simultaneous planar bias where justified by a separate hypothesis;
- Gaussian action noise with independent per-episode generators;
- masked action-scale reduction;
- identity/no-perturbation control.

### Immediate ambiguity benchmark

Construct matched **stable-bias versus stochastic-noise pairs**. Candidate cases
must have similar passive symptoms—initial success state, task progress, and final
object-goal distance—but different temporal repeatability. Selection uses tuning
data and is frozen before held-out evaluation.

The intended causal distinction is:

```text
stable bias  -> repeated probe estimates agree in axis and sign
random noise -> repeated probe estimates vary across independent realizations
```

Delayed control, contact mismatch, and perception error remain future taxonomy
entries. They should not be added until a concrete ambiguity and discriminating
probe are specified.

## Probe types

### Implemented

- **Symmetric directional probe:** paired `+x/-x/+y/-y` commands estimate common
  planar drift while canceling the commanded component.
- **Repeated symmetric probe:** independent repeats estimate whether the inferred
  drift is stable or stochastic.

### Future candidates, not current deliverables

- repeated single action for temporal delay;
- low-force contact for free-space versus contact-dynamics mismatch;
- small exploratory push for local object-response uncertainty.

A new probe is justified only when it targets a named uncertainty, has a predicted
observation under competing hypotheses, and has an explicit safety and step budget.

## Metrics

### Primary research metrics

- mechanism-hypothesis accuracy on post-hoc Oracle audit labels;
- balanced accuracy for ambiguity-pair classification;
- uncertainty calibration or confidence/error relationship;
- probe request rate and probe environment steps;
- evidence efficiency: diagnostic improvement per probe step;
- intervention-selection accuracy;
- verification success and false-acceptance rate;
- total environment steps across initial, probe, and verification interactions.

### Supporting task metrics

- task success rate;
- final object-goal distance in metres;
- progress to goal;
- episode and recovery steps;
- return as an auxiliary metric only.

### Audit and operational metrics

- clipped-step and clipped-element fractions;
- wall-clock latency separated from environment steps;
- optional API calls, token usage, invalid-response count, and model version;
- stopped or abstained cases and the reason budget was exhausted.

## Experimental protocol

- Use Python 3.10, MetaWorld 3.1.1, `push-v3`, and the fixed
  `SawyerPushV3Policy` unless a later stage explicitly changes the task.
- Freeze tuning, validation, and held-out seed lists in tracked configuration files.
- Use identical environment seeds across compared methods.
- Give stochastic perturbations independent, reproducible NumPy generators.
- Select thresholds and ambiguity pairs on tuning data only; never retune held-out
  results.
- Record raw per-job JSONL/CSV before producing summaries.
- Declare maximum jobs, environment steps, wall time, and optional API calls.
- Do not render video during timed comparisons. Rerun only rule-selected
  representative cases with rendering.
- Report warnings, incomplete runs, negative results, and confidence intervals where
  the sample size supports them.

## Expected experiments

### E0 — Platform regression

Confirm baseline demo, video, schema-v2 trajectory, batch evaluation, perturbation
reproducibility, and Agent/Oracle leakage checks. This is engineering evidence, not
a research comparison.

### E1 — Passive sufficiency audit

Measure how often passive diagnosis and correction already succeed for each
implemented fault family. This prevents active probes from receiving credit where
they are unnecessary.

### E2 — Bias-versus-noise ambiguity benchmark

Build matched stable-bias/noise cases and compare passive versus repeated-probe
mechanism accuracy. Promotion requires a measurable diagnostic gap, not merely a
successful probe rollout.

The first tuning-only manifest is now frozen in
`outputs/ambiguity_benchmark/bias_noise_tuning_v1/`. Its global one-to-one matching
uses only return, final object-goal distance, and progress from failed initial
rollouts. Repeated-probe evidence is joined only after selection. The resulting
8-case tuning pilot is documented in
[`reports/bias_noise_ambiguity_benchmark.md`](../reports/bias_noise_ambiguity_benchmark.md);
it must not be reported as held-out evidence.

### E3 — Evidence-allocation ablation

Compare passive, always-probe, random-probe, and frozen threshold gating on the
ambiguity benchmark. The target is to approach always-probe diagnostic accuracy
with fewer probe steps and no held-out retuning.

The first four-case held-out pilot produced a deliberately retained negative
result: always-probe resolved both passive errors, while the tuning-frozen
centroid-margin gate requested no probes. Thus probe informativeness has initial
held-out support, but selective evidence allocation has not passed its gate. See
[`reports/ambiguity_agent_heldout_pilot.md`](../reports/ambiguity_agent_heldout_pilot.md).

### E4 — Hypothesis-grounded intervention

Map stable bias to bounded compensation and stochastic noise to an appropriate
non-bias response or abstention. Evaluate whether correct diagnosis changes
verification success relative to applying the same compensation to both mechanisms.

### E5 — Verification ablation

Compare accepting interventions immediately versus requiring a fresh verification
rollout. Measure false acceptance, wasted future interactions, and unsupported
experience entries.

### E6 — Verified memory, future stage

Only after E2–E5 pass held-out gates, test whether retrieving accepted experiences
reduces later evidence cost. The current repository exposes a memory contract but
does not implement this experiment.

## Promotion criteria

The project may claim value for active evidence only if a frozen held-out experiment
shows all of the following:

1. passive evidence has a documented ambiguity or diagnostic failure mode;
2. the selected probe improves mechanism discrimination;
3. the evidence policy uses fewer interactions than always-probe or provides a
   justified accuracy/cost tradeoff;
4. improved diagnosis changes verification outcomes or prevents unsupported
   intervention;
5. all numbers are traceable to tracked configs and real raw artifacts.

If passive diagnosis remains equally successful at lower cost, the correct result is
that the current benchmark does not require active evidence.
