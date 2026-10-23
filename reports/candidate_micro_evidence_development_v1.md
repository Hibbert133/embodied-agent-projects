# Candidate-Conditioned Micro-Evidence Development v1

## Research question

The 20-case noise coverage study showed that aggregate failure evidence did not
reliably identify whether bias compensation or stochastic retry had higher
downstream utility. This development experiment tested a narrower alternative:
can short Agent-visible executions of both intervention candidates reveal which
candidate will work in an independent full verification rollout?

This is simulator branching between rollout attempts. It is not step-level
planning, a replacement for the frozen v1 diagnostic probe, or a held-out
performance claim.

## Frozen setup

- Source: the immutable 20 paired-comparable stochastic-noise cases from
  `development_20260731T035004Z_ed696b94484e` (seeds drawn sequentially from
  430--488).
- Candidates: registered probe-grounded compensation and stochastic retry.
- Prefix horizons: 16, 32, 64, and 128 steps; all were reported.
- Evidence: schema-v2 Agent View summaries only.
- Selection: prefix success first; otherwise lower final object-goal distance,
  then fewer steps and candidate ID.
- Scoring: the previously collected independent fresh-verification outcomes.
- No API calls, video rendering, threshold fitting, or held-out retuning.

## Results

| Horizon | Utility agreement | Selected recovery | Paired W/T/L vs compensation | Mean prefix steps | Mean total additional steps |
|---:|---:|---:|---:|---:|---:|
| 16 | 10/20 (50%) | 8/20 (40%) | 3/14/3 | 32.0 | 406.7 |
| 32 | 9/20 (45%) | 9/20 (45%) | 3/15/2 | 64.0 | 422.25 |
| 64 | 11/20 (55%) | 9/20 (45%) | 3/15/2 | 128.0 | 486.15 |
| 128 | 8/20 (40%) | 9/20 (45%) | 3/15/2 | 238.7 | 587.85 |

Both fixed candidates recovered 8/20 cases (40%). A post-hoc candidate oracle,
which chooses either candidate whenever one succeeds, would recover 13/20
(65%). The selector therefore recovered at most one additional case over a
fixed candidate while leaving four of the five oracle-recoverable additional
cases unresolved. At horizons 32, 64, and 128, the paired recovery difference
versus fixed compensation was +5 percentage points with a paired-bootstrap 95%
interval of [-15, +25] points. The interval includes both meaningful harm and
benefit.

## Interpretation

The experiment does not support a stable, cost-justified micro-evidence
selector. Longer prefixes did not monotonically improve utility agreement, and
the maximum observed recovery increase was small relative to 64--239 extra
prefix steps per case. This is a useful negative result: immediate object-goal
distance under a candidate action is not a reliable proxy for its independent
full-rollout utility under stochastic execution error.

Scientifically, the remaining gap to the 65% post-hoc candidate oracle shows
that candidate selection still matters, but the missing information is not
captured by this simple single-prefix geometric ranking. The next experiment
should isolate repeatability: compare repeated short candidate executions using
variance or consistency evidence under a newly frozen development protocol.
It must not tune against these 20 outcomes or alter the held-out v1 allocation
claim.

## Reproduction

```bash
python scripts/run_candidate_micro_evidence_development.py
python scripts/analyze_candidate_micro_evidence.py \
  --run-dir outputs/candidate_micro_evidence/runs/micro_20260731T064558Z_2fa7f211eb53 \
  --output-figure outputs/figures/candidate_micro_evidence_cost_outcome_v1.png
```

Run ID: `micro_20260731T064558Z_2fa7f211eb53`
Implementation commit: `2fa7f211eb53777affec4a0e3633b6a3bd122d80`
