# Evidence persistence: crossed-context result

Status: `COMPLETED_FEASIBILITY_PASS`

- experiment_run_id: `evidence_persistence_20261013T085037Z_6b88d1b48e41`
- manifest_id: `4eb8ad74c102163067a6f6b294854a3d74c362c8a63f6cd8903c262aec7c6b8a`
- source_git_commit: `6b88d1b48e41162d252b49653b06041b52f30dfb`

Evaluator-only task-success experiment; all task states included. Not failure recovery or an online agent evaluation.

| Method | Coupling | Success / logical cases | Rate | Mean logical steps |
|---|---|---:|---:|---:|
| PROBE_COMPENSATION | aligned | 52/64 | 81.2% | 211.48 |
| PROBE_COMPENSATION | independent | 101/256 | 39.5% | 393.86 |
| UNCORRECTED | aligned | 22/64 | 34.4% | 368.86 |
| UNCORRECTED | independent | 88/256 | 34.4% | 368.86 |

Primary coupling interaction: **+41.80%**; 95% task-cluster bootstrap interval **[38.67%, 45.31%]**.

The independent sample unit is the task seed (16 clusters), not the 512 logical rows. The independent-context estimator includes the diagonal. The source-independent control has zero coupling effect.

Physical execution: 320 task rollouts, 108052 task steps and 4096 probe steps. Logical control rows reuse target rollouts with an explicit branch ID.

Independent audit: chronology, reset identity, manifest/source hashes, cached branches, complete factorial population, budgets, and registered statistics reproduced. No API calls or memory writes.

This is development feasibility for evidence transport. It does not establish a novel algorithm, selective acquisition, memory improvement, unseen-task generalization, or paper readiness.
