# ProbeMem Frozen Noise Selector Validation

Run: `probemem_paired_utility_20260731T174415Z_ddd061fcec73`
Manifest: `a45c2620a73ab8f6c6542a2d7063ce5dea10587deab458e66620482be5633984`
Source commit: `ddd061fcec73b100d31546ee20f3196f5fad4d1b`

## Frozen rule

Retry when `probe_relative_bias_std <= 2.0`, otherwise compensation.

## Actual result

The label-blind collection scanned 56 initial units and reached 20 operational pairs.
- Frozen selector: 13/20 accepted.
- Always retry: 11/20 accepted.
- Always compensation: 14/20 accepted.
- Selector choices: {'BOUNDED_PLANAR_COMPENSATION': 8, 'INDEPENDENT_STOCHASTIC_RETRY': 12}.
- Selector vs retry: {'win': 3, 'tie': 16, 'loss': 1}.
- Selector vs compensation: {'win': 1, 'tie': 17, 'loss': 2}.
- Promotion gate passed: False.

## Interpretation

This is a fresh development-validation result for one frozen deterministic rule. It is not a held-out result and does not promote a scientific-memory principle. A failed gate is retained without threshold revision on this stream.
