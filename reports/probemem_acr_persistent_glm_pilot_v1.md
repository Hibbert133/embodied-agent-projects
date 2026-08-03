# Persistent-Regime GLM-5.2 Pilot v1

## Scope

This is a frozen ten-case qualitative reasoning-layer pilot. GLM-5.2 received
only the `agent_visible_evidence` that had been persisted before paired
candidate outcomes existed. Evaluator-only condition identity was used to pick
five cases per stratum but was not included in the payload. Model decisions did
not control MuJoCo and consumed zero environment steps.

- Source commit: `cda26cb373f1866114a5c744c3e4a62dac6f6c8e`
- Source evidence manifest:
  `193a741a195085e255c7baac20ce22207aa268371dd425df56f55fa73e7d1129`
- Pilot run: `persistent_glm_pilot_20260803T062800Z_cda26cb373f1`
- Model: `glm-5.2`

## Operational result

- API calls: 10
- Valid structured outputs: 9/10
- Fail-closed outputs: 1/10
- Schema-repair calls: 0
- Environment steps: 0
- Model actions executed: 0
- Valid-call median latency: 67.501 seconds
- Valid-call maximum latency: 85.325 seconds
- Input tokens over valid calls: 49,431
- Output tokens over valid calls: 22,917
- Total wrapper wall time: approximately 688 seconds

The failed case returned no valid shadow-decision object and correctly became
`ABSTAIN` without retrying the API or executing an action.

## Decisions and matched evaluator audit

All five stable-bias cases selected bounded compensation. Four had an accepted
compensation outcome; in the fifth, neither candidate was accepted.

For the five stochastic-noise cases, the model produced four abstentions and
one compensation selection. All four abstained cases had an accepted retry in
the evaluator-only paired outcomes. The compensation case had an inconclusive
compensation outcome and a rejected retry outcome.

If shadow choices were naively scored as executed decisions, they would recover
4/10 selected cases, versus 8/10 for the frozen deterministic probe rule on the
same pilot cases. This descriptive matched audit is reported to expose the
cost of conservative abstention; with only ten stratified development cases it
is not a statistical model comparison.

## Research interpretation

GLM-5.2 consistently recognized the stable-bias intervention pattern, but it
treated high-variance probe evidence primarily as a reason to abstain instead
of as support for the registered stochastic-retry skill. This is a concrete
reasoning-to-action failure: uncertainty recognition alone is insufficient if
the action contract does not make the robust fallback utility operationally
clear.

The 67.5-second median latency and large payload/token cost also confirm that
this model belongs at the rollout-attempt decision layer, not inside low-level
control. The next development question should be whether a compact,
causally sufficient evidence summary plus explicit skill semantics reduces
conservative abstention on fresh development cases. This pilot must not be used
to tune and rerun the same ten cases.

No memory, validation, held-out, generalization, or GLM superiority claim is
authorized by this result.

## Artifacts

`outputs/probemem_acr/persistent_glm_pilot_runs/persistent_glm_pilot_20260803T062800Z_cda26cb373f1/`
