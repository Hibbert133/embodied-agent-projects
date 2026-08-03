# ProbeMem-ACR Verification Feedback Sufficiency Audit

## Scope

This development-only audit investigates why the frozen attempt-level status
rule did not replicate in independent validation. It does not test an online
selector, memory, GLM reasoning, validation, or held-out performance.

Run ID: `acr_feedback_sufficiency_20260803T031147Z_dc82fef58e26`  
Manifest ID: `e7ee616e070af571479838f8719be1ff0e6da0e348026d463035e709af4e237a`  
Source commit: `dc82fef58e2693c0c91ed23a9147964d4177492b`

An earlier run under commit `cc72bb3b562e` failed because heterogeneous CSV
rows violated the writer schema. Its manifest, partial records, and failure
status are preserved; no scientific result was derived from it.

## Setup

The immutable campaign scanned seeds 3300--3400 under registered `fault_05`
until it reached 30 label-blind eligible initial failures. Each state received
four independent first stochastic-retry realizations. Every non-accepted first
retry was followed by evaluator-only paired repeat-retry and switch-compensation
rollouts from independent resets and matched random streams.

The collection contains 120 first-retry branches: 81 `ACCEPTED`, 19
`INCONCLUSIVE`, and 20 `REJECTED`. Thirty-nine branches required a second
decision. Twenty were exclusive-recovery cases: retry alone recovered 14 and
compensation alone recovered 6.

## Results

- Mean modal first-status share across states: **0.750**.
- States exhibiting more than one first status: **21/30 (70.0%)**.
- States whose paired candidate winner changed across realizations: **9/30**.
- After `INCONCLUSIVE`, repeat accepted 12/19 (63.2%) and switch accepted 4/19
  (21.1%).
- After `REJECTED`, both repeat and switch accepted 12/20 (60.0%).
- The frozen status rule was tied with always-repeat on the 39 second-decision
  branches; cluster-bootstrap difference 0.000, 95% CI [-0.179, 0.172].
- The status rule exceeded always-switch by 0.205, 95% CI [0.059, 0.368].
- On 20 exclusive-recovery branches, the preregistered raw AUC for
  first-observed progress predicting retry-only recovery was **0.798**. Negative
  first final distance reached **0.726**.

All chronology, leakage, namespace, reset, and budget checks passed. API calls
were zero. Reserved and held-out seeds were not executed.

## Interpretation

The first status is not a stable state label under stochastic execution. In
particular, `REJECTED` did not identify a reliable switch-to-compensation
regime: repeat and switch had equal marginal acceptance. Compressing fresh
feedback into three categories therefore discards potentially useful response
magnitude.

The continuous-progress AUC is a promising feasibility signal, not an evaluated
policy. It was computed on evaluator-only exclusive outcomes and cannot justify
fitting a threshold on this stream. The legal next step is a separately frozen,
fresh-seed prospective comparison of a predeclared continuous-feedback rule
against always-repeat—not GLM, memory, or held-out evaluation.

## Claim boundary

This audit supports only: repeated fresh-verification status is realization-
sensitive, while continuous first-attempt progress merits prospective testing.
It does not show statistical recovery improvement, online learning, memory
benefit, or LLM benefit.
