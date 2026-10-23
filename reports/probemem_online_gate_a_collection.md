# ProbeMem-Online Gate A evidence collection

Run `probemem_online_gate_a_collection_20260803T072303Z_b3a2f71691fb`
was generated from commit `b3a2f71691fb5fc89d1c863a30a72111d2cff97a`.
The immutable manifest ID is
`c059684461ceebc6b77212190f66f1cbc92403aa566c98cf63011c9b03d09b7d`.

The frozen collection inspected 71 candidate units and retained exactly 30
operational failures: 15 under registered stable bias (`fault_01`) and 15 under
registered persistent stochastic noise (`fault_05`). It produced 60 paired,
evaluator-only fresh-verification outcomes. Agent evidence was persisted before
either outcome. The run reported zero chronology, Oracle-leakage, budget, and
random-namespace violations and made no API calls.

Descriptively, compensation was accepted in 14/15 stable-bias cases and retry
in 0/15. Under stochastic noise, compensation was accepted in 9/15 and retry in
10/15. These paired outcomes audit interface selections; they were not included
in a model payload and do not establish an online-agent result.

Command:

```powershell
.\.venv\Scripts\python.exe scripts\run_online_gate_a_collection.py --manifest outputs\probemem_online\gate_a_collection_runs\probemem_online_gate_a_collection_20260803T072303Z_b3a2f71691fb\immutable_manifest.json
```

The Gymnasium observation-space and MetaWorld action-clipping warnings are
known upstream warnings. The run completed and its integrity counters remained
zero.
