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

## Immutable result

The completed development run is:

- run ID: `probemem_paired_utility_20260731T173200Z_aceee1a6eca2`;
- manifest ID: `f191171b0dd485a9e6f08f232acf17205d687c5de52cf7a83ebb39d542e3f76f`;
- source commit: `aceee1a6eca2d3313bb0b7c71629d0828b5ada3d`.

It scanned 58 initial units and stopped at the registered target of 20
operational pairs. Compensation was accepted in 10/20 cases, retry in 14/20,
and the evaluator-only per-case Oracle upper bound was 16/20. There were 2
compensation-only, 6 retry-only, 8 both-accepted, and 4 neither-accepted cases.
No selector, threshold, memory principle, API decision, or held-out claim was
produced from this run.
