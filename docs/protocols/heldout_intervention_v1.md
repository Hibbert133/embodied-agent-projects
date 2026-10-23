# Held-Out Evidence-Grounded Intervention Protocol v1

## Purpose

Phase 2 established that the frozen gate can allocate one registered probe at
lower interaction cost. Phase 3 asks a separate causal question:

> Does additional evidence change the selected corrective intervention, and does
> that change improve a fresh verification outcome?

No threshold, feature, mechanism classifier, seed, or Phase-2 label is retuned.
The executable source is `configs/autoresearch/heldout_intervention_v1.json`.

## Population and attempt semantics

The source population is exactly the 33 `decision_required` units from immutable
allocation run `heldout_20260731T015847Z_a39271db862f`. Successful initial
rollouts are excluded because they require no intervention.

```text
attempt 0: existing initial rollout
attempt 1: the already registered optional diagnostic probe
attempt 2: at most one fresh corrective verification
```

The maximum case budget remains 1064 environment steps. The Phase-2
counterfactual probe artifact may be reused as evidence, but each method is
charged 64 steps only when that method requests it.

## Registered interventions

1. `no_intervention`: retain the failed initial outcome; no added interaction.
2. `bias_compensation_for_all`: always use the registered probe and the frozen
   `research_r1_c1` bounded compensation rule.
3. `stochastic_retry_for_all`: execute the fixed policy with an independent
   verification perturbation stream and no correction.
4. `passive_diagnosis_intervention`: stable-bias belief uses compensation derived
   from initial Agent evidence; stochastic-noise belief uses independent retry.
5. `active_evidence_intervention`: use the frozen Phase-2 gate. Without a probe,
   use the passive plan. With a probe, update the mechanism belief; stable-bias
   uses probe-grounded compensation and stochastic-noise uses retry.
6. `oracle_mechanism_intervention`: audit-only mechanism selection. Oracle truth
   selects the family, but stable-bias correction remains grounded in visible
   probe evidence rather than direct cancellation of injected parameters.

Compensation is quantized on the existing correction grid. Skill and schedule
selection use the committed `research_r1_c1` rule; no case-specific tuning is
allowed.

## Matched fresh verification

All methods for a case share the same task reset and verification perturbation
seed derived with namespace 4101. Identical intervention configurations are
executed once and referenced by multiple method rows. This is matched evaluation,
not outcome reuse across different actions.

Verification status is:

- `ACCEPTED`: task success;
- `INCONCLUSIVE`: failure with strictly lower final object-goal distance than the
  initial failure;
- `REJECTED`: failure without strict distance improvement.

The status definition is frozen before verification execution.

## Causal audit

Each case records:

```text
initial evidence
-> probe decision
-> probe observation (if requested)
-> passive and post-probe mechanism beliefs
-> passive and active interventions
-> fresh verification IDs and outcomes
```

`decision-change rate` is the proportion of requested probes that change the
intervention. `useful-probe rate` additionally requires a strictly better active
verification status than the passive verification. The evaluator-only
`decision_probe_needed` label is identical to that useful-probe condition and may
not enter Agent evidence or future thresholds.

## Stop rule

Promotion requires at least one intervention change, at least one useful probe,
active recovery no worse than passive recovery, lower probe cost than
Always-probe, and no leakage. A failed gate is preserved as a negative result.
No Phase-2 or Phase-3 held-out result may be used for prompt, feature, threshold,
or intervention-rule tuning.
