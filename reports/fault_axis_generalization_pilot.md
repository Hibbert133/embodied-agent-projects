# Fault Axis and Direction Generalization Pilot

## Research question

Does the active probe estimator infer unseen execution-error axes and signs, or
does its apparent success depend on the developed `+x` condition?

## Frozen setup

- unseen fault conditions: `-x`, `+y`, `-y`;
- magnitude: 0.145;
- seeds: `220-229` shared across conditions;
- correction schedule: whole;
- four symmetric probes, eight steps each after initial failure;
- two full rollouts maximum;
- no estimator or threshold changes between conditions.

## Real results

| Fault | Initial failures | Recovered | Conditional recovery | Wilson lower bound |
|---|---:|---:|---:|---:|
| `-x 0.145` | 2/10 | 2/2 | 100% | 34.2% |
| `+y 0.145` | 1/10 | 1/1 | 100% | 20.7% |
| `-y 0.145` | 3/10 | 3/3 | 100% | 43.9% |

Across the six episodes that required recovery, audit-only comparison found
6/6 correct inferred axes and 6/6 correction directions opposing the injected
fault. Correction magnitudes were selected from the fixed grid: 0.16 for both
`-x` cases, 0.12 for the `+y` case, and 0.16 for all three `-y` cases.

## Interpretation

The result supports an implementation-level generalization claim: the probe
estimator is not hard-coded to x or to a positive fault, and it can drive
successful corrections on both planar axes and signs.

The result does not support a reliable cross-condition recovery-rate claim.
The same magnitude produces very different initial failure prevalence: only
one `+y` episode needed recovery. Conditional denominators of one to three are
too small, as reflected by the wide Wilson intervals.

## Confounder and next decision

MetaWorld push-v3 is directionally asymmetric with respect to the policy,
initial-state distribution, and goal geometry. Comparing recovery at a shared
numeric bias magnitude therefore confounds Agent quality with fault severity.

Before adding two-axis bias or Gaussian noise, calibrate magnitude separately
for `-x`, `+y`, and `-y` to obtain approximately 40%-60% initial failure on a
calibration split. Freeze those condition-specific magnitudes, then evaluate
diagnosis and recovery on new held-out seeds. This calibration changes only
benchmark difficulty; it must not use recovery outcomes to tune the Agent.

## Artifacts

- `outputs/fault_matrix/x_negative.csv`
- `outputs/fault_matrix/y_positive.csv`
- `outputs/fault_matrix/y_negative.csv`
- `outputs/fault_matrix/summary.csv`
- `outputs/fault_matrix/diagnosis_audit.csv`

## Reproduction

```powershell
python scripts/summarize_recovery_ablation.py --group-by-fault --input-csv outputs/fault_matrix/x_negative.csv outputs/fault_matrix/y_positive.csv outputs/fault_matrix/y_negative.csv --output-csv outputs/fault_matrix/summary.csv
python scripts/summarize_fault_diagnosis.py --trial-csv outputs/fault_matrix/x_negative.csv outputs/fault_matrix/y_positive.csv outputs/fault_matrix/y_negative.csv --audit-jsonl outputs/fault_matrix/x_negative_audit.jsonl outputs/fault_matrix/y_positive_audit.jsonl outputs/fault_matrix/y_negative_audit.jsonl --output-csv outputs/fault_matrix/diagnosis_audit.csv
```
