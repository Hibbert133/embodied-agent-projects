# Noise Repeatability Source v1 — Incomplete Protocol Result

## Outcome

The source collection executed all 60 preregistered initial units (seeds
500--559) but produced only 15 paired-comparable operational failures. The
registered target was 20. Coverage therefore failed:

- full collection: 60 units;
- successful initial rollout: 45 units;
- operational paired-comparable failure: 15 units (25%);
- Wilson 95% interval for operational prevalence: 15.8%--37.2%;
- coverage target: 20 units;
- `coverage_target_reached`: `false`.

The frozen stopping rule is preserved. The seed range was not extended and the
target was not lowered after observing the result.

## Outcome-blinding violation

The reused collection runner emitted each candidate winner to the terminal and
wrote evaluator outcome tables before a repeatability selector was committed.
This violates the protocol's intended ordering:

```text
freeze selector -> collect fresh outcomes -> evaluate selector
```

Consequently this run is marked
`INVALID_FOR_CONFIRMATORY_REPEATABILITY_EVALUATION`. It may be retained for
pipeline auditing and exploratory prevalence reporting, but it must not be used
to fit a repeatability rule, choose a threshold, or support a performance
claim.

For transparency only, the evaluator table contains 10 retry-preferred and 5
compensation-preferred cases; each fixed candidate recovered 8/15, while a
post-hoc candidate oracle recovered 12/15. These numbers motivated no selector
change and are not confirmatory evidence.

## Research interpretation

This failure is methodological rather than an environment crash. It identifies
two requirements for the next attempt:

1. freeze the complete repeatability selector before any new outcome collection;
2. use a new seed range and a source runner that does not expose candidate
   outcomes until evidence collection has finished.

The negative/incomplete run remains committed rather than overwritten.

## Reproduction

```bash
python scripts/run_intervention_identifiability_development.py \
  --config configs/autoresearch/noise_repeatability_source_v1.json
```

Run ID: `development_20260731T065555Z_c214dc0f4a08`

Source commit: `c214dc0f4a08b233986f3288a8620260d7845ec5`
