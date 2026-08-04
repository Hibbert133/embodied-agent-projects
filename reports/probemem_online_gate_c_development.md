# ProbeMem-Online Chronological Development Result

## Status

Run status: `COMPLETED`

Operational cases: `60/60`

This completed development run may be interpreted only according to the preregistered promotion gate.

## Recovery and harmful transfer

| Method | Accepted | Rate | Harmful selections | Abstentions | Total environment steps |
| --- | ---: | ---: | ---: | ---: | ---: |
| ALWAYS_COMPENSATION | 38/60 | 63.3% | 12 | 0 | 48519 |
| ALWAYS_RETRY | 31/60 | 51.7% | 19 | 0 | 51455 |
| DETERMINISTIC_ACTION_POSTERIOR | 38/60 | 63.3% | 12 | 0 | 48519 |
| EVALUATOR_ONLY_ORACLE | 50/60 | 83.3% | 0 | 0 | 44027 |
| FROZEN_VARIANCE_RULE | 43/60 | 71.7% | 7 | 0 | 46078 |
| GLM_FROZEN_BOOTSTRAP_MEMORY | 38/60 | 63.3% | 12 | 0 | 48245 |
| GLM_ONLINE_ACTION_MEMORY | 40/60 | 66.7% | 10 | 0 | 47386 |
| GLM_ONLINE_MEMORY_RESONANCE | 41/60 | 68.3% | 9 | 0 | 46954 |
| STATELESS_GLM | 40/60 | 66.7% | 10 | 0 | 47365 |

## Memory decision pathway

Relative to stateless GLM, the full resonance Agent changed the selected action
in 12 cases: 4 helpful, 3
harmful, and 5 verification-status ties.

These counts require an actual registered-skill change. Changes in explanation,
confidence, or prediction without an action change are not counted as memory
benefit.

Paired accepted-rate difference: 1.7
percentage points, paired bootstrap 95% CI
[-6.7, 10.0].
Status-utility win/tie/loss: 4/53/3.

## Online model operation

* API calls: 242
* Valid structured outputs: 240
* Valid final decisions: 240/240
* Schema-repair calls: 2
* Input/output tokens: 435165 / 470379
* Median latency: 42.6 s
* p90 latency: 86.8 s
* Maximum latency: 136.3 s

API latency is reported separately from robot environment interaction.

## Integrity and claim boundary

Integrity counters: `{'chronology_violations': 0, 'oracle_leakage_events': 0, 'budget_violations': 0, 'random_namespace_violations': 0, 'future_memory_access': 0, 'counterfactual_memory_writes': 0, 'invalid_memory_ids': 0, 'invalid_skill_executions': 0}`

## Promotion gate

Overall promotion: **FAIL**

| Check | Result |
| --- | --- |
| action_change_rate_at_least_15_percent | PASS |
| net_helpful_changes_at_least_3 | FAIL |
| harmful_transfer_reduction_at_least_30_percent | FAIL |
| recovery_within_one_case_of_strongest_deterministic | FAIL |
| post_shift_gain_or_equal_recovery_lower_cost | FAIL |

Diagnostics:

* Full accepted: 41
* Strongest deterministic accepted: 43
* Net helpful changes: 1
* Harmful-transfer reduction: 0.1
* Full post-shift rate: 0.6153846153846154
* Stateless post-shift rate: 0.6923076923076923

This development run does not establish validation, held-out generalization,
policy learning, VLA improvement, or cross-task transfer. Evaluator-only paired
outcomes are never written to operational memory.
