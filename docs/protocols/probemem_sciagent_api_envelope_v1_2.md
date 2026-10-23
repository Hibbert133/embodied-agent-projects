# ProbeMem-SciAgent API Envelope v1.2

Status: `SHADOW_FROZEN_BEFORE_EXECUTION`

## Question

The v1.1 shadow gate failed before semantic action evaluation because three of
four API calls were not bare JSON. This successor asks only whether a
deterministic unique-object envelope extractor improves certified transport
validity without weakening the existing decision schema, grounding
certificate, ID allowlists, circuit breaker, or API budget.

The v1.1 run and seeds 5850--5899 are immutable. Seeds 5900--5999 remain
reserved. This protocol may scan fresh development seeds 6000--6049 once;
6050--6149 remain reserved.

## Frozen change

The only method change is response-envelope parsing. Bare JSON is accepted as
before. Otherwise the host scans the complete response and accepts it only if
there is exactly one unique JSON object whose top-level keys are exactly
`decision` and `certificate`. Markdown or reasoning text has no authority and
is never interpreted as an action. Zero objects, two distinct certified
objects, malformed JSON, schema errors, ID errors, or certificate errors fail
closed. The parser records `BARE_JSON`, `WRAPPED_UNIQUE_JSON`, or `REJECTED`.

The GLM model, prompt, decision schema, certificate, compact evidence,
mandatory repeated probe, memory-empty condition, action registry, temperature,
token limit, call budget, repair budget, circuit breaker, population target,
and promotion thresholds remain unchanged from v1.1.

## Population, budget, and gate

After one synthetic health check, scan at most 50 initial units until eight
operational failures are collected. No model decision executes. The immutable
budget is nine primary calls, one global repair, ten total calls, and zero
transport retries.

Passing requires a valid health check, eight operational payloads, at least
seven fully certified outputs, grounded-output rate at least 0.875, at most one
fail-closed output, at most one actual repair API call, and zero integrity
violations. Transport-valid but certificate-invalid outputs remain invalid.

Passing authorizes only a separately frozen future online-execution protocol.
Failure is retained without rerunning these seeds or relaxing the unique-object
or certificate rules. No recovery, memory, principle, or online-learning claim
is permitted.
