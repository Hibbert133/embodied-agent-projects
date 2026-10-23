# ProbeMem Calibrated Verifier v2: Calibration Result

Status: `CALIBRATION_FAILED_NO_ELIGIBLE_THRESHOLD_COMBINATION`

This is a development-only calibration result, not validation, held-out
evidence, or a statistical superiority claim.

## Immutable provenance

- Run ID: `probemem_calibrated_verifier_calibration_20260804T132849Z_072b93ad1545`
- Manifest ID: `18024ea6cb0486715487d412c81c40839eb185c9f935a5749e795aca0e639993`
- Source commit: `072b93ad154546b8605dfa2e9ccac4a8a6e54b29`
- Episode seeds: 4800--4899, scanned once in ascending order

The collection exhausted 100 initial units and produced 37 operational cases,
including 18 evaluator-only exclusive-recovery cases. Both population minima
were met. Chronology, Oracle leakage, future-memory access, counterfactual
writes, budget violations, invalid memory IDs, and invalid skill executions
were all zero.

## Descriptive method results

| Method | Accepted | Calls | Overrides | Helpful | Harmful | Tie |
|---|---:|---:|---:|---:|---:|---:|
| Frozen deterministic | 28/37 | 0 | 0 | 0 | 0 | 0 |
| Unweighted verifier v1 | 26/37 | 21 | 3 | 0 | 2 | 1 |
| Weighted posterior with v1 guard | 26/37 | 21 | 2 | 0 | 2 | 0 |
| Evaluator-only Oracle | 33/37 | 0 | 15 | N/A | N/A | N/A |

Distance weighting alone did not improve operational recovery or override
quality under the frozen v1 guard.

## Posterior calibration

| Predictor | Default Brier | Alternative Brier | Pooled Brier | Pooled NLL | Pooled ECE |
|---|---:|---:|---:|---:|---:|
| Unweighted v1 | 0.147804 | 0.186186 | 0.166995 | 0.620856 | 0.150901 |
| Weighted posterior | 0.149287 | 0.186069 | 0.167678 | 0.620343 | 0.149127 |

The weighted posterior had slightly lower pooled NLL and ECE, but worse Brier.
Mean 95% interval width was 0.5861, and default/alternative intervals overlapped
in all 37 cases. True parameter coverage is `N/A_SINGLE_REALIZATION` because
each candidate has one Bernoulli realization.

## Frozen grid result

All 4,800 preregistered combinations were replayed chronologically, each writing
only its selected outcome. Every combination produced zero overrides because
the strict 95% interval-separation condition never passed. There were zero
eligible combinations and no selected thresholds, so prospective development
is blocked.

This does not authorize a post-hoc interval, prior, distance, top-k, or threshold
change. The stream will not be revised or rerun. Artifacts are under
`outputs/probemem_calibrated_verifier/calibration/runs/probemem_calibrated_verifier_calibration_20260804T132849Z_072b93ad1545/`.
