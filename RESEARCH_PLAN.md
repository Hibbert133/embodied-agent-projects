# Budgeted Active Evidence Acquisition Research Roadmap

The canonical experimental roadmap is maintained in:

- [Frozen Execution Plan v1](docs/research/frozen_execution_plan_v1.md)
- [Held-Out Allocation Protocol v1](docs/protocols/heldout_allocation_v1.md)
- [Problem Definition](docs/problem_definition.md)
- [Agent Architecture](docs/agent_architecture.md)
- [Experiment Plan](docs/experiment_plan.md)

## Current research state

The repository has completed the reproducible platform, controlled-failure,
schema-v2 trajectory, directional-probe, bounded-correction, and campaign-ledger
foundations. Existing single-axis studies also produced an important negative
result: passive correction was sufficient on the frozen held-out cases, while
always-probe and the historical online comparison spent additional evidence.

## Immediate milestone: P0

Implement `StructuredEvidenceState`, strict leakage checks, and budget invariants,
then execute the immutable seeds 330--339 held-out allocation protocol exactly
once. Version 1 asks whether the Agent should spend interaction budget on one
fixed registered probe; it does not claim multi-probe selection.

The executable frozen configuration is
`configs/autoresearch/heldout_allocation_v1.json`. Held-out results must not be
used to change the threshold, features, matching, evaluator labels, or promotion
gate.

## Deferred milestones

- additional probe families, only when tied to a defined ambiguity;
- Verified Episodic Memory proof of concept, only after allocation and fresh-
  verification gates pass;
- new tasks or real-robot transfer, only after the single-task research claim is
  established;
- learned policies, RL, behavior cloning, and VLA training remain out of scope.
