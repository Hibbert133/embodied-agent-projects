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
