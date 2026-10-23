# ProbeMem-ACR Independent Resonance Validation v1

## Status

`INCOMPLETE_FOR_VALIDATION` and `NOT_PROMOTED`.

The immutable population was fully executed, but it produced only 55 eligible
first attempts and 16 second-decision cases, below the preregistered minima of
60 and 25. No seeds may be added and the run may not be repeated or replaced.
The descriptive matched result also fails the promotion direction.

## Provenance and integrity

- source commit: `ac9d40d8d581d774f55a1746b3aa90dbdcae9960`;
- run: `acr_resonance_validation_20260803T023904Z_ac9d40d8d581`;
- manifest: `f8afcf766c5c01da0d89ae7053e5ae07f023f8902c52cefe203a9fcadded5655`;
- validation seeds: 3050--3099 followed by 3200--3299;
- initial units executed: 150/150;
- held-out seeds 3100--3199 executed: 0;
- eligible first attempts: 55;
- first retry accepted: 39;
- second-decision cases: 16;
- paired second-candidate rollouts: 32;
- API calls: 0.

Chronology, Oracle leakage, budget, random namespace, attempt limit, manifest,
and counterfactual pre-decision violations were all zero. The recurring
Gymnasium observation-space and MetaWorld policy clipping warnings did not stop
or invalidate any rollout.

## Descriptive matched results

These values are retained for audit but cannot be promoted as a completed
validation result.

| Method | Accepted | Added recoveries | Harmful selections | Mean steps | Mean final distance |
|---|---:|---:|---:|---:|---:|
| One retry | 39/55 (70.9%) | 0 | 0 | 802.58 | 0.1129 |
| Always repeat retry | **50/55 (90.9%)** | 11 | **1** | **868.49** | 0.0700 |
| Always switch compensation | 47/55 (85.5%) | 8 | 4 | 902.96 | 0.0748 |
| Frozen status-conditioned | 47/55 (85.5%) | 8 | 4 | 900.82 | 0.0781 |
| Rejection-abstain | 44/55 (80.0%) | 5 | 1 | 838.56 | 0.0981 |
| Per-case Oracle audit | 51/55 (92.7%) | 12 | 0 | 872.62 | 0.0612 |

Always repeat was the strongest fixed second policy. Relative to it, the frozen
status rule had 0 paired wins, 52 ties, and 3 losses. It recovered three fewer
cases, produced three additional harmful selections, and used 32.33 more steps
per eligible case on average.

Paired bootstrap differences, status rule minus always repeat:

- accepted rate: -5.45 percentage points, 95% CI [-12.73, 0.00];
- harmful-selection rate: +5.45 points, 95% CI [0.00, 12.73];
- environment steps: +32.33, 95% CI [7.98, 61.96].

## Research interpretation

The development observation that `REJECTED -> switch compensation` improved
recovery did not transfer to this independent population. In validation,
repeat retry recovered six of eight first-`REJECTED` cases, while switching
compensation recovered only three. The first status is therefore not a stable,
sufficient intervention-utility signal under the current stochastic protocol.

This result strengthens the project's negative evidence rather than supporting
the proposed broad method: static similarity failed, and a single categorical
fresh-verification status also fails to generalize. A future development-only
hypothesis may examine richer causal feedback such as progress magnitude,
distance response, or repeated verification uncertainty, but it cannot tune on
this validation artifact or access held-out seeds.

GLM development, verification-transition memory, Principle Memory, and held-
out execution remain unauthorized.

## Artifacts

- run directory: `outputs/probemem_acr/resonance_validation_runs/acr_resonance_validation_20260803T023904Z_ac9d40d8d581/`;
- figure: `outputs/probemem_acr/figures/acr_resonance_validation_v1.png`;
- protocol: `docs/protocols/resonance_validation_v1.md`.
