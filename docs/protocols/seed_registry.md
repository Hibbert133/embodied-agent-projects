# Episode Seed Registry

The machine-readable source is
`configs/probemem_acr/seed_registry_v1.json`. Structured seed-field scanning
confirmed that the following episode seeds were unused before ProbeMem-ACR:

| Partition | Seeds | Status |
|---|---:|---|
| ACR development | 1100--1199 | frozen for one development run |
| ACR validation | 1200--1249 | reserved, not authorized |
| ACR held-out | 1300--1399 | reserved, not authorized |

Random seed namespaces are not episode seeds and are audited separately.
Development uses namespaces 8301, 8302, and 8303 for initial perturbation,
diagnostic probe, and paired verification respectively. Bootstrap uses 9301.

## Retry-utility replication reservation

The separately frozen `probemem_acr_retry_utility_replication_v1` protocol
reserves fresh ranges after the original ACR registry:

- development replication: 1400--1499;
- validation reserved: 1500--1549;
- held-out reserved: 1550--1599.

These ranges were checked against existing configs and outputs before the
protocol was frozen. Only 1400--1499 may be executed by the replication.

## Utility-realization stability reservation

The separately versioned
`probemem_acr_utility_realization_stability_v1` protocol reserves:

- development: 1600--1699;
- validation reserved: 1700--1749;
- held-out reserved: 1750--1799.

Only development seeds 1600--1699 may be scanned, with a label-blind stop after
20 failed initial rollouts. The protocol estimates repeated action-outcome
distributions and cannot fit a selector or execute the reserved partitions.

The v1 execution stopped after 13 complete cases because paired-candidate
eligibility was underspecified. Its partial artifacts remain immutable. The v2
correction uses fresh development seeds 1800--1899 and reserves 1900--1999;
eligibility requires both candidates to be constructible before any outcome is
executed or read.

## Distributional memory development reservation

The `probemem_acr_distributional_memory_development_v1` protocol uses fresh
development seeds 2000--2099 and reserves 2100--2199. It stops after 40
Agent-visibly eligible failed cases without reading candidate outcomes. Only
2000--2099 may be executed; validation and held-out partitions remain blocked.

The v1 run exhausted all 100 initial units with 39/40 operational cases and is
preserved as `INCOMPLETE_POPULATION`. It is not extended. The separately
versioned v2 population reserves:

- development: 2200--2349;
- validation reserved: 2350--2399;
- held-out reserved: 2400--2499.

Only 2200--2349 may be scanned under v2, with the unchanged label-blind stop at
40 eligible failures. The larger initial population is a preregistered capacity
correction; it does not relax the operational target or estimator gate.
