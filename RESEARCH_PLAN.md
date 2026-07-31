# Budgeted Active Evidence Acquisition Research Roadmap

## Versioned successor under development

The completed and falsified v1 milestones below remain immutable. A separate
development protocol, [ProbeMem v2](docs/research/online_llm_scientific_memory_v2.md),
now investigates whether action-conditional fresh verification can support
chronological scientific memory. Phase B first validates the constrained LLM
tool boundary with an empty memory snapshot; memory benefit is not claimed until
later registered phases pass their own gates.

ProbeMem Phase B passed its bounded tool-integration gate on five development
failures, with five fresh verification rollouts and no invalid skill execution
or budget overrun. An initial Phase-C run stopped at 54/60 method-cases because
the Windows host exhausted commit/pagefile capacity; that immutable incomplete
artifact remains preserved. After a restart, a registered no-API endurance
preflight completed 100 environment lifecycle cycles and 20 full rollouts with
process RSS plateauing below 147 MB.

The new immutable Phase-C run then completed all 60 method-cases over 20 paired
development episodes. Ten episodes required online decisions. Stateless, raw
episodic retrieval, and accepted-only verified retrieval each obtained 5/10
accepted verifications, with identical intervention selections and outcomes on
all 10 operational pairs. Raw and verified histories were cited in 9/10 and
8/10 cases, but did not change behavior; they increased token and latency cost.
Phase C therefore records a completed negative result: chronological retrieval
alone is insufficient for recovery improvement in this setup. This does not
promote Phase D or justify a held-out memory claim.

A no-API trace audit further localizes this negative result. Raw retrieval was
associated with a different predicted verification status in 6/10 operational
cases, while verified retrieval changed post-probe confidence in 4/10. Both
still produced zero intervention changes. Phase D must therefore begin with a
development-only, falsifiable intervention-utility record and contradiction
test; it must not promote free-form principles merely because memory was cited.

The canonical experimental roadmap is maintained in:

- [Frozen Execution Plan v1](docs/research/frozen_execution_plan_v1.md)
- [Held-Out Allocation Protocol v1](docs/protocols/heldout_allocation_v1.md)
- [Held-Out Intervention Protocol v1](docs/protocols/heldout_intervention_v1.md)
- [Problem Definition](docs/problem_definition.md)
- [Agent Architecture](docs/agent_architecture.md)
- [Experiment Plan](docs/experiment_plan.md)

## Current research state

The repository has completed the reproducible platform, controlled-failure,
schema-v2 trajectory, directional-probe, bounded-correction, and campaign-ledger
foundations. Existing single-axis studies also produced an important negative
result: passive correction was sufficient on the frozen held-out cases, while
always-probe and the historical online comparison spent additional evidence.

## Completed milestone: P0 / Evidence Allocation

`StructuredEvidenceState`, strict leakage checks, budget invariants, and the
immutable seeds 330--339 allocation experiment are complete. The frozen phase
gate matched Always-probe diagnosis on the 33-unit operational population while
using 448 rather than 2,112 probe steps. This supports allocation of one fixed
registered probe; it does not claim multi-probe selection or recovery benefit.

The executable frozen configuration is
`configs/autoresearch/heldout_allocation_v1.json`. Held-out results must not be
used to change the threshold, features, matching, evaluator labels, or promotion
gate.

## Completed falsification: P1 / Evidence-Grounded Intervention

The immutable P1 run completed with status `NOT_PROMOTED`. The registered probe
changed six executable interventions but improved zero matched fresh-
verification outcomes. Active evidence recovered 29/33 operational cases versus
30/33 for passive diagnosis while adding probe cost. The result is preserved in
`reports/evidence_grounded_intervention_negative.md`.

The immediate development question is now intervention identifiability: whether
the broad mechanism class is sufficient to determine which bounded candidate is
actually useful. Protocol
`docs/protocols/intervention_identifiability_development_v1.md` uses fresh seeds
400--409 and cannot alter completed held-out results. P2 memory and P3 GLM remain
blocked while this abstraction failure is unresolved.

The follow-up noise-only development extension on seeds 410--429 confirmed that
the stochastic-noise mechanism is utility-heterogeneous: four of seven failures
preferred compensation and three preferred retry. Some preregistered visible
scores showed AUC 0.75, but the operational population is too small to freeze a
selector. The next step must increase independent operational coverage or define
a stronger action-conditional evidence source; it must not tune on held-out
seeds or promote memory from this exploratory result.

A label-blind coverage extension then reached 20 comparable stochastic-noise
failures after 59 initial units. Compensation was preferred in 12 and retry in
8; both recovered 8/20. The earlier phase/temporal AUC 0.75 signals fell to
0.469, while probe bias variability reached only 0.698. This larger development
result blocks freezing the current aggregate features as an intervention-
utility gate and motivates genuinely action-conditional evidence.

## Deferred milestones

- additional probe families, only when tied to a defined ambiguity;
- Verified Episodic Memory proof of concept, only after allocation and fresh-
  verification gates pass;
- new tasks or real-robot transfer, only after the single-task research claim is
  established;
- learned policies, RL, behavior cloning, and VLA training remain out of scope.
