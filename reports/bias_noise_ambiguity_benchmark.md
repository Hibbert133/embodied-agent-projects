# Bias–Noise Passive-Ambiguity Benchmark (Tuning Pilot)

## Research question

Can two failed Push rollouts with similar passive task symptoms arise from different
execution mechanisms, and can a bounded repeated probe expose that difference?
This pilot operationalizes the immediate ambiguity benchmark in the active-evidence
research plan. It does not introduce a new diagnostic algorithm or call an online
model.

## Selection protocol

The builder read the real tuning artifacts from the existing 50-case fault
benchmark. It retained only initial rollout failures and formed two Oracle audit
classes: stable injected action bias and stochastic Gaussian action noise. The
Oracle class is used to construct and score the benchmark, never as Agent input.

Pair selection used exactly three passive rollout outcomes:

- episode return;
- final object–goal distance;
- progress to goal.

The features were standardized across the candidate failure pool. A global
one-to-one assignment paired every noise failure with a distinct bias failure while
minimizing total Euclidean distance. Probe consistency, injected parameters, and
counterfactual outcomes were excluded from matching. Input SHA-256 hashes are saved
in `summary.json` so the manifest can be traced to exact source artifacts.

## Real tuning result

The source pool contained 30 stable-bias failures and 4 stochastic-noise failures.
The frozen builder produced four pairs (eight cases):

| Pair | Stable-bias case | Noise case | Standardized passive distance |
|---|---|---|---:|
| pair_01 | case_0021 | case_0041 | 0.8963 |
| pair_02 | case_0006 | case_0044 | 0.5927 |
| pair_03 | case_0004 | case_0045 | 0.8778 |
| pair_04 | case_0027 | case_0047 | 0.5552 |

Mean standardized distance was 0.7305. After the pairs were frozen, the existing
four-repeat symmetric-probe score was joined for audit. With the already selected
tuning threshold 0.11560838, all 8/8 cases were classified correctly (balanced
accuracy 1.0). Each repeated-probe record cost 64 environment steps.

This is a **tuning-set separability result**, not a held-out claim: the cases and
threshold both originate from seeds 300–309. The deterministic bias probes have
exactly zero repeat variance while Gaussian noise uses a large calibrated standard
deviation of 0.60, so the mechanism distinction is unusually clean. The pilot
establishes a reproducible benchmark construction path; it does not establish that
passive diagnosis fails statistically, that active probing is interaction-efficient,
or that the result transfers beyond these synthetic faults.

## Why this matters

The eight cases hold coarse passive symptoms reasonably close while changing the
temporal repeatability of the execution fault. This creates a more relevant unit of
study than maximizing Push success across unrelated failures: an evidence manager
can now be evaluated on whether it requests repeat evidence only when passive
evidence is insufficient and whether the information gain justifies 64 extra steps.

## Reproduction

```powershell
python scripts/build_bias_noise_ambiguity_benchmark.py
python -m unittest tests.test_bias_noise_ambiguity_benchmark -v
```

Outputs:

- `outputs/ambiguity_benchmark/bias_noise_tuning_v1/pairs.csv`
- `outputs/ambiguity_benchmark/bias_noise_tuning_v1/cases.csv`
- `outputs/ambiguity_benchmark/bias_noise_tuning_v1/probe_audit.csv`
- `outputs/ambiguity_benchmark/bias_noise_tuning_v1/summary.json`

## Next decision

Freeze a held-out matching protocol on seeds 310–319, then compare passive,
always-probe, random-probe, and uncertainty-gated agents. Promotion requires a
diagnostic accuracy/evidence-cost gain under no held-out retuning. If passive
evidence performs equally well at lower cost, the benchmark does not justify active
evidence and must be redesigned.
