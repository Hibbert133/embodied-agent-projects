# ProbeMem-SciAgent Distributional Probe Identifiability v1.8 Result

Status: `COMPLETED_GATE_FAILED`

Run ID: `probemem_sciagent_probe_identifiability_20260811T035724Z_045ccee8041f`

## Result

The frozen evaluator-only audit scanned 73 fresh initial units and completed
all 30 operational states. For every state it persisted both registered probe
records before collecting four independent paired verification realizations
for compensation and retry. All integrity counters were zero.

The promotion gate failed:

| Metric | Result | Frozen requirement |
|---|---:|---:|
| Operational cases | 30 | 30 |
| Distributionally decisive cases | 9 | >= 12 |
| Compensation-superior / retry-superior | 6 / 3 | each >= 4 |
| Probe-contrast ROC AUC | 0.778 | >= 0.75 |
| Stratified bootstrap AUC 95% interval | [0.389, 1.000] | lower > 0.50 |
| Spearman contrast vs utility margin | 0.170 | >= 0.30 |
| Integrity violations | 0 | 0 |

The point AUC exceeded its threshold, but it was estimated from only nine
decisive states, missed the minimum retry-superior population, had a bootstrap
interval spanning chance, and did not correlate sufficiently with the utility
margin over the complete population. It is therefore not an actionable probe
allocation signal.

## Distributional evidence

Twenty-one of 30 states were non-decisive after four realizations per action.
Ten states exhibited a within-state candidate-winner reversal across the four
paired realizations. This independently reinforces the earlier finding that a
single candidate outcome is an unstable action label.

Across all 120 realizations per skill, compensation was accepted 78 times and
retry 73 times. Mean per-state acceptance rates were 0.650 and 0.608. The small
aggregate difference and high non-decisive prevalence leave little stable
action contrast for a probe to identify.

The frozen probe contrast was also sparse: compensation support was exactly
zero in 12/30 states, primarily because the registered contact-preservation
term failed, while retry support was zero in 2/30. Contrast ranged from -1.000
to 0.733 with median -0.218. No alternate coefficients, transformations, or
thresholds were evaluated.

## Cost and integrity

The audit used 86,184 evaluator environment steps, including 7,585 micro-probe
steps and 61,679 candidate-verification steps. These are research collection
costs, not deployed online interaction costs.

Exactly 30 probe pairs, 30 distributional case records, and 240 candidate
outcomes were recorded. Probe records were persisted before outcomes. Each
realization used the same random seed for compensation and retry. Agent payload,
API, online recovery, memory, hypothesis, and principle artifacts remained
empty. Chronology, leakage, pairing, budget, and identifier violations were all
zero.

## Scientific interpretation

The registered probes show a weak descriptive rank signal on a small decisive
subset, but they do not provide sufficiently stable or broadly applicable
information about action-outcome distributions. This explains why v1.7's two
admitted probes were confirmatory: most states do not have a large stable
utility difference to reveal, and the frozen evidence contrast is only weakly
related to the distributional margin.

The result does not justify restoring online API calls, fitting a probe score,
or starting scientific memory and principle promotion. Any future successor
must change the causal evidence design rather than retune this contrast—for
example, first establish a persistent action-response signal across independent
probe realizations under a separately frozen evaluator protocol.

## Boundary

Seeds 6950--7099 cannot be rerun, extended, or used to fit another score.
Reserved seeds 7100--7199 remain blocked. No recovery, Agent performance,
online-learning, memory, principle, validation, held-out, VLA, or RL claim is
supported.
