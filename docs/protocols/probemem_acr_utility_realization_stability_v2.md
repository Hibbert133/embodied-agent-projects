# ProbeMem-ACR Utility Realization Stability v2

Status: `FROZEN_BEFORE_EXECUTION`

This protocol preserves every question, estimand, repetition count, and gate
from v1. The v1 run stopped after 13 complete operational cases when the host
planner abstained from constructing bounded compensation for a later failed
case. No formal analysis was performed.

V2 makes the missing eligibility rule explicit before using fresh seeds:

```text
operational = initial rollout failed
              and registered probe is valid
              and both registered candidate skills are constructible
                  from Agent-visible probe evidence
```

Eligibility is checked before any candidate verification and cannot inspect a
candidate outcome. An ineligible failure is retained with its reason and does
not count toward the 20-case target. V2 uses fresh development seeds 1800--1899
and reserves 1900--1999. It does not reuse v1's partially observed seeds.

All remaining execution rules and estimands are defined in
`probemem_acr_utility_realization_stability_v1.md`. V2 still cannot fit a
selector, invoke an LLM, write online memory, or execute validation/held-out
partitions.
