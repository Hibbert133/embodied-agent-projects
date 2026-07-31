# ProbeMem Frozen Selector Causal Audit

Run: `probemem_paired_utility_20260731T174415Z_ddd061fcec73`
Manifest: `a45c2620a73ab8f6c6542a2d7063ce5dea10587deab458e66620482be5633984`

## Result

Among 7 exclusive-recovery cases, the frozen selector chose the accepted skill in 4 and failed in 3.
Error seeds were [865, 883, 884], with absolute threshold margins {'865': 0.9463022241233874, '883': 0.38872216393326986, '884': 11.714296024637116}.

The errors are not confined to a narrow threshold boundary. Low relative probe variation contains both retry-only and compensation-only recoveries, while one extreme high-variation case is retry-only. The observed intervention utility is therefore non-monotonic in this single feature.

## Claim boundary

This audit is descriptive and post-hoc. It executed no rollout or API call, fit no threshold or selector, generated no principle, and does not unblock Phase D. It motivates testing whether additional Agent-visible state or explicit verification-grounded surprise is necessary.

The corresponding plot is generated directly from the causal-audit CSV at
`outputs/probemem_v2/figures/noise_selector_causal_audit.png`.
