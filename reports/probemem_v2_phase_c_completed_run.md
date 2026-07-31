# ProbeMem Phase C: Completed Sequential Retrieval Development Run

Run: `probemem_phase_c_20260731T155344Z_f7176579eb82`
Manifest: `97fffbc4fe1c44b8b920b791d621bd574678c56593edd8312e91ec142e3582e0`
Source commit: `f7176579eb82f49adfd6ade0eeeeae2f495ac8f4`

## Status

The immutable development run completed all 60/60 method-cases (20/20 paired episodes; 10 required an online decision).

This artifact supports a narrow development conclusion: episodic records were retrieved through a chronological leakage-safe interface, but neither raw nor accepted-only retrieval changed the intervention or verification outcome on this stream. It does not establish broad method equivalence or a memory benefit.

## Method results

- `stateless_online_llm`: 5/10 accepted, 0 retrieved records, 20 API calls, 75323 input and 33741 output tokens.
- `raw_episodic_retrieval_development_only`: 5/10 accepted, 24 retrieved records, 20 API calls, 87854 input and 45778 output tokens.
- `verified_episodic_retrieval`: 5/10 accepted, 20 retrieved records, 20 API calls, 85667 input and 36019 output tokens.

## Integrity audit

- Operational audit records: 30.
- Chronology violations: 0.
- Agent/Oracle leakage violations: 0.
- Interaction-budget violations: 0.
- Operational paired episodes: 10.
- Paired outcome ties: 10/10.
- Paired intervention-skill ties: 10/10.
- Raw-memory non-accepted record exposures: 14.

## Interpretation

All operational pairs selected the same bounded intervention and had the same verification outcome. Raw retrieval exposed the model to 14 non-accepted historical records, while verified retrieval excluded them. The absence of behavioral change shows that retrieval alone is insufficient in this registered setup; Phase D must not be promoted merely because memory was cited.

## Reproduction

```powershell
.\scripts\run_probemem_phase_c_comparison.ps1 -Manifest "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_phase_c_20260731T155344Z_f7176579eb82\manifest.json" -ApiTimeout 300
.\.venv\Scripts\python.exe scripts\analyze_probemem_phase_c.py --run-dir "C:\Users\Administrator\Desktop\embodied-agent-projects\outputs\probemem_v2\runs\probemem_phase_c_20260731T155344Z_f7176579eb82"
```

This is a completed development result. Held-out or stronger memory claims require a separately frozen protocol and cannot be inferred here.
