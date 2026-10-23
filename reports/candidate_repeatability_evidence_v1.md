# Candidate Repeatability Evidence v1

## Question

Does repeating short candidate-conditioned rollouts provide sufficiently stable
evidence to select between bias compensation and stochastic retry under
stochastic execution error?

The selector and all random namespaces were committed before collecting the
fresh source population. This is a development evaluation, not a held-out claim.

## Setup

- Fresh sequential source range: seeds 600--699.
- Label-blind coverage stop: 20 paired-comparable failures, reached after 56
  initial units.
- Candidate prefixes: 64 steps, three independent stochastic realizations.
- Reported evidence budgets: one, two, and three repetitions for both candidates.
- Frozen score: prefix-success count first, then
  `mean(final distance) + population std(final distance)`.
- Full candidate outcome: independent matched fresh verification from the
  immutable source run.
- No fitted threshold, API call, rendering, or outcome-driven rule update.

## Results

| Repetitions per candidate | Utility agreement | Selected recovery | Paired W/T/L vs fixed retry | Mean prefix steps | Mean total additional steps |
|---:|---:|---:|---:|---:|---:|
| 1 | 14/20 (70%) | 10/20 (50%) | 2/14/4 | 127.9 | 438.9 |
| 2 | 11/20 (55%) | 9/20 (45%) | 2/13/5 | 255.65 | 590.4 |
| 3 | 11/20 (55%) | 6/20 (30%) | 1/12/7 | 383.65 | 770.8 |

Fixed compensation recovered 4/20 (20%); fixed retry recovered 12/20 (60%). A
post-hoc candidate oracle recovered 14/20 (70%). Relative to fixed retry, the
selected-recovery differences were -10, -15, and -30 percentage points. Their
paired-bootstrap 95% intervals were respectively [-35, +15], [-40, +10], and
[-55, -5] points.

Additional repetitions frequently changed behavior without improving outcome:

- k=1 to k=2: five decisions changed; one recovery improved and two worsened;
- k=1 to k=3: eleven decisions changed; two recoveries improved and six worsened.

## Interpretation

The registered repeatability hypothesis is not supported. More independent
prefix evidence increased environment interaction but reduced both utility
agreement and recovery. At three repetitions, the paired interval indicates a
negative recovery difference relative to fixed retry on this development
population.

This result suggests that averaging short geometric outcomes across stochastic
realizations suppresses neither the candidate-ranking error nor the mismatch
between short-horizon motion and full-rollout success. Repeatability alone is
therefore not evidence value: evidence must be linked to the downstream
decision and verification objective.

The result also narrows the project direction. The next useful analysis is not
another prefix score. It is a case-level failure analysis of the 11 decisions
changed by added evidence, using Agent-visible trajectories to identify when
short-horizon ranking diverges from full-rollout utility. No new selector should
be proposed until that mechanism is understood on development data.

## Decision-change audit

The preregistered audit covered all 11 decisions changed between k=1 and k=3:

- helpful: 2;
- neutral: 3;
- harmful: 6;
- robust-distance rank flip: 10;
- prefix-success priority: 1.

The only prefix-success-priority change was helpful (seed 636), whereas most
changes were driven by small reversals in the robust-distance ordering. This is
a descriptive clue, not a decision rule: one positive example cannot justify a
new selector. It does show why the `mean + std` abstraction failed—the summary
can reverse candidate rank without demonstrating task completion or durable
contact behavior.

## Representative verification videos

Cases were selected mechanically by the largest absolute k=3 robust-score
margin within each registered outcome class. Both candidates were rerendered
using the exact frozen verification random stream, and success, steps, and final
distance were checked against the source CSV.

- helpful seed 636: compensation fails; retry succeeds;
- harmful seed 620: k=3 changes from successful retry to failed compensation;
- neutral seed 600: both candidates fail.

The paired videos and their provenance are stored under
`outputs/videos/candidate_repeatability_changes_v1/manifest.csv`.

## Execution note

The foreground command wrapper returned exit 124 at its wall-time boundary,
after the Python runner had completed all 20 cases and atomically written
`run_status.json` with `status=COMPLETED`. Artifact completeness, not the wrapper
exit code, is used here; all expected cases and result files are present.

## Reproduction

```bash
python scripts/run_intervention_identifiability_development.py \
  --config configs/autoresearch/noise_repeatability_confirmatory_source_v1.json

python scripts/run_candidate_repeatability_evidence.py \
  --source-run outputs/intervention_identifiability/runs/development_20260731T070305Z_1046f463d168

python scripts/analyze_candidate_repeatability.py \
  --run-dir outputs/candidate_repeatability/runs/repeatability_20260731T070645Z_9650e171518a \
  --source-run outputs/intervention_identifiability/runs/development_20260731T070305Z_1046f463d168 \
  --output-figure outputs/figures/candidate_repeatability_cost_outcome_v1.png
```

Source run: `development_20260731T070305Z_1046f463d168`

Repeatability run: `repeatability_20260731T070645Z_9650e171518a`

Frozen selector commit: `1046f463d16807f5a93c96870bc1eae43f0e7cab`
