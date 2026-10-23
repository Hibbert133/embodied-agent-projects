# ProbeMem Verified Intervention Episode Snapshot

## Purpose

The legacy Phase-C episodic schema stores seven pre-probe evidence features.
Intervention applicability in the later noise experiment uses a 13-feature
post-probe signature. This snapshot introduces a separate versioned episode
record rather than silently changing the historical schema.

## Actual source

- Run: `probemem_paired_utility_20260731T174415Z_ddd061fcec73`
- Manifest: `a45c2620a73ab8f6c6542a2d7063ce5dea10587deab458e66620482be5633984`
- Selection policy: `rounded_relative_probe_variation_v1`
- Operational cases: 20

Only the selector-chosen intervention and its fresh verification are eligible.
The unselected paired candidate remains evaluator-only.

## Actual snapshot

- Freshly accepted records: 13
- Independent stochastic retry: 7
- Bounded planar compensation: 6
- Excluded inconclusive outcomes: 3
- Excluded rejected outcomes: 4
- Unselected counterfactuals exported: 0
- Oracle fields exported: 0

## Claim boundary

The records satisfy accepted-only provenance and can support a future frozen
Phase-C retrieval protocol. Operational retrieval is currently disabled. This
snapshot does not promote a principle, repair the failed selector gate, or
constitute online memory improvement.
