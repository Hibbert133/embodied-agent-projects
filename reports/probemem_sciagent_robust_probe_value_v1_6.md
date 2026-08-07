# ProbeMem-SciAgent Robust Probe Value v1.6 Result

Status: `COMPLETED_GATE_FAILED_INTEGRITY`

Run ID: `probemem_sciagent_robust_value_20260807T033154Z_fb9d976ac5ce`

## Result

The frozen run completed eight operational shadow cases and all ten allowed API
calls. Seven of eight operational outputs were fully certified. The external
wall-clock mechanism terminated two calls at 210 seconds; the first was
recovered by the single permitted repair, while the second failed closed.

The robust value behavior met every numerical method threshold: two of eight
cases admitted a probe, five produced valid rejected assessments, call rate was
25%, and only one operational output failed closed. Four rejections arose
because the Agent selected a non-probe mode. In one additional case the Agent
requested a probe but the Host rejected it because robust lower-bound value did
not exceed cost.

| Reconstructed metric | Result |
|---|---:|
| Operational cases | 8 |
| Fully certified outputs | 7/8 |
| API calls | 10 |
| Hard-deadline timeouts | 2 |
| Repairs | 1 |
| Current-case valid value assessments | 7 |
| Probe admissions | 2 |
| Probe rejections | 5 |
| Admission rate | 25% |
| Agent non-probe decisions | 4 |
| Robust-guard blocked requests | 1 |
| Action executions | 0 |
| Memory/principle writes | 0 |

Completed responses used 17,622 input and 48,450 output tokens. Latency was
175.29 seconds at P50 and 210.00 seconds at P90, including hard timeouts.

## Why the formal gate failed

After all environment and API interaction completed, the runner crashed while
building its summary. Timeout audit rows omitted a probe-contract boolean, and
the summary attempted to add `None` inside a `sum`. A second audit bug attached
the previous case's valid assessment to the later timeout output because the
lookup searched the full audit history rather than only rows created by the
current request.

No model action used the stale assessment, but it is still an audit association
integrity violation. The original `run_status.json` is preserved as `FAILED`.
A deterministic no-new-call reconstruction removes the stale assessment and
shows that the method thresholds would otherwise pass. Because the frozen gate
requires zero integrity violations, the formal result is failure, not passage.

The runner is now corrected to bind assessments to the current call's audit
slice and to coerce optional audit booleans before aggregation. Regression tests
cover both defects. Seeds 6600--6649 are not rerun.

## Scientific interpretation

Two conclusions survive the integrity failure:

1. a child-process hard deadline successfully restored bounded API behavior;
2. robust ambiguity and lower-bound value produced selective probe behavior,
   including one Host-blocked probe request, instead of v1.3's all-probe pattern.

These are interface and mechanism observations only. Probe outcomes were not
executed, so there is no evidence that either admission was helpful or that the
blocked request would have been harmful. Recovery, calibrated probe utility,
memory, principles, validation, and held-out claims remain unauthorized.

## Boundary

No probe, recovery action, paired candidate, memory update, or principle update
executed. All earlier reserves and seeds 6650--6749 remain blocked. Any successor
requires a separately frozen protocol and must evaluate actual probe utility
without treating this audit-failed run as a passed promotion gate.
