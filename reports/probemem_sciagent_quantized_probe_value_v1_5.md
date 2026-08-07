# ProbeMem-SciAgent Quantized Probe Value v1.5 Result

Status: `INCOMPLETE_TRANSPORT_TIMEOUT_ENFORCEMENT`

Run ID: `probemem_sciagent_quantized_value_20260807T030613Z_f107da6cbd56`

Source implementation commit: `f107da6cbd56`

## Result

The one-shot shadow run was stopped when an operational API request remained
in flight beyond the frozen 300-second SDK timeout. Continuing would have
violated the bounded-cost protocol. The partial run is immutable and its gate
is not evaluated.

Seven initial trajectory files were created. Four operational requests were
started; three produced output records and the fourth was terminated without a
response. Including the health check and one repair, six API calls were started
and five have completed audit records.

| Partial metric | Result |
|---|---:|
| Completed operational outputs | 3 |
| Fully certified operational outputs | 2/3 |
| Completed API audit rows | 5 |
| Transport-valid completed calls | 5/5 |
| Capability-valid completed calls | 5/5 |
| Valid quantized value responses | 3/4 operational responses |
| Invalid quantized value responses | 1/4 operational responses |
| Repairs | 1 |
| In-flight calls terminated | 1 |
| Valid value assessments admitted | 3/3 |
| Valid value assessments rejected | 0/3 |
| Action executions | 0 |
| Memory or principle writes | 0 |
| Integrity violations | 0 |

Completed audit records used 10,294 input tokens and 27,511 output tokens.
Their latency was 124.60 seconds at P50 and 186.98 seconds at P90. Usage and
latency for the terminated in-flight request are unavailable.

## Failure localization

The quantized probability language materially improved the narrow numerical
interface compared with v1.4. Three of four returned operational responses
passed the quantized value validator. The remaining primary response assigned a
lower probability to its provisional skill than to its alternative. Its repair
passed the quantized value validator, but the ordinary decision grounding
certificate then had missing or extra fields, so that operational decision
still failed closed.

The run nevertheless cannot pass or fail the preregistered gate because it did
not reach eight operational outputs. More importantly, all three valid partial
value assessments admitted the proposed compensation probe. Thus the partial
trace does not show the required budgeted rejection behavior even though value-
schema validity improved.

This separates two unresolved problems:

1. the quantized language improves numerical and cross-branch coherence;
2. the compatible API transport does not reliably enforce the configured
   timeout, and the model still assigns high value to every observed probe.

The second point prevents an online API-success claim. Interface validity alone
does not establish calibrated value of information.

## Boundary

No proposed probe, provisional recovery skill, or continuous action executed.
No outcome, memory record, hypothesis, or principle was written. Seeds
6450--6499 must not be rerun or completed, and reserved seeds 6200--6299,
6350--6449, and 6500--6599 remain blocked. A successor requires a new protocol;
it must first enforce a wall-clock deadline outside the compatibility SDK and
must change the scientific question beyond another formatting repair.
