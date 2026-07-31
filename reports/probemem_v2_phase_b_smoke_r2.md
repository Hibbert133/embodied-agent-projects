# ProbeMem v2 Phase-B Tool Contract Smoke — Revision 2

Protocol: `online_llm_scientific_memory_v2`

Run: `probemem_v2_smoke_20260731T085550Z_582bb0cce256`

Manifest: `be444104ba57f29cbe01b6ffaf9cebfbd0b4a19a547799015fc1258aa3102c9b`

Source commit: `582bb0cce2566985d1cf547200a3e34027dd6766`

## Registered change

Revision 2 added explicit cross-field rules and retained raw model responses.
The case-selection rule, seeds, five perturbation conditions, robot budgets,
empty memory snapshot, tool set, skill set, and ten-call cap were unchanged.

## Real result

- Collection units: 8; operational failures: 5; initial successes: 3.
- API calls: 10.
- First-pass valid structured decisions: 1/5 (20%).
- Operational cases that executed the registered 64-step probe: 4/5.
- Fresh verification rollouts: 0.
- Cases ending fail-closed in `ABSTAIN`: 5/5.
- Invalid skills executed: 0; budget overruns: 0.
- Total environment steps: 3,124.
- Promotion status: **NOT_PROMOTED**.

## What changed scientifically

Unlike Revision 1, the online Agent successfully invoked a real diagnostic tool
in four operational cases. This is evidence that the constrained active-tool
path is executable. It is not evidence of recovery benefit because no case
reached fresh verification.

Raw-response audit identified a protocol-level inefficiency. Four first
responses omitted `schema_version`, even though their substantive probe decision
was otherwise well formed. The repair call then consumed the second and final
API call, leaving no call for post-probe belief update. Provenance fields are
known deterministically by the host and should not consume model reasoning
capacity. The next implementation therefore moves schema version and decision,
evidence, and memory-snapshot IDs into a host-owned envelope while keeping the
semantic model body strict.

One post-probe response selected bounded compensation but returned an unsupported
verification-status value (`verified`). The validator rejected it. Enum
validation remains strict; the host-envelope change does not weaken this safety
boundary.

## Decision

Revision 2 fails the 80% first-pass validity and fresh-verification gates. Phase C
remains blocked. A third, new-manifest Phase-B run may test the host-owned
provenance envelope; it must not overwrite either earlier negative run.
