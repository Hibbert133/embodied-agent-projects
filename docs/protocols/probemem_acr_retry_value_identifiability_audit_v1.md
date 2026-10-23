# Retry-Value Identifiability Audit v1

## Scope

This is a post-hoc, evaluator-only audit of the completed immutable continuous-
feedback development run. It performs no new environment interaction and cannot
promote an online rule. Its narrow question is:

> Does feedback from the first retry rank whether one additional independent
> stochastic retry will be accepted?

The source run, manifest, population, score directions, and label are frozen in
`configs/probemem_acr/retry_value_identifiability_audit_v1.json`.

## Population and evaluator label

The population contains only source-run cases with
`second_decision_required == true`. The evaluator-only positive label is true
exactly when the paired `INDEPENDENT_STOCHASTIC_RETRY` candidate is `ACCEPTED`.
That counterfactual outcome was not available to the online policy before its
decision and is used only for this feasibility audit.

## Registered scores

No score direction is inferred from the paired outcome:

* higher first observed progress means higher predicted retry value;
* lower first final object-goal distance means higher predicted retry value;
* `INCONCLUSIVE` maps to 1 and `REJECTED` maps to 0.

The audit reports tie-aware ROC AUC, grouped-threshold average precision, label
prevalence, and score distributions. A descriptive threshold frontier reports
retry request rate, recovered cases, unnecessary retries, missed recoveries,
actual additional environment steps, and recoveries per 100 additional steps.

## Claim boundary

Every threshold on the frontier is evaluator-visible and retrospective. The
audit must not select an operating point, fit a threshold, claim prospective
online adaptation, call an LLM, write memory, execute validation, or touch
held-out seeds. A positive ranking result can only motivate a separately frozen
fresh-seed protocol; a negative result closes this feedback line without another
threshold search on the same run.
