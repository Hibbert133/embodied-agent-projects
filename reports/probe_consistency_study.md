# Agent-Visible Probe Consistency Study

## Motivation and hypothesis

The online Research Agent did not outperform seeded random search because all
candidate policies attempted bias compensation on the Gaussian OOD case. A single
symmetric probe set made persistent bias and a particular stochastic execution
realization look similar. The new hypothesis was that repeated controlled probes
would expose cross-trial variance using only causally available transitions.

## Protocol

- Task: MetaWorld `push-v3`.
- Conditions: four deterministic bias families and Gaussian noise `std=0.60`.
- Probe: `+x/-x/+y/-y`, magnitude 0.2, four steps per direction.
- Repetitions: four independent perturbation streams derived deterministically
  from the episode seed and repeat index.
- Per-case diagnostic cost: 64 environment steps.
- Score: Euclidean norm of the cross-repeat standard deviation of inferred x/y
  action bias.

The Agent-visible context contains commanded probe actions, observed gripper
transitions, per-repeat estimates, and consistency statistics. Fault type and the
binary stochastic label exist only in evaluator CSVs.

## Tuning and frozen-threshold validation

On seeds 300–309, all 40 deterministic-bias scores were exactly zero; the ten
Gaussian scores ranged from 0.2312 to 0.9802. The Oracle-only tuning rule selected
threshold 0.11560838 and produced ROC AUC 1.0 and balanced accuracy 1.0.

The threshold was frozen before seeds 310–319. On these independent seeds, all 40
bias cases remained below the threshold and all ten Gaussian cases were above it,
giving 100% stochastic recall and 100% bias specificity. This is seed-generalization
evidence within the same synthetic fault families, not real-robot or unknown-noise
generalization.

## End-to-end interaction result

On the same six fixed tuning cases used by Autoresearch, consistency-gated
`research_r1_c1` retained 5/6 recovery success and correctly abstained on the one
Gaussian OOD case. Mean recovery environment steps fell from 161.00 to 125.67,
a reduction of 35.33 steps per case (21.9%). Mean final object-goal distance rose
from 0.08955 m to 0.10304 m because abstention no longer allowed an unsuccessful
500-step rollout to make incidental progress. Under the registered ordering of
success first and interaction cost second, the gated method improves tuning cost.

## Limitations

- Deterministic injected bias has exactly zero cross-repeat variance, making this
  simulator distinction unusually clean.
- Repeated reset-controlled probes assume access to safe, repeatable calibration
  trials and cost twice the original 32-step protocol.
- The end-to-end efficiency comparison has only six tuning cases.
- No held-out end-to-end recovery claim or real-world robustness claim is made.

## Frozen end-to-end validation and rejected promotion

The complete validation used all 50 initial episodes on seeds 310–319. Thirty
episodes initially failed. The frozen `research_r1_c1` and `random_03` policies
both recovered 29/30 failures (96.7%), with 91.07 and 101.13 mean recovery steps.
The consistency-gated policy recovered 27/30 (90.0%) with 134.83 mean steps.

Both Gaussian failures exceeded the consistency threshold, but both were recovered
by the ungated Research policy. Abstention therefore harmed two outcomes and did
not improve any. Relative to `research_r1_c1`, gating changed recovery rate by
-6.7 percentage points and added 43.77 mean steps. The pre-registered promotion
gate rejects the method.

This negative result changes the research interpretation: fault stochasticity is
identifiable here, but it is not a sufficient statistic for recoverability. A
robotic agent should estimate the expected value of attempting a bounded repair,
including success probability and interaction cost, rather than mapping OOD
detection directly to abstention.

## Reproduction

```powershell
python scripts/evaluate_probe_consistency.py --seed-start 300 --num-seeds 10 --repeats 4 --probe-steps 4 --probe-magnitude 0.2 --output-dir outputs/autoresearch/probe_consistency_tuning
python scripts/evaluate_probe_consistency.py --seed-start 310 --num-seeds 10 --repeats 4 --probe-steps 4 --probe-magnitude 0.2 --fixed-threshold 0.11560838098372882 --output-dir outputs/autoresearch/probe_consistency_validation
python scripts/plot_probe_consistency.py --tuning-csv outputs/autoresearch/probe_consistency_tuning/results.csv --validation-csv outputs/autoresearch/probe_consistency_validation/results.csv --threshold 0.11560838098372882 --output outputs/autoresearch/figures/probe_consistency_tuning_validation.png
python scripts/evaluate_gated_recovery_validation.py --seed-start 310 --num-seeds 10 --research-config outputs/autoresearch/search_tuning/research_agent/research_r1_c1/candidate.json --random-config outputs/autoresearch/search_tuning/random_search/random_03/candidate.json --consistency-threshold 0.11560838098372882 --repeats 4 --consistency-probe-steps 4 --max-steps 500 --output-dir outputs/autoresearch/gated_recovery_validation
```
