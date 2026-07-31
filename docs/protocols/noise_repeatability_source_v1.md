# Noise Repeatability Source Protocol v1

## Purpose

This protocol creates a fresh development population for evaluating repeated
candidate-prefix evidence. It does not define or fit the repeatability selector.
The outcome table is generated first, then treated as evaluator-only data after
the evidence rule is separately frozen.

## Population and stopping

- MetaWorld `push-v3`, fixed `SawyerPushV3Policy`.
- Stochastic-noise condition `fault_05` only.
- Sequential seeds 500--559, disjoint from held-out seeds 330--339 and all
  previous utility-development seeds 400--488.
- Stop after 20 paired-comparable operational failures or 60 initial units.
- Stopping depends only on paired-comparable coverage, never candidate utility.

Each operational case receives the same two registered intervention candidates
and independent matched fresh verification. Initial, diagnostic-probe, and
verification stochastic streams use separate frozen namespaces.

## Boundary

This is development data, not held-out evidence. It makes no selector claim,
uses no API or rendering, and cannot be used to revise the frozen v1 evidence
allocation protocol. The later repeatability rule must be committed before it
reads candidate outcomes from this run.
