# Candidate-Conditioned Micro-Evidence Development Protocol v1

## Question

Aggregate failure evidence did not reliably predict whether compensation or
retry had higher utility. This protocol asks whether short, action-conditioned
candidate rollouts improve that decision.

## Source population

The population is the immutable 20-case paired-comparable noise coverage run
`development_20260731T035004Z_ed696b94484e`. Final candidate outcomes remain
unchanged and are used only after selection for evaluator scoring.

## Evidence acquisition

For each case, both registered candidates execute from the same task reset with
the same independent prefix perturbation realization. Maximum prefix length is
128 steps. Agent-visible summaries are evaluated at horizons 16, 32, 64, and
128. Prefix evidence never contains perturbation truth or final verification
outcomes.

The deterministic selector prefers prefix success, then lower object-goal
distance, then fewer observed steps. Evidence cost is the sum of both candidate
prefix lengths. No threshold or feature combination is fitted.

## Scope boundary

This is simulator branching across rollout attempts. It is not the original
single registered diagnostic probe, step-level replanning, continuous-action
generation, or a real-robot capability. Every horizon is reported; no favorable
horizon is silently selected. A later held-out protocol would be required for a
performance claim.
