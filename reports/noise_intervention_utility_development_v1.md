# Noise-Stratum Intervention Utility Development v1

## Research question

Within the registered stochastic-noise condition, can existing Agent-visible
evidence distinguish failures where an independent retry is preferable from
failures where probe-grounded compensation remains preferable?

This is a development characterization, not a fitted selector or held-out claim.

## Provenance and setup

- Run: `development_20260731T032936Z_72681fa3b583`
- Source commit: `72681fa3b5837da2a1a49025763095ebc506979f`
- Seeds: 410--429
- Condition: registered `fault_05` stochastic noise
- Full initial units: 20
- Operational failures: 7
- Paired comparable cases: 7
- Candidate-specific probes: none
- API calls: 0
- Timing render: disabled; representative videos were rerun afterward

The two candidates share task initialization and verification perturbation
realization. `retry_preferred` is evaluator-only and is computed after both fresh
verification outcomes exist.

## Candidate outcomes

| Measure | Compensation | Retry |
| --- | ---: | ---: |
| Preferred candidate count | 4/7 | 3/7 |
| Fresh-verification success | 4/7 | 4/7 |
| Mean verification steps | 285.7 | 283.3 |
| Mean final object-goal distance | 0.184 m | 0.131 m |

The broad stochastic-noise mechanism selected retry for every case, but retry
was outcome-preferred in only 3/7. Passive belief aligned with preferred utility
in 5/7, while post-probe mechanism routing aligned in 3/7. Six beliefs changed;
two changes improved the selected outcome and four made it worse.

The earlier seeds 400--409 audit contained four comparable stochastic-noise
failures: three retry-preferred and one compensation-preferred. Descriptively
pooling the two disjoint development audits gives six retry-preferred and five
compensation-preferred cases out of eleven. This pooled count is contextual only;
the registered feature analysis below uses seeds 410--429 alone.

## Preregistered feature characterization

No threshold or multi-feature model was fitted.

| Agent-visible score | ROC AUC | PR AUC | Retry median | Compensation median |
| --- | ---: | ---: | ---: | ---: |
| Phase inconsistency | 0.75 | 0.83 | 0.984 | 0.966 |
| Temporal uncertainty | 0.75 | 0.83 | 0.974 | 0.969 |
| Probe bias std norm | 0.67 | 0.81 | 0.745 | 0.548 |
| Relative bias std | 0.75 | 0.64 | 4.398 | 1.829 |
| Probe residual | 0.33 | 0.59 | 2.93e-5 | 4.79e-5 |
| Sign disagreement | 0.33 | 0.37 | 0.50 | 0.50 |

Phase inconsistency, temporal uncertainty, and relative probe variance are
candidate signals, but seven cases are insufficient to freeze a decision rule.
Residual and sign disagreement fail in their preregistered directions on this
split and should not be direction-flipped after inspection.

## Representative paired cases

Selection used the smallest case ID satisfying each rule.

### Retry helpful: seed 412

- compensation: `INCONCLUSIVE`, 500 steps, final distance 0.372 m;
- retry: `ACCEPTED`, 119 steps, final distance 0.048 m.

### Retry harmful: seed 418

- compensation: `REJECTED`, 500 steps, final distance 0.158 m;
- retry: `REJECTED`, 500 steps, final distance 0.247 m.

The second case does not claim compensation success. It shows that retry can
produce strictly worse task progress even under the correct stochastic-noise
mechanism label.

## Interpretation and limitation

The registered mechanism taxonomy is useful for diagnosis but too coarse for
intervention selection. The scientific target should be action-conditional
utility under uncertainty, not mechanism accuracy alone.

The current operational sample is small because 13/20 initial noise rollouts
succeeded and required no adaptation. AUC values are therefore exploratory.
They do not justify a frozen selector, memory promotion, or GLM comparison.

## Reproduction

```powershell
python scripts/run_intervention_identifiability_development.py --config configs/autoresearch/noise_intervention_utility_development_v1.json
python scripts/analyze_noise_intervention_utility.py --run-dir outputs/intervention_identifiability/runs/development_20260731T032936Z_72681fa3b583
python scripts/validate_intervention_identifiability_artifacts.py --run-dir outputs/intervention_identifiability/runs/development_20260731T032936Z_72681fa3b583
python scripts/plot_noise_intervention_utility.py --run-dir outputs/intervention_identifiability/runs/development_20260731T032936Z_72681fa3b583
python scripts/render_noise_intervention_utility_cases.py --run-dir outputs/intervention_identifiability/runs/development_20260731T032936Z_72681fa3b583
```
