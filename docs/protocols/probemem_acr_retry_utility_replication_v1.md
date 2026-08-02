# ProbeMem-ACR Retry-Utility Replication v1

Status: `FROZEN_BEFORE_EXECUTION`

## Motivation

The completed ACR development campaign contained four retry-only recoveries.
All four came from evaluator condition `fault_05`, and deterministic ACR chose
compensation in all four. Post-hoc analysis found higher phase inconsistency
and probe mean estimation residual in these four cases than in 47
compensation-only cases, but only one compensation-only case shared
`fault_05`. The original contrast is therefore condition-confounded and cannot
define an intervention rule.

## Prospective question

Within a fresh stream containing only registered condition `fault_05`, do
retry-only recoveries still exhibit higher Agent-visible phase inconsistency
and probe mean estimation residual than compensation-only recoveries?

This is a prospective development replication of feature direction. It is not
an intervention selector, validation experiment, online-memory experiment, or
held-out claim.

## Population

Development replication uses exactly seeds 1400--1499. Each seed receives
`fault_05`; initial perturbation, registered probe, and paired candidate
verification use independent namespaces 8401, 8402, and 8403. Both candidates
start from independent resets and share the paired verification random stream.

Seeds 1500--1549 and 1550--1599 are reserved and must not be executed by this
protocol. A repository scan found no previous registered use of 1400--1599
before this protocol was written.

## Registered endpoints

For exclusive-recovery cases only, compute tie-aware
`P(retry-only feature > compensation-only feature)` separately for:

1. `phase_inconsistency`;
2. `probe_mean_estimation_residual`.

The replication gate requires at least 30 operational cases, at least eight
retry-only and eight compensation-only cases, and rank probability at least
0.70 for both features. Chronology, Oracle-leakage, and budget violations must
all be zero.

No threshold is fit. No other feature may replace a registered endpoint after
results are observed. If population diversity or either direction fails, the
result is retained and this hypothesis is not promoted.

## Claim boundary

Passing would justify a separately frozen development-stage selector design;
it would not itself show improved recovery. Failure blocks threshold fitting,
GLM action prediction, validation, and held-out execution under this line of
work.
