# ProbeMem-SciAgent Probe Value v1.4

Status: `SHADOW_FROZEN_BEFORE_EXECUTION`

## Research question

Capability Contract v1.3 produced eight fully certified decisions, but every
decision requested a micro-probe. This successor asks whether a complete,
host-recomputed expected-value-of-sample-information certificate can reject
probes whose predicted action-selection benefit does not justify their fixed
interaction cost.

The v1.1--v1.3 results are immutable. Seeds 6200--6299 remain reserved. This
protocol may scan fresh development seeds 6300--6349 once; 6350--6449 are
reserved.

## Single method change

For each proposed probe, the model must report current success probabilities
for both registered recovery skills and exactly two registered outcome
branches. Each branch contains its probability, updated candidate
probabilities, and the resulting registered skill. The Host independently
checks capability tokens, branch coverage and normalization, a minimum branch
probability of 0.05, branch argmax consistency, and the claimed expected gain.

The frozen host calculation is:

```text
expected value gain
= sum(branch probability * branch best success probability)
  - current best success probability

normalized probe cost = maximum probe steps / 1256
```

`COMPENSATION_RESPONSE_PROBE` costs 64/1256 and
`RETRY_REPEATABILITY_PROBE` costs 192/1256. A shadow probe is admitted only if
at least one branch changes the provisional skill and expected value gain is
strictly greater than normalized cost. Invalid certificates fail closed. A
valid but low-value certificate is recorded as a rejected probe request, not
silently replaced by a recovery action.

No probe, recovery action, paired candidate, memory update, or principle update
executes. The mandatory repeated probe is existing diagnostic evidence, not the
new action-conditioned micro-probe. The model sees no Oracle condition, paired
outcome, fault label, or future result.

## Population and gate

After one health check, scan at most 50 units until eight operational failures
are collected. The maximum remains nine primary calls, one repair, ten calls,
and zero transport retries.

Passing requires all v1.3 interface conditions, at least seven valid probe-
value certificates, at least four rejected probe requests, probe admission rate
at most 50%, and zero integrity violations. Passing establishes only that the
model can express budget-sensitive probe value under a strict host certificate.
It does not authorize online actions, recovery claims, memory, principles,
validation, or held-out execution. Failure is preserved without retuning costs,
branch constraints, prompt, tokens, or gate on this stream.
