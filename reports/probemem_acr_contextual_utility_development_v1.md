# ProbeMem-ACR Contextual Utility Development v1

## Question

Can a Bayesian action model conditioned on all 13 registered Agent-visible
evidence fields improve fresh-verification intervention selection relative to a
global action posterior?

This was a development-only paired counterfactual feasibility study. It did not
call an LLM, learn policy weights, promote principles, or execute validation or
held-out seeds.

## Frozen run

- source commit: `f54f00df645e7d1747344ef6e48165f676fda97c`;
- run: `acr_contextual_20260802T134851Z_f54f00df645e`;
- manifest: `ff6c241462123c37f800eab7974751b3a98155e264ded2846e5c4380cb4f6abd`;
- scanned initial units: 160;
- operational cases: 60;
- paired candidate rollouts: 120;
- reserved seeds 2700--2849: not executed.

The paired population contained 35 exclusive recoveries, 16 both-accepted
cases, and 9 neither-accepted cases. Compensation was accepted in 30/60 and
retry in 37/60.

## Results

| Method | Accepted | Harmful transfer | Abstentions | Utility Brier |
| --- | ---: | ---: | ---: | ---: |
| Always compensation | 30/60 | 21 | 0 | 0.187 |
| Always retry | 37/60 | 14 | 0 | 0.202 |
| Accepted-only last | 38/60 | 13 | 0 | 0.185 |
| Global posterior | 37/60 | 14 | 0 | 0.190 |
| Contextual greedy | 37/60 | 14 | 0 | 0.253 |
| Contextual abstain | 10/60 | 3 | 44 | 0.354 |

Contextual greedy changed 17 interventions relative to the global posterior.
Five changes recovered a case the global posterior missed, five lost a recovery
the global posterior obtained, and seven were neutral. Thus the model crossed
the reasoning-to-action boundary but produced no net recovery gain. Its paired
accepted-rate difference was 0 points with a 95% bootstrap interval of -10 to
+10 points.

Contextual abstention reduced harmful transfer but abstained on every one of 44
post-exploration cases. It missed 38 recoverable cases and therefore failed the
coverage and recovery requirements.

## Integrity and promotion

- chronology violations: 0;
- Oracle leakage events: 0;
- current-outcome pre-decision reads: 0;
- scaler current/future reads: 0;
- collection budget violations: 0;
- API calls: 0.

Both promotion routes failed. No model constant or feature is revised, and no
GLM, principle, validation, or held-out phase is authorized.

## Interpretation

The negative result separates behavior change from useful adaptation. A linear
mapping over the complete evidence signature can alter robot-level intervention
choices, but its helpful and harmful changes cancel. The contextual model is
also less calibrated than the global posterior.

This suggests that the current evidence representation lacks a stable causal
predictor of per-case intervention utility, or that a single stochastic outcome
per selected action is too noisy for this model. Increasing model flexibility
without new evidence would risk fitting stochastic realization noise. A future
protocol should test an additional causally motivated evidence source or repeated
outcome aggregation, not retune this model on the completed stream.
