# Qualified calibration: prospective continuous task utility

Freeze before outcomes. This tests a standard identification baseline with an
independently qualified prior; neither qualification nor task passage establishes
a novel algorithm or publication readiness. The saved model is immutable.

## Population, information, and cost

New seeds 9100--9115, all states crossed with historical bias contexts
fault_01--fault_04 and Gaussian xyz execution noise std 0.05. One realization
per cell. Total 64 units and 320 independent physical method episodes. Reserve
9116--9399; all earlier reserved allocations remain untouched. Fixed push-v3
and SawyerPushV3Policy, no weight update or initial-failure selection.

NO_PROBE and CONT_NO_CORRECTION provide task and probe-motion controls.
CONT_DYNAMIC uses the frozen online local dynamic OLS estimator.
PRIOR_AFFINE and PRIOR_NEAREST share the exact qualified calibration artifact
from `response_calibration_20261013T105913Z_bfbd86c7c1dd`. They use affine
response inversion and the nine stored nearest centroids respectively.
The model is loaded and validated once, never fitted to task data. Hidden
context, injected bias, seed, RNG state, and future task outcome do not enter
correction inference. The model's known nominal regime and fixed initial
robot-state assumptions remain material limitations.

Every method episode owns an environment, policy, and actuator instance.
All methods share initial state and noise namespace for each seed/context.
Every probing method collects the same continuous 16-step nominal program;
probe transcripts must match across the four methods. No environment or RNG
reset occurs at the probe/task boundary. Whole-episode xy correction uses the
existing bounded magnitude grid, with zero correction for invalid online fits.
Terminal probe outcomes end the episode and count toward success and cost.

Primary online budget: 500 total steps including probe, leaving 484 task
steps. NO_PROBE may use all 500. A secondary equal-484-policy-step success
metric is descriptive and explicitly allows extra probe cost. No branch
deduplication, outcome-based stopping, extra rollout realization, or tuning.

Offline calibration plus qualification cost 2,304 steps/144 resets. Charge
this entire qualification cost to each prior baseline's logical system cost;
amortized over 64 task units it adds 36 steps and 2.25 resets per unit.
The research collection physically shares those already-collected artifacts,
so do not double-count them as freshly executed simulation. Report online
cost, offline cost, and amortized total separately. Maximum new physical
collection 64*5*500=160,000 steps; one initial reset per method episode.

## Gate and audit

Primary contrast: PRIOR_AFFINE minus CONT_NO_CORRECTION task success under
the matched online total budget. Resample 16 whole task-seed clusters, each
containing four contexts, for 10,000 draws (seed 20261013). Feasibility requires
the paired 95% interval lower endpoint >0, affine success count at least both
NO_PROBE and CONT_DYNAMIC, and complete integrity/population/budget checks.
Nearest-prior and dynamic comparisons are descriptive; do not select a method
post hoc or claim affine superiority over nearest if unsupported.

Report all method successes, total steps, paired cluster contrasts, prior
offset error (evaluator-only), full offline cost, and costs under uniform
reset-cost sensitivity. This gate targets useful continuous evidence with a
qualified prior; it is not a cost-superiority or novel-method gate.

Write the visible decision before the first task step. Keep exact initial and
handoff observations, continuous probe transitions, task-state hash chains,
actuator-call counters, and RNG digests. Replay correction decisions and RNG
consumption without resimulating task dynamics. Task traces may be losslessly
gzip-compressed; record their artifact hashes. No API or memory writes.
Preserve failure without fitting on these task seeds or replacing any cell.
