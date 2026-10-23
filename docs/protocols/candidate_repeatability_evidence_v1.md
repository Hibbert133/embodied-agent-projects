# Candidate Repeatability Evidence Protocol v1

## Hypothesis

One candidate prefix was not a reliable proxy for full-rollout intervention
utility. This protocol tests whether repeated responses provide more useful
evidence under stochastic execution error.

The rule is frozen before collecting seeds 600--699. For each operational case,
both candidates execute three independent 64-step prefixes. Results are
reported after one, two, and three repetitions; no favorable repetition count
is selected after evaluation.

## Frozen selector

For each candidate and repetition count:

1. count prefix successes;
2. compute mean final object-goal distance;
3. compute population standard deviation of that distance;
4. define `robust_distance_score = mean + std`.

The selector prefers higher prefix success count, then lower robust distance,
then lower mean observed steps and candidate ID. It has no fitted threshold.
The same stochastic realization is shared by both candidates within a
repetition, while repetitions and final verification use independent random
streams.

## Evaluation and scope

The selector reads Agent-visible prefix summaries only. Candidate outcomes are
evaluator-only and come from independent matched fresh verification. Report:

- utility agreement;
- selected recovery versus both fixed candidates;
- paired win/tie/loss and paired bootstrap interval;
- prefix and total additional environment steps;
- the post-hoc candidate-oracle ceiling.

This is attempt-level simulator branching on a development split. It is not
held-out evidence, real-time control, online policy learning, or multi-probe
selection.
