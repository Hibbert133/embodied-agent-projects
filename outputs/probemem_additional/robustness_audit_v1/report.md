# Additional-experiment robustness audit

Post-hoc analysis only; no new rollout, API call, memory replay, or promotion.

- experiment_run_id: `probemem_additional_ablation_20260901T031926Z_4f9fd0b4556c`
- manifest_id: `759c9586f88d5bff43380b67e2bdae1931cd24e3bd57c726643e95510c6fc80f`
- source_git_commit: `4f9fd0b4556c11c0b730ccef787bff4beee977d1`

## Paired binary recovery

Wins/losses mean gaining/losing ACCEPTED recovery; they differ from ordinal transfer labels.

| Left minus right | Population | N | Win / tie / loss | Difference (pp) | Exact p reference |
|---|---|---:|---:|---:|---:|
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | all | 60 | 4 / 56 / 0 | +6.67 | 0.1250 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | stable_bias | 52 | 1 / 51 / 0 | +1.92 | 1.0000 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | stochastic_noise | 8 | 3 / 5 / 0 | +37.50 | 0.2500 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | fault_01 | 9 | 1 / 8 / 0 | +11.11 | 1.0000 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | fault_02 | 9 | 0 / 9 / 0 | +0.00 | 1.0000 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | fault_03 | 15 | 0 / 15 / 0 | +0.00 | 1.0000 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | fault_04 | 19 | 0 / 19 / 0 | +0.00 | 1.0000 |
| EVIDENCE_ACQUISITION_ENABLED − BASELINE | fault_05 | 8 | 3 / 5 / 0 | +37.50 | 0.2500 |
| MEMORY_ONLY − BASELINE | all | 60 | 1 / 59 / 0 | +1.67 | 1.0000 |
| MEMORY_ONLY − BASELINE | stable_bias | 52 | 1 / 51 / 0 | +1.92 | 1.0000 |
| MEMORY_ONLY − BASELINE | stochastic_noise | 8 | 0 / 8 / 0 | +0.00 | 1.0000 |
| MEMORY_ONLY − BASELINE | fault_01 | 9 | 1 / 8 / 0 | +11.11 | 1.0000 |
| MEMORY_ONLY − BASELINE | fault_02 | 9 | 0 / 9 / 0 | +0.00 | 1.0000 |
| MEMORY_ONLY − BASELINE | fault_03 | 15 | 0 / 15 / 0 | +0.00 | 1.0000 |
| MEMORY_ONLY − BASELINE | fault_04 | 19 | 0 / 19 / 0 | +0.00 | 1.0000 |
| MEMORY_ONLY − BASELINE | fault_05 | 8 | 0 / 8 / 0 | +0.00 | 1.0000 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | all | 60 | 1 / 55 / 4 | -5.00 | 0.3750 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | stable_bias | 52 | 1 / 51 / 0 | +1.92 | 1.0000 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | stochastic_noise | 8 | 0 / 4 / 4 | -50.00 | 0.1250 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | fault_01 | 9 | 1 / 8 / 0 | +11.11 | 1.0000 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | fault_02 | 9 | 0 / 9 / 0 | +0.00 | 1.0000 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | fault_03 | 15 | 0 / 15 / 0 | +0.00 | 1.0000 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | fault_04 | 19 | 0 / 19 / 0 | +0.00 | 1.0000 |
| PROBE_MEMORY − EVIDENCE_ACQUISITION_ENABLED | fault_05 | 8 | 0 / 4 / 4 | -50.00 | 0.1250 |
| FULL_PROBEMEM − PROBE_MEMORY | all | 60 | 0 / 60 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | stable_bias | 52 | 0 / 52 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | stochastic_noise | 8 | 0 / 8 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | fault_01 | 9 | 0 / 9 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | fault_02 | 9 | 0 / 9 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | fault_03 | 15 | 0 / 15 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | fault_04 | 19 | 0 / 19 / 0 | +0.00 | 1.0000 |
| FULL_PROBEMEM − PROBE_MEMORY | fault_05 | 8 | 0 / 8 / 0 | +0.00 | 1.0000 |

## Frozen-action realization sensitivity

Realization 0 is the registered primary result. Later realizations are evaluator-only.

| Method | Accepted r0 / r1 / r2 / r3 | Mean acceptance | Nonexecuted states |
|---|---|---:|---:|
| BASELINE | 51 / 54 / 52 / 51 | 86.7% | 2 |
| MEMORY_ONLY | 52 / 54 / 53 / 53 | 88.3% | 3 |
| EVIDENCE_ACQUISITION_ENABLED | 55 / 57 / 53 / 52 | 90.4% | 1 |
| PROBE_MEMORY | 52 / 55 / 56 / 55 | 90.8% | 1 |
| FULL_PROBEMEM | 52 / 55 / 56 / 55 | 90.8% | 1 |

## Interpretation limits

- Exact discordance p-values are exploratory reference calculations, not new promotion gates.
- Chronological memory induces dependence; episode-wise bootstrap and binomial references do not establish policy-level uncertainty.
- Four realizations reuse fixed decisions from the original memory history; this is not a replay of four online policies or 240 independent states.
- Blank-skill, zero-step REJECTED records are nonexecuted plan failures, retained in the denominator, not physical verification trials.
- Zero observed paired differences do not establish equivalence or a zero population effect.
- Strata are evaluator-only, post-hoc, small, and unadjusted for multiple comparisons.

Input SHA-256 hashes and unchanged historical bootstrap intervals are in `audit.json`.
