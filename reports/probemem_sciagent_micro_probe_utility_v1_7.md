# ProbeMem-SciAgent Micro-Probe Utility v1.7 Result

Status: `COMPLETED_GATE_FAILED`

Run ID: `probemem_sciagent_probe_utility_20260808T074324Z_4ff12cf4e451`

## Result

The frozen one-shot development run scanned 29 fresh initial units and reached
all 12 operational cases. It executed two Host-admitted compensation-response
micro-probes. Both post-probe decisions were certified and both retained the
pre-probe compensation skill. Consequently, the run produced zero probe-induced
action changes, zero helpful probes, zero harmful probes, and two
`NO_DECISION_BENEFIT` probes.

| Metric | Result |
|---|---:|
| Operational cases | 12 |
| Valid pre-probe outputs | 7/12 |
| Valid post-probe action outputs | 2/2 |
| Executed probes | 2 |
| Probe admission rate, all operational | 16.7% |
| Direct decisions among valid pre outputs | 4 |
| Robust-guard blocked probe requests | 1 |
| Helpful / harmful probes | 0 / 0 |
| No-decision-benefit probes | 2 |
| Integrity violations during causal execution | 0 |
| Memory/principle writes | 0 / 0 |
| Online recovery executions | 0 |

The interface gate also failed. Five of 12 pre-probe outputs failed closed,
leaving seven valid outputs against the frozen minimum of nine. Four external
210-second hard timeouts occurred. Two repair calls exhausted the repair budget;
later failures therefore failed closed, and the final operational case was
blocked by the circuit breaker. Two completed responses violated the value
certificate constraint that the provisional skill probability cannot be below
the alternative.

## Probe utility cases

In episode 003 (seed 6754), the compensation-response probe showed strong goal
alignment and preserved contact. The Agent selected compensation both before
and after the probe. Evaluator-only outcomes were compensation `ACCEPTED` and
retry `REJECTED`.

In episode 007 (seed 6766), the probe again showed strong alignment and
preserved contact. The Agent again retained compensation. Both evaluator-only
candidates were `ACCEPTED`. Neither case provides action-selection gain because
the probe did not change the persisted pre-probe action.

This is a sharper negative result than the earlier all-probe behavior: robust
value produced selective admission, but the admitted evidence was confirmatory
rather than decision-changing. It therefore added interaction without improving
the recovery-skill selection on either evaluated case.

## API cost and reporting correction

The run produced 16 actual API audit rows: 12 transport-valid completions and
four hard timeouts. Completed responses used 26,820 input and 60,885 output
tokens. Latency including timeout rows was 143.35 seconds at P50, 210.01 seconds
at P90, and 210.01 seconds maximum.

The immutable original summary reported zero hard timeouts because it matched
the Python exception class name `TimeoutExpired`, while the transport audit
stores the normalized text `TimeoutError: API hard deadline exceeded`. This
post-run reporting defect did not affect decisions, admission, utility labels,
or the already-failed gate. The original summary is preserved. A no-new-call
analysis records the corrected count of four, and the future summarizer now
uses the audited transport failure text with a regression test.

## Scientific interpretation

The experiment does not support promotion. It establishes that the complete
online sequence can safely execute a selectively admitted micro-probe, persist
a second decision before outcomes, and evaluate action utility without leakage.
It does not show that the probes improve action selection. The two admitted
probes only confirmed compensation choices that were already correct or tied.

The result argues against proceeding to scientific memory or principle
promotion. A future successor, if separately authorized, should investigate
whether probe admission predicts *decision-changing information* rather than
another calibration or response-format revision. It must use fresh seeds and
must not rerun this stream.

## Boundary

No online recovery action executed. Paired candidate outcomes were evaluator-
only and entered neither Agent payloads nor memory. No experience, hypothesis,
or principle was written. Seeds 6750--6849 cannot be rerun or extended, and
reserved seeds 6850--6949 remain blocked. This result supports no recovery,
online-learning, validation, held-out, VLA, RL, or principle claim.
