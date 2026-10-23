# ProbeMem-ACR Distributional Memory Development V1: Incomplete Population

## Scope

This was a development-only collection for testing chronological distributional
action-outcome memory and abstention. It did not call an LLM, update a robot
policy, promote a principle, or execute validation or held-out seeds.

The protocol was frozen at source commit
`ce7d9daa5547f3c995543ddd9778b27b936d2f09`. The immutable run identifiers are:

- experiment run: `acr_distributional_20260802T125208Z_ce7d9daa5547`;
- manifest: `7f67a0a2d04ad38e73101194fbf2af0a50b229255d2282bcc9fa34f78798edcb`.

## Registered stopping rule

The frozen development population contained seeds 2000--2099. Collection was
required to reach 40 Agent-visibly eligible failed initial rollouts without
reading candidate outcomes. Validation seeds 2100--2149 and held-out seeds
2150--2199 were reserved and were not executed.

## Actual collection result

All 100 registered development seeds were scanned. The stream contained 61
successful initial rollouts and 39 eligible failed initial rollouts. No failed
rollout was excluded for intervention constructibility. The collection therefore
ended with 39 operational cases, one below the preregistered minimum, and the run
was marked `INCOMPLETE_POPULATION`.

For audit only, the 39 operational cases produced 78 paired counterfactual
candidate rollouts. Their outcome counts were:

| Candidate | ACCEPTED | INCONCLUSIVE | REJECTED |
| --- | ---: | ---: | ---: |
| Bounded planar compensation | 18 | 13 | 8 |
| Independent stochastic retry | 24 | 9 | 6 |

The paired audit contained 26 exclusive-recovery cases, 8 cases where both
candidates were accepted, and 5 cases where neither candidate was accepted.
These evaluator-only outcomes were not replayed as operational memory because
the population gate had already failed.

## Integrity audit

- chronology violations: 0;
- Oracle leakage events: 0;
- budget violations: 0;
- API calls: 0;
- candidate-outcome reads by the stopping rule: false.

The familiar Gymnasium/MetaWorld observation-space and action-clipping warnings
were emitted. They did not terminate an episode or alter the recorded integrity
counters.

## Decision and claim boundary

The frozen 40-case minimum was not met. Consequently:

- the chronological method replay was not run;
- the promotion gate was not evaluated as passed or failed on method quality;
- no selector, GLM, principle, validation, or held-out experiment is authorized;
- no distributional-memory performance or online-learning claim is made.

The result is preserved as an incomplete preregistered experiment rather than
extending the seed range or lowering the sample-size threshold after observing
the data. A future protocol may preregister a larger development population,
but it must use a new run ID, a new manifest, and fresh seeds.

## Artifacts

The immutable run directory is
`outputs/probemem_acr/distributional_runs/acr_distributional_20260802T125208Z_ce7d9daa5547/`.
It contains the manifest, run status, collection summary, case table, paired
candidate table, and Agent-visible evidence signatures. Large initial trajectory
files remain ignored by Git.
