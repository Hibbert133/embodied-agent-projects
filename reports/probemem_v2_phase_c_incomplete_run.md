# ProbeMem Phase C: Incomplete Sequential Retrieval Run

Run: `probemem_phase_c_20260731T094646Z_9dc037acb04c`
Manifest: `4e4bdf071b977fd23964c0f8b1370eb285b6c83a39ced6c01d58563da5d928f8`
Source commit: `9dc037acb04c461f9ab12c1d8e7f1bd9901d938b`

## Status

The immutable development run ended with `FAILED` after 54/60 method-cases (18/20 complete paired episodes). The recorded error was `ValueError: Error: engine error: Could not allocate memory`.

This artifact is **not claim-eligible** and must not be used to state that episodic retrieval improves or harms recovery. It is retained as an incomplete infrastructure result.

## Completed-prefix audit

- Operational audit records: 27.
- Chronology violations: 0.
- Agent/Oracle leakage violations: 0.
- Interaction-budget violations: 0.
- Paired outcome ties: 18/18.
- Paired intervention-skill ties: 18/18.

The completed prefix is useful for integration and cost auditing only. Raw and verified retrieval were exercised chronologically, but identical paired outcomes in this incomplete prefix are neither evidence of benefit nor evidence of equivalence.

## Reproduction

```powershell
.\scripts\run_probemem_phase_c_comparison.ps1 -Manifest "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_phase_c_20260731T094646Z_9dc037acb04c\manifest.json" -ApiTimeout 300
.\.venv\Scripts\python.exe scripts\analyze_probemem_phase_c.py --run-dir "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_phase_c_20260731T094646Z_9dc037acb04c"
```

A new full run requires a new immutable manifest and an explicit decision to spend the API budget again. This failed run must not be overwritten.
