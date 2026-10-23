# Value-Aware Stochastic Retry Study

## Question

The consistency study showed that stochastic execution noise is identifiable but
that direct abstention is harmful. This follow-up tested whether the Agent should
route high-variance cases to an independent no-bias retry while retaining bias
compensation for repeatable drift.

The environment reset seed remains fixed. A retry receives a deterministic derived
perturbation seed, representing a new execution-noise realization. The seed is an
Oracle reproducibility field and is not part of the Agent decision.

## Controls

- `same_seed_retry`: exact replay control; it should reproduce the initial failure.
- `independent_retry`: blindly retry every failure with a new execution stream.
- `bias_compensation`: frozen `research_r1_c1` policy.
- `value_aware`: consistency below threshold selects compensation; above threshold
  selects independent retry.
- `no_recovery`: interaction-free lower bound.

## Results

On tuning seeds 300–309, 34 episodes initially failed. Same-seed retry recovered
0/34, confirming deterministic replay. Blind independent retry recovered 2/34 and
failed on every bias case. Bias compensation recovered 31/34 (91.2%, 120.85 mean
steps). Value-aware routing recovered 32/34 (94.1%, 158.47 mean steps), so it passed
the tuning success-first gate despite higher cost.

On frozen validation seeds 310–319, 30 episodes initially failed. Bias compensation
recovered 29/30 (96.7%, 91.07 steps). Value-aware routing recovered 28/30 (93.3%,
153.83 steps). Of two stochastic failures, independent retry recovered one while
compensation recovered both. The promotion gate therefore rejects value-aware retry.

## Interpretation

The negative result rules out a simple fault-type-to-skill mapping. Even when noise
is correctly identified, a compensation skill can remain the higher-value action.
Future routing must estimate candidate-specific recoverability or expected utility,
not only latent fault class, OOD status, or transition variance.

No held-out test was run because the method failed frozen validation.
