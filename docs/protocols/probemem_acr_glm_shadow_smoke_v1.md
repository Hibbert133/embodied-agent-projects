# GLM-5.2 Shadow Reasoning Smoke v1

This smoke test accelerates API integration without bypassing the failed
identifiability gate. It selects the first three registered development rows and
constructs a new allowlisted payload containing only first-attempt Agent-visible
feedback. Evaluator-only paired outcomes are deliberately discarded before the
request object is built.

GLM-5.2 must predict both registered candidate outcomes and return exactly one
of `REPEAT_STOCHASTIC_RETRY`, `SWITCH_TO_BOUNDED_COMPENSATION`, or `ABSTAIN`.
The deterministic host validates the exact schema, probability bounds, candidate
coverage, and leakage boundary. Invalid output fails closed to `ABSTAIN`, with
at most one schema-repair call per case and six total API calls.

Every decision is shadow-only: it is logged but never passed to MetaWorld. This
test may report structured-output validity, latency, tokens, fail-closed events,
and representative reasoning. It cannot report recovery improvement, compare
model accuracy, write memory, or authorize validation/held-out execution.
