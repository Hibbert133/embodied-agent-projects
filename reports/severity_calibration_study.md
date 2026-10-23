# Direction-Specific Fault Severity Calibration

## Research question

Can single-axis bias conditions be calibrated to comparable baseline difficulty
without making action saturation the dominant failure mechanism?

This calibration is required before comparing recovery across axes. A shared
numeric magnitude is not a shared task difficulty in MetaWorld push-v3.

## Protocol

- calibration seeds: `230-239`;
- no recovery, no active probes, and no Agent decisions;
- maximum 500 steps;
- target baseline failure rate: 40%-60%;
- maximum accepted clipped-step fraction: 50%;
- paired seeds across every magnitude within a scan;
- selection minimizes distance to 50% failure, then chooses the lower magnitude
  on a tie.

Round 1 scanned 0.16, 0.20, and 0.24 on all four directions. Local scans then
resolved transition regions. The first long sweep reached the command wrapper's
timeout after printing all episodes, but artifact validation confirmed exactly
120 detail rows and 10 rows for every configuration, so the saved data are
complete.

## Selected conditions

| Direction | Magnitude | Baseline failure | Clipped steps | Role |
|---|---:|---:|---:|---|
| `+x` | 0.145 | 50% | 22.6% | primary |
| `-x` | 0.180 | 40% | 40.1% | primary |
| `-y` | 0.198 | 60% | 18.7% | primary |
| `+y` | 0.180 | 80% | 30.2% | stress only |

The automatic selector enforces the clipping constraint. `+y` has no candidate
that satisfies both constraints and is therefore not eligible for the primary
balanced benchmark.

## Positive-y discontinuity

The `+y` response is non-monotonic and coupled to saturation:

| Magnitude | Failure | Clipped steps |
|---:|---:|---:|
| 0.1800 | 80% | 30.2% |
| 0.1850 | 80% | 51.1% |
| 0.1875 | 70% | 57.0% |
| 0.1900 | 60% | 59.1% |
| 0.2000 | 50% | 56.4% |

Increasing bias does not yield a smooth severity curve because the scripted
policy, environment clipping, and contact dynamics can switch behavioral modes.
This is a benchmark limitation, not evidence that the Agent is better or worse.

## Interpretation

The calibration confirms substantial directional asymmetry. Matching fault
magnitudes numerically would produce an unfair recovery comparison. Three
conditions can be balanced while retaining a bounded saturation criterion.
Positive-y should be reported separately as a saturation-stress case.

Calibration data must not be reused to tune recovery parameters. The next
recovery evaluation uses new seeds and the frozen selected magnitudes. It must
also expand the allowed correction grid before testing magnitudes above 0.16;
otherwise repair capacity, rather than diagnosis quality, becomes the limiting
factor.

## Artifacts

- `outputs/severity_calibration/round1.csv`
- `outputs/severity_calibration/round1_summary.csv`
- `outputs/severity_calibration/round2_*`
- `outputs/severity_calibration/round3_*`
- `outputs/severity_calibration/selected_configs.csv`

## Reproduction

```powershell
python scripts/select_severity_configs.py --summary-csv outputs/severity_calibration/round1_summary.csv outputs/severity_calibration/round2_x_positive_summary.csv outputs/severity_calibration/round2_x_negative_summary.csv outputs/severity_calibration/round2_y_positive_summary.csv outputs/severity_calibration/round2_y_negative_summary.csv outputs/severity_calibration/round3_y_positive_summary.csv outputs/severity_calibration/round3_y_negative_summary.csv --target-failure-rate 0.5 --max-clipped-step-fraction 0.5 --output-csv outputs/severity_calibration/selected_configs.csv
```
