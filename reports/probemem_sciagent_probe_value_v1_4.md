# ProbeMem-SciAgent Probe Value v1.4 Result

Status: `COMPLETED_GATE_FAILED`

Run ID: `probemem_sciagent_probe_value_20260807T014800Z_cda27b82ce4d`

Manifest ID: `bac62ade5400da10cd82a8ce4f815816179533a02fdcce4ae63042f771b50a8a`

Source implementation commit: `cda27b82ce4d`

## Result

The frozen shadow run scanned 31 initial units from seeds 6300--6349 and
obtained eight operational failures. The health check passed. The Probe Value
gate failed: zero operational outputs passed the complete semantic certificate,
and no valid probe-value assessment was produced.

| Metric | Result |
|---|---:|
| Operational cases | 8 |
| API calls | 4 |
| Transport-valid calls | 4/4 |
| Capability-valid calls | 4/4 |
| Valid operational decisions | 0/8 |
| Valid probe-value certificates | 0 |
| Invalid probe-value calls | 3 |
| Schema repairs | 1 |
| Circuit breaker open | yes |
| Action executions | 0 |
| Memory writes | 0 |
| Principle updates | 0 |
| Integrity violations | 0 |

The API used 7,381 input tokens and 21,871 output tokens. Call latency was
102.70 seconds at P50 and 254.71 seconds at P90. These include the health check
and the three operational attempts that reached the API.

## Failure localization

The health check remained valid under the v1.3 capability-token interface. On
the first operational case, the primary response passed unique-object transport
extraction and capability expansion but did not provide an object-valued probe-
value certificate. The one permitted repair produced a certificate object, but
its provisional selected skill did not equal the argmax of its own current
candidate probabilities. The second operational API response again omitted an
object-valued probe-value certificate. This was the second consecutive logical
failure, so the frozen circuit breaker prevented calls for the remaining six
operational cases.

This isolates a new interface limit: complete enum/capability disclosure was
sufficient for the v1.3 categorical decision contract, but it did not make the
richer numerical, cross-field EVSI contract reliable. The failure is not
evidence that active probes lack value. No valid EVSI estimate existed, so the
observed zero admission rate is a fail-closed artifact and must not be treated
as budgeted-probe behavior.

## Scientific interpretation

The result strengthens the distinction between three levels of API success:

1. transport validity;
2. categorical semantic validity;
3. numerical and counterfactual coherence across multiple fields.

v1.3 passed levels 1 and 2. v1.4 retained those properties on every observed
call but failed level 3. Increasing output complexity also raised cost: the
single repair response used 9,649 output tokens and took 254.71 seconds, without
becoming coherent.

A successor, if separately authorized on fresh seeds, should test a smaller
quantized value language rather than weakening host validation. One candidate
is a per-request capability lattice for probabilities and branch effects, with
all arithmetic, normalization, argmax, cost comparison, and admission retained
by the Host. It should first pass a no-environment contract suite and a fresh
shadow gate. It must not derive an executable action from invalid or incomplete
model output, and it cannot reuse seeds 6300--6349.

## Claim boundary

This run supports only a negative interface result. It provides no robot action,
recovery, memory, principle, online-learning, validation, or held-out evidence.
Seeds 6300--6349 will not be rerun or used to change the frozen v1.4 contract.
Seeds 6200--6299 and 6350--6449 remain unexecuted reserves.
