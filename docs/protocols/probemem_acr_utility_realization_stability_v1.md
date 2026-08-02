# ProbeMem-ACR Utility Realization Stability v1

Status: `FROZEN_BEFORE_EXECUTION`

## Motivation

The ACR development run and the prospective `fault_05` replication did not
support a state-feature selector. Earlier candidate-prefix and repeatability
studies also showed that short candidate trajectories can mis-rank an
independent full rollout. Under per-step Gaussian execution noise, a single
paired winner may therefore be a noisy realization rather than a stable
state-conditioned action-utility target.

## Registered question

For a fixed failed task state and Agent-visible registered-probe evidence, are
the relative utilities of bounded compensation and independent retry stable
across independent fresh-verification noise realizations?

This protocol estimates `P(outcome | evidence, intervention)` through repeated
evaluator-only verification. It does not train a selector and does not present
the repeated counterfactuals as experience available to an online Agent.

## Population and execution

- Scan fresh development seeds 1600--1699 under `fault_05` only.
- Stop after 20 failed initial rollouts, or after 100 initial units.
- For each operational unit, collect the registered 64-step probe once.
- Execute both registered candidates for six independent paired realizations.
- Within a realization, both candidates use independent resets of the same task
  state and the same perturbation seed. Realizations use independent seeds.
- Initial, probe, and verification streams use disjoint namespaces.
- Seeds 1700--1799 are reserved and cannot be executed by this protocol.

The stopping rule reads only initial success/failure and never reads candidate
outcomes.

## Frozen estimands

Status utility is `ACCEPTED=1`, `INCONCLUSIVE=0.5`, and `REJECTED=0`.
Per-state action utility is the mean status utility over six realizations.
A stable preference requires an absolute mean-utility margin of at least 0.20.

Single-realization label reliability is evaluated prospectively by
leave-one-realization-out comparison: a realization's candidate winner is
compared with the expected winner computed from the other five realizations.
Complete status/progress/cost ties and leave-one-out expected-utility ties are
excluded and counted explicitly.

Report:

- per-action outcome distributions and accepted rates;
- per-state mean utility and utility margin;
- stable-preference case count;
- realization-level winner reversal rate;
- leave-one-realization-out winner reliability and paired bootstrap interval;
- within-state outcome entropy and action-stratified results;
- chronology, leakage, random-stream, and budget audits.

Feasibility requires at least 20 operational cases, at least eight stable
preferences, reliability at least 0.70, and zero integrity violations. Passing
would only authorize a separately frozen expected-utility prediction protocol.
Failure would support an abstention or additional-sampling formulation. Neither
outcome authorizes LLM, validation, held-out, or memory-benefit claims.

## Claim boundary

This is a development-only repeated paired counterfactual feasibility study.
It measures target stability under simulated stochastic execution. It is not
online learning, a deployed Agent interaction trace, a policy improvement, or
a held-out result.
