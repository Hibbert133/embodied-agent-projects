# ProbeMem Memory Contradiction and Resonance Audit

This is a post-hoc evaluator-only audit of the frozen development run. It does not alter retrieval, create actionable memory, or promote a principle.

## Question

Does accepted-only local precedent provide a stable prediction that the same intervention will be accepted on a nearby Agent-visible query?

## Result

The gate used memory in 2/20 operational cases. The implicit ACCEPTED prediction was supported in 0, unresolved in 1, and contradicted in 1.
It abstained on 14 local skill conflicts. Among all 18 abstentions, unguarded nearest retrieval would have been accepted in 9 and not accepted in 9 cases.
Conflict outcome partitions were `{'COMPENSATION_ONLY_RECOVERY': 2, 'NEITHER_RECOVERS': 3, 'BOTH_RECOVER': 5, 'RETRY_ONLY_RECOVERY': 4}`.

## Harmful transfers

* Seed 1002: selected `INDEPENDENT_STOCHASTIC_RETRY`, fresh outcome `INCONCLUSIVE` (UNRESOLVED); radius ratio 0.692; dominant distance features `estimated_drift_x` (47.0%) and `final_object_goal_distance` (18.4%).
* Seed 1021: selected `BOUNDED_PLANAR_COMPENSATION`, fresh outcome `REJECTED` (CONTRADICTED); radius ratio 0.721; dominant distance features `probe_estimated_bias_x` (20.2%) and `final_object_goal_distance` (17.6%).

## Interpretation

The failures are not explained solely by crossing the frozen coverage boundary: both memory uses were inside coverage with unanimous local skill support. Local geometric agreement therefore did not imply repeatable intervention utility. The high conflict rate also shows that nearby accepted episodes frequently support different skills.

This evidence blocks principle promotion. A future protocol must predict action-conditional outcomes and test resonance explicitly, or acquire evidence that is more causally informative about intervention response. Threshold retuning on this run is prohibited.
