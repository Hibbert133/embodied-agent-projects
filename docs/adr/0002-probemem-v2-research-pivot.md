# ADR 0002: Add ProbeMem v2 without rewriting budgeted-evidence v1

Status: Accepted for development
Protocol: `online_llm_scientific_memory_v2`

## Context

Budgeted-evidence v1 showed that a fixed probe can improve diagnosis efficiently,
but its held-out intervention experiment was not promoted. A mechanism label and
a short diagnostic response were insufficient proxies for downstream recovery
utility. Continuing to optimize that classifier would weaken the causal claim.

## Decision

Create an independent v2 protocol that studies verification-grounded,
action-conditional experience over a chronological deployment stream. The LLM is
a constrained reasoning layer over registered tools and skills. Deterministic
code owns validation, budgets, execution, verification, chronology, and future
memory promotion.

V1 configurations, seeds, manifests, thresholds, reports, and results remain
immutable. V2 uses separate configuration and output namespaces and cannot cite
v1 held-out outcomes as v2 training data.

## Consequences

The scientific claim becomes stronger but narrower: future improvement must be
traced to earlier freshly verified intervention experience, not to prompt changes
or Oracle fault labels. Phase B is only an integration/falsification milestone;
it cannot establish memory benefit. A sequential benchmark and principle memory
are deferred until the tool interface passes its promotion gate.
