# Prospective prefix acquisition and evidence refresh v1

Status: frozen before outcomes. This new development study follows the user's
continuing publication objective and the passed context-persistence feasibility
study; it does not reuse or tune on seeds 8000--8015 or release 8016--8199.

## Question and candidate

Can agreement about an executable correction reduce reacquisition cost without
losing task success to cheap fixed-prefix baselines under execution noise?
This is a method feasibility study, not a novelty claim. Decision-region active
learning predates this project, including
[Javdani et al., AISTATS 2014](https://proceedings.mlr.press/v33/javdani14.html).
Leave-one-out agreement is a stability heuristic, not a confidence interval or
proof that the selected action maximizes recovery.

Each probe repetition contains the unchanged four symmetric directions, four
steps per direction at magnitude 0.2 (16 steps). A method receives only its
requested prefix. Pool drift and response gain by arithmetic mean, then use
the existing frozen correction quantization, skill, and schedule mapping.
All current plans are written before any current task outcome is evaluated.

`DECISION_STABILITY`: if no accepted cache exists, acquire four repetitions.
Otherwise acquire one repetition; if its complete execution signature matches
the cached action, stop. If different, acquire repetitions two through four,
stopping when the pooled plan and every leave-one-out pooled plan share the same
complete execution signature. At the four-repeat maximum use the pooled plan
and explicitly record any unresolved disagreement. A missing/invalid response
cannot silently pass validation.

Each method owns its cache, cleared at every stream boundary. Only its selected
ACCEPTED fresh outcome and actually consumed current measurements can update
the cache; no-probe reuse does not create new evidence. Rejected/inconclusive
outcomes never update actionable cache. All task states are included, so the
metric is task success, not recovery conditional on initial failure.

## Baselines and fair comparison

- FIXED_16, FIXED_32, FIXED_64: always use exactly 1, 2, or 4 current repetitions,
  respectively, with the same pooled estimator. FIXED_16 is required because
  the historical four-repeat correction used only its first repetition.
- STALE: bootstrap with four when no accepted cache exists, otherwise reuse.
- PERIODIC_4: the same bootstrap and four-repeat refresh at episode indices
  0,4,8; reuse accepted cache otherwise.
- CHANGE_THRESHOLD: bootstrap with four; then one current repetition and
  four total when Euclidean inferred-bias change exceeds 0.04, otherwise reuse
  the cached plan. This fixed-scale change detector is a simple baseline,
  not an implementation of Bayesian online change-point detection.
- UNCORRECTED: no probe and the unmodified low-level policy.

The full 64-step probe is physically collected once per episode as shared
evaluator infrastructure. Its unrequested suffix is not passed to a method or
its cache. All methods see the same prefixes when they request them. Logical
cost charges exactly the evidence accessed, while physical collection cost is
reported separately. Identical executable plans share one reset-matched outcome
within an episode with explicit branch references; distinct plans own fresh
environment/policy/perturbation objects and use common random numbers.
Each method writes only its selected outcome to its own accepted cache.

## Frozen population and budgets

Eight independent streams, 12 episodes each, use exactly fresh task seeds
8200--8295. Streams 0--3 have one stationary context (one per historical bias).
Streams 4--7 rotate through all four contexts in three-episode blocks, starting
from the stream index modulo four. The learner sees neither stream category,
context identity, schedule, nor perturbation parameters. Numeric stream/episode
IDs enforce chronology; only PERIODIC_4 uses the episode index for its schedule.

Every bias context adds Gaussian execution noise std 0.05 on xyz translation,
matching the previously used perturbation class and low-noise setting. Task,
policy, correction magnitudes, and planner thresholds remain unchanged. Noise
namespaces are independent across repetitions/episodes; each directional group
uses the registered common noise namespace across opposite directions.
The execution context stays fixed through the current probe and task rollout.
This tests evidence reuse *between episodes*, not unseen changes after a probe.

At most 64 probe + 500 execution steps per method/episode. Maximum physical
collection: 96x64 probe steps plus 96x8x500 task steps = 390,144 steps.
No outcome-based stopping, tuning, rerun, or resampling. Seeds 8296--8499 become
reserved. No API calls, free-form principles, policy-weight updates, or
publication/generalization claim are part of this protocol.

## Registered metrics and development gate

Primary: paired task success and mean acquired probe steps on all 96 episodes.
Compute method differences within each of the eight streams, then bootstrap
whole streams (10,000 draws; seed 20261014). Report stationary/abrupt strata
descriptively, stale action changes, acquired prefixes, accepted cache writes,
and total logical and physical steps. Never treat 768 method rows as independent.

DECISION_STABILITY passes feasibility only when all are satisfied:

1. lower endpoint of its paired success difference versus FIXED_64 is greater
   than -0.05 (a development tolerance, not a powered noninferiority trial);
2. mean probe use is at least 25% below FIXED_64;
3. no registered noncandidate baseline has weakly higher success and weakly
   lower probe cost with at least one strict improvement;
4. all 96 episodes complete and chronology, leakage, cache ownership, budget,
   reset, population, and source-integrity checks pass.

A failed gate is preserved without revising the threshold, prefix policy,
noise, cache rule, or stream schedule on this population. Passage would permit
further method development, not independent validation or a publication claim.
Eight streams and one task are insufficient to establish the final objective.
