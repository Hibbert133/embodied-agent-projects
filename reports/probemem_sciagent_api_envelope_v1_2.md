# ProbeMem-SciAgent API Envelope v1.2

Status: `COMPLETED_GATE_FAILED`

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

## Registered result

Immutable run `probemem_sciagent_api_envelope_20260806T115659Z_372dc823e8e9`
executed once. It scanned 13 initial units and reached eight operational shadow
cases. The health check passed on its primary call without repair.

```text
status: COMPLETED_GATE_FAILED
certified valid outputs: 0/8
transport-valid API calls: 4/4
bare JSON calls: 1
wrapped unique JSON calls: 3
actual repair API calls: 1
API calls: 4
input tokens: 3,801
output tokens: 11,294
P50 latency: 74.8 s
P90 latency: 81.5 s
action executions: 0
memory writes: 0
integrity violations: 0
```

The envelope intervention removed the registered v1.1 transport bottleneck:
all four calls yielded exactly one extractable certified object, including
three wrapped responses. It did not make those objects semantically valid. The
first operational case failed both primary and repair validation with `unknown
probe justification`; the second then exhausted the already-used global repair
budget, and the two-failure circuit breaker prevented six further calls.

Failure localization found an interface under-specification: the response
schema says `registered codes` for `probe_justification_codes` but does not
enumerate the five registered values. The model therefore has no complete
copyable symbol table for that required enum. This is evidence for a distinct
future interface question, not permission to patch and rerun this stream. A
successor should preregister a capability-tokenized contract that supplies
exact allowed symbols for skills, modes, probes, justification codes, evidence
IDs, and memory IDs, while retaining the full host certificate checks.

Seeds 6000--6049 must not be rerun or used to tune that successor, and reserved
seeds 6050--6149 remain unexecuted. This shadow result supports a transport
validity mechanism claim only; it provides no recovery or action-quality claim.
