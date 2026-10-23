# ProbeMem-Online Gate A interface ablation

Run `probemem_online_interface_ablation_20260803T072817Z_1c19c23bafb3`
used 30 fresh development cases and manifest
`b02cd5e3e8d283ff248ea0c17c4735ad1be9081f8f8a7d616322f8d4028f7245`.
It completed 90 base GLM-5.2 calls and 12 preregistered single repairs (102
calls total). No model-selected action was executed.

## Frozen result

| Interface | Raw valid | Post-repair valid | Correct skill | Stable compensation | Stochastic retry | Stochastic abstain | Descriptive matched accepted |
|---|---:|---:|---:|---:|---:|---:|---:|
| Historical full payload | 27/30 | 29/30 | 22/30 | 15/15 | 7/15 | 5/15 | 19/30 |
| Compact causal evidence | 24/30 | 29/30 | 22/30 | 15/15 | 7/15 | 6/15 | 21/30 |
| Compact + explicit skill semantics | 27/30 | 30/30 | 27/30 | 15/15 | 12/15 | 0/15 | 23/30 |

Interface C passed every absolute gate and both comparative alternatives. It
added five correct registered-skill selections relative to the historical full
payload and reduced stochastic abstention from 5/15 to 0/15. This supports the
narrow conclusion that explicit registered-skill semantics reduce conservative
abstention and improve action grounding on fresh persistent-regime development
cases.

The result does not show online recovery improvement: all choices were shadow
predictions matched after the fact to already frozen paired candidate outcomes.
It also does not establish a memory benefit. Compact-only had the highest
exclusive-case accuracy (18/21 versus 17/21 for compact plus semantics), so the
evidence does not justify claiming that Interface C dominates every action-
utility metric.

## Operational audit

Post-repair validity was 88/90 overall. Two repairs remained invalid and failed
closed to abstention. Interface-C median API latency was 32.3 seconds, p90 was
129.3 seconds, and max was 300.0 seconds. Provider-reported token usage is
preserved verbatim in the audit; it may include hidden reasoning tokens and is
not inferred from response text. Oracle leakage and invalid skill execution
counts were zero.

Gate B memory infrastructure is authorized. Validation and held-out execution
remain unauthorized.

Commands:

```powershell
.\scripts\run_glm_interface_ablation.ps1 --manifest outputs\probemem_online\interface_ablation_runs\probemem_online_interface_ablation_20260803T072817Z_1c19c23bafb3\immutable_manifest.json -ApiTimeout 300
.\.venv\Scripts\python.exe scripts\analyze_glm_interface_ablation.py --run-dir outputs\probemem_online\interface_ablation_runs\probemem_online_interface_ablation_20260803T072817Z_1c19c23bafb3
```
