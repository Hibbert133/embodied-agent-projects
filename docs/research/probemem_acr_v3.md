# ProbeMem-ACR: Action-Conditional Resonance Memory

Protocol family: `probemem_acr_v3`

## Research question

Given current Agent-visible evidence and strictly earlier verified history,
can an embodied decision layer separately estimate the fresh-verification
outcome of bounded compensation and independent retry, rather than copying the
skill used by the nearest successful state?

The research object is a rollout-level decision layer above a fixed robot
policy. The first phase is a deterministic, paired counterfactual feasibility
study. It asks whether action-conditioned evidence contains predictive signal;
it does not test online learning or LLM memory.

## Frozen first-phase method

For every action and outcome class, retrieve up to five strictly earlier
records with the existing 13-feature applicability signature. Standardized RMS
distance generates candidate records. Weights are `1 / (1 + distance)` and a
Dirichlet `(1, 1, 1)` prior yields ACCEPTED, INCONCLUSIVE, and REJECTED
probabilities. Utility is `P(ACCEPTED) + 0.5 * P(INCONCLUSIVE)`.

All predictions are produced before the current episode is executed and
appended. Development counterfactual outcomes may enter the next episode's
offline research memory but never an operational Agent payload.

## Claim boundary

Passing the development gate would justify only a frozen validation study of
action-conditioned outcome estimation. Failure is retained without retuning.
Neither result establishes online adaptation, LLM benefit, principle learning,
or held-out recovery improvement.
