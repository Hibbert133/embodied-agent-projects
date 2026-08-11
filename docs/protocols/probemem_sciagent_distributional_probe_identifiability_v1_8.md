# ProbeMem-SciAgent Distributional Probe Identifiability v1.8

Status: `DEVELOPMENT_FROZEN_BEFORE_EXECUTION`

## Question

Micro-Probe Utility v1.7 executed two selectively admitted probes, but both
merely confirmed the pre-probe action. Before spending further API budget, this
audit asks a prerequisite causal question:

> Do the two registered micro-probes contain action-discriminative information
> about the distribution of compensation versus retry outcomes?

This is not an Agent performance experiment. It makes no API calls and does not
select or execute an online recovery action. Both probe branches and all paired
recovery outcomes are evaluator-only research measurements.

Seeds 6750--6849 are immutable and seeds 6850--6949 remain reserved. This
protocol may scan fresh development seeds 6950--7099 once. Seeds 7100--7199 are
reserved.

## Collection

Scan in ascending seed order until exactly 30 failed initial rollouts with
constructible compensation are collected, or all 150 initial units are
exhausted. Stopping may inspect only initial failure and constructibility, never
probe measurements or candidate outcomes.

For every operational state:

1. collect the existing 64-step repeated evidence;
2. from independent reset-matched namespaces, execute one 64-step
   `COMPENSATION_RESPONSE_PROBE` and three 64-step nominal prefixes comprising
   `RETRY_REPEATABILITY_PROBE`;
3. persist both probe records before any recovery outcome;
4. collect four independent paired verification realizations for each of the
   two registered recovery skills.

No probe or recovery branch enters Agent View, memory, hypotheses, or
principles. Candidate order is fixed as compensation then retry, and each
realization uses one common random namespace across the two candidates.

## Frozen scores and distributional target

The compensation support score is:

```text
max(0, expected_direction_alignment)
* response_consistency
* int(contact_preserved)
```

The retry support score is:

```text
positive_progress_rate * (1 - severe_failure_rate)
```

The only primary probe score is:

```text
probe_contrast = compensation_support - retry_support
```

No coefficient or threshold is fitted. Higher contrast is preregistered to
indicate compensation utility.

For each skill, accepted recovery rate is computed over its four independent
verification realizations. A state is distributionally decisive only when:

```text
compensation_accept_rate - retry_accept_rate >= 0.50
```

or the reverse difference is at least 0.50. Other states are retained as
non-decisive. The positive AUC class is compensation-superior.

## Metrics and gate

Report operational and decisive populations, each class count, probe-score
distributions, action acceptance distributions, candidate-winner reversals,
probe-contrast ROC AUC, rank correlation with acceptance-rate margin, and a
10,000-sample fixed-seed stratified bootstrap interval for AUC.

Feasibility promotion requires all of:

```text
operational cases = 30
decisive cases >= 12
at least 4 decisive cases per action
probe-contrast ROC AUC >= 0.75
bootstrap AUC lower bound > 0.50
rank correlation with utility margin >= 0.30
all integrity violations = 0
```

Failure or incomplete population is preserved without changing scores,
realization count, labels, gate, or seeds. Passing would authorize only a
separately frozen development experiment that asks an Agent to allocate the
more informative registered probe. It does not authorize memory, principles,
online recovery, validation, held-out execution, VLA, RL, continuous actions,
or performance claims.
