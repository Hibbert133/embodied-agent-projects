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

The first `InterventionUtilityRecord` audit binds the post-probe Agent-visible
signature to the predicted outcome, executed bounded skill, and fresh observed
outcome. Host-derived labels produced 5 supported, 3 unresolved, and 2
contradicted executions, with 5 matched predictions and 5 negative surprises.
All 10 records used only `BOUNDED_PLANAR_COMPENSATION`; consequently they audit
resonance for an executed action but cannot rank compensation against retry.
Schema-v1 utility records are development-only, non-actionable, and ineligible
for principle promotion.

The next development protocol freezes a paired evaluator collection on seeds
740--759. For every failed initial rollout, compensation and independent retry
receive the same initial state, registered probe evidence, and common
verification random stream. The second verification is evaluator-only and is
not presented as online Agent behavior. This collection tests whether the
13-feature Agent-visible applicability signature is action-discriminative
before any hypothesis or principle generation is enabled.

The paired run completed 20/20 initial units and 10 complete operational pairs.
Compensation achieved 9/10 accepted recoveries; retry achieved 0/10. The only
retry utility win occurred when both skills were rejected and retry merely
avoided harmful compensation. No stochastic-noise rollout failed initially,
leaving no operational noise cases. This is an
`INSUFFICIENT_ACTION_UTILITY_DIVERSITY` development result, not evidence for a
selector, scientific-memory principle, or held-out promotion.

The registered label-blind noise extension then scanned 58 fresh initial
rollout units and stopped at 20 operational paired cases without inspecting
candidate outcomes. Compensation was accepted in 10/20 cases, retry in 14/20,
and an evaluator-only per-case Oracle could choose an accepted candidate in
16/20. The partitions were 2 compensation-only, 6 retry-only, 8 both accepted,
and 4 neither. This establishes the action-utility diversity needed to design a
selector candidate, but it does not validate one. The feature ranking was
post-hoc on only 8 decisive cases; Phase D remains blocked until a separately
specified candidate is evaluated on fresh development data.

The next development-validation protocol freezes exactly one candidate before
using seeds 840--899: choose independent retry when the Agent-visible
`probe_relative_bias_std <= 2.0`, otherwise choose bounded compensation. The
rounded threshold is explicitly post-hoc from the preceding development run.
It is compared once against always retry, always compensation, and the
evaluator-only Oracle; failure is retained and cannot trigger threshold
revision on this stream.

The fresh validation scanned 56 initial units and stopped at 20 operational
pairs. The selector chose retry 12 times and compensation 8 times, recovering
13/20. Always retry recovered 11/20, while always compensation recovered 14/20.
The selector gained three and lost one case relative to retry, but gained one
and lost two relative to compensation. Because the registered no-loss gate
against compensation failed, this is a retained negative result. Phase D is
still blocked and no threshold revision, principle generation, or held-out run
is permitted from this result.

A post-hoc causal audit then examined the seven exclusive-recovery cases
without new rollout or API interaction. The selector chose correctly in four
and incorrectly in three. Because compensation-only outcomes occur below the
threshold and a retry-only outcome occurs far above it, the relationship is
non-monotonic rather than merely sensitive to threshold rounding. This finding
motivates richer verification-grounded applicability evidence, but does not
authorize feature search, threshold revision, or Phase-D promotion on the same
data.

A chronological retrieval-feasibility audit also tested whether the full
13-feature signature rescued the failure. It standardized eight earlier
decisive references using reference-only statistics and queried seven later
decisive cases. Nearest-reference skill agreement was only 2/7, versus 4/7 for
the frozen single-feature rule, with four compensation-only queries mapped to
retry. This is consistent with raw episodic retrieval becoming dogmatic under
a changed outcome mixture. However, reference skill labels came from
evaluator-only paired counterfactuals, so the result is a separability audit,
not actionable Verified Episodic Memory or online self-improvement.

The repository therefore separates evaluator analysis from legitimate memory
construction. A new post-probe episode schema exported only the 13
selector-chosen interventions that received fresh `ACCEPTED` verification: 7
retry and 6 compensation. Three inconclusive and four rejected selected
outcomes, plus every unselected counterfactual, remain outside actionable
memory. Operational retrieval is deliberately disabled pending a separately
frozen applicability/abstention protocol, so this snapshot is infrastructure,
not a memory-benefit claim or Phase-D promotion.

The next Phase-C development extension freezes a coverage-aware gate over this
snapshot. It uses snapshot-only normalization, a 90th-percentile leave-one-out
coverage radius, three-neighbor unanimous skill support, and a full 500-step
verification reservation. Queries outside coverage or with conflicting local
experience must abstain. The rule is committed before fresh seeds 980--1059;
held-out seeds 900--979 remain untouched, and Phase D stays blocked regardless
of this extension until its own promotion requirements are satisfied.

The fresh development run produced a strict negative result. Among 20
operational queries, the gate used memory twice and abstained 18 times: 14 for
conflicting nearby verified skills and 4 outside coverage. Neither memory use
was accepted, and in both cases the alternative intervention was accepted.
Thus accepted-only provenance, geometric coverage, and unanimous local support
did not establish transferable action utility. The registered gate failed;
parameters remain frozen, held-out seeds remain untouched, and Phase D remains
blocked.

An evaluator-only contradiction audit treated each selected accepted precedent
as an implicit prediction that the same skill would again be `ACCEPTED`. The
two memory uses produced one `INCONCLUSIVE` and one `REJECTED` fresh result.
Both were inside the registered coverage radius with unanimous neighbor
support. Nearest-neighbor coverage is therefore not considered a valid
resonance model or a verified intervention principle.

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
