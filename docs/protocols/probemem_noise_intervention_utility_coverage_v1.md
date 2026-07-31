# ProbeMem Noise Intervention-Utility Coverage Protocol v1

## Motivation

The first paired development stream produced 10 complete operational pairs but
zero operational stochastic-noise failures. Compensation recovered 9/10 cases;
retry recovered none. A selector or scientific-memory principle cannot be
evaluated without cases where the alternative intervention has distinct
recovery utility.

## Label-blind collection

This protocol scans fresh development seeds 760--839 under registered
`fault_05` only. It stops after collecting 20 complete operational candidate
pairs or after 80 initial units, whichever occurs first.

The stopping rule may inspect only:

- whether the initial rollout requires an online decision;
- whether both registered candidates are executable.

It must not inspect candidate verification status, winner, final distance, or
any other utility outcome. This prevents favorable-outcome seed selection.

## Matched candidates and costs

Each operational failure receives the same registered probe evidence followed
by matched fresh verification of `BOUNDED_PLANAR_COMPENSATION` and
`INDEPENDENT_STOCHASTIC_RETRY`, using common verification random numbers. The
second candidate remains evaluator-only.

Online single-candidate cost is bounded at 1,064 environment steps. Paired
evaluator collection is bounded at 1,564 steps. These costs are reported
separately.

## Scope and stop condition

No LLM API, rendering, memory write, principle generation, selector fitting, or
held-out seed is permitted. If the target is not reached, or if no retry-only
accepted recovery is observed, the result remains incomplete for an
action-discriminative selector. Existing negative results are not overwritten.
