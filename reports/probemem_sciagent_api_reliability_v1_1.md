# ProbeMem-SciAgent API Reliability v1.1

Status: `IMPLEMENTED_NOT_EXECUTED`

This shadow-only successor adds evidence-grounding certificates, a no-environment
API health-check, canonical request fingerprints, validated-response caching, a
two-failure circuit breaker, and separate transport/schema/semantic audit.

No model action may execute, no memory or principle may be written, and no
recovery claim is permitted. Live execution requires configured GLM credentials,
a completely clean worktree, a committed immutable manifest, and fresh seeds
5850--5899. No seed in that range has been executed.

Current preflight on 2026-08-06 stopped before manifest generation because the
worktree contains an unrelated untracked `.vscode/` directory. Both
`ANTHROPIC_API_KEY` and `ANTHROPIC_BASE_URL` were also unset. This is an
infrastructure blocker, not an API-validity or recovery result; API calls,
initial units, and consumed fresh seeds remain zero.

## Registered shadow result

After confirming the existing DPAPI-protected local credential path and
committing an ignore rule for local editor state, immutable run
`probemem_sciagent_api_reliability_20260806T114419Z_768c2436390a` executed once.
It scanned 33 fresh initial units and reached the registered target of eight
operational shadow cases.

The health check passed after consuming the single global repair call. None of
the eight operational responses passed the complete certificate contract. The
first two operational cases failed closed, then the two-consecutive-failure
circuit breaker opened and prevented calls for the remaining six cases. The
run therefore ended `COMPLETED_GATE_FAILED` with:

```text
certified valid outputs: 0/8
grounded output rate: 0.0%
fail-closed outputs: 8/8
API calls: 4
actual repair API calls: 1
input tokens: 3,362
output tokens: 11,036
P50 latency: 45.6 s
P90 latency: 135.5 s
action executions: 0
memory writes: 0
principle updates: 0
integrity violations: 0
```

Three of four calls failed the strict transport parser because the response was
not one bare JSON object. The sole transport-valid response was the repaired
health-check response. This localizes the immediate API reliability bottleneck
to response-envelope conformance before action-grounding quality can be
evaluated. The generated `analysis.json` counts two output objects with a true
`repaired` pathway flag, while the authoritative call budget and API audit show
that only one repair request was actually sent; this reporting-semantic
discrepancy is retained rather than rewriting the registered result.

This failed run must not be rerun or replaced on seeds 5850--5899. A successor
requires a separately frozen fresh-seed protocol. A reasonable next question is
whether a deterministic, ambiguity-rejecting single-object envelope extractor
can improve transport validity without weakening the decision certificate or
adding repair calls. No recovery, online-learning, or action-selection benefit
is established by this shadow result.
