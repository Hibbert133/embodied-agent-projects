# ProbeMem-ACR Deterministic Development Result

Run: `probemem_acr_20260802T103454Z_dedbf7f07ec8`

Manifest: `d2cb1281b5b1cad4804e36c519507a2e745d1c460ff76d574da99e040437b825`

Frozen source commit: `dedbf7f07ec814b9a96605920182007178d182ea`

## Question and protocol

This development-only paired counterfactual study asks whether a frozen,
transparent action-conditional outcome estimator predicts the better recovery
candidate more reliably than state-only retrieval. Seeds 1100--1199 each map to
exactly one of five registered conditions. Predictions use only unique prior
episode signatures; both candidate outcomes are appended after the prediction.
Compensation and retry start from independent resets with a shared paired
verification random stream.

The estimator uses the preregistered 13-feature order, prior-only population
standardization, standardized RMS distance, the five nearest records per action
and outcome class, weights `1 / (1 + distance)`, a unit Dirichlet prior, and
utility `P(ACCEPTED) + 0.5 * P(INCONCLUSIVE)`. No API or rendering was used.

## Population and integrity

- Initial units: 100, exactly 20 per condition.
- Operational paired cases: 66.
- Outcome partitions: 47 compensation-only, 4 retry-only, 2 both recover,
  and 13 neither recovers.
- Exclusive-recovery cases: 51; decisive-status cases: 61.
- Chronology violations: 0.
- Oracle leakage events: 0.
- Budget violations: 0.

## Actual comparison

| Method | Accepted | Coverage | Decisive correct | Harmful transfers |
|---|---:|---:|---:|---:|
| Always compensation | 49/66 | 100.0% | 57/61 | 4 |
| Always retry | 6/66 | 100.0% | 4/61 | 47 |
| State-only nearest accepted | 48/66 | 98.5% | 56/61 | 4 |
| Frozen v2 coverage-aware | 0/66 | 0.0% | 0/61 | 0 |
| Frozen single-feature selector | 5/66 | 100.0% | 3/61 | 48 |
| Deterministic action-conditional | 46/66 | 95.5% | 54/61 | 4 |

ACR decisive accuracy was 88.52%, 3.28 percentage points below state-only
retrieval (paired bootstrap 95% CI for ACR minus state-only: -9.84 to +3.28
points). Its accepted count was three below always compensation (accepted-rate
difference -4.55 points; paired 95% CI -10.61 to 0.00). Harmful transfer did not
decrease relative to state-only retrieval (difference 0; paired 95% CI -4.55
to +4.55 points).

Prediction audit across both candidates produced 106 supported, 17 unresolved,
and 9 contradicted resonance records. Status accuracy was 80.30%, acceptance
Brier score 0.1939, and progress MAE 0.0697. These prediction metrics did not
translate into better candidate selection.

## Promotion decision

All integrity and population requirements passed, but neither performance path
passed and recovery non-inferiority failed. The registered promotion gate is
therefore **FAILED** and `validation_authorized=false`. Seeds 1200--1249 and
1300--1399 were not run. The estimator is not retuned on seeds 1100--1199, and
the LLM action-prediction, principle-generation, and held-out stages remain
blocked.

## Research interpretation

Separating history by intervention is a better causal representation than
copying the action from the nearest successful state, but representation alone
did not yield a useful decision boundary here. The dataset is strongly skewed
toward compensation-only recovery, and the frozen local posterior mostly
preserves that dominant action. The result narrows the next scientific problem:
future work needs independently justified evidence that discriminates the four
retry-only cases without sacrificing compensation-dominant recovery, rather
than another distance tweak or post-hoc threshold fit.

## Claim boundary

Paired counterfactual outcomes are evaluator-only development evidence, not
experience naturally available to an online deployed Agent. This result does
not establish online learning, LLM memory benefit, principle learning,
validation, or held-out improvement.
