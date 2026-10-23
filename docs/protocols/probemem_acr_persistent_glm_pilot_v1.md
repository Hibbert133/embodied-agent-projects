# Persistent-Regime GLM-5.2 Pilot v1

This frozen qualitative pilot is authorized because the preceding persistent-
regime development run passed its action-identifiability gate. It asks whether
GLM-5.2 can consume the same leakage-safe evidence interface and choose between
the two registered skills. It does not execute model choices.

Ten cases are selected before API calls: the first five operational episode IDs
from each evaluator-only registered condition. Condition identity is used only
to balance the pilot and is never included in the model payload. The payload is
the exact `agent_visible_evidence` persisted before paired outcomes were
collected. It contains no condition label, threshold, candidate outcome, or
Oracle winner.

The model must predict both candidates and select compensation, retry, or
abstain. There is no schema-repair call, so the hard cap is ten API calls.
Invalid output, timeout, or unsupported decisions fail closed to abstention.

Report structured-output validity, leakage audit, action selections,
disagreement with the frozen deterministic rule, evaluator-only matched outcome
audit, latency, tokens, and fail-closed behavior. Ten cases cannot support a
statistical claim that GLM is better or worse than the deterministic method.
No environment steps, memory writes, validation, or held-out execution are
authorized.
