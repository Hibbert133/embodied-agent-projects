# Reset-resource sensitivity audit

Read-only accounting of a completed simulator experiment. No new episodes or method decisions.

Run: `evidence_refresh_20261013T092539Z_ac3fa90f6d20`.

| Method | Success / 96 | Charged probe steps | Charged direction resets | Mean task + probe steps | Mean extra direction resets |
|---|---:|---:|---:|---:|---:|
| CHANGE_THRESHOLD | 89 | 4896 | 1224 | 146.06 | 12.75 |
| DECISION_STABILITY | 87 | 3568 | 892 | 141.41 | 9.29 |
| FIXED_16 | 88 | 1536 | 384 | 116.93 | 4.00 |
| FIXED_32 | 88 | 3072 | 768 | 131.89 | 8.00 |
| FIXED_64 | 88 | 6144 | 1536 | 163.56 | 16.00 |
| PERIODIC_4 | 71 | 1536 | 384 | 194.41 | 4.00 |
| STALE | 71 | 512 | 128 | 183.53 | 1.33 |
| UNCORRECTED | 41 | 0 | 0 | 333.27 | 0.00 |

Let R >= 0 be a common reset cost in environment-step equivalents. Omitting a common task-start reset,
cost(method,R) = mean(task steps + probe steps) + R * mean(extra directional resets).

Candidate minus fixed-16 cost = 24.4792 + 5.2917 R. The candidate has one fewer success.
Thus adding any nonnegative uniform reset cost cannot rescue this candidate's observed dominance failure.

Explicit physical collection resets: `{'initial_state_inspections': 96, 'direction_probes': 1536, 'task_branches': 332, 'total': 1964}`.

Source-derived explicit reset calls, not measured robot time; internal constructor work excluded.
This is a sensitivity model, not measured latency, energy, human intervention, or a real-robot cost estimate.
Each repetition has four directional starts; each method episode has one task start afterward, common to every method.
A true continuous probe needs different transitions and cannot be simulated by subtracting resets from these logs.
