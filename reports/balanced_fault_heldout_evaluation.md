# Balanced Single-Axis Fault Held-Out Evaluation

## Research question

Can the deterministic active-diagnosis Agent localize and recover unseen
single-axis execution faults after benchmark severity is calibrated separately
for direction?

## Evaluation protocol

- held-out seeds: `240-259`, never used for severity calibration;
- primary faults frozen from calibration:
  - `+x 0.145`;
  - `-x 0.180`;
  - `-y 0.198`;
- whole correction schedule;
- active symmetric probes only after an initial failure;
- 32 probe steps and at most two full rollouts;
- expanded fixed correction grid including 0.18, 0.198, and 0.20;
- no estimator, threshold, or schedule tuning on held-out outcomes;
- video rendering disabled during quantitative evaluation.

The initial trial in each episode provides the no-recovery baseline. Conditional
recovery counts only episodes whose initial trial failed.

## Real results

| Fault | Initial failures | Recovered | 95% Wilson CI | Mean recovery steps | Mean final distance (m) |
|---|---:|---:|---:|---:|---:|
| `+x 0.145` | 9/20 | 9/9 | [70.1%, 100%] | 63.67 | 0.048126 |
| `-x 0.180` | 10/20 | 10/10 | [72.2%, 100%] | 60.80 | 0.048399 |
| `-y 0.198` | 12/20 | 12/12 | [75.8%, 100%] | 62.25 | 0.047701 |

Across the 31 initial failures, recovery is 31/31 with a combined 95% Wilson
interval of [89.0%, 100%]. Audit-only comparison reports 31/31 correct fault
axes and 31/31 correction directions opposing the hidden injected bias.

## Magnitude analysis

The selected repair magnitudes are not exact system-identification estimates:

- `+x 0.145` maps to correction 0.10, absolute error 0.045;
- `-x 0.180` maps to correction 0.20, absolute error 0.020;
- `-y 0.198` maps to correction 0.20, absolute error 0.002.

Mean absolute magnitude error across recovery cases is 0.0203. Successful
recovery despite the `+x` underestimate indicates that the current mechanism is
best described as active fault localization plus robust bounded repair, not
precise actuator-parameter identification.

## Interpretation

The held-out evidence supports the central single-axis mechanism: symmetric
agent-visible transitions identify fault axis and sign well enough to choose an
effective correction across direction-specific severities.

The result remains limited to one task, scripted low-level policy, deterministic
single-axis bias, and a fixed probe protocol. The combined interval is stronger
than any individual condition but does not imply generalization to two-axis
bias, stochastic noise, perception error, or real hardware.

Oracle recovery was not rerun after the non-Oracle Agent reached the success
ceiling on all three primary conditions. It would not resolve the current
hypothesis. Hidden labels are used only in post-run diagnosis audit.

## Artifacts

- `outputs/balanced_heldout/x_positive.csv`
- `outputs/balanced_heldout/x_negative.csv`
- `outputs/balanced_heldout/y_negative.csv`
- `outputs/balanced_heldout/summary.csv`
- `outputs/balanced_heldout/diagnosis_audit.csv`
- `outputs/balanced_heldout/diagnosis_summary.csv`
- `outputs/balanced_heldout/figures/balanced_fault_recovery_rate.png`
- `outputs/balanced_heldout/figures/bias_vs_correction_magnitude.png`

## Next decision

Freeze this single-axis Agent as the reference method. The next scientific
question is not another single-axis seed expansion. Extend the estimator and
proposal from a dominant axis to a two-dimensional bias vector, then test
whether symmetric probes can separate simultaneous x/y bias. Gaussian noise
should follow only after repeated-probe variance estimation is implemented.

## Reproduction

```powershell
python scripts/summarize_recovery_ablation.py --group-by-fault --input-csv outputs/balanced_heldout/x_positive.csv outputs/balanced_heldout/x_negative.csv outputs/balanced_heldout/y_negative.csv --output-csv outputs/balanced_heldout/summary.csv
python scripts/summarize_fault_diagnosis.py --trial-csv outputs/balanced_heldout/x_positive.csv outputs/balanced_heldout/x_negative.csv outputs/balanced_heldout/y_negative.csv --audit-jsonl outputs/balanced_heldout/x_positive_audit.jsonl outputs/balanced_heldout/x_negative_audit.jsonl outputs/balanced_heldout/y_negative_audit.jsonl --output-csv outputs/balanced_heldout/diagnosis_audit.csv --summary-csv outputs/balanced_heldout/diagnosis_summary.csv
python scripts/plot_balanced_fault_results.py --diagnosis-csv outputs/balanced_heldout/diagnosis_audit.csv --summary-csv outputs/balanced_heldout/diagnosis_summary.csv --output-dir outputs/balanced_heldout/figures
```
