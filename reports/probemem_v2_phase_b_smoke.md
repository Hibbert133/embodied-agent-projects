# ProbeMem v2 Phase-B Tool-Grounded Smoke

Protocol: `online_llm_scientific_memory_v2`

Run: `probemem_v2_smoke_20260731T082819Z_d11430b80e3f`

Manifest: `82d584631a4d308b5a01e76ffd4674d69c8995dcbdb6123345961e92aaa5004b`

Source commit: `d11430b80e3f5e388fc997cfd1111f92243e529a`

## Question

Can GLM-5.2 reliably use the strict ProbeMem tool schema, without Oracle access,
before any actionable memory is implemented?

This is an integration and falsification smoke, not a model-performance or
memory-benefit benchmark. Every memory retrieval returned a versioned empty
snapshot.

## Registered execution

The runner scanned seeds 700--719 through the frozen five-condition cycle and
stopped after the first five failed initial rollouts. It did not inspect recovery
outcomes when selecting cases. Each operational case allowed at most two model
calls; the complete run allowed at most ten. Robot interaction was limited to
500 initial steps, 64 probe steps, and 500 reserved verification steps per case.

Exact commands:

```powershell
.\.venv\Scripts\python.exe scripts\generate_probemem_v2_manifest.py
.\scripts\run_probemem_v2_smoke.ps1 `
  -Manifest outputs\probemem_v2\runs\probemem_v2_smoke_20260731T082819Z_d11430b80e3f\manifest.json `
  -ApiTimeout 300
```

## Real result

- Collection units: 8 (seeds 700--707).
- Operational failed initial rollouts: 5.
- Initial successes requiring no adaptation: 3.
- GLM-5.2 API calls: 10.
- First-pass valid structured decisions: 0/5 (0%).
- Cases ending fail-closed in `ABSTAIN`: 5/5 (100%).
- Registered probes executed: 0.
- Fresh verification rollouts executed: 0.
- Invalid skills executed: 0.
- Interaction-budget overruns: 0.
- Total environment steps: 2,868.

The run completed its collection rule but is **NOT_PROMOTED**. `COMPLETED` in
`run_status.json` means collection finished; it does not mean the method passed.

## Failure analysis

The first responses commonly requested a diagnostic probe while also populating
fields that must be null for a probe request. Schema-repair responses then added
or omitted exact fields. The deterministic validator correctly rejected these
cross-field violations and prevented any physical action. This establishes
fail-closed behavior, but the 0% first-pass validity is below the registered 80%
promotion threshold.

The first runner retained response hashes and validation errors but not the text
of invalid responses. That is an audit limitation. The subsequent code revision
adds raw structured-response retention and explicit conditional schema rules;
because this changes the implementation, any new experiment must receive a new
commit, manifest, and run ID. The failed run remains unchanged.

## Interpretation

This result does not show that scientific memory helps recovery, nor that GLM-5.2
cannot use tools in general. It shows that the initial ProbeMem contract was not
sufficiently robust for this Anthropic-compatible endpoint under a ten-call
budget. The safety boundary worked: malformed reasoning produced abstention
rather than an unregistered action. Phase C verified episodic memory remains
blocked until a new development smoke passes the Phase-B gate.

The MetaWorld/Gymnasium observation-space and policy-clipping warnings were the
known upstream warnings seen in prior runs; they did not crash the environment.
