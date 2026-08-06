# ProbeMem-SciAgent API Envelope v1.2

Status: `IMPLEMENTED_NOT_EXECUTED`

This fresh-seed, shadow-only successor changes only response-envelope parsing.
It accepts a non-bare response only when the complete response contains exactly
one unique object with top-level keys `decision` and `certificate`. All existing
schema, evidence-binding, memory-ID, skill, circuit-breaker, and no-execution
guards remain active.

The immutable v1.1 failure localized three of four calls to non-bare JSON. This
v1.2 protocol tests whether safe envelope normalization removes that transport
bottleneck; it does not assume semantic certificates will pass afterward and it
does not test recovery success. Execution requires a committed implementation,
a clean worktree, and a separately committed immutable manifest for fresh seeds
6000--6049.
