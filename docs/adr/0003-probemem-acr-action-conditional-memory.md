# ADR 0003: ProbeMem-ACR action-conditional memory

Status: accepted for development

## Context

ProbeMem v2 established negative results that remain immutable: retrieval was
behaviorally inert in Phase C; the frozen single-feature selector did not beat
the strongest fixed baseline; raw nearest-state retrieval mispredicted action
utility; and accepted-only coverage-aware memory still produced harmful
transfer. State similarity, prior success, and neighbor agreement were not
sufficient conditions for intervention utility transfer.

## Decision

ProbeMem-ACR changes the prediction target from a copied historical action to
the conditional fresh-verification outcome of each registered action. The
first phase uses a deterministic estimator over chronological, Agent-visible
evidence and paired development counterfactuals. Distance generates evidence
candidates only; it is not itself an action recommendation.

The phase is restricted to MetaWorld push-v3, the fixed SawyerPushV3Policy,
the existing diagnostic probe, bounded planar compensation, and independent
stochastic retry. It does not use an API, update policy weights, generate
principles, or make an online-memory benefit claim.

## Consequences

Development counterfactuals can test whether action-conditioned outcome
evidence is predictive, but they are not operational Agent experience. Only a
later promoted protocol may define selected-action chronological memory and an
online LLM comparison.
