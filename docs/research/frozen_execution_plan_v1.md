# Frozen Execution Plan v1

## Research claim

This project studies an embodied research Agent operating above a fixed
`SawyerPushV3Policy` in MetaWorld `push-v3`.

The first-version question is:

> Given a fixed diagnostic probe, can the Agent decide whether and when the
> expected diagnostic value justifies its interaction cost?

The intended first claim is deliberately narrow: a deterministic decision layer
can allocate one registered diagnostic probe under a limited interaction budget,
retain most of the diagnostic or recovery benefit of always probing, and reduce
unnecessary environment interaction.

Version 1 studies execution uncertainty under reliable low-level state
estimation. Controlled perception corruption and RGB evidence extraction are
future extensions, not part of the first scientific claim.

## Online adaptation boundary

Adaptation occurs between rollout attempts, not at each low-level control step:

```text
INITIAL_ROLLOUT
-> BUILD_EVIDENCE
-> ALLOCATE_PROBE_BUDGET
-> OPTIONAL_PROBE
-> UPDATE_BELIEF
-> SELECT_INTERVENTION
-> FRESH_VERIFICATION
-> OPTIONAL_MEMORY_WRITE
```

The first version does not claim step-level planning, real-time continuous
control, multi-probe selection, policy-weight updates, VLA improvement,
continual robot learning, or safety-aware planning. Its capability is described
as **online decision-layer adaptation** above a fixed robot policy.

## Frozen scope

- Environment: MetaWorld `push-v3`.
- Low-level policy: fixed `SawyerPushV3Policy`.
- Evidence: schema-v2 Agent View only.
- Extra evidence action: one registered diagnostic probe.
- Decisions: `CONTINUE`, `REQUEST_DIAGNOSTIC_PROBE`, or `ABSTAIN`.
- Per-case flow: one initial rollout, at most one probe, and at most one fresh
  corrective verification rollout.
- Held-out seeds: 330--339.
- Allocation threshold: `0.91612970415368`.
- Maximum initial rollout: 500 environment steps.
- Registered probe cost: 64 environment steps.
- Reserved verification budget: 500 environment steps.
- Total case budget: 1064 environment steps.

The complete executable settings are frozen in
`configs/autoresearch/heldout_allocation_v1.json`. The held-out protocol is
defined in `docs/protocols/heldout_allocation_v1.md`.

## Evidence and causal boundary

`StructuredEvidenceState` may contain only causally available state evidence:

- task progress, object displacement, and relevant distances;
- task-phase occupancy;
- response gain and drift estimates;
- normalized and phase-conditioned residuals;
- action excitation;
- evidence provenance and interaction cost;
- the count of earlier accepted experiences, once memory is enabled.

It must reject direct or nested perturbation truth, perturbed/executed actions
unavailable to the Agent, evaluator labels, future verification outcomes, and
Oracle conclusions. Leakage validation fails closed.

## Research stages and promotion order

### P0 -- Budgeted evidence allocation

1. Implement `StructuredEvidenceState` and strict Agent/Oracle tests.
2. Enforce the attempt and budget invariants.
3. Generate an immutable held-out manifest from a clean committed tree.
4. Execute the frozen held-out allocation once.
5. Compare Passive, seeded Random, Always-probe, the global temporal gate, the
   frozen phase-conditioned gate, and Oracle audit.

Promotion uses the operational decision population and requires all criteria in
the executable config. A single-class probe-need population makes the experiment
`INCOMPLETE_FOR_PROBE_NEED_EVALUATION`; it is not assigned a synthetic AUC.

### P1 -- Evidence-grounded intervention

Test whether the probe changes the mechanism belief, changes the discrete
intervention, and improves a matched fresh-verification outcome. Compare no
intervention, fixed compensation, stochastic retry, passive diagnosis-driven,
active-evidence-driven, and Oracle mechanism selection.

Every case records the causal chain from initial evidence through verification.
Development seeds are 340--349; held-out seeds are 350--369 after parameters are
frozen.

### P2 -- Verified Episodic Memory proof of concept

Only `ACCEPTED` fresh-verification records may be stored. Chronological retrieval
on seeds 370--389 tests whether recurring mechanisms require fewer probes or
recovery trials. This is non-parametric experience reuse, not policy learning or
a general long-term self-improvement claim.

### P3 -- Frozen GLM-5.2 qualitative pilot

The model is a constrained reasoning-layer pilot with at most ten calls. It may
select only allowed discrete decisions, cannot see the frozen threshold or
Oracle truth, and fails closed to `ABSTAIN`. The pilot reports structured-output
validity, leakage, latency, tokens, retries, and representative disagreements; it
does not support statistical model-performance claims.

## Application-ready stopping points

After P0 passes, Milestone A contains the frozen held-out table, evidence
allocation frontier, leakage-safe interface diagram, one passive/active case,
README preliminary results, and a one-page research summary.

After P1 passes, Milestone B adds recovery/cost results, a causal funnel, a fresh
verification video, a technical-report draft, a CV entry, and a faculty-outreach
paragraph. P2 memory does not block initial faculty outreach.

## Freeze rule

After the manifest is generated, held-out results must not change the research
question, seeds, features, allocation threshold, matching rule, evaluator-label
definitions, or promotion gates. A code defect, leakage finding, or inexecutable
protocol requires a new run ID and manifest; old artifacts remain immutable.
