# ProbeMem Paired Intervention-Utility Development Protocol v1

## Question

Can an Agent-visible post-probe applicability signature distinguish whether
`BOUNDED_PLANAR_COMPENSATION` or `INDEPENDENT_STOCHASTIC_RETRY` produces the
better fresh-verification outcome?

This is a development evaluator collection, not an online memory experiment.
It makes no principle, retrieval, or held-out performance claim.

## Population

Twenty fresh development seeds, 740--759, are assigned cyclically to the five
registered execution conditions. They do not overlap ProbeMem Phase C seeds
720--739 or reserved held-out seeds 900--979. The condition mapping is available
only to the Oracle evaluator.

Each failed initial rollout produces one Agent-visible applicability signature
containing the registered initial state/response features and six registered
probe-consistency features. Injected condition, perturbation parameters, and
candidate winner never enter this signature.

## Matched execution

For the same failed initial rollout and the same registered probe evidence, the
evaluator executes both registered intervention candidates. Both fresh
verification rollouts use the same environment seed and perturbation random
stream. This common-random-number pairing reduces stochastic comparison noise;
the stream remains independent of the initial rollout and diagnostic probe.

The online protocol still allows only one verification rollout. The second
candidate is an evaluator-only counterfactual development rollout and must not
be charged as online Agent behavior.

## Costs

- Online single-candidate maximum: 500 initial + 64 probe + 500 verification =
  1,064 environment steps.
- Evaluator paired-collection maximum: 500 initial + 64 probe + two 500-step
  verifications = 1,564 environment steps.

The two costs are reported separately and must not be combined into a claim
about online interaction efficiency.

## Utility label

Candidate utility uses the existing preregistered evaluator ordering:

1. `ACCEPTED > INCONCLUSIVE > REJECTED`;
2. if both are accepted, fewer steps then lower final object-goal distance;
3. otherwise, lower final distance then fewer steps.

The winner is evaluator-only. It cannot enter Agent evidence, an online LLM
payload, retrieval, or a future held-out decision rule without a separately
frozen development procedure.

## Integrity

The implementation and configuration are committed before manifest creation.
The manifest binds source commit, configuration, code hashes, recovery config,
noise calibration, dependencies, seeds, candidates, and budgets. Runs are
written to new directories and never overwritten. No API calls or video
rendering occur in this collection.

## Immutable result

Run `probemem_paired_utility_20260731T172244Z_44bc5d206ddf` completed all 20
initial units and all 10 operational candidate pairs. Compensation recovered
9/10; retry recovered 0/10. The sole retry utility winner was a both-rejected
case where compensation worsened final distance and retry preserved it. The
four noise-condition initial rollouts all succeeded, so none entered the
operational population. The result is retained as
`INSUFFICIENT_ACTION_UTILITY_DIVERSITY`; it does not authorize selector fitting
or Phase-D promotion.
