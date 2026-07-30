# Active Evidence Acquisition Research Roadmap

The canonical experimental roadmap is maintained in:

- [Problem Definition](docs/problem_definition.md)
- [Agent Architecture](docs/agent_architecture.md)
- [Experiment Plan](docs/experiment_plan.md)

## Current research state

The repository has completed the reproducible platform, controlled-failure,
schema-v2 trajectory, directional-probe, bounded-correction, and campaign-ledger
foundations. Existing single-axis studies also produced an important negative
result: passive correction was sufficient on the frozen held-out cases, while
always-probe and the historical online comparison spent additional evidence.

## Immediate milestone

The next promotion gate is a stable-bias versus stochastic-noise ambiguity
benchmark. Active evidence is scientifically justified only if repeated probes
improve mechanism discrimination and intervention verification over passive
evidence under a fixed held-out interaction budget.

## Deferred milestones

- additional probe families, only when tied to a defined ambiguity;
- verified-experience retrieval, only after diagnosis and verification gates pass;
- new tasks or real-robot transfer, only after the single-task research claim is
  established;
- learned policies, RL, behavior cloning, and VLA training remain out of scope.
