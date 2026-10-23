# Prospective Continuous Feedback Development Result

## Protocol identity

Run ID: `acr_continuous_feedback_20260803T033027Z_fdff57ab321b`

Manifest ID: `4bca2c97898ef8f36e3fc100cf5df19fe37808f9da44de5205b17a09d3d9e856`

Source commit: `fdff57ab321bbf4edc5f8ed6e17bcd8a83c4c17a`

This was a prospective development experiment. The progress threshold was
frozen at exactly zero metres before execution and was not fitted from the
preceding feedback-sufficiency audit.

## Collection

The run scanned 231 fresh `fault_05` initial units, obtained 85 eligible first
retry attempts, and stopped at 30 non-accepted first attempts. Twelve were
`INCONCLUSIVE` and 18 were `REJECTED`. Paired repeat-retry and
switch-compensation outcomes were evaluator-only. No API, GLM, or memory was
used, and no held-out seed was executed.

## Results

| Method | Accepted | Rate | Harmful selections | Mean steps |
|---|---:|---:|---:|---:|
| One retry | 55/85 | 64.7% | 0 | 824.1 |
| Always repeat | 74/85 | 87.1% | 7 | 919.9 |
| Always switch | 71/85 | 83.5% | 10 | 938.8 |
| Frozen status rule | 70/85 | 82.4% | 11 | 934.3 |
| Zero-progress rule | 70/85 | 82.4% | 11 | 934.3 |
| Evaluator Oracle | 81/85 | 95.3% | 0 | 897.8 |

Against always-repeat, the zero-progress rule's accepted-rate difference was
-4.71 percentage points with paired-bootstrap 95% CI [-11.76, +2.35]. Its
harmful-selection difference was +4.71 points, CI [-2.35, +11.76], and it used
14.4 more environment steps per case on average, CI [-12.0, +40.8].

The zero-progress rule exactly duplicated the historical status rule: all 12
positive-progress second decisions were `INCONCLUSIVE` and repeated retry; all
18 non-positive decisions were `REJECTED` and switched compensation.

## Research interpretation

The previous raw AUC showed ordering on evaluator-only exclusive outcomes, but
that ordering did not imply a useful zero-metre operating point. In this fresh
prospective stream, progress sign was only another encoding of the unstable
categorical status and underperformed the strongest fixed policy.

This falsifies the proposed zero-progress allocation rule. It does not justify
searching a better threshold on the same data. GLM, transition memory,
validation, and held-out execution remain unauthorized. The next scientific
step should change the evidence source or experimental identification design,
not add another post-hoc threshold.
