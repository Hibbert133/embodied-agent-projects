# ProbeMem-ACR Retry-Utility Replication v1

Run: `acr_retry_replication_20260802T112921Z_1c45014434b2`

Manifest: `1fb27aa4238731c97cfa9ae07607ac84b6fbb5d4ddecc17ab3bdb3533329dca1`

## Prospective question

Within fresh `fault_05` seeds, do retry-only recoveries show higher
`phase_inconsistency` and `probe_mean_estimation_residual` than
compensation-only recoveries? The protocol tests feature direction only. It
does not fit an intervention rule.

## Actual population

- Initial units: 100, seeds 1400--1499.
- Operational paired cases: 36.
- Retry-only: 11.
- Compensation-only: 5.
- Both recover: 14.
- Neither recovers: 6.
- Chronology, Oracle-leakage, and budget violations: 0.

## Registered endpoints

| Endpoint | P(retry-only > compensation-only) | Bootstrap 95% CI | Required | Result |
|---|---:|---:|---:|---|
| Phase inconsistency | 0.673 | 0.400--0.909 | >=0.70 | Fail |
| Probe mean estimation residual | 0.727 | 0.418--0.982 | >=0.70 | Pass |

The population gate also required at least eight cases in each exclusive
group. Retry-only met the requirement (11), while compensation-only did not
(5). The combined replication gate therefore failed.

## Interpretation

The original perfect post-hoc separation did not replicate for phase
inconsistency after controlling the registered condition. Probe estimation
residual retained the registered direction, but its interval is wide and the
comparison lacks the required compensation-only sample size. It cannot support
a threshold or selector.

The result suggests that stochastic intervention utility is not captured by a
stable monotonic phase-inconsistency signal. A larger or more mechanistically
targeted evidence design would need a new protocol and fresh seeds; extending
this run or tuning against its outcomes is prohibited.

## Decision

`replication_gate_passed=false`. No selector fitting, GLM action reasoning,
validation, or held-out execution is authorized by this result. Seeds
1500--1599 remain untouched.
