# ProbeMem-SciAgent v1 Demo

Status: `BLOCKED_MISSING_GLM_CREDENTIALS`

The implementation, tests, and corrected immutable execution manifest are
complete. Live execution stopped during credential preflight before any fresh
environment seed was consumed:

```text
run_id: probemem_sciagent_demo_20260806T031924Z_4ae5e0a72f8f
manifest_id: 54eb4a8655cd8869039a1178cadb2920428ce843c88a889c53641e28e1a9dfd8
initial_units: 0
operational_cases: 0
fresh_seed_consumed: false
GLM calls: 0
```

This is an execution blocker, not a recovery, probing, memory, or online-learning
result. Seeds 5300--5349 remain unexecuted. Historical ProbeMem Online, Verifier
Demo, and Calibrated Verifier results remain unchanged.

The engineering implementation uses three chronological memory layers, one
optional action-conditioned micro-probe, a mandatory post-probe decision, selected-
action-only experience writes, deterministic principle promotion, and fail-closed
GLM handling. Synthetic pathway audits are excluded from all research metrics.

An earlier manifest
`probemem_sciagent_demo_20260806T031748Z_7accad04fe79` was preserved as
`SUPERSEDED_PRE_EXECUTION_PROTOCOL_DEFECT`: its original runner required HEAD to
equal the pre-manifest source commit, which was incompatible with committing the
manifest. It consumed zero seeds. The corrected runner accepts only a
manifest-only descendant while still verifying every bound file hash.
