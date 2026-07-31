# Intervention Identifiability Development Protocol v2

Protocol v1 stopped fail-closed because the frozen recovery policy returned
`ABSTAIN` for a registered compensation candidate. V2 changes only missing-
candidate accounting; it does not change seeds, evidence, correction logic,
verification streams, or the evaluator utility order.

`ABSTAIN` is not coerced into an action. The case remains in the operational
population with `compensation_available = false`. Other executable candidates
may still be evaluated, but the outcome-derived paired-utility label is defined
only for the **comparable population** where both registered candidates are
available.

Reports must include:

* full collection units;
* operational failures;
* paired-comparable units;
* compensation availability and abstention count;
* candidate metrics with their method-specific denominators;
* utility agreement only on the comparable population.

The incomplete v1 run remains immutable under its original run ID. V2 is still
development-only and cannot support a held-out selector claim.
