# Phase-Conditioned Evidence Allocation: Development Study

## Research question

Can an Agent-visible response model become a more selective evidence-need signal
when robot motion is fitted separately during approach, push, and near-goal phases?
The hypothesis was registered before this development rerun: a global linear fit
mixes free-space and contact dynamics, whereas within-phase inconsistency should
better identify cases where a repeated diagnostic probe is useful.

This is a development study, not held-out evidence.

## Causal evidence and phase definition

The estimator reads schema-v2 Agent View transitions only. For every transition it
uses `observation_t`, `commanded_action_t`, and `next_observation_t`; it never reads
the injected mechanism, perturbed/executed actions, clipping fields, or the probe
outcome. Phase labels are computed from visible geometry using the verified
MetaWorld `push-v3` gripper, object, and goal positions:

- `near_goal`: object-goal distance at most 0.08 m;
- `push`: otherwise, gripper-object distance at most 0.08 m;
- `approach`: all remaining transitions.

Within each phase with at least eight samples, the estimator fits
`gripper_delta_xy = gain_xy * commanded_action_xy + drift_xy`. The
`phase_inconsistency` score is the eligible-sample-weighted mean normalized
residual norm. Higher scores request more evidence.

## Registered development protocol

The tracked config fixed seeds 320--329, the phase thresholds, minimum sample
count, score direction, and promotion criteria before the rerun. Fifty passive
rollouts were executed across five registered conditions. Raw Agent trajectories
were temporary; only derived per-condition features and metadata were retained.
Ten matched ambiguity cases were then evaluated using already-recorded real
64-step probe outcomes.

Promotion required all of:

1. probe-need ROC AUC at least 0.75;
2. diagnostic accuracy equal to the always-probe baseline;
3. probe request rate at most 0.60.

## Results

The phase-conditioned score achieved probe-need ROC AUC 0.792. The selected
development threshold was 0.91612970415368.

| Method | Correct | Accuracy | Probe requests | Probe steps |
|---|---:|---:|---:|---:|
| Passive | 6/10 | 60% | 0/10 | 0 |
| Always-probe | 10/10 | 100% | 10/10 | 640 |
| Global temporal gate | 10/10 | 100% | 9/10 | 576 |
| Phase-conditioned gate | 10/10 | 100% | 6/10 | 384 |

Thus the preregistered development gate passed exactly at its maximum permitted
request rate and used 40% fewer probe steps than always-probe. This supports
promotion of the frozen deterministic score to a new held-out split; it does not
yet support a generalization claim.

## Online research-Agent comparison

Because every promotion criterion passed, one bounded GLM-5.2 run was allowed.
The online Agent received the phase summaries and registered probe description,
but not the selected threshold or Oracle labels. Ten real API calls produced ten
`request_probe` decisions. Reusing the registered real probe outcomes yielded
10/10 diagnoses, 640 probe steps, mean API latency 36,995.6 ms, and
endpoint-reported totals of 8,918 input and 13,384 output tokens.

This is a negative evidence-allocation result. The online model matched the
always-probe policy and was less selective than the deterministic phase gate. Its
confidence ranged from 0.78 to 0.92 despite making the same decision in every
case. No additional prompt tuning or API calls were performed on this development
set.

## Interpretation and limitations

Phase conditioning is a plausible, interpretable improvement over the global
residual on these development cases. The strongest current method is the simple
frozen gate, not the online model. The study does not show that phase labels are
optimal, that the threshold generalizes, or that better diagnosis improves a
verification rollout. The phase rules may still mix contact regimes, and ten
matched cases are too few for a performance claim.

MetaWorld emitted known observation-space and policy-clipping warnings during the
rollout rerun. Episodes completed and artifacts were written; the warnings remain
an environment declaration issue rather than evidence of rollout failure.

## Reproduction

```powershell
python scripts/collect_temporal_evidence_development.py
python scripts/analyze_phase_conditioned_evidence_need.py
.\scripts\run_online_temporal_evidence_agent.ps1 -EvidenceMode phase_conditioned -OutputDir outputs\online_evidence_agent\glm52_phase_conditioned_development_v1 -ApiTimeout 300 -ApiMaxRetries 2 -MaxApiCalls 10
python scripts/plot_phase_conditioned_evidence.py
```

The next experiment should freeze threshold 0.91612970415368 and evaluate it once
on new seeds 330--339. No online call is justified until the deterministic phase
signal generalizes.
