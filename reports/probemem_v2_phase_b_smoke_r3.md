# ProbeMem v2 Phase-B Host-Envelope Smoke — Revision 3

Protocol: `online_llm_scientific_memory_v2`

Run: `probemem_v2_smoke_20260731T090445Z_1cd7978961a2`

Manifest: `39972eb7563ea3742dfd9600d6e242cf72ca1776ded2aeb367bea8c5cc893c98`

Source commit: `1cd7978961a27bbf02fe7a5f3b26d6f3aae81865`

## Registered change

Revision 3 moved schema version and decision/evidence/memory provenance into a
host-owned envelope. The semantic model body, exact-field validation, leakage
boundary, case selection, seeds, physical budgets, tool set, and skill set were
not relaxed.

## Real result

- Collection units: 8; operational failures: 5; initial successes: 3.
- API calls: 10.
- First-pass valid structured decisions: 5/5 (100%).
- Registered probes: 5/5 operational cases, 64 steps each.
- Valid post-probe intervention decisions: 0/5.
- Fresh verification rollouts: 0.
- Cases safely ending in `ABSTAIN`: 5/5.
- Invalid skills executed: 0; budget overruns: 0.
- Promotion status: **NOT_PROMOTED**.

## Interpretation

The host-owned envelope removed the format bottleneck without weakening the
semantic decision contract. Every initial decision now validly requested the
registered probe, so the attempt-level active evidence loop is reproducibly
executable.

All five post-probe responses selected a plausible bounded intervention, most
often `BOUNDED_PLANAR_COMPENSATION`, and explained it using repeated visible
probe consistency. They nevertheless failed strict predicted-outcome validation:
the model invented statuses such as `pending` or `stable_bias_compensated`, and
one response used qualitative text where numeric progress was required. No
intervention was executed.

This is a useful interface result: tool selection and physical reasoning can be
semantically plausible while the machine contract remains unsafe to execute.
The next development revision adds one state-specific valid response example and
repeats the allowed uppercase verification enum. It does not map invalid aliases
or silently coerce values, preserving fail-closed evaluation.

Phase C remains blocked until a new run reaches fresh verification and passes
the registered promotion evaluator.
