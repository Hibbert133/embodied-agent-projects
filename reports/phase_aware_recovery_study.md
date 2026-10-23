# Phase-Aware Recovery Study

## Question

Does the timing of an agent-proposed correction explain the remaining recovery
failure after active bias diagnosis?

The experiment keeps the task, injected `+x 0.145` bias, active probes,
probe-derived `-x 0.10` correction, seeds, and two-rollout budget fixed. Only
the correction schedule changes. Seeds `103, 107, 108, 144, 148` are development
seeds, so this is mechanism discovery rather than held-out evaluation.

## Agent-visible phase definition

The phase classifier reads only the current 39-value push-v3 observation:

- `near_goal`: object-goal distance is at most 0.08 m;
- `push`: otherwise, gripper-object distance is at most 0.08 m;
- `approach`: otherwise.

The observation positions use the MetaWorld 3.1.1 indices already documented
and tested in `src/task_metrics.py`. No injected bias or executed-action field
is used.

## Schedules

| Schedule | Approach | Push | Near goal |
|---|---:|---:|---:|
| whole | 100% | 100% | 100% |
| push_only | 0% | 100% | 25% |
| phase_aware | 50% | 100% | 25% |

Percentages scale the same probe-estimated correction. They do not alter the
hidden perturbation or the base Sawyer policy.

## Real development results

| Schedule | Successes | Mean final distance (m) | Mean total environment steps |
|---|---:|---:|---:|
| whole | 4/5 | 0.052907 | 684.8 |
| push_only | 3/5 | 0.110571 | 790.0 |
| phase_aware | 5/5 | 0.048218 | 648.0 |

`push_only` recovers seed 144 but loses seeds 103 and 148. This indicates that
approach-phase compensation matters. The balanced `phase_aware` schedule
recovers all five development cases while using fewer mean interactions than
the whole schedule.

For seed 144, the phase-aware corrected trial contains 69 approach, 127 push,
and 4 near-goal steps. It succeeds in 200 steps with final distance 0.044989 m.
The whole schedule fails after 500 corrected steps with final distance 0.069487
m. Both results are backed by CSV rows and decoded videos.

## Interpretation

The evidence supports a mechanism claim on the development set: correct bias
axis/sign diagnosis is insufficient; when the repair is applied affects policy
recovery. Completely removing approach correction is also insufficient.

The evidence does not establish 100% general recovery. The schedule and its
0.08 m thresholds were selected after inspecting development failures and must
now be frozen before held-out evaluation.

## Artifacts

- `outputs/active_probes/phase_whole.csv`
- `outputs/active_probes/phase_push_only.csv`
- `outputs/active_probes/phase_aware.csv`
- `outputs/active_probes/phase_schedule_summary.csv`
- `outputs/active_probes/phase_figures/`
- `outputs/active_probes/representative_videos/manifest.csv`
- `outputs/active_probes/representative_videos/probe_rule_phase_aware_x_negative_0.10_seed144_trial02_success.mp4`

## Reproduction

```powershell
python scripts/run_recovery_agent.py --planner probe_rule --active-probes --seeds 103 107 108 144 148 --max-steps 500 --max-trials 2 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --correction-schedule phase_aware --output-csv outputs/active_probes/phase_aware.csv --audit-jsonl outputs/active_probes/phase_aware_audit.jsonl --trajectory-dir outputs/active_probes/phase_trajectories/phase_aware
python scripts/summarize_recovery_ablation.py --input-csv outputs/active_probes/phase_whole.csv outputs/active_probes/phase_push_only.csv outputs/active_probes/phase_aware.csv --output-csv outputs/active_probes/phase_schedule_summary.csv
python scripts/plot_recovery_results.py --input-csv outputs/active_probes/phase_whole.csv outputs/active_probes/phase_push_only.csv outputs/active_probes/phase_aware.csv --output-dir outputs/active_probes/phase_figures
```

## Next gate

Freeze `phase_aware`, contact threshold 0.08 m, near-goal threshold 0.08 m, and
the probe estimator. Evaluate on a separately recorded held-out seed set before
changing any threshold or claiming generalization.
