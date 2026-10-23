# ProbeMem-Online Selective Override Development Result

## Protocol status

Run: `probemem_online_selective_override_20260804T064750Z_1107f99883b4`

Manifest: `2b1945a7bdf273d7ed76d44c330a851ad1f3c63c722126bd29fd7b79c4c6eb8f`

Source commit: `1107f99883b408fd10ce548488e95241ee284ec3`

Final status: `INCOMPLETE_POPULATION`

The run reached 40 operational cases but produced only three leave-one-probe-
repeat-out ambiguous cases, below the preregistered minimum of ten. The
promotion gate is not evaluated. The run cannot be extended, replaced, or used
to select a wider ambiguity band.

## Integrity

Chronology, Oracle leakage, budget, random namespace, future-memory access,
counterfactual writes, invalid Memory IDs, invalid skills, and high-confidence
API-call violations were all zero. All nine GLM calls produced valid structured
outputs without schema repair.

## Descriptive results

| Method | Accepted | Harmful | Abstain | API decisions |
|---|---:|---:|---:|---:|
| Frozen variance rule | 34/40 | 1 | 0 | 0 |
| Ambiguity-gated Stateless GLM | 33/40 | 2 | 0 | 3 |
| Memory with deterministic fallback | 34/40 | 1 | 0 | 3 |
| Memory with conflict abstention | 33/40 | 1 | 1 | 3 |
| Evaluator-only Oracle | 35/40 | 0 | 0 | 0 |

The primary Memory-fallback method changed two frozen-rule actions. Both were
verification-status ties: one case had both candidates accepted, and one had
both rejected. It therefore achieved exactly the same accepted recovery as the
frozen rule, with a paired difference of zero.

Only three cases requested online reasoning. Nine API calls replaced the 120
calls required by running all three GLM variants on every case, a descriptive
92.5% reduction. Provider-reported usage was 16,119 input and 22,956 output
tokens. Median latency was 57.0 seconds and maximum latency was 138.0 seconds.

## Ambiguous cases

Episode 22 exposed the clearest interface benefit. Stateless GLM proposed retry
instead of accepted deterministic compensation and obtained `REJECTED`.
Action-conditioned Memory preferred compensation, so the fallback guard
blocked the override and preserved `ACCEPTED`. The abstention variant detected
the conflict but unnecessarily abstained from an accepted action.

In episode 30, Memory changed retry to compensation, but both candidates were
accepted. In episode 36, Memory made the same change, but both candidates were
rejected. These changes did not alter task outcome.

The host guard can therefore prevent an individual harmful Stateless GLM
action, but the registered stream contains too few ambiguous cases to estimate
a reliable selective-Agent effect.

## Research interpretation

The outcome-independent gate was highly selective: 92.5% of cases bypassed API
reasoning. This supports the engineering premise that a strong physical rule
can eliminate most online-model cost. It does not support the stronger claim
that GLM or Memory improves recovery.

The result separates cost allocation from decision benefit. Selective
invocation sharply reduced API use, while the observed ambiguous population
was insufficient and the primary method produced no net recovery change.
Widening the ambiguity region now would invalidate the registered test.

## Claim boundary

Allowed narrow statement:

> A leave-one-probe-repeat-out host gate bypassed GLM on 37/40 operational
> cases and preserved frozen-rule recovery descriptively, but the preregistered
> ambiguity population was insufficient for evaluating online Memory benefit.

This result does not establish GLM or Memory recovery improvement, validate the
selective policy, authorize held-out execution, or justify principle memory.
