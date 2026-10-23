# Continuous-probe matched-budget result

Status: `COMPLETED_FEASIBILITY_FAILED`. Integrity: `PASSED`.

Eight independent task seeds x four contexts; five baselines. All states included, 500 total steps each.

| Method | Success / 32 | Mean total steps | Resets | Valid fits | Mean offset error | Success with 484 task steps |
|---|---:|---:|---:|---:|---:|---:|
| NO_PROBE | 12 | 364.88 | 32 | 0 | n/a | 12 |
| CONT_NO_CORRECTION | 13 | 347.16 | 32 | 0 | n/a | 13 |
| CONT_STATIC | 5 | 436.19 | 32 | 32 | 0.7965 | 5 |
| CONT_DYNAMIC | 15 | 305.16 | 32 | 32 | 0.2087 | 15 |
| RESET_REFERENCE | 31 | 87.53 | 160 | 32 | 0.0950 | 31 |

The final column is secondary: equal policy-step cap permits additional probe cost. RESET_REFERENCE is privileged by resets.

- CONT_STATIC vs probe-without-correction: -25.00 pp; 97.5% seed-cluster interval [-50.00, 0.00] pp.
- CONT_DYNAMIC vs probe-without-correction: +6.25 pp; 97.5% seed-cluster interval [-9.38, 21.88] pp.

Passing standard estimators: `[]`.

160 decisions replayed; 96 continuous handoffs and 47261 task-step RNG/observation links verified.
Physical steps: 49309; explicit resets: 288.

Visible decisions, hash-chain continuity, complete actuator RNG consumption, budgets and statistics. Task dynamics are not resimulated.

This is standard-baseline development evidence, not a new algorithm, multi-task validation, or publication readiness.
