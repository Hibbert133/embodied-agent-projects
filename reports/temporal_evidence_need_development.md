# Temporal Evidence-Need Development Study

## Motivation

The first held-out ambiguity pilot showed that repeated probes corrected two
passive mechanism errors, but the terminal-feature uncertainty gate requested no
evidence. This development study tests a more causal alternative: can transition
dynamics already visible during the failed rollout predict when an additional
probe is needed?

No online model was called. No new held-out split was consumed.

## Agent-visible temporal model

The study reuses the existing, tested schema-v2 passive planar model:

```text
gripper_delta_xy = response_gain_xy * commanded_action_xy + execution_drift_xy
```

MetaWorld 3.1.1 source was inspected before interpreting the response. In
`SawyerXYZEnv.set_xyz_action`, xyz actions are clipped to `[-1, 1]`, multiplied by
`action_scale=0.01`, and applied to mocap position before simulation. The estimator
uses only `observation`, `commanded_action`, and `next_observation` from Agent View.
It cannot access perturbed/executed actions or injected fault parameters.

Per-axis confidence combines commanded-action excitation with normalized response
residual. Temporal uncertainty is one minus mean axis confidence. The direction of
the candidate gate was fixed before inspecting development labels: request a probe
when temporal uncertainty is high.

## Actual experiment

- Split: development seeds 320–329.
- Fault conditions: four stable action-bias families and Gaussian noise std 0.60.
- Initial rollouts: 50, no video.
- Repeated probes: 50 records, four repeats and 64 environment steps per record.
- Matched ambiguity set: five bias/noise pairs, ten failed cases.
- Mean standardized passive matching distance: 1.0854.
- Raw schema-v2 Agent trajectories: temporary only, not retained.
- API calls: zero.

The tuning-frozen repeated-probe threshold remained perfectly separable on these
synthetic conditions. It is used as a diagnostic evidence source, not as an
evidence-need signal.

## Real development result

| Method | Correct | Probe requests | Probe steps |
|---|---:|---:|---:|
| Passive terminal-feature baseline | 6/10 | 0/10 | 0 |
| Always-probe | 10/10 | 10/10 | 640 |
| Temporal-uncertainty gate | 10/10 | 9/10 | 576 |

The development-selected threshold was 0.71202. Four cases met the post-hoc Oracle
definition of probe-needed: passive diagnosis was wrong and probe diagnosis was
correct. Temporal uncertainty achieved ROC AUC 0.6667 for this label.

Although gated accuracy equals always-probe on development, the gate saves only one
probe (64 steps, 10% of always-probe evidence cost). It therefore behaves nearly
like always-probe rather than demonstrating selective evidence acquisition. The
candidate is **not promoted to held-out evaluation**.

The figure
`outputs/ambiguity_benchmark/figures/temporal_uncertainty_development.png` shows
substantial overlap between stable-bias, stochastic-noise, and probe-needed cases.

## Interpretation

This negative result narrows the problem. A global linear response residual is
affected by nominal policy phase, action excitation, contact, and workspace
constraints, not only stochastic execution. Treating all steps as one stationary
regression therefore produces high uncertainty for many stable-bias cases.

The next hypothesis should be phase-conditioned and pre-registered: estimate
response consistency separately during free-space approach and object-contact push,
then test whether within-phase variance predicts probe need. This uses the same
Agent-visible transitions but reduces a concrete confound rather than adding an
unstructured model.

## Warnings and limitations

- The ambiguity set has only ten development cases.
- Passive matching distance is higher than in the four-case held-out pilot.
- Noise std 0.60 and zero-variance deterministic bias remain synthetic and easy for
  repeated probes.
- MetaWorld/Gymnasium emitted the previously documented observation-space and
  scripted-policy clipping warnings.
- Development threshold accuracy is not a generalization result.

## Reproduction

```powershell
python scripts/collect_temporal_evidence_development.py
python scripts/evaluate_probe_consistency.py --seed-start 320 --num-seeds 10 --repeats 4 --probe-steps 4 --probe-magnitude 0.2 --fixed-threshold 0.11560838098372882 --output-dir outputs/ambiguity_benchmark/probe_consistency_temporal_development
python scripts/build_bias_noise_ambiguity_benchmark.py --oracle-audit outputs/ambiguity_benchmark/temporal_development_rollouts/oracle_audit.jsonl --probe-results outputs/ambiguity_benchmark/probe_consistency_temporal_development/results.csv --threshold-selection outputs/autoresearch/probe_consistency_tuning/threshold_selection.json --output-dir outputs/ambiguity_benchmark/bias_noise_temporal_development_v1 --benchmark-id bias_noise_temporal_development_v1 --split development
python scripts/analyze_temporal_evidence_need.py
python scripts/plot_temporal_evidence_need.py
```
