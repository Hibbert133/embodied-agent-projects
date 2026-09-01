# Outcome-Blind Representative Case Report

Cases are the first sequential operational episode for each registered perturbation category. Selection does not use diagnosis, recovery, Memory, or Verifier outcomes; failure labels are assigned only after selection.

## FIRST_SEQUENTIAL_OPERATIONAL_fault_01

- Observed case type(s): `SUCCESS_OR_NO_REGISTERED_FAILURE_TAG`
- Episode / seed: `1` / `7200`
- Initial task description: MetaWorld `push-v3`; use the frozen SawyerPushV3Policy to push the object to the observable goal.
- Failure observation: initial rollout ended after `500` steps without success; final object-goal distance was `0.2475`, progress-to-goal `0.0036`, lateral drift `0.0086`.
- Agent hypothesis (FULL_PROBEMEM): `stable_bias`; evaluator mechanism: `stable_bias`.
- Selected probe(s): None.
- Evidence obtained: No post-failure evidence was acquired; the decision used only pre-action observable rollout features.
- Final decision: execute `BOUNDED_PLANAR_COMPENSATION`. Verifier invoked=`False`, proposal=`BOUNDED_PLANAR_COMPENSATION`, selected=`BOUNDED_PLANAR_COMPENSATION`, reason=`NOT_INVOKED`.
- Outcome: `ACCEPTED` after `65` verification steps; final object-goal distance `0.0475`.

Configuration comparison:

| Method | Hypothesis | Evidence steps | Recovery action | Outcome |
|---|---|---:|---|---|
| `BASELINE` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `MEMORY_ONLY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `EVIDENCE_ACQUISITION_ENABLED` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `PROBE_MEMORY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `FULL_PROBEMEM` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |

Interpretation is restricted to this registered development case.

## FIRST_SEQUENTIAL_OPERATIONAL_fault_02

- Observed case type(s): `SUCCESS_OR_NO_REGISTERED_FAILURE_TAG`
- Episode / seed: `2` / `7201`
- Initial task description: MetaWorld `push-v3`; use the frozen SawyerPushV3Policy to push the object to the observable goal.
- Failure observation: initial rollout ended after `500` steps without success; final object-goal distance was `0.1766`, progress-to-goal `-0.0000`, lateral drift `0.0000`.
- Agent hypothesis (FULL_PROBEMEM): `stable_bias`; evaluator mechanism: `stable_bias`.
- Selected probe(s): None.
- Evidence obtained: No post-failure evidence was acquired; the decision used only pre-action observable rollout features.
- Final decision: execute `BOUNDED_PLANAR_COMPENSATION`. Verifier invoked=`True`, proposal=`BOUNDED_PLANAR_COMPENSATION`, selected=`BOUNDED_PLANAR_COMPENSATION`, reason=`GUARD_RETAINED_PROPOSAL`.
- Outcome: `ACCEPTED` after `58` verification steps; final object-goal distance `0.0492`.

Configuration comparison:

| Method | Hypothesis | Evidence steps | Recovery action | Outcome |
|---|---|---:|---|---|
| `BASELINE` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `MEMORY_ONLY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `EVIDENCE_ACQUISITION_ENABLED` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `PROBE_MEMORY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `FULL_PROBEMEM` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |

Interpretation is restricted to this registered development case.

## FIRST_SEQUENTIAL_OPERATIONAL_fault_03

- Observed case type(s): `SUCCESS_OR_NO_REGISTERED_FAILURE_TAG`
- Episode / seed: `3` / `7202`
- Initial task description: MetaWorld `push-v3`; use the frozen SawyerPushV3Policy to push the object to the observable goal.
- Failure observation: initial rollout ended after `500` steps without success; final object-goal distance was `0.2320`, progress-to-goal `-0.0000`, lateral drift `0.0000`.
- Agent hypothesis (FULL_PROBEMEM): `stable_bias`; evaluator mechanism: `stable_bias`.
- Selected probe(s): One registered fixed diagnostic evidence rollout (64 environment steps).
- Evidence obtained: The registered 64-step diagnostic evidence retained the passive hypothesis `stable_bias` as `stable_bias`.
- Final decision: execute `BOUNDED_PLANAR_COMPENSATION`. Verifier invoked=`True`, proposal=`BOUNDED_PLANAR_COMPENSATION`, selected=`BOUNDED_PLANAR_COMPENSATION`, reason=`GUARD_RETAINED_PROPOSAL`.
- Outcome: `ACCEPTED` after `62` verification steps; final object-goal distance `0.0497`.

Configuration comparison:

| Method | Hypothesis | Evidence steps | Recovery action | Outcome |
|---|---|---:|---|---|
| `BASELINE` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `MEMORY_ONLY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `EVIDENCE_ACQUISITION_ENABLED` | `stable_bias` | 64 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `PROBE_MEMORY` | `stable_bias` | 64 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `FULL_PROBEMEM` | `stable_bias` | 64 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |

Interpretation is restricted to this registered development case.

## FIRST_SEQUENTIAL_OPERATIONAL_fault_04

- Observed case type(s): `SUCCESS_OR_NO_REGISTERED_FAILURE_TAG`
- Episode / seed: `4` / `7203`
- Initial task description: MetaWorld `push-v3`; use the frozen SawyerPushV3Policy to push the object to the observable goal.
- Failure observation: initial rollout ended after `500` steps without success; final object-goal distance was `0.2175`, progress-to-goal `0.0015`, lateral drift `0.0050`.
- Agent hypothesis (FULL_PROBEMEM): `stable_bias`; evaluator mechanism: `stable_bias`.
- Selected probe(s): None.
- Evidence obtained: No post-failure evidence was acquired; the decision used only pre-action observable rollout features.
- Final decision: execute `BOUNDED_PLANAR_COMPENSATION`. Verifier invoked=`True`, proposal=`BOUNDED_PLANAR_COMPENSATION`, selected=`BOUNDED_PLANAR_COMPENSATION`, reason=`GUARD_RETAINED_PROPOSAL`.
- Outcome: `ACCEPTED` after `67` verification steps; final object-goal distance `0.0496`.

Configuration comparison:

| Method | Hypothesis | Evidence steps | Recovery action | Outcome |
|---|---|---:|---|---|
| `BASELINE` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `MEMORY_ONLY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `EVIDENCE_ACQUISITION_ENABLED` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `PROBE_MEMORY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |
| `FULL_PROBEMEM` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `ACCEPTED` |

Interpretation is restricted to this registered development case.

## FIRST_SEQUENTIAL_OPERATIONAL_fault_05

- Observed case type(s): `MEMORY_HARMFUL_TRANSFER;VERIFIER_FAILED_TO_PREVENT_UNRELIABLE_ACTION`
- Episode / seed: `9` / `7209`
- Initial task description: MetaWorld `push-v3`; use the frozen SawyerPushV3Policy to push the object to the observable goal.
- Failure observation: initial rollout ended after `500` steps without success; final object-goal distance was `0.1234`, progress-to-goal `0.0391`, lateral drift `0.0278`.
- Agent hypothesis (FULL_PROBEMEM): `stochastic_noise`; evaluator mechanism: `stochastic_noise`.
- Selected probe(s): One registered fixed diagnostic evidence rollout (64 environment steps).
- Evidence obtained: The registered 64-step diagnostic evidence changed the passive hypothesis `stable_bias` as `stochastic_noise`.
- Final decision: execute `BOUNDED_PLANAR_COMPENSATION`. Verifier invoked=`True`, proposal=`BOUNDED_PLANAR_COMPENSATION`, selected=`BOUNDED_PLANAR_COMPENSATION`, reason=`GUARD_RETAINED_PROPOSAL`.
- Outcome: `REJECTED` after `500` verification steps; final object-goal distance `0.3543`.

Configuration comparison:

| Method | Hypothesis | Evidence steps | Recovery action | Outcome |
|---|---|---:|---|---|
| `BASELINE` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `REJECTED` |
| `MEMORY_ONLY` | `stable_bias` | 0 | `BOUNDED_PLANAR_COMPENSATION` | `REJECTED` |
| `EVIDENCE_ACQUISITION_ENABLED` | `stochastic_noise` | 64 | `INDEPENDENT_STOCHASTIC_RETRY` | `ACCEPTED` |
| `PROBE_MEMORY` | `stochastic_noise` | 64 | `BOUNDED_PLANAR_COMPENSATION` | `REJECTED` |
| `FULL_PROBEMEM` | `stochastic_noise` | 64 | `BOUNDED_PLANAR_COMPENSATION` | `REJECTED` |

Interpretation is restricted to this registered development case.
