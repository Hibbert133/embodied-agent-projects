# ProbeMem Coverage-Aware Verified Memory Development

Run: `probemem_paired_utility_20260731T184353Z_cca94dad8cbe`
Manifest: `12a47860c1b8f6b95858be5cf3d5b9e0b50ccdef017fd41102b445b40a63f9e9`

## Actual result

The stream scanned 61 initial units and reached 20 operational pairs.
The frozen memory gate used a verified episode in 2/20 cases and abstained in 18.
Among uses, 0/2 were accepted and 2 were wrong-memory applications with an accepted alternative.
Decision reasons: {'CONFLICTING_VERIFIED_EPISODES': 14, 'OUTSIDE_VERIFIED_COVERAGE': 4, 'WITHIN_COVERAGE_WITH_UNANIMOUS_SUPPORT': 2}.
The registered promotion gate passed: False.

The two memory uses occurred at seeds 1002 and 1021. At seed 1002, unanimous
retrieval selected retry, which was inconclusive while compensation was
accepted. At seed 1021, it selected compensation, which was rejected while
retry was accepted.

For context, unguarded nearest retrieval was accepted in 9/20 cases, always
retry in 12/20, and always compensation in 8/20. These paired alternatives are
evaluator-only and were not available to the online decision. Memory decision
latency excluded ten warm-up calls and the environment: median 0.161 ms, p90
0.170 ms, maximum 0.177 ms.

The figure at
`outputs/probemem_v2/figures/coverage_aware_memory_funnel.png` is generated
directly from the summary JSON.

## Claim boundary

This is a development-only Phase-C applicability result. Paired alternative outcomes are evaluator-only. It does not promote a scientific principle, use an API, alter policy weights, or support a held-out claim.
