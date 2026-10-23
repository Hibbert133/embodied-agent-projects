# Prospective evidence refresh: strong-baseline result

Status: `COMPLETED_FEASIBILITY_FAILED`

- experiment_run_id: `evidence_refresh_20261013T092539Z_ac3fa90f6d20`
- manifest_id: `2cf32cb330906f2df423b24800d7fe5fb1389c8f94456aeb5da062569891a96b`
- source_git_commit: `ac3fa90f6d20f433675ebbf497af281a814807c5`

Eight independent chronological streams; all 96 task states included. Task success, not initial-failure recovery.

| Method | Success / 96 | Mean probe steps | Mean total path steps | Stationary / 48 | Abrupt / 48 |
|---|---:|---:|---:|---:|---:|
| FIXED_16 | 88 | 16.00 | 116.93 | 44 | 44 |
| FIXED_32 | 88 | 32.00 | 131.89 | 43 | 45 |
| FIXED_64 | 88 | 64.00 | 163.56 | 43 | 45 |
| STALE | 71 | 5.33 | 183.53 | 48 | 23 |
| PERIODIC_4 | 71 | 16.00 | 194.41 | 43 | 28 |
| CHANGE_THRESHOLD | 89 | 51.00 | 146.06 | 43 | 46 |
| DECISION_STABILITY | 87 | 37.17 | 141.41 | 43 | 44 |
| UNCORRECTED | 41 | 0.00 | 333.27 | 22 | 19 |

Candidate minus FIXED_64: -1.04 percentage points; 95% stream-bootstrap interval [-3.12, 0.00].
Probe saving vs FIXED_64: 41.9%.
Dominating baselines: ['FIXED_16', 'FIXED_32'].
Frozen performance gates: {'success_tolerance': True, 'probe_saving': True, 'not_pareto_dominated': False}.

All 768 decisions and 205 accepted cache writes reproduced from charged prefixes and strictly prior method-owned state. Probe inference was recomputed from visible transitions; source hashes, sequence, branch, cost, and reset audits passed.

This development test does not establish calibrated confidence, novelty, unseen-task generalization, or publication readiness.

## Paired comparisons

All intervals resample eight whole streams. Comparisons beyond the frozen gate are descriptive; no multiplicity-adjusted claim.

| Candidate minus baseline | Difference (pp) | 95% stream interval (pp) |
|---|---:|---:|
| FIXED_16 | -1.04 | [-4.17, 2.08] |
| FIXED_32 | -1.04 | [-4.17, 2.08] |
| FIXED_64 | -1.04 | [-3.12, 0.00] |
| STALE | +16.67 | [-4.17, 37.50] |
| PERIODIC_4 | +16.67 | [4.17, 30.21] |
| CHANGE_THRESHOLD | -2.08 | [-5.21, 0.00] |
| UNCORRECTED | +47.92 | [40.62, 56.25] |

## Acquisition and action diagnostics

These are post-collection descriptions, not new selection rules or tuned thresholds.

| Method | 0 repeats | 1 repeat | 2 repeats | 3 repeats | 4 repeats | Different action vs fixed 64 (win/loss/tie) |
|---|---:|---:|---:|---:|---:|---|
| FIXED_16 | 0 | 96 | 0 | 0 | 0 | 3/3/34 |
| FIXED_32 | 0 | 0 | 96 | 0 | 0 | 2/2/26 |
| FIXED_64 | 0 | 0 | 0 | 0 | 96 | 0/0/0 |
| STALE | 88 | 0 | 0 | 0 | 8 | 6/23/27 |
| PERIODIC_4 | 72 | 0 | 0 | 0 | 24 | 1/18/15 |
| CHANGE_THRESHOLD | 0 | 26 | 0 | 0 | 70 | 1/0/6 |
| DECISION_STABILITY | 0 | 45 | 11 | 4 | 36 | 0/1/5 |
| UNCORRECTED | 96 | 0 | 0 | 0 | 0 | 2/49/45 |

Candidate stopping reasons: `{'BOOTSTRAP_OR_PERIODIC': 8, 'MAXIMUM_PREFIX_UNRESOLVED': 24, 'CURRENT_ACTION_MATCHES_CACHE': 45, 'LEAVE_ONE_OUT_ACTION_STABLE': 19}`.

Physical collection: 332 task rollouts, 68593 task steps and 6144 probe steps.
