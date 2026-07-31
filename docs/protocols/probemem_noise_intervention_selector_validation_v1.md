# ProbeMem Noise Intervention Selector Validation v1

## Frozen development hypothesis

This protocol tests one deliberately simple action-discriminative hypothesis:

```text
if probe_relative_bias_std <= 2.0:
    INDEPENDENT_STOCHASTIC_RETRY
else:
    BOUNDED_PLANAR_COMPENSATION
```

The direction and rounded threshold were selected post-hoc from the completed
760--817 development coverage. They are frozen before this validation and are
not a scientific result by themselves. The feature is Agent-visible and the
selector does not receive the outcome partition, perturbation label, or either
candidate's verification result.

## Fresh population

- Seeds 840--899 are a fresh development-validation stream.
- Only registered `fault_05` is used.
- Collection stops at 20 paired operational failures or 60 initial units.
- The stop rule may inspect paired executability only, never outcomes.
- Seeds 900--979 remain untouched held-out data.

Each operational case executes both registered candidates under common random
numbers for evaluator-only paired comparison. Online cost is computed using
only the selector-chosen candidate; the unchosen candidate is not presented as
online Agent behavior.

## Comparisons and gate

The frozen selector is compared against always retry, always compensation, and
an evaluator-only per-case Oracle. Promotion to a Phase-D *candidate* requires
20 pairs, both skills to be selected, zero leakage, at least one net accepted
recovery over always retry, and no loss versus always compensation. This gate
does not promote a scientific-memory principle or support a held-out claim.

Negative results are retained. The threshold, feature, direction, stop rule,
and gate must not be changed after execution begins.

## Immutable result

- Run ID: `probemem_paired_utility_20260731T174415Z_ddd061fcec73`
- Manifest ID: `a45c2620a73ab8f6c6542a2d7063ce5dea10587deab458e66620482be5633984`
- Source commit: `ddd061fcec73b100d31546ee20f3196f5fad4d1b`
- Initial units scanned: 56
- Operational pairs: 20
- Frozen selector: 13/20 accepted
- Always retry: 11/20 accepted
- Always compensation: 14/20 accepted
- Promotion gate: **FAILED** (`no_loss_vs_compensation == false`)

The threshold was not revised. No principle, memory record, API conclusion, or
held-out claim was produced.
