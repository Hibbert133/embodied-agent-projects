# ProbeMem Verifier Failure-Localization Audit

## Scope

This audit uses no new rollout, API call, memory write, threshold fit, or seed.
It attributes the immutable Demo's 11/21
Budgeted verifier calls and guard outcomes. It does not propose a replacement
admission or override rule.

## Admission localization

Atomic trigger presence was: ambiguity band 5,
recent similar contradiction 7,
and global/recent conflict 1.
Single-trigger-only calls were {"GLOBAL_RECENT_MEMORY_CONFLICT": 1, "RECENT_SIMILAR_CONTRADICTION": 5, "WITHIN_AMBIGUITY_BAND": 3}.

Descriptively removing only the contradiction trigger from the already-frozen
trace would retain 6
calls; removing only the ambiguity-band trigger would retain
8.
These are overlap counts, not registered candidate policies and must not be used
to select a new rule on seeds 4700--4749.

## Guard localization

Nonexclusive blocker counts were {"ALTERNATIVE_CONTRADICTION_TOO_HIGH": 8, "ALTERNATIVE_NOT_BETTER": 9, "PROBABILITY_MARGIN_TOO_SMALL": 9, "RECENT_GLOBAL_PREFERENCE_NOT_ALIGNED": 9, "VERIFIER_CONFIDENCE_TOO_LOW": 9}.
The two authorized alternatives comprised
{"HARMFUL": 1, "TIE": 1}. The nine
blocked alternatives comprised
{"HARMFUL": 4, "HELPFUL": 1, "TIE": 4}.

The failure is therefore not merely excess admission: the posterior/applicability
stack both authorized a harmful alternative and rejected a helpful one. A valid
successor must pose a new calibration or causal-evidence question on fresh seeds;
this audit does not choose its parameters.

## Claim boundary

No parameter is changed. Seeds 4750--4799, validation, held-out execution, GLM,
and principle generation remain blocked.
