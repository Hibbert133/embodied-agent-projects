# ADR: Online action-conditioned regime memory

## Decision

Use compact repeated-probe evidence, registered discrete skill semantics, fresh
verification, and action-separated chronological outcome summaries. Preserve
all executed outcomes in audit/statistical memory while exposing accepted cases
separately as verified examples.

## Consequences

State similarity can generate retrieval candidates but cannot directly choose
an action. Current/future outcomes, unselected paired candidates, condition
labels, perturbation parameters, and host thresholds never enter Agent inputs.
Memory updates only after the selected skill receives fresh verification.
