# Intervention Identifiability Development v1: Incomplete Run

## Research question

After the frozen P1 intervention experiment was not promoted, this development
audit asked whether the broad mechanism class was sufficient to identify the
higher-utility bounded intervention on each failed rollout.

## Provenance

- Run: `development_20260731T030038Z_c3dac4e631fb`
- Source commit: `c3dac4e631fbf20d77dfe584554e6aab10061c67`
- Split: development seeds 400--409
- Registered conditions: `fault_01` through `fault_05`
- API calls: 0
- Rendering: disabled

## Execution status

The run stopped fail-closed at `development_case_0047` (`fault_05`, seed 406).
The registered probe-grounded compensation candidate returned `ABSTAIN`, while
protocol v1 required exactly two executable candidates. The runner did not
coerce abstention into a zero action or silently remove the case.

Artifacts contain 46 completed initial rollout units, 29 operational failures,
and 58 matched candidate verification outcomes. The run status is `FAILED`; no
complete-development performance claim is made.

## Partial observations

Among the 29 completed operational units:

- probe-grounded compensation was the evaluator-preferred candidate in 28;
- stochastic retry was preferred in 1;
- there were 3 passive-to-probe belief changes;
- those changes selected a better outcome twice and a worse outcome once.

The two completed stochastic-noise operational units disagreed: one preferred
retry and one preferred compensation. This is evidence against treating the
mechanism label as a sufficient per-instance utility label, but it remains a
partial observation because protocol v1 did not complete.

## Protocol correction required

A new protocol version must record candidate availability explicitly and define
a comparable subset before execution. Protocol v1 and its artifacts remain
immutable. The correction may not redefine `ABSTAIN` as an executable action or
retroactively label the incomplete run as completed.

## Command

```powershell
python scripts/run_intervention_identifiability_development.py
```
