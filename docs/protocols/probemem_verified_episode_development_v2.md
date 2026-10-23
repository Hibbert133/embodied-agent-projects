# ProbeMem Phase C: Verified Episodic Retrieval Development Protocol

Status: DEVELOPMENT

Source Phase-B manifest:
`a76e003d13229e4932eae907b14c6fe67e5dc4a9cce7971ae4c9f063e327503b`

## Question

Does chronological retrieval of earlier freshly accepted recovery episodes give
the online LLM a more reliable intervention context than either no memory or raw
retrieval that mixes accepted and rejected episodes?

This phase tests episodic retrieval only. It does not generate principles,
measure resonance, update model weights, or support a held-out memory claim.

## Methods

1. stateless online LLM with an empty memory snapshot;
2. raw episodic retrieval, explicitly development-only, including earlier
   accepted, rejected, and inconclusive verification records;
3. verified episodic retrieval containing only earlier `ACCEPTED` records.

All methods use identical registered tools, intervention skills, case order,
failure configuration, and environment budgets. Retrieval may inform a decision
but never executes a skill automatically.

## Chronology and leakage

Development stream seeds are 720--739. At episode `t`, retrieval may access only
records with `source_episode_id < t`. Future records, Oracle fault fields,
condition labels, perturbation parameters, and evaluator outcomes from the
current episode are forbidden. Accepted memory is written only after fresh
verification completes.

Raw retrieval is an ablation, not operational memory. It is never exposed to a
future held-out Agent. Rejected and inconclusive records remain in the immutable
audit but cannot enter verified actionable memory.

## Registered similarity baseline

The first baseline uses a deterministic normalized Euclidean distance over seven
Agent-visible features: progress, final distance, temporal uncertainty, phase
inconsistency, x/y drift estimates, and normalized residual norm. Scales are
fixed in the executable config before collection. No learned embedding or Oracle
mechanism label is used.

## Required outputs

Each method must record the chronological memory snapshot, retrieved record IDs
and distances, selected skill, prediction, fresh verification, environment-step
cost, API latency/tokens, and full manifest provenance. Analysis must report
memory coverage, retrieval hit rate, rejected-record exposure for the raw
ablation, recovery outcome, and interaction cost over episode index.

## Frozen development execution

The executable stream is 20 seeds (720–739) crossed with a five-condition
cycle. The three methods share each initial rollout and then maintain separate,
chronological memory states. The registered upper bounds are 120 API calls
(at most two per method-case) and 1064 environment steps per method-case:
500 initial, 64 probe, and 500 reserved for fresh verification. Randomness for
the initial rollout, diagnostic probe, fresh verification, and stochastic retry
uses distinct recorded namespaces.

This is a development comparison, not a held-out result. Seeds 900–979 remain
untouched. The immutable manifest must be generated from a clean committed
worktree before execution, and every output row must reference that manifest.

Phase D principle abstraction remains blocked until this comparison is stable
and its result—positive or negative—is preserved.
