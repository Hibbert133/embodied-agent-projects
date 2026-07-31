# ProbeMem v2 Phase-C Verified Episodic Memory Smoke

Source run: `probemem_v2_smoke_20260731T091458Z_ee38f29c0731`

Source manifest: `a76e003d13229e4932eae907b14c6fe67e5dc4a9cce7971ae4c9f063e327503b`

## Objective

Validate the storage and chronology boundary required before comparing stateless,
raw episodic, and verified episodic online Agents. This smoke reuses real Phase-B
verification records and makes no additional API calls or robot rollouts.

## Real result

- Records preserved in the immutable interaction audit: 5.
- Freshly accepted records promoted to verified episodic memory: 4.
- Rejected records retained only in audit: 1.
- Chronology violations: 0.
- Oracle leakage events: 0.

The rejected stochastic retry from seed 703 remains available to the
development-only raw retrieval ablation but is absent from operational verified
memory. Accepted compensation episodes from seeds 700, 701, 705, and 707 enter
verified memory only after their fresh rollout returned `ACCEPTED`.

## Interface semantics

Each retrieval query is formed from seven schema-v2 Agent-visible values:
progress, final distance, temporal uncertainty, phase inconsistency, x/y drift,
and normalized residual norm. Retrieval at episode `t` is restricted to records
with `source_episode_id < t`. The current or future verification result is never
part of the query.

Raw episodic retrieval is explicitly marked development-only and may expose
earlier negative records for an ablation. Verified retrieval contains only
accepted records. Neither path automatically executes the retrieved skill; the
online Agent must still make a bounded decision and obtain fresh verification.

## Interpretation

This result validates memory hygiene, not memory benefit. Phase C still requires
a chronological development comparison using identical cases and budgets for:

1. stateless online LLM;
2. online LLM plus raw episodic retrieval;
3. online LLM plus accepted-only verified episodic retrieval.

Principle abstraction and resonance remain blocked until that comparison is
stable and its positive or negative result is recorded.
