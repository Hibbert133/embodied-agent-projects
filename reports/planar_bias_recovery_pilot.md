# Planar Bias Recovery Pilot

## Research question

The single-axis study showed that leakage-safe active probes can localize one
control bias. This pilot asks whether retaining both estimated planar components
reduces recovery interaction cost when x and y biases occur simultaneously.
It does not use an API, hidden labels, reinforcement learning, or memory.

## Frozen mechanism

Four reset-controlled probes (+x, -x, +y, -y) estimate common visible gripper
drift and local command-response gain. The Agent converts each drift/gain pair
into an inferred action bias, negates it, and quantizes each component onto the
existing bounded correction grid. Injected bias is absent from this computation.
It is written only to Oracle audit artifacts after the decision.

Compared methods:

- `dominant_only`: discard the smaller estimated component;
- `sequential`: try the dominant component, then the full planar correction if needed;
- `simultaneous`: apply both inferred components in the first repair rollout;
- `oracle`: cancel the known injected bias, as an audit-only upper bound.

All methods use the frozen `whole` schedule. Total environment steps include 32
active-probe steps and all repair rollouts, but exclude the initial failure so
that recovery methods are compared from the same observed failure.

## Development calibration

The first fixed development condition, bias `(x=+0.10, y=-0.10)` on seeds
250-254, produced only one initial failure. It was therefore rejected as too
weak for comparison. It is retained as a negative calibration result.

Increasing both components to `(x=+0.14, y=-0.14)` on the same five development
seeds produced 5/5 initial failures. Dominant-only recovered 3/5; sequential,
simultaneous, and Oracle each recovered 5/5. Mean total recovery budgets were
286.8, 313.6, 92.0, and 94.2 environment steps respectively. This condition and
all decision parameters were then frozen.

## Held-out mechanism check

Seeds 260-269 were not used for condition selection. All 10 initially failed.

| Method | Recovered | Conditional recovery | Mean final distance | Mean total env steps |
|---|---:|---:|---:|---:|
| dominant_only | 2/10 | 20% | 0.2224 | 444.3 |
| sequential | 10/10 | 100% | 0.0481 | 495.4 |
| simultaneous | 10/10 | 100% | 0.0480 | 95.3 |
| oracle | 10/10 | 100% | 0.0482 | 96.6 |

The selected repair was approximately `(-0.10, +0.18)`, compared with the
injected `(+0.14, -0.14)` bias. Thus the result supports robust bounded
recovery, not exact system identification.

## Interpretation and limitations

For this fixed diagonal fault, discarding the non-dominant component causes a
large recovery failure and budget penalty. Sequential repair reaches the same
success rate, but spends a failed rollout before using information already in
the probe estimate. Simultaneous repair matches the Oracle outcome and budget
closely on these ten seeds.

This is a small, direction-specific mechanism study. It does not establish
generalization to other quadrants, unequal magnitudes, stochastic noise,
perception error, or other tasks. The near-constant free-space probe estimate
across seeds also motivates a later probe-duration ablation.

## Visual evidence

The representative rule is the lowest held-out seed where dominant-only fails
and simultaneous succeeds. It selects seed 260 without manual cherry-picking.
Baseline and dominant-only fail after 500 steps; simultaneous succeeds in 69
rendered steps. The manifest records exact corrections and artifact paths.

## Reproduction

```powershell
python scripts/evaluate_planar_bias_recovery.py --seeds 250 251 252 253 254 --bias-x 0.14 --bias-y -0.14 --max-steps 500 --output-dir outputs/planar_bias_pilot/xpos014_yneg014_dev
python scripts/evaluate_planar_bias_recovery.py --seeds 260 261 262 263 264 265 266 267 268 269 --bias-x 0.14 --bias-y -0.14 --max-steps 500 --output-dir outputs/planar_bias_pilot/xpos014_yneg014_heldout
python scripts/plot_planar_bias_recovery.py --summary-csv outputs/planar_bias_pilot/xpos014_yneg014_heldout/summary.csv --output outputs/planar_bias_pilot/figures/heldout_2d_recovery.png
python scripts/render_planar_bias_representative.py --trials-csv outputs/planar_bias_pilot/xpos014_yneg014_heldout/trials.csv --output-dir outputs/planar_bias_pilot/representative
python scripts/validate_schema_v2_trajectories.py --trajectory-dir outputs/planar_bias_pilot/representative
```
