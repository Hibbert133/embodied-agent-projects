# ProbeMem-ACR Utility Realization Stability v2

## Research question

Earlier ACR experiments treated one paired compensation-versus-retry outcome
as the intervention label for a task state. This prospective development study
tested whether that label is stable under independent stochastic execution.

## Frozen setup

- MetaWorld `push-v3`, fixed `SawyerPushV3Policy`, `fault_05` only.
- Fresh development seeds 1800--1899; seeds 1900--1999 remained untouched.
- Label-blind stop after 20 paired-candidate-eligible failed initial rollouts.
- One registered 64-step probe and six independent verification realizations.
- Candidate pairs shared randomness within a realization and used independent
  resets; different realizations used independent streams.
- 45 initial units were scanned; one failed unit was Agent-visibly ineligible.
- No API, selector, threshold fitting, memory write, validation, or held-out run.

The preceding v1 execution stopped after 13 complete cases because candidate
eligibility was undefined. Its partial artifacts were not used by v2.

## Real results

V2 collected 20 operational states and 240 fresh candidate rollouts.

| Quantity | Result |
|---|---:|
| Stable mean-utility preferences (`|margin| >= 0.20`) | 11/20 |
| States with a winner reversal across realizations | 18/20 |
| Leave-one-realization-out winner reliability | 77/120 = 64.2% |
| Cluster-bootstrap 95% CI | 55.0%--73.3% |
| Compensation accepted | 61/120 = 50.8% |
| Retry accepted | 82/120 = 68.3% |
| Compensation / retry mean within-state status entropy | 0.635 / 0.594 |

The feasibility gate required 20 operational states, eight stable preferences,
70% winner reliability, and zero integrity failures. Reliability was only
64.2%, so the gate failed. Chronology, Oracle leakage, budget,
pair-completeness, and paired-random-stream violations were all zero.

## Interpretation

Intervention utility is not a deterministic label attached to a state: 18 of
20 states changed candidate winner across independent realizations. A single
retry-only or compensation-only observation is a noisy sample of an
action-outcome distribution and is unsafe to store as a reusable principle.

Retry had higher aggregate accepted probability in this `fault_05` population,
but that does not validate a per-state selector. The correct future ACR target
is calibrated action-conditional outcome distributions with abstention when
posterior separation is weak—not nearest-neighbor imitation of one success.

This is development-only evaluator evidence. It does not show online learning,
LLM benefit, memory benefit, validation performance, or held-out improvement.
Selector fitting, GLM reasoning, principle promotion, and seeds 1900--1999
remain unauthorized.

## Representative stochastic reversal

The renderer mechanically selected the smallest state seed containing both a
compensation-only and retry-only realization: seed 1805. Realization 1 accepts
compensation while retry is inconclusive; realization 2 rejects compensation
while accepting retry. Four audited videos reproduce the exact frozen CSV
outcomes under the original paired random streams. They are stored under
`outputs/probemem_acr/videos/stochastic_reversal/` with `manifest.csv`.

## Reproduction

```bash
python scripts/generate_probemem_acr_utility_stability_manifest.py
python scripts/run_probemem_acr_utility_stability.py --manifest outputs/probemem_acr/utility_stability_runs/acr_utility_stability_20260802T120914Z_8b9c2f827d59/manifest.json
python scripts/analyze_probemem_acr_utility_stability.py --run-dir outputs/probemem_acr/utility_stability_runs/acr_utility_stability_20260802T120914Z_8b9c2f827d59
python scripts/render_probemem_acr_utility_stability.py --run-dir outputs/probemem_acr/utility_stability_runs/acr_utility_stability_20260802T120914Z_8b9c2f827d59
```

Run ID: `acr_utility_stability_20260802T120914Z_8b9c2f827d59`

Manifest ID: `9cc531eecc45cfe63790729ccf52c3b2994c8e46e46b7e31ddc9c13dea339cda`

Frozen source commit: `8b9c2f827d593a29ca389da863d02f99b6ebbded`
