# ProbeMem v2 Phase-B Promoted Tool-Grounded Smoke

Protocol: `online_llm_scientific_memory_v2`

Run: `probemem_v2_smoke_20260731T091458Z_ee38f29c0731`

Manifest: `a76e003d13229e4932eae907b14c6fe67e5dc4a9cce7971ae4c9f063e327503b`

Source commit: `ee38f29c0731219c8810f12b58bbea9685ee3e85`

## Research question

Can the constrained online LLM interface complete an attempt-level sequence from
visible rollout evidence through optional probing, bounded skill selection, and
fresh verification, while the deterministic host preserves leakage and budget
invariants?

This five-case development smoke tests integration, not comparative performance.
Memory retrieval is a versioned empty snapshot in every case.

## Real result

- Collection population: 8 units, seeds 700--707.
- Operational failed initial rollouts: 5; initial successes: 3.
- GLM-5.2 calls: 9.
- First-pass structured validity: 5/5 (100%).
- Probe requests: 4/5; registered probe cost: 64 steps per request.
- Direct intervention without probe: 1/5.
- Fresh verification: 5/5.
- Accepted verifications: 4/5.
- Rejected verifications: 1/5.
- Invalid skill executions, leakage events, and budget overruns: 0.
- Total environment steps across collection: 3,899.
- Promotion evaluator: **PROMOTED**.

The four accepted cases used `BOUNDED_PLANAR_COMPENSATION` after registered
probe evidence. Their seeds were 700, 701, 705, and 707. Seed 703 selected
`INDEPENDENT_STOCHASTIC_RETRY` without probing; its fresh verification was
rejected. This negative case is retained because it demonstrates that a fluent
online decision is not accepted without physical verification.

## Causal interpretation

The result supports three narrow claims:

1. a skill-grounded LLM can invoke a real diagnostic interaction and then choose
   a bounded skill using only Agent-visible evidence;
2. host-owned provenance avoids spending reasoning calls on deterministic IDs;
3. fresh verification separates plausible explanations from successful physical
   interventions.

It does not establish that GLM-5.2 outperforms deterministic reasoning, that
probing improves recovery, or that memory produces self-improvement. Those
claims require Phase C chronological comparisons and later frozen evaluation.

## Artifacts

The immutable run directory contains `manifest.json`, `results.csv`,
`interaction_audit.jsonl`, schema-v2 initial trajectories, `summary.json`, and
`promotion_evaluation.json`. Representative verification videos are generated
separately from the exact recorded execution configuration so rendering does not
contaminate timing.

## Promotion decision

Phase B passes its integration gate. Phase C may implement an accepted-only,
chronological verified episodic baseline. Principle abstraction, resonance,
held-out evaluation, and memory-benefit claims remain out of scope until their
own protocols are frozen and evaluated.
