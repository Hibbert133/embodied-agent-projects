# ProbeMem-SciAgent Capability Contract v1.3

Status: `COMPLETED_GATE_PASSED`

This fresh-seed shadow successor supplies complete request-local capability
tokens for every constrained enum and reference field. Host expansion occurs
before the unchanged SciAgent decision and grounding-certificate validators.
It tests structured semantic validity only; it cannot establish recovery,
action quality, memory benefit, or online learning.

## Registered result

Immutable run `probemem_sciagent_capability_20260806T142111Z_14010335fc33`
executed once on fresh seeds 6150--6199. It scanned 18 initial units and reached
the registered target of eight operational shadow cases.

```text
status: COMPLETED_GATE_PASSED
certified valid outputs: 8/8
grounded output rate: 100%
transport-valid API calls: 9/9
capability-valid API calls: 9/9
capability-invalid API calls: 0
wrapped unique JSON calls: 9
actual repair API calls: 0
API calls: 9
input tokens: 14,764
output tokens: 36,515
P50 latency: 96.4 s
P90 latency: 149.5 s
action executions: 0
memory writes: 0
principle updates: 0
integrity violations: 0
```

This passes the preregistered interface gate and localizes the v1.2 semantic
failure: complete request-local capability tokens removed unknown enum and ID
generation without relaxing the original SciAgent decision or grounding-
certificate validators. The unique-envelope layer also remained necessary,
because all nine responses were wrapped rather than bare JSON.

## Decision-behavior audit

All eight operational decisions selected `RUN_MICRO_PROBE`. Five requested
`COMPENSATION_RESPONSE_PROBE` with provisional compensation, and three requested
`RETRY_REPEATABILITY_PROBE` with provisional retry. Grounding claims were four
`ACTION_UTILITY_UNCERTAIN`, three `RESPONSE_VARIABILITY_SUPPORTS_RETRY`, and one
`REPEATED_RESPONSE_SUPPORTS_COMPENSATION`.

This is a valid structured interface but a 100% shadow probe-request rate. It
does not demonstrate budgeted probe allocation, action quality, or recovery.
Under the current GLM qualitative-pilot boundary, model decisions remain
non-executing. Any online successor must be separately frozen and must evaluate
whether a requested action-conditioned probe supplies a preregistered missing
utility statistic under the case budget; interface validity alone is
insufficient to authorize execution.

Seeds 6150--6199 must not be rerun or used to tune the token table. Seeds
6200--6299 remain unexecuted and reserved.
