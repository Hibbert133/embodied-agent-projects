# ProbeMem-SciAgent Micro-Probe Utility v1.7

Status: `DEVELOPMENT_FROZEN_BEFORE_EXECUTION`

## Question

Robust Probe Value v1.6 restored a hard transport deadline and produced
selective shadow admissions, but its formal gate failed on an audit-association
defect and it executed no proposed micro-probe. This successor asks one new
question:

> When the unchanged robust value contract admits a registered micro-probe,
> does the resulting evidence improve the Agent's recovery-skill selection on
> reset-matched evaluator outcomes?

The capability-token contract, 5% probability language, robust value rule,
registered skills, registered probes, regimes, and GLM model remain unchanged.
The corrected current-call audit binding is frozen before execution.

Seeds 6600--6649 and their failed v1.6 audit are immutable. Seeds 6650--6749
remain reserved. This protocol may scan fresh development seeds 6750--6849
once; seeds 6850--6949 are reserved.

## Causal execution

For each failed, constructible case:

1. collect the existing 64-step repeated-probe evidence;
2. persist one certified pre-probe decision and Host robust-value assessment;
3. execute no micro-probe unless both the Agent requests one and the frozen Host
   robust guard admits it;
4. execute at most one registered micro-probe in an independent random namespace;
5. reset the environment and request one post-probe decision citing the new
   probe record;
6. only after both decisions are persisted, collect reset-matched evaluator-only
   outcomes for both registered recovery skills.

The paired outcomes cannot enter either Agent request. No selected or
counterfactual outcome enters memory, hypotheses, or principles. The paired
verification cost is evaluator collection cost, not deployed online cost.

## Utility estimand

The pre-probe comparator is the provisional registered skill persisted in the
pre-probe decision. Post-probe utility is evaluable only when a certified
post-probe decision selects a registered skill.

Verification status order is frozen as:

```text
REJECTED < INCONCLUSIVE < ACCEPTED
```

An executed probe is `HELPFUL_PROBE` only when it changes the selected skill and
the post-probe skill has strictly better status on the paired outcomes. It is
`HARMFUL_PROBE` only when it changes skill and has strictly worse status.
Unchanged skills and equal-status changes are `NO_DECISION_BENEFIT`. Invalid or
abstaining post-probe decisions are `NOT_EVALUABLE`; no fallback skill is
invented.

## Population and budgets

Scan at most 100 initial units until 12 operational failures. One health call,
12 pre-probe calls, at most six post-probe calls, and at most two repairs are
allowed (21 total calls). The external child-process deadline remains 210
seconds per call with zero transport retries.

Online interaction per case is bounded by 500 initial + 64 repeated evidence +
192 optional micro-probe + 500 reserved recovery steps = 1,256. Formal recovery
does not execute in this evaluator-only feasibility stage. Candidate collection
may add two separately accounted 500-step verification rollouts.

## Promotion gate

Completeness requires at least 10 operational cases, at least 9 valid pre-probe
outputs, at least two Host-admitted and executed probes, at least two valid
post-probe outputs, no more than two repairs, no more than two fail-closed
outputs, and zero chronology, Oracle-leakage, audit-association, budget,
counterfactual-write, invalid-probe, or invalid-skill violations.

Mechanism promotion additionally requires:

```text
helpful probes >= 1
helpful probes > harmful probes
```

Failure, incomplete population, or integrity failure is preserved without
changing seeds, gates, prompts, value bounds, probe definitions, or API
envelope. Passing supports only development feasibility of active probe utility.
It does not authorize memory, principles, online recovery claims, validation,
held-out execution, VLA, RL, or continuous Agent actions.
