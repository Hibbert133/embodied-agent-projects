# Design Review: Active-Evidence Embodied Research Agent

## What changed

The repository now presents one research question: how an embodied agent decides
what evidence is missing after failure and tests mechanism hypotheses through
bounded interaction. The README, research plan, architecture, terminology, and
reproduction guide use this question as the organizing principle.

Core execution code was physically separated from research reasoning:

- rollout executes environments and records results;
- trajectory owns aligned schema-v2 records and Agent/Oracle projections;
- probe owns authorization contracts and the existing directional implementation;
- diagnosis and uncertainty represent hypotheses, revisions, and evidence decisions;
- planner and verification separate proposed interventions from acceptance;
- memory exposes a verified-only contract without persistence or retrieval logic;
- evaluation and visualization define research artifact schemas.

Compatibility facades preserve existing rollout, trajectory-view, and directional-
probe import paths. Historical scripts and reports remain reproducible.

## Why the direction is scientifically stronger

The previous repository could demonstrate components—perturbation, diagnosis,
intervention, online model calls—but did not force a scientific relationship among
them. The new lifecycle makes four falsifiable commitments:

1. A probe must target declared uncertainty and consume an explicit budget.
2. A hypothesis must retain supporting and contradicting evidence provenance.
3. A corrective intervention must state its predicted effect and verification
   criteria before execution.
4. An experience cannot enter memory unless verification is accepted.

This moves the project from passive failure labeling toward experimental design by
an embodied agent. It also makes negative results informative: the existing
candidate-ranking reversal now motivates repeated uncertainty-aware evidence rather
than another unstructured model prompt.

## Information hygiene

`EvidencePacket` recursively rejects perturbation truth and action audit fields.
Oracle views remain valid for post-hoc scoring and controlled simulator setup but
cannot enter uncertainty, probe planning, hypothesis revision, or intervention
planning. The lifecycle state machine rejects skipped evidence decisions and memory
updates before accepted verification.

## API credential boundary

Online wrappers share a local credential loader. A one-time setup command stores a
DPAPI-encrypted SecureString in a Git-ignored file tied to the current Windows user.
Wrappers expose the decrypted key only through process environment variables and
restore the prior environment in `finally`. Python modules, prompts, CSV, JSONL,
reports, and Git never read the credential file directly.

No credential was available during this refactor, so no real API request was made.
DPAPI round-trip, script parsing, environment cleanup, missing-config failure, mock
adapters, and tracked-secret scanning provide the architecture-level evidence.

## Compatibility evidence

The refactor was checked with the complete unit suite, recursive Python compilation,
dependency validation, Git whitespace validation, MetaWorld installation/rendering,
the original video demo, and a real one-episode evaluation. The smoke demo produced
a valid MP4 and schema-v2 JSONL. Seed 100 evaluation succeeded in 63 steps. These are
regression observations, not new research performance claims.

## Experiments enabled by the redesign

1. **Evidence gating:** never probe vs always probe vs uncertainty-gated probe under
   identical failure and interaction budgets.
2. **Probe selection:** directional, repeated-action, and contact probes compared by
   uncertainty reduction per environment step.
3. **Hypothesis calibration:** confidence before/after evidence versus post-hoc audit
   correctness, with reliability diagrams and proper scoring rules.
4. **Intervention verification:** accepted/rejected/inconclusive outcomes compared
   against task improvement and false acceptance rate.
5. **Adaptive budget allocation:** decide whether to collect another paired
   stochastic realization or execute the currently preferred intervention.
6. **Verified experience:** measure whether accepted experience reduces later probe
   cost without increasing unsupported interventions.

## Remaining limitations

The architecture is not itself an algorithmic contribution. The threshold evidence
policy is a transparent reference for testing and future ablation, not a learned
uncertainty estimator. Only the existing directional probe has an implementation.
Memory has no backend, and no new online Agent result was produced. Claims remain
limited to MetaWorld `push-v3`, controlled faults, and a scripted low-level policy.
