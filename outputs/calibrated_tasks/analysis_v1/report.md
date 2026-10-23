# Qualified response prior: prospective task utility

Status: `COMPLETED_FEASIBILITY_PASS`. Integrity: `PASSED`.

16 independent task-seed clusters x four contexts; 500 online steps per method episode. All states included.

| Method | Success / 64 | Mean online steps | Offline steps | Mean amortized steps | Mean offset error | Success with 484 policy steps |
|---|---:|---:|---:|---:|---:|---:|
| NO_PROBE | 19 | 379.09 | 0 | 379.09 | n/a | 19 |
| CONT_NO_CORRECTION | 33 | 307.22 | 0 | 307.22 | n/a | 33 |
| CONT_DYNAMIC | 22 | 358.28 | 0 | 358.28 | 0.1785 | 22 |
| PRIOR_AFFINE | 64 | 79.36 | 2304 | 115.36 | 0.0170 | 64 |
| PRIOR_NEAREST | 62 | 92.05 | 2304 | 128.05 | 0.0415 | 62 |

Both priors pay 2,304 offline steps and 144 resets, amortized over 64 units. Offline artifacts were physically shared, not recollected.
The final column is a secondary equal-policy-step cap that permits additional probe cost; it is not used for promotion.

- Affine minus NO_PROBE: +70.31 pp; seed-cluster 95% interval [59.38, 81.25] pp.
- Affine minus CONT_NO_CORRECTION: +48.44 pp; seed-cluster 95% interval [39.06, 57.81] pp.
- Affine minus CONT_DYNAMIC: +65.62 pp; seed-cluster 95% interval [56.25, 75.00] pp.
- Affine minus PRIOR_NEAREST: +3.12 pp; seed-cluster 95% interval [0.00, 7.81] pp.

Registered utility gates: `{'evidence_utility': True, 'no_probe_count': True, 'dynamic_count': True}`.

320 decisions, 256 continuous handoffs, and 73728 task-step state/RNG links verified.
New physical task collection: 77824 steps and 320 initial resets.

Decision/model replay, exact observation hash chains and RNG consumption. Task dynamics are not resimulated.

This is a standard calibrated-identification baseline. Task benefit does not establish algorithm novelty, multi-task transfer, or publication readiness.
