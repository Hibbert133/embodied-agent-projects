# ProbeMem: Verification-Grounded Scientific Memory for Online Embodied Agents

Protocol: `online_llm_scientific_memory_v2`
Status: `DEVELOPMENT`

## Research question

Can a tool-grounded online LLM embodied agent improve failure recovery over a
chronological deployment stream by turning freshly verified interaction into
reusable intervention principles, while requesting additional evidence when
retrieved knowledge is uncertain or contradicted?

The research object is an attempt-level decision agent above the fixed
`SawyerPushV3Policy`. The LLM may interpret leakage-safe physical evidence,
invoke registered tools, select bounded intervention skills, predict outcomes,
and explain decisions. It may not emit continuous controls, inspect injected
fault truth, update policy weights, or modify the experiment protocol.

## Scientific motivation from v1

The immutable budgeted-evidence v1 experiments established useful constraints:

1. selective fixed-probe allocation reduced interaction while preserving
   mechanism diagnosis;
2. mechanism diagnosis did not reliably identify intervention utility;
3. short candidate probes could mis-rank full-rollout recovery;
4. skill-grounded LLM interfaces were more reliable than raw action proposals.

ProbeMem therefore changes the unit of learning from an unverified diagnosis to
a verified, action-conditional intervention claim. These v1 results and
artifacts remain historical evidence and are not overwritten by v2.

## Online loop

```text
Initial rollout
-> StructuredEvidenceState
-> retrieve earlier verified episodes/principles
-> reason about applicability and evidence sufficiency
-> CONTINUE / REQUEST_DIAGNOSTIC_PROBE / ABSTAIN
-> optional registered probe
-> select one bounded skill
-> predict outcome
-> fresh verification rollout
-> compare prediction with outcome
-> immutable audit
-> later: deterministic promotion to verified memory
```

Adaptation occurs between rollout attempts, not at every low-level control
timestep. Each case permits one initial rollout, at most one 64-step registered
probe, and at most one 500-step fresh verification rollout.

## Memory layers

- Layer 0, immutable interaction audit: every valid, invalid, failed, and
  inconclusive decision and execution is retained for research audit.
- Layer 1, verified episodes: only `fresh_verification == ACCEPTED` can become
  actionable episodic memory.
- Layer 2, working hypotheses: development-only, unverified claims that cannot
  control held-out execution.
- Layer 3, verified principles: human-readable conditional intervention claims
  promoted only by frozen deterministic support and contradiction gates.

Phase B implements Layer 0 and a versioned **empty** retrieval snapshot. It does
not implement or claim memory-based improvement.

## Phase sequence

1. **A — protocol and versioned scaffold**: preserve v1, freeze v2 namespaces,
   tool contracts, seed partitions, budgets, and artifact provenance.
2. **B — tool-grounded online LLM smoke**: validate constrained decisions,
   fail-closed behavior, fresh verification, and complete API/interaction audit.
3. **C — verified episodic baseline**: compare stateless, raw episodic, and
   accepted-only chronological retrieval.
4. **D — scientific principles**: generate development hypotheses and promote
   or reject them through deterministic evidence gates.
5. **E — resonance-triggered evidence**: request the registered probe when
   principle predictions conflict with current visible evidence.
6. **F — frozen sequential evaluation**: one immutable held-out execution after
   prompt, schemas, promotion rules, and memory rules are frozen.

Later phases are blocked until their predecessor's promotion gate is evaluated.
Negative and incomplete results are retained without held-out retuning.

## Current execution status

Phase B passed its development-only constrained-tool integration gate. An
initial Phase-C run stopped at 54/60 method-cases under host commit/pagefile
exhaustion and remains an immutable incomplete artifact. After a restart, the
registered no-API endurance preflight completed 100 environment lifecycle
cycles and 20 full rollouts, enabling a new immutable run.

The replacement Phase-C run completed the registered stateless, raw episodic,
and accepted-only comparison on all seeds 720–739. Ten of 20 paired episodes
required online decisions. All three methods obtained 5/10 accepted
verifications and selected the same intervention on all operational pairs. Raw
retrieval was cited in 9/10 cases and verified retrieval in 8/10, but neither
changed an intervention or verification outcome. Chronology, leakage, budget,
and structured-output audits all passed. This completed development result
supports a narrow negative conclusion—retrieval alone was behaviorally inert
while adding context cost—not method equivalence or a memory benefit. Phase D
is not promoted by this result.

The registered post-hoc decision-trace audit uses no new API calls or robot
rollouts. Raw retrieval differed from the stateless predicted verification
status in 6/10 operational cases (2 improved and 4 worsened exact prediction
matches), and verified retrieval changed post-probe confidence in 4/10. All
post-probe mechanism hypotheses nevertheless collapsed to `stable_bias`, and
all methods chose `BOUNDED_PLANAR_COMPENSATION`. Independent model sampling is
a confound, so these differences are descriptive associations. The audit
motivates an action-discriminative intervention-utility contract before any
principle-promotion experiment.

## Scope

The first result keeps one task, a fixed low-level policy, one registered probe,
two intervention families, structured state evidence, and fresh verification.
It excludes RGB perception, VLA/RL training, policy-weight updates, multiple
robot embodiments, unrestricted coding agents, and claims of real-world safety.

## Phase B execution

Activate the project virtual environment, validate the committed implementation,
then create a new immutable run directory:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
python scripts/generate_probemem_v2_manifest.py
```

The manifest command prints the unique path used by the online runner. On
Windows, the local DPAPI-protected API configuration can be loaded without
placing credentials in the command or repository:

```powershell
.\scripts\run_probemem_v2_smoke.ps1 `
  -Manifest outputs\probemem_v2\runs\<run-id>\manifest.json `
  -ApiTimeout 300
```

The smoke scans seeds 700--719 in a fixed five-condition cycle and stops after
the first five failed initial rollouts. This stopping rule does not inspect
recovery outcomes. Timing runs do not render video.
