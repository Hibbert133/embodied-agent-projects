# P1 Negative Result: Diagnosis Does Not Guarantee Better Intervention

## Registered question

Does the Phase-2 diagnostic probe change the mechanism belief, change the
selected intervention, and improve a matched fresh verification outcome?

The protocol, status definition, six comparison methods, recovery policy, and
random namespaces were committed before verification. The run uses the 33 failed
initial rollouts from the immutable Phase-2 allocation population. It makes no
API calls and does not update policy weights.

## Result

| Method | Accepted | Recovery | Probe steps | Verification steps | Added steps |
|---|---:|---:|---:|---:|---:|
| No intervention | 0/33 | 0.0% | 0 | 0 | 0 |
| Bias compensation for all | 27/33 | 81.8% | 2,112 | 4,702 | 6,814 |
| Stochastic retry for all | 3/33 | 9.1% | 0 | 15,505 | 15,505 |
| Passive diagnosis intervention | 30/33 | 90.9% | 0 | 3,771 | 3,771 |
| Active-evidence intervention | 29/33 | 87.9% | 448 | 4,158 | 4,606 |
| Oracle mechanism intervention | 29/33 | 87.9% | 1,728 | 4,107 | 5,835 |

Active versus passive produced 0 wins, 32 ties, and 1 loss on accepted recovery.
The paired recovery-rate difference was -3.03 percentage points with a 95%
stratified bootstrap interval of [-9.09, 0.00]. Active evidence spent 25.30 more
additional steps per case; its paired 95% interval was [9.70, 47.64].

The registered promotion result is `NOT_PROMOTED`.

## Causal audit

Among seven probe requests:

- four changed the mechanism belief;
- six changed an executable intervention configuration;
- zero improved verification status over passive;
- useful-probe rate was 0/7.

The four corrected stochastic-noise beliefs switched from bounded compensation
to independent retry. Two methods tied on three cases, while seed 338
(`heldout_case_0049`) exposed the counterexample:

```text
passive belief: stable_bias
-> phase-aware y correction -0.06
-> ACCEPTED in 156 verification steps

active belief: stochastic_noise
-> zero-correction independent retry
-> REJECTED after 500 verification steps
```

Both use the same task seed and verification noise realization. The active route
also paid 64 probe steps. This is not a diagnosis error: the evaluator mechanism
is stochastic noise. It is a failure of the assumed mechanism-to-intervention
mapping.

The rendered pair was selected by the same rule and automatically checked against
the frozen CSV:

- `outputs/videos/intervention_counterexample/heldout_case_0049_seed338_passive_diagnosis_intervention_accepted.mp4`
- `outputs/videos/intervention_counterexample/heldout_case_0049_seed338_active_evidence_intervention_rejected.mp4`
- `outputs/videos/intervention_counterexample/manifest.csv`

## Interpretation

Phase 2 showed that probe evidence can improve a latent mechanism label cheaply.
P1 shows why that is insufficient for an embodied Agent: the label is not the
decision objective. A small evidence-grounded correction can improve a particular
stochastic rollout even when `stochastic_noise` is the correct generating class,
whereas an unmodified retry has low expected utility. The Oracle mechanism router
also recovered only 29/33, below passive's 30/33, strengthening this conclusion.

The evidence supports a revised scientific hypothesis for development data only:
future evidence allocation should estimate **candidate-specific intervention
utility**, not merely mechanism correctness. It does not authorize retuning on
seeds 330--339, adding memory, or claiming recovery improvement.

## Runtime and warnings

Intervention-plan construction over the six registered methods took median 1.61
ms per case (p90 2.18 ms, maximum 4.65 ms), excluding environment rollout time.
MetaWorld/Gymnasium emitted the existing observation-space and action-clipping
warnings; all 33 cases completed without an environment exception.

## Provenance

- Intervention manifest:
  `d72191c58554208dff0ec0ef6768bd37639ed54f603ca4ce562f239dfe2dc922`
- Source implementation commit:
  `5f38aca299057f7d16b4473b6be6670e998f23e5`
- Parent allocation manifest:
  `a39271db862f28574ad9eb47de4b2bf476950b58749b21baaac59117cf75981c`

```bash
python scripts/generate_intervention_manifest.py
python scripts/run_frozen_heldout_intervention.py --manifest \
  outputs/heldout_intervention/runs/intervention_20260731T024143Z_d72191c58554/manifest.json
python scripts/plot_intervention_results.py --run-dir \
  outputs/heldout_intervention/runs/intervention_20260731T024143Z_d72191c58554
python scripts/render_intervention_counterexample.py --run-dir \
  outputs/heldout_intervention/runs/intervention_20260731T024143Z_d72191c58554
```
