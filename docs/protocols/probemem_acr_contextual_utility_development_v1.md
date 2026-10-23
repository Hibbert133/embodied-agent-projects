# ProbeMem-ACR Contextual Utility Development v1

Status: `FROZEN_BEFORE_EXECUTION`

## Question

Can a chronological Bayesian action model conditioned on the complete frozen
Agent-visible evidence signature improve candidate selection over a global
action posterior and accepted-only reuse?

This protocol follows two negative findings: state-similarity retrieval did not
predict action utility, and a global action posterior did not change decisions
relative to last-success memory. It tests a different hypothesis: smooth,
case-conditioned utility structure may be learnable without nearest-neighbor
imitation or outcome-label feature selection.

## Model

For each registered action, fit a Bayesian linear model to ordinal utility
`ACCEPTED=1`, `INCONCLUSIVE=0.5`, `REJECTED=0`. The model uses all 13 fields in
`INTERVENTION_APPLICABILITY_FEATURES`; no feature is selected from prior outcome
audits. The prior utility is 0.5, prior precision is 1, and observation variance
is 0.25. These generic constants are frozen before fresh collection.

At episode `t`, feature mean/scale and both action models are rebuilt only from
that method's selected outcomes at episodes `<t`. The current context is
excluded from scaling statistics. Sixteen alternating exploration episodes are
followed by contextual mean-greedy selection or a 0.80 posterior-superiority
abstention rule.

## Population and causal boundary

- development seeds: 2500--2699;
- validation 2700--2749 and held-out 2750--2849: reserved and unauthorized;
- label-blind stop: 60 eligible failed cases or 200 initial units;
- paired candidates: evaluator-only common-random-number rollouts;
- operational history: only the method-selected current outcome is appended
  after its decision.

## Promotion

All integrity requirements and the 60-case population are mandatory. A route
also requires contextual recovery to finish within one accepted case of the
strongest fixed baseline. Contextual greedy must gain at least three accepted
cases over the global posterior without more harmful transfer; alternatively,
contextual abstention must reduce harmful transfer by at least 30% and two
cases, cover at least half of post-exploration cases, and improve covered
precision by ten points.

Failure is preserved without changing features, priors, thresholds, or seeds.
This development paired-counterfactual study cannot establish online learning,
LLM-memory benefit, principle learning, validation, or held-out performance.
