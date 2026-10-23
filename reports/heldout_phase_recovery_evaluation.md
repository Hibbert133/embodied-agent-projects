# Held-Out Phase Recovery Evaluation

## Research question

Does the phase-aware correction selected on development seeds generalize beyond
those initial states, relative to the simpler whole-rollout correction?

## Frozen protocol

- held-out seeds: `200-219`;
- MetaWorld `push-v3`;
- injected bias: `+x 0.145`;
- active probes: four directions, eight steps each after initial failure;
- correction: probe-derived `-x 0.10`;
- at most two full rollouts;
- phase thresholds: contact 0.08 m and near-goal 0.08 m;
- no threshold or schedule change after observing held-out results.

These seeds were not used in the preceding development experiments. Video
rendering was disabled during evaluation.

## Real results

Nine of 20 episodes succeeded on the initial biased rollout. Conditional
recovery is therefore measured only on the 11 initial failures.

| Schedule | Overall success | Conditional recovery | 95% Wilson CI | Mean recovery-trial steps | Mean final distance (m) | Mean total steps |
|---|---:|---:|---:|---:|---:|---:|
| whole | 20/20 | 11/11 | [74.1%, 100%] | 60.64 | 0.048369 | 373.65 |
| phase-aware | 20/20 | 11/11 | [74.1%, 100%] | 69.00 | 0.048348 | 378.25 |

All numbers are generated from `outputs/heldout/whole.csv` and
`outputs/heldout/phase_aware.csv` by
`scripts/summarize_recovery_ablation.py`.

## Interpretation

The held-out experiment does not support a general phase-aware advantage.
Both schedules recover every initial failure, while whole correction uses about
8.36 fewer recovery-trial steps on average. Final distances are effectively
the same at the reported precision.

The earlier seed-144 result remains useful mechanism evidence: timing can rescue
a specific failure. It should not be generalized into a claim that phase-aware
repair is universally better. The current held-out set also has a ceiling
effect, so it cannot distinguish method robustness under different failure
directions or severities.

Oracle was not added after both non-Oracle schedules reached the success-rate
ceiling. It would not resolve the schedule hypothesis and would consume
additional simulation budget. The already established development Oracle
remains an audit upper bound, not an Agent input.

## Next decision

Keep both schedules as Agent-selectable repair tools rather than replacing
whole correction with phase-aware correction. The next evaluation should freeze
both implementations and vary unseen fault conditions (axis, sign, and
magnitude). This tests whether an Agent can select the appropriate repair based
on evidence, which is more scientifically useful than further threshold tuning.

## Reproduction

```powershell
python scripts/run_recovery_agent.py --planner probe_rule --active-probes --seeds 200 201 202 203 204 205 206 207 208 209 210 211 212 213 214 215 216 217 218 219 --max-steps 500 --max-trials 2 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --correction-schedule whole --output-csv outputs/heldout/whole.csv --audit-jsonl outputs/heldout/whole_audit.jsonl --trajectory-dir outputs/heldout/trajectories/whole
python scripts/run_recovery_agent.py --planner probe_rule --active-probes --seeds 200 201 202 203 204 205 206 207 208 209 210 211 212 213 214 215 216 217 218 219 --max-steps 500 --max-trials 2 --bias-axis x --bias-sign positive --bias-magnitude 0.145 --correction-schedule phase_aware --output-csv outputs/heldout/phase_aware.csv --audit-jsonl outputs/heldout/phase_aware_audit.jsonl --trajectory-dir outputs/heldout/trajectories/phase_aware
python scripts/summarize_recovery_ablation.py --input-csv outputs/heldout/whole.csv outputs/heldout/phase_aware.csv --output-csv outputs/heldout/summary.csv
```
