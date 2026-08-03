# ProbeMem-Online Gate B bootstrap

The successful immutable run is
`probemem_online_bootstrap_20260803T093056Z_6e6c4ba0f6fe`, with manifest
`6c221715cc560d05ee72795c5a7b6442a0f6447c394dfb52e4f7ce7879ddc47f`.
It produced snapshot `bootstrap_1aa7ee3f2c69a0df` from 20 outcome-blind,
counterbalanced selected-action executions.

Each of the four registered condition/action cells contributed five records.
The audit contains 10 ACCEPTED, 3 INCONCLUSIVE, and 7 REJECTED outcomes. All 20
outcomes enter action-conditioned statistics, while only the 10 ACCEPTED
records enter the verified-example index. No unselected candidate was executed
or stored. Chronology, Oracle leakage, budget, random-namespace, and
counterfactual-record violations were all zero.

This result establishes Gate B memory integrity and a shared cold-start
snapshot. It does not establish a memory benefit or online adaptation result.

An earlier immutable run
`probemem_online_bootstrap_20260803T092923Z_83675e9d1be5` failed after its first
record because heterogeneous CSV field names were not initialized before the
first operational row. That failed run remains preserved. The schema-only fix
did not alter seeds, assignments, budgets, perturbations, or the stop rule.

Command:

```powershell
.\.venv\Scripts\python.exe scripts\build_regime_memory_bootstrap.py --manifest outputs\probemem_online\bootstrap_runs\probemem_online_bootstrap_20260803T093056Z_6e6c4ba0f6fe\immutable_manifest.json
```
