# ProbeMem Additional Experiments

Run: `probemem_additional_ablation_20260901T031926Z_4f9fd0b4556c`

Recovery Rate = successful recoveries / initial failed episodes. All primary methods use the same denominator (`60`).

## Ablation Result

| Method | Diagnosis | Evidence steps | Recovery |
|---|---:|---:|---:|
| BASELINE | 52/60 (86.7%) | 0 | 51/60 (85.0%) |
| MEMORY_ONLY | 52/60 (86.7%) | 0 | 52/60 (86.7%) |
| EVIDENCE_ACQUISITION_ENABLED | 57/60 (95.0%) | 960 | 55/60 (91.7%) |
| PROBE_MEMORY | 57/60 (95.0%) | 960 | 52/60 (86.7%) |
| FULL_PROBEMEM | 57/60 (95.0%) | 960 | 52/60 (86.7%) |

## Evidence Acquisition Policy Comparison

| Policy | Diagnosis | Mean evidence steps |
|---|---:|---:|
| NO_ACQUISITION | 29/33 (87.9%) | 0.00 |
| ALWAYS_ACQUIRE_FIXED_64_STEP_EVIDENCE | 33/33 (100.0%) | 64.00 |
| ADAPTIVE_ACQUISITION | 33/33 (100.0%) | 13.58 |

## Configuration-level Marginal Contributions

These contrasts are marginal system contributions, not fully independent component causal effects.

- Memory contribution (`MEMORY_ONLY - BASELINE`): +1.7% recovery rate.
- Evidence Acquisition contribution (`EVIDENCE_ACQUISITION_ENABLED - BASELINE`): +6.7% recovery rate. This is not an isolated probe-selector effect.
- Memory after acquisition (`PROBE_MEMORY - EVIDENCE_ACQUISITION_ENABLED`): -5.0% recovery rate.
- Verifier addition (`FULL_PROBEMEM - PROBE_MEMORY`): +0.0% recovery rate.

## Memory Retrieval Utility and Leakage Audit

- `MEMORY_ONLY_VS_BASELINE`: no retrieval 1/60; useful 2/60; harmful 1/60; neutral 56/60.
- `PROBE_MEMORY_VS_EVIDENCE_ACQUISITION`: no retrieval 1/60; useful 2/60; harmful 4/60; neutral 53/60.
- Retrieved items audited: 522; owner mismatches: 0; non-ACCEPTED items: 0; non-prior items: 0.
- Retrieval similarity, source availability time, failure-mechanism consistency, and method ownership are recorded in `memory_retrieval_audit.csv`.

## Verifier Coverage and Calibration

- Proposal coverage: 60/60 (100.0%)
- Invocation coverage: 59/60 (98.3%)
- Brier score: 0.12324779215183314
- Confidence/outcome consistency: `{'HIGH_CONFIDENCE_SUCCESS': 50, 'HIGH_CONFIDENCE_FAILURE': 8, 'UNCERTAIN_PREDICTION': 1, 'LOW_PREDICTED_SUCCESS': 0}`
- Intervention outcomes: `{'NOT_INVOKED': 1, 'CORRECT_ACCEPTANCE': 51, 'FALSE_ACCEPTANCE': 8}`
- Prevented unsafe actions: 0; unnecessary rejections: 0.

Low invocation coverage must not be interpreted as high verifier reliability.

## Population Coverage

- Perturbation categories: `{'fault_01': 9, 'fault_02': 9, 'fault_03': 15, 'fault_04': 19, 'fault_05': 8}`
- Failure mechanisms: `{'stable_bias': 52, 'stochastic_noise': 8}`
- Descriptive population imbalance: `True`. Coverage targets did not alter stopping, resampling, or seed selection.

## Full-population Failure Taxonomy

- Diagnosis failure: 3/60.
- Diagnosis correct but recovery failed: 2/60.
- Harmful Memory transfer: 4/60.
- Correct diagnosis but verifier failed to prevent an unreliable action: 6/60.
- These are full-population counts, not result-selected examples. The separate five-case report uses outcome-blind first-sequential-per-condition selection.

The five-row ablation identifies configuration-level marginal effects, not fully independent component causal effects.

## Research Findings

### RQ1

Question: Does adaptive evidence acquisition reduce diagnosis cost?

Observed evidence: On 33 comparable historical cases, adaptive acquisition and fixed 64-step acquisition both diagnosed 33/33 cases (100.0%); adaptive acquisition used 13.58 mean evidence steps versus 64.00, a 78.8% reduction.

Conclusion: Supported. The results support that adaptive evidence acquisition affects diagnostic interaction cost under this development evaluation setting.

Limitation: Fixed evidence action space, development-only population, and configuration-level marginal effects.

### RQ2

Question: Does memory improve evidence utilization?

Observed evidence: Adding method-isolated accepted-only memory on top of evidence acquisition changed recovery from 55/60 to 52/60 (paired difference -5.0%); transfer labels were 2 useful, 4 harmful, 53 neutral, and 1 no-retrieval.

Conclusion: Not supported. The results reject that accepted-only chronological memory affects recovery and transfer utility beneficially under this development evaluation setting.

Limitation: Fixed evidence action space, development-only population, and configuration-level marginal effects.

### RQ3

Question: Can verification bridge diagnosis and recovery?

Observed evidence: Adding verifier on top of Probe+Memory changed recovery by +0.0% (52/60 versus 52/60). Proposal coverage was 60/60, invocation coverage was 59/60, and no unsafe proposal was converted from a non-ACCEPTED evaluator outcome to an ACCEPTED selected outcome.

Conclusion: Not supported. The results reject that adding verifier on top of Probe+Memory affects recovery behavior under this development evaluation setting.

Limitation: Fixed evidence action space, development-only population, and configuration-level marginal effects.
