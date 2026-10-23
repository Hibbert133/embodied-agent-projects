# Evidence validity under a changing execution context

Working mathematical specification. The identities below are elementary
consequences of conditional independence and linearity, not claims of a novel
theorem. The crossed experiment is a measurement of these quantities, not a
learned model or a publication-ready algorithm.

## Variables and information boundary

Let X be the observed task state, S the execution context during a probe, E its
observed response, T the context during the subsequent skill, and A the chosen
skill. The agent observes X and E, not S or T. Let u(X,T,A) be expected success
or another explicitly bounded outcome. The host executes the skill; the agent
never reads injected actions or an evaluator's counterfactual outcome.

A probe can estimate S accurately while saying little about T. Thus uncertainty
about the current diagnostic mechanism and uncertainty about the validity of
that evidence for the upcoming intervention are different quantities.

## A necessary negative control

Assume T is conditionally independent of E given X, and probing has no physical
effect on the subsequent state (as in a reset-matched experiment). For every
evidence-dependent policy pi(A|X,E), its expected utility at a given X is a
convex combination of the utilities of actions under P(T|X). Therefore

    E[u(X,T,A)] <= max_a E[u(X,T,a) | X].

Proof: conditional independence makes each action's conditional expected
utility independent of E. Averaging the policy's weights over E yields
nonnegative weights summing to one; their weighted utility cannot exceed the
maximum. A strictly positive probe cost only reduces net value.

The comparison is against the *best prior action*, not necessarily the nominal
uncorrected policy. Probe compensation could outperform a weak uncorrected
baseline even when E conveys no information about T. This is why the first
crossed-context experiment can establish sensitivity to coupling but cannot
establish a general value-of-information claim.

The assumption also fails if a probe physically changes the object, if hidden
task-state information in E predicts T, or if the skill changes T. Those cases
need their own model rather than this lemma.

## Controlled persistence model

For K equally likely contexts, define

    P_rho(T=t | S=s) = rho * 1[t=s] + (1-rho)/K,
    0 <= rho <= 1.

Source and target marginals are both uniform for every rho. For a fixed
evidence-dependent policy, let U_aligned and U_independent be its expected
utilities under rho=1 and rho=0. Then

    U(rho) = rho * U_aligned + (1-rho) * U_independent.

The full KxK independent table includes diagonal pairs with probability 1/K.
Using only off-diagonal pairs represents a different intervention. A policy
independent of S has identical aligned and independent utility. For bounded
u in [0,1], |U_aligned - U_independent| <= 1-1/K: write the independent
mean as (1/K)*U_aligned + ((K-1)/K)*U_offdiagonal.

The interaction in the frozen experiment subtracts the source-independent
control, so its value is the compensation coupling contrast. Its sampling unit
is a task seed, with all KxK cells retained within that cluster.

## What a future acquisition method would need

For acquisition q, let Delta_q(rho) be its task-utility advantage over the
strongest admissible no-acquisition policy, and C_q(rho) its additional physical
cost (including changed task-execution length). An explicit cost preference
lambda defines net value Delta_q(rho) - lambda*C_q(rho). Under the mixture
model both terms are affine in rho for a fixed policy, so a robust lower bound
over a calibrated interval [rho_low, rho_high] is the minimum of the two endpoint
values. This elementary calculation is a reference decision rule, not a new
contribution.

The unresolved research work is to obtain a causally valid, calibrated estimate
of persistence and outcome advantage under partial observations, and select
useful evidence without spending more than the recovery gain warrants. A cheap
measurement may detect irrelevant changes; a seemingly stable history may miss
a change affecting the chosen skill. A competitive method must target changes
that alter action utility and outperform standard cost-aware change detection.

## Directly relevant prior art and required baselines

- [Adams & MacKay, Bayesian Online Changepoint Detection](https://arxiv.org/abs/0710.3742)
  supplies a standard posterior over time since a change; generic Bayesian change
  detection is not new.
- [Gundersen et al., Active multi-fidelity Bayesian online changepoint detection](https://arxiv.org/abs/2103.14224)
  already trades measurement fidelity/cost against information about changes.
  Merely adding an acquisition cost to a change detector is not our contribution.
- [Steinparz et al., Reactive Exploration](https://proceedings.mlr.press/v199/steinparz22a.html)
  connects detecting domain shifts to renewed exploration in lifelong RL.
  "Detect then explore" alone is not a novel mechanism.
- [Altamirano et al., Robust and Scalable Bayesian Online Changepoint Detection](https://proceedings.mlr.press/v202/altamirano23a.html)
  gives a robust change-detection comparison when rare disturbances can produce
  false resets. Its role and assumptions must be assessed before implementation.

These references narrow the prospective contribution to *action-relevant
evidence validity and reacquisition*, with measured advantages over the above
ideas in matched robot-interaction budgets. Novelty remains unverified; a full
review and independent prospective evaluation are required.
