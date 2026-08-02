# ProbeMem-ACR: Second-Verification Allocation Development v1

## Research question

Can the Agent-visible result of one fresh retry determine whether a second
recovery attempt is worth its cost and whether that attempt should repeat retry
or switch to bounded compensation? This is a development-only attempt-level
feedback study. It is not an LLM, memory, validation, held-out, or online-
learning result.

## Frozen execution

- source commit: `af2acb3b380b498fbf1f2853b5ec42f53035e95f`;
- run: `acr_resonance_20260802T142610Z_af2acb3b380b`;
- manifest: `747da99f8929aa9c17159c4af220ee5afdfab4ca93866d673bf778debd5ca839`;
- condition: registered `fault_05`;
- scanned seeds: 2850--3000 in chronological order;
- initial units scanned: 151;
- eligible initial failures receiving the fixed first retry: 75;
- first retry accepted: 45;
- registered second-decision population: 30;
- evaluator-only paired second rollouts: 60.

The stopping rule read the first retry status but never the second candidate
outcomes. First and second verification streams were independent. Both second
candidates used the same paired stream and independent environment resets.
There were zero chronology, Oracle-leakage, namespace, budget, or attempt-limit
violations. No API was called.

## Results

| Method | Accepted | Incremental recoveries | Second attempts | Harmful selections | Mean online steps |
|---|---:|---:|---:|---:|---:|
| Single retry | 45/75 (60.0%) | 0 | 0 | 0 | 836.68 |
| Always repeat retry | 63/75 (84.0%) | 18 | 30 | 7 | 941.48 |
| Always switch compensation | 61/75 (81.3%) | 16 | 30 | 9 | 961.75 |
| Status-conditioned | 65/75 (86.7%) | 20 | 30 | 5 | 935.51 |
| Reject-to-abstain | 55/75 (73.3%) | 10 | 14 | 2 | 877.40 |
| Per-case Oracle audit | 70/75 (93.3%) | 25 | 30 | 0 | 908.53 |

The status-conditioned rule repeats retry after an `INCONCLUSIVE` first result
and switches to compensation after `REJECTED`. It exceeded the strongest fixed
second policy by two accepted cases, had five paired wins, three paired losses,
and 67 ties, while consuming 448 fewer total online environment steps. The
paired-bootstrap accepted-rate difference was +2.67 percentage points with a
95% interval of [-4.0, +10.67], so the uncertainty still includes no effect.

Relative to the single retry, status conditioning spent 7,412 additional steps
for 20 additional recoveries (370.6 steps per added recovery). Always repeat
spent 7,860 additional steps for 18 recoveries (436.7 per added recovery).

Reject-to-abstain cut second attempts by 53.3% relative to always repeat, but
lost eight accepted recoveries and missed 13 recoverable cases. Its cost saving
therefore failed the frozen utility gate.

## Interpretation

The preregistered status-conditioned route passed its development gate. This is
a feasibility signal that fresh verification feedback can cross the
reasoning-to-action boundary: it changes the second intervention and slightly
improves both recovery count and interaction cost over either fixed second
action. It does not establish generalization because the confidence interval
crosses zero and all data come from one development condition.

The result also narrows the next research hypothesis. Static state similarity
and contextual posterior models failed in earlier ACR studies, while a causal
outcome from an executed verification provides a more useful evidence source.
Any successor must freeze a separate validation protocol; it must not retune
this status rule on seeds 2850--3049.

## Artifact paths

- raw run: `outputs/probemem_acr/resonance_runs/acr_resonance_20260802T142610Z_af2acb3b380b/`;
- figure: `outputs/probemem_acr/figures/acr_resonance_second_verification_development_v1.png`;
- frozen protocol: `docs/protocols/probemem_acr_resonance_second_verification_development_v1.md`.
