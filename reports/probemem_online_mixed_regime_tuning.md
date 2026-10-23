# ProbeMem-Online Mixed Persistent Regime Tuning

## Scope

This is a tuning-only paired counterfactual feasibility study. It does not
evaluate an online Agent, memory benefit, GLM benefit, validation, or held-out
performance. No operational memory was written and no API was called.

Run ID: `probemem_online_mixed_tuning_20260803T093907Z_f9b56fbeba64`

Manifest ID: `dc6da911985a78ce05509a92079d0a763f19100e43c53814af56f602556d1271`

Source commit: `f9b56fbeba6405443dffcf040daaed423f37e3a6`

## Result

The campaign completed all 100 preregistered initial units. Thirty-nine were
operational failures with valid paired compensation and retry verification.
Their evaluator-only paired outcomes were:

| Outcome class | Cases |
| --- | ---: |
| Compensation-only or retry-only recovery | 19 |
| Both recover | 15 |
| Neither recovers | 5 |

All four registered regimes contributed operational cases. The integrity audit
reported zero chronology, Oracle-leakage, budget, and random-namespace
violations.

## Interpretation

The mixed benchmark contains meaningful action-utility diversity: neither a
single action nor state similarity can be assumed to determine every paired
winner. This authorizes freezing a separate chronological Gate-C development
stream. It does not establish that GLM reasoning or action-conditioned memory
improves recovery.

The command monitor reached its 320-second outer timeout after the experiment
had written all results. `run_status.json` records `COMPLETED`; therefore this
was a monitoring timeout rather than an experiment failure.

## Artifacts

All raw artifacts are under:

`outputs/probemem_online/mixed_tuning_runs/probemem_online_mixed_tuning_20260803T093907Z_f9b56fbeba64/`

The preceding import-related launch failure remains preserved in its own run
directory and was not overwritten.
