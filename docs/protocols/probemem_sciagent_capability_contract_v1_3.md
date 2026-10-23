# ProbeMem-SciAgent Capability Contract v1.3

Status: `SHADOW_FROZEN_BEFORE_EXECUTION`

## Question

API Envelope v1.2 made all observed calls transport-valid, but semantic
validation failed first on an unknown probe-justification code because the
payload did not enumerate registered values. This successor asks only whether a
complete per-request capability-token contract improves fully certified output
validity without weakening any existing host validator.

The v1.1 and v1.2 runs are immutable. Seeds 5900--5999 and 6050--6149 remain
reserved. This protocol may scan fresh development seeds 6150--6199 once;
6200--6299 remain reserved.

## Frozen change

The Host supplies a complete symbol table on every request. Static namespaces
enumerate decision modes, skills, probes, probe-justification codes,
certificate bases, and grounding claims. Dynamic namespaces assign request-
local tokens to the current evidence and to every allowlisted principle,
experience, hypothesis, and probe record. The model must return tokens in every
listed enum or ID field. The Host expands known tokens to canonical values and
then runs the unchanged SciAgent schema, chronology, ID, skill, and grounding-
certificate validators.

Unknown tokens, canonical strings in token-only fields, tokens from another
request, incomplete namespaces, duplicate mappings, and illegal nulls fail
closed. Free-text summaries have no execution authority. The v1.2 unique-object
envelope extractor remains frozen.

The model, system prompt, compact evidence, decision and certificate fields,
mandatory repeated probe, empty-memory condition, temperature, token limit,
repair budget, circuit breaker, population target, and success thresholds are
unchanged from v1.2. Capability-token disclosure is the only method variable.

## Population, budget, gate, and claims

After one synthetic health check, scan at most 50 initial units until eight
operational failures are collected. The immutable budget is nine primary calls,
one global repair, ten total calls, and zero transport retries. Model decisions
do not execute and cannot write memory or principles.

Passing requires a valid health check, eight operational payloads, at least
seven fully certified outputs, grounded-output rate at least 0.875, at most one
fail-closed output, at most one actual repair API call, and zero integrity
violations. Passing authorizes only a separately frozen future online-execution
protocol. Failure is preserved without rerunning these seeds, changing tokens,
or weakening validation. No recovery or online-learning claim is permitted.
