# ProbeMem-Online Chronological Development Protocol v1

Status: **frozen before execution**. This is development, not validation or
held-out evaluation.

## Question

Can a compact, skill-grounded GLM decision layer use action-conditioned outcome
memory to change recovery choices helpfully across a preregistered persistent
regime stream, without future or counterfactual access?

## Stream

Seeds 4300–4499 are assigned one regime each before execution. Four chronological
segments change the regime mixture: bias-dominant, noise-dominant, mixed, and
recurrence. Collection stops only after 60 operational failures have completed,
or the registered population is exhausted. Segment and condition identity are
evaluator-only.

Every method shares the same initial rollout and repeated-probe evidence for a
case. Fresh verification uses independent method namespaces. GLM methods use the
same model, temperature, token limit, schema, and skill contract.

## Causal memory rule

Episode `t` retrieves only records with `episode_id < t`. A selected action is
executed once by the deterministic host. Only after fresh verification may that
selected action and observed outcome be appended. The unselected paired outcome
is evaluator-only and can never enter operational memory or the GLM payload.

All statuses are retained for statistical estimation. Only accepted records may
be shown as verified episodic examples. Neither accepted nor failed nearest
records are copied directly as actions.

## Gate

Integrity requires zero chronology, Oracle, future-memory, counterfactual,
budget, invalid-ID, and invalid-skill violations. Relative to stateless GLM, the
full Agent requires at least 15% action changes, at least three net helpful
changes, and at least a 30% harmful-transfer reduction. It must additionally
improve post-shift recovery by five percentage points or reduce environment cost
by ten percent at equal recovery. Recovery may trail the strongest non-Oracle
deterministic baseline by at most one case.

Failure is preserved as a negative result and blocks principle generation,
validation, and held-out execution.
