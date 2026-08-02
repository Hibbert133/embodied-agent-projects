# ProbeMem-ACR Failure Localization

Source run: `probemem_acr_20260802T103454Z_dedbf7f07ec8`

This is a no-new-rollout, evaluator-only analysis. It fitted no threshold,
created no selector, and made no validation or held-out claim.

## Finding

The frozen campaign contained 51 exclusive-recovery cases: 47
compensation-only and 4 retry-only. Deterministic ACR selected compensation in
all four retry-only cases and therefore recovered none of them.

Across all exclusive cases, `phase_inconsistency` and
`probe_mean_estimation_residual` each had tie-aware rank separation 1.0 between
retry-only and compensation-only outcomes. Several probe-variability features
also had high descriptive separation.

## Critical confound

All four retry-only cases came from evaluator condition `fault_05`. Only one
compensation-only case shared that condition. The apparent separation can
therefore reflect condition identity rather than within-condition intervention
utility. It must not be used to set a threshold or recommend retry.

## Falsifiable next step

`probemem_acr_retry_utility_replication_v1` prospectively tests only the two
registered directions within fresh `fault_05` seeds 1400--1499. It requires
adequate exclusive-outcome diversity and does not fit a selector. Validation
and held-out seeds remain reserved.

## Outputs

- `outputs/probemem_acr/failure_localization_cases.csv`
- `outputs/probemem_acr/failure_localization_feature_contrasts.csv`
- `outputs/probemem_acr/failure_localization_summary.json`
- `outputs/probemem_acr/figures/acr_retry_only_feature_contrasts.png`
