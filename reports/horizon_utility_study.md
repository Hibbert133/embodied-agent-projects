# Evidence Horizon and Stochastic Candidate-Ranking Reversal

## Motivation

The GLM-5.1 utility Agent selected stochastic retry for `case_0041` because its
80-step probe showed stronger immediate progress. A matched full-rollout control
later showed that compensation succeeded while retry failed. This study asks
whether a longer candidate-observation horizon fixes that error.

## Experimental hygiene correction

The original online pilot used different independent perturbation streams for the
two candidate probes. That is reproducible but confounds candidate action effects
with stochastic realization. The pilot remains preserved as integration evidence,
but its candidate comparison is now explicitly treated as confounded.

This follow-up uses common random numbers: compensation and retry receive the same
probe noise sequence. The common probe stream is strictly independent from the
final execution stream. Selection reads only schema-v2 Agent View prefixes. Hidden
fault fields and future transitions are unavailable. Full outcomes are used only
to compute post-hoc candidate labels.

## Real results

| Horizon | Oracle agreement | Recovery rate | Mean candidate-probe steps | Mean total steps |
|---:|---:|---:|---:|---:|
| 20 | 16.7% | 16.7% | 40.0 | 485.5 |
| 40 | 66.7% | 66.7% | 80.0 | 311.5 |
| 80 | 83.3% | 83.3% | 155.0 | 316.0 |
| 120 | 83.3% | 83.3% | 201.7 | 362.7 |
| 160 | 83.3% | 83.3% | 248.3 | 409.3 |
| 240 | 83.3% | 83.3% | 328.3 | 489.3 |
| 320 | 83.3% | 83.3% | 408.3 | 569.3 |
| 400 | 83.3% | 83.3% | 488.3 | 649.3 |
| 500 | 83.3% | 83.3% | 588.3 | 749.3 |

Longer evidence does not repair `case_0041`. On the probe stream, retry remains the
preferred candidate even at 500 steps. On the independent final stream, retry
fails at 500 steps while compensation succeeds at step 431. Candidate ordering
therefore reverses across stochastic realizations.

## Interpretation

The failure cannot be solved by extending a single probe trajectory or asking the
online model for more elaborate reasoning over that trajectory. One realization
does not estimate expected recovery utility under high execution noise. At 500
steps, extra evidence raises mean interaction cost to 749.3 steps without improving
the 83.3% recovery rate.

The next testable mechanism is repeated, paired candidate evaluation across common
random streams, followed by uncertainty-aware selection. This should first be
studied offline with separate tuning and validation streams. Only if repeated
evidence changes held-out candidate ranking should it be exposed to the online
Agent as a bounded decision interface.

## Artifacts

- `outputs/online_utility_agent/glm51_utility_dev/horizon_results.csv`
- `outputs/online_utility_agent/glm51_utility_dev/horizon_summary.csv`
- `outputs/online_utility_agent/glm51_utility_dev/horizon_utility_curve.png`

High-volume Agent trajectories are reproducible but excluded from Git.

## Reproduction

```powershell
python scripts/evaluate_horizon_utility.py --run-dir outputs/online_utility_agent/glm51_utility_dev

python scripts/plot_horizon_utility.py --summary-csv outputs/online_utility_agent/glm51_utility_dev/horizon_summary.csv --output outputs/online_utility_agent/glm51_utility_dev/horizon_utility_curve.png
```
