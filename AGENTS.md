# AGENTS.md

## Project Mission

This repository studies budgeted active evidence gathering for an embodied research agent operating above a fixed low-level robot policy.

The first-version research question is:

> Given a fixed diagnostic probe, can the Agent decide whether and when the expected diagnostic value justifies its interaction cost?

The Agent performs attempt-level online adaptation:

```text
INITIAL_ROLLOUT
→ BUILD_EVIDENCE
→ ALLOCATE_PROBE_BUDGET
→ OPTIONAL_PROBE
→ UPDATE_BELIEF
→ SELECT_INTERVENTION
→ FRESH_VERIFICATION
→ OPTIONAL_MEMORY_WRITE
```

The project does not claim step-level planning, continuous control, multi-probe selection, online policy-weight learning, VLA improvement, or safety-aware planning.

## Source of Truth

Before modifying research logic, read:

1. `RESEARCH_PLAN.md`
2. `docs/research/frozen_execution_plan_v1.md`
3. `docs/protocols/heldout_allocation_v1.md`
4. the active experiment configuration under `configs/autoresearch/`

The frozen protocol and executable config take precedence over comments, prompts, and older reports.

## Current Priority

Execute work in this order:

```text
P0:
StructuredEvidenceState
Agent/Oracle leakage tests
Budget invariants
Frozen held-out evidence allocation
Cost-performance evaluation

P1:
Evidence-grounded intervention
Matched fresh verification
Causal-chain reporting
Application-ready research artifact

P2:
Verified Episodic Memory proof of concept

P3:
Frozen GLM qualitative pilot
Additional visualizations
```

Do not begin P2 or P3 before the required promotion gates for earlier phases are evaluated.

## Frozen First-Version Constraints

Do not modify without explicit user authorization:

* environment: MetaWorld `push-v3`;
* low-level policy: fixed `SawyerPushV3Policy`;
* held-out seeds: 330–339;
* registered perturbation conditions;
* frozen phase threshold: `0.91612970415368`;
* registered probe maximum cost: 64 environment steps;
* initial rollout maximum: 500 steps;
* reserved fresh-verification budget: 500 steps;
* total case budget: 1064 steps;
* maximum one diagnostic probe;
* maximum one corrective verification rollout;
* evidence feature definitions;
* matching rules;
* evaluator-only label definitions;
* promotion gates.

Do not retune against held-out results.

If a frozen protocol cannot be executed, stop that experiment, preserve the negative or incomplete result, and report the blocking issue. Do not silently relax the protocol.

## Evidence and Leakage Rules

`StructuredEvidenceState` must be built only from schema-v2 Agent View data that are causally available at decision time.

Reject direct or nested Oracle information, including:

* perturbation labels;
* injected bias axes or magnitudes;
* executed perturbed actions unavailable to the Agent;
* future verification results;
* evaluator-only probe-need labels;
* Oracle conclusions.

Leakage checks must fail closed.

Evaluator-only labels must never enter:

* Agent View;
* StructuredEvidenceState;
* deterministic decision rules;
* GLM payloads;
* threshold fitting;
* memory retrieval signatures.

## Decision Semantics

First-version decisions are:

```text
CONTINUE
REQUEST_DIAGNOSTIC_PROBE
ABSTAIN
```

`REQUEST_DIAGNOSTIC_PROBE` is valid only when:

```text
remaining_budget
>= registered_probe_cost
+ minimum_reserved_verification_budget
```

Otherwise return `ABSTAIN`.

Successful initial rollouts use:

```text
decision_required = False
evidence_decision = CONTINUE
adaptation_cost = 0
```

Do not count this as a successful active-allocation decision.

## Verification and Memory

Every corrective intervention must be evaluated with a fresh rollout.

Verification outcomes are:

```text
ACCEPTED
INCONCLUSIVE
REJECTED
```

Only `ACCEPTED` experiences may enter Verified Episodic Memory.

Never store:

* rejected outcomes;
* inconclusive outcomes;
* unverified GLM hypotheses;
* Oracle-derived conclusions;
* records from future episodes.

Memory retrieval must be chronological and traceable to earlier accepted records.

## Experiment Integrity

Before the first held-out run:

1. commit the implementation and frozen configuration;
2. ensure the worktree is clean;
3. generate an immutable experiment manifest;
4. generate a new run ID;
5. write results to a new output directory;
6. never overwrite previous held-out artifacts.

Every result artifact must reference:

* experiment run ID;
* manifest ID;
* source Git commit.

## GLM Role

GLM-5.2 is a frozen qualitative reasoning-layer pilot only.

It must not:

* control continuous actions;
* access Oracle View;
* access frozen threshold values;
* access perturbation truth;
* replace deterministic results after failure.

Invalid output, timeout, or retry exhaustion must fail closed to `ABSTAIN` and be reported.

Do not draw statistical model-performance conclusions from the maximum ten-call pilot.

## Reporting Language

User-facing research progress and experiment reports default to Chinese, following
the user's reporting preference. Preserve executable commands, code identifiers,
run IDs, hashes, and original scientific data. Use the same data and conclusions
when localizing figures or prose.

## Required Validation

Run inside the project virtual environment:

```bash
python -m unittest discover -s tests -v
python -m compileall -q src scripts tests
python -m pip check
python scripts/check_tracked_secrets.py --staged
git diff --check
```

Unit-test, secret-check, and diff-check failures block commits.

For `pip check`, distinguish project-introduced conflicts from pre-existing host-environment conflicts. Project-introduced conflicts block commits.

## Git Rules

* Create one local commit per completed phase.
* Do not push or merge without explicit authorization.
* Do not modify global Git or GPG configuration.
* Use `git commit -S` only when cryptographic signing is already configured.
* `git commit -s` is DCO sign-off, not cryptographic signing.
* Preserve negative and incomplete experiment results.

## ProbeMem v2 development overlay

Work on branch `research/probemem-v2` follows
`docs/research/online_llm_scientific_memory_v2.md` and
`configs/probemem_v2/development_smoke_v2.json`. This is a new development
protocol and must not modify budgeted-evidence v1 artifacts or frozen seeds.

In Phase B, the retrieval tools return a versioned empty memory snapshot. The
only valid claim is tool-grounded online integration with leakage, budget,
fail-closed, and fresh-verification audit. Do not describe it as learned memory.
The LLM may select only registered tools and skills; deterministic host code
owns continuous parameters, environment execution, verification, and audit.

## ProbeMem-ACR v3 development overlay

Work on branch `research/probemem-acr-v3` follows
`docs/research/probemem_acr_v3.md` and
`docs/protocols/probemem_acr_development_v1.md`. ProbeMem v2 artifacts and
negative results are immutable inputs, not results to overwrite or reframe.

The first ACR phase is a development-only paired counterfactual feasibility
study. It may implement deterministic action-conditioned outcome estimation
and evaluator resonance, but it must not call an LLM, generate or promote
principles, run validation or held-out seeds, or claim online learning. Paired
counterfactual records are research data and must never be represented as
experience naturally available to a deployed Agent.

Seeds 1100--1199 are a single frozen development run. Estimator and baseline
predictions must be written before the current episode's candidate outcomes
are executed or appended. A failed promotion gate is retained without tuning
or rerunning this seed range.

After the ACR v1 promotion failure, the only authorized successor experiment
is `docs/protocols/probemem_acr_retry_utility_replication_v1.md`. It may execute
only seeds 1400--1499 under registered condition `fault_05` and may test only
the two frozen directional endpoints. It must not fit a threshold, create a
selector, call an LLM, or execute reserved seeds 1500--1599.

That replication has completed and failed its combined gate. Do not extend the
1400--1499 run, fit a selector from it, or execute seeds 1500--1599 under this
protocol. A further experiment requires explicit user authorization and a new
scientific protocol with fresh seeds.

The user subsequently authorized continuation under the new
`docs/protocols/probemem_acr_utility_realization_stability_v1.md` protocol.
It may scan development seeds 1600--1699 and collect six evaluator-only paired
verification realizations for at most 20 failed `fault_05` initial rollouts.
It may estimate target stability only. It must not fit a selector, call an LLM,
write online memory, or execute reserved seeds 1700--1799.

The v1 utility-stability execution stopped after 13 complete cases because a
later failed case could not construct bounded compensation. The partial run is
audit-only. The corrected v2 protocol uses fresh seeds 1800--1899, requires
both registered candidates to be constructible before candidate execution,
and reserves 1900--1999. It retains the same estimands and prohibitions.

The v2 utility-stability run completed and failed its feasibility gate:
candidate winner reversed in 18/20 states and single-realization reliability
was 64.2%, below 70%. Treat one paired outcome as a stochastic sample, not a
stable action label. Do not fit a selector, invoke an LLM, promote a principle,
or execute seeds 1900--1999 from this result. A successor must explicitly model
action-outcome distributions and abstention under a new protocol.

The user authorized that successor as
`docs/protocols/probemem_acr_distributional_memory_development_v1.md`.
It may collect one evaluator-only paired outcome for 40 eligible failures from
seeds 2000--2099 and replay frozen chronological deterministic methods. Each
method may append only its own selected outcome after deciding. Rejected and
inconclusive outcomes are statistical posterior evidence, not actionable
episodic records. Do not call an LLM, fit on this stream, promote principles,
or execute seeds 2100--2199.

That run exhausted its 100 initial units with 39/40 operational cases and is
immutably `INCOMPLETE_POPULATION`; do not extend or replay it. The user then
authorized the separately frozen v2 capacity correction in
`docs/protocols/probemem_acr_distributional_memory_development_v2.md`. It may
scan fresh development seeds 2200--2349 and stop at the unchanged target of 40
eligible failures. It uses the unchanged methods, posterior, abstention rule,
and promotion gate. Do not execute reserved seeds 2350--2499, call an LLM,
promote principles, or tune from either distributional stream.

Distributional v2 completed 40 operational cases and failed both promotion
routes. Posterior greedy exactly matched accepted-only last at 22/40 accepted;
posterior abstention had zero post-exploration coverage. Preserve this negative
result. Do not revise the frozen posterior or abstention threshold on seeds
2200--2349, and do not execute 2350--2499, call an LLM, or promote principles.

The user subsequently authorized the separately registered contextual
feasibility protocol in
`docs/protocols/probemem_acr_contextual_utility_development_v1.md`. It may scan
fresh seeds 2500--2699 for at most 60 eligible failures and compare the frozen
global posterior with Bayesian linear action models over the complete 13-field
Agent-visible signature. Only selected outcomes at earlier episodes may update
each method. Do not select features, retune priors or thresholds, call an LLM,
promote principles, or execute reserved seeds 2700--2849.

That contextual run completed and failed both promotion routes. Contextual
greedy changed 17 decisions but produced 5 helpful and 5 harmful changes, with
no net accepted-recovery gain over the global posterior. Contextual abstention
had zero post-exploration coverage. Do not tune the 13-feature model on seeds
2500--2699 or advance to GLM, principles, validation, or held-out evaluation.

The user then authorized the separately frozen attempt-level feedback protocol
in `docs/protocols/probemem_acr_resonance_second_verification_development_v1.md`.
It may scan fresh development seeds 2850--3049 until 30 first retry
verifications are non-accepted. It compares one registered optional second
verification using only the first verification status. The online protocol has
at most two verification attempts; paired second candidates are evaluator-only.
Do not call an LLM, write memory, tune on the stream, or execute reserved seeds
3050--3199.

The resonance development run completed 75 eligible first attempts and 30
registered second-decision cases. The status-conditioned rule achieved 65/75
accepted versus 63/75 for always-repeat and used fewer total online steps,
passing its preregistered development route. The paired-bootstrap confidence
interval crosses zero, so this is a feasibility signal only. Do not retune on
seeds 2850--3049 or treat this as validation, held-out, memory, LLM, or online-
learning evidence. Reserved seeds remain blocked pending a separately frozen
protocol and explicit user authorization.

The user explicitly authorized the independent validation protocol in
`docs/protocols/resonance_validation_v1.md`. It may execute exactly seeds
3050--3099 followed by 3200--3299 once, using the frozen status-conditioned
rule. Seeds 3100--3199 remain held-out and must not be executed. Validation may
collect paired second outcomes for evaluation only; it must not call an LLM,
write memory, retune the rule, replace the run, or advance on a failed gate.

The immutable validation run completed all 150 initial units but produced only
55 eligible first attempts and 16 second-decision cases, below the frozen 60/25
population minima. It is `INCOMPLETE_FOR_VALIDATION` and cannot be extended or
replaced. Descriptively, the frozen status rule recovered 47/55 versus 50/55
for always-repeat, with more harmful selections and higher cost. Treat the
development signal as not independently replicated. Do not call GLM, write
transition memory, execute held-out seeds, or tune on this validation result.

The user subsequently authorized a fresh development-only verification-feedback
sufficiency audit under
`docs/protocols/probemem_acr_verification_feedback_sufficiency_development_v1.md`.
It may scan seeds 3300--3499 and collect repeated first-retry realizations plus
paired evaluator-only second candidates for at most 30 eligible initial states.
The audit may measure categorical-status stability and preregistered continuous
feedback signals only. It must not fit a selector, call an LLM, write online
memory, execute seeds 3500--3599, or revive the failed validation claim.

That audit completed on 30 eligible states. Seventy percent showed multiple
first statuses across four realizations, and the frozen status rule tied
always-repeat. Preregistered continuous progress produced raw AUC 0.798 on 20
evaluator-only exclusive-recovery branches. This is a signal for a separately
frozen prospective development protocol only; no selector, GLM, memory,
validation, or held-out phase is authorized from the audit itself.

The user then authorized the separately frozen prospective continuous-feedback
development protocol in
`docs/protocols/probemem_acr_continuous_feedback_development_v1.md`. It may scan
fresh seeds 3500--3799 once and compare a zero-threshold physical-progress rule
with always-repeat, always-switch, and the historical status rule. The rule and
zero threshold are frozen before outcomes. Seeds 3800--3899 and held-out seeds
3100--3199 must not be executed. No LLM, memory, fitting, or validation claim is
authorized.

The prospective zero-progress run completed 30 second-decision cases and failed
its gate. The rule exactly reproduced the old status mapping and recovered
70/85 eligible first attempts versus 74/85 for always-repeat, with 11 versus 7
harmful selections. Preserve this negative result. Do not tune a nonzero
threshold on seeds 3500--3730 or advance to GLM, memory, validation, or held-out
execution. A successor requires a new question rather than another threshold.

The evaluator-only retry-value identifiability audit subsequently reused that
immutable run without new environment interaction. First progress, negative
final distance, and categorical status obtained ROC AUC values 0.464, 0.488,
and 0.457 for whether an independent second retry was accepted. These scores do
not support selective retry allocation. Do not choose a threshold from the
descriptive frontier, rerun the source stream, or treat paired counterfactuals
as online experience. GLM, memory, validation, and held-out execution remain
blocked.

A state-stratified audit then controlled for fixed initial-state difficulty on
the earlier repeated-realization run. Across 14 informative within-state
positive-negative pairs, all three registered feedback scores had conditional
AUC 0.500, with one-sided permutation p-values 0.589--0.662. This provides no
evidence that one independently seeded retry predicts the next. Do not add
another scalar threshold or use these evaluator counterfactuals as online
memory. A successor must change the causal evidence design, such as a persistent
latent execution context, under a separately frozen protocol.

The user explicitly authorized GLM acceleration as a shadow-only integration
smoke. Protocol `docs/protocols/probemem_acr_glm_shadow_smoke_v1.md` may call
GLM-5.2 on exactly three allowlisted development rows with at most six calls.
Every output is non-executing and cannot support a performance, memory,
validation, or held-out claim. This exception tests the reasoning interface; it
does not lift the scientific promotion block.

The user then authorized a fresh persistent-execution-regime feasibility
protocol in
`docs/protocols/probemem_acr_persistent_regime_development_v1.md`. It may cross
task seeds 3900--3949 with registered `fault_01` stable bias and `fault_05`
stochastic noise, using the historical repeated-probe consistency threshold
without retuning. Paired compensation and retry outcomes are evaluator-only;
the Agent decision must be written before either outcome is collected. Seeds
3950--3999 and held-out seeds 3100--3199 remain untouched. This run must not
call GLM or write memory. Passing its frozen gate authorizes only a separately
frozen development GLM action-selection experiment; failure must be preserved
without threshold tuning.

The persistent-regime run passed that gate on 40 operational cases. The user
therefore authorized the qualitative pilot in
`docs/protocols/probemem_acr_persistent_glm_pilot_v1.md`. It may make exactly
one GLM-5.2 call on each of ten preregistered, condition-balanced development
cases. Condition identity is evaluator-only and must not enter the payload.
The model must not see the frozen threshold or paired outcomes, and its choices
must not execute. This pilot may report validity, decisions, matched audit,
latency, tokens, and disagreement only; it cannot support a statistical GLM,
memory, validation, or held-out claim.

That pilot completed with 9/10 valid structured outputs and one fail-closed
case. GLM selected compensation on all five stable-bias cases, but abstained on
four of five stochastic-noise cases; all four abstained cases had an accepted
evaluator-only retry. Descriptively, its shadow choices corresponded to 4/10
accepted outcomes versus 8/10 for the frozen deterministic rule. Preserve this
negative reasoning-to-action result. Do not revise the prompt and rerun these
ten cases. A successor may test a compact causally sufficient evidence summary
and explicit registered-skill semantics only on fresh development cases under
a separately frozen protocol. Memory, validation, and held-out execution remain
unauthorized.

Branch `research/probemem-online-v4` follows
`docs/research/probemem_online_v4.md`. Gate A may use fresh seeds 4000--4099 to
collect exactly 15 eligible stable-bias and 15 eligible stochastic-noise cases,
then run the frozen 90-call three-interface shadow ablation with at most 15
repair calls. GLM decisions cannot execute. Gate B is blocked until Gate A's
registered promotion gate is evaluated. Seeds 4100--4599 retain their v4
registry roles and must not be executed early; historical held-out and reserved
partitions remain blocked.

Gate A run `probemem_online_interface_ablation_20260803T072817Z_1c19c23bafb3`
passed its frozen promotion gate. Gate B may collect the outcome-blind bootstrap
defined in `configs/probemem_online/bootstrap_memory_v1.json`. Gate B stores
exactly one manifest-assigned selected action per episode; unselected paired
outcomes are prohibited. Gate C, mixed-regime execution, validation, held-out,
and principle generation remain blocked until Gate B integrity is recorded.

Gate C run `probemem_online_gate_c_20260803T095434Z_f346d23912a9` completed 60
operational cases and failed its promotion gate. Full online Memory recovered
41/60 versus 40/60 for Stateless GLM and 43/60 for the frozen variance rule.
Its 12 action changes contained four helpful, three harmful, and five tied
changes; the paired recovery interval crossed zero and post-shift recovery was
worse than Stateless GLM. Preserve this result. Do not advance to principles,
validation, or held-out execution.

The no-rollout causal audit in
`reports/probemem_online_gate_c_action_change_audit.md` found that three of the
four helpful changes merely restored the frozen deterministic action, whereas
all three harmful changes overrode high-confidence retry decisions. Do not fit
a numeric ambiguity band or modify the Gate C prompt from these 12 cases.

The user authorized the separately registered development successor in
`docs/protocols/probemem_online_selective_override_development_v1.md`. It may
use fresh seeds 4500--4599 once, after implementation is committed and an
immutable manifest is generated. High-confidence decisions are defined by
leave-one-probe-repeat-out stability and must bypass the API. Only ambiguous
cases may invoke the unchanged constrained GLM and action-conditioned Memory.
An override requires global/recent action-preference agreement; conflict falls
back to the frozen deterministic rule or the separately reported abstention
variant. Seeds 4600--4699 remain reserved. No validation, held-out execution,
principle generation, prompt retuning, or outcome-fitted ambiguity threshold is
authorized.

Selective-override run
`probemem_online_selective_override_20260804T064750Z_1107f99883b4` reached 40
operational cases but only three ambiguous cases against the frozen minimum of
ten. It is `INCOMPLETE_POPULATION`; the promotion gate was not evaluated. The
primary Memory-fallback method tied the frozen variance rule at 34/40 accepted,
made two outcome-tied action changes, and used nine API calls. Preserve the
92.5% descriptive call reduction without claiming Memory benefit. Do not
extend or replace seeds 4500--4599, widen the ambiguity definition, execute
reserved seeds 4600--4699, or advance to validation, held-out execution, or
principles. A successor requires explicit authorization and a new scientific
question with fresh seeds.

The user explicitly authorized the engineering/research feasibility successor
in `docs/protocols/probemem_verifier_demo_v1.md`. It may scan fresh development
seeds 4700--4749 once and compare Frozen, Always-on, and Budgeted deterministic
history-aware verification on a shared paired evaluator stream. Each method may
write only its selected fresh outcome to its own chronological memory. Seeds
4750--4799 remain reserved. The ambiguity band and override guard are fixed
before execution and must not be tuned from Demo outcomes. The registered run
must not call GLM, run validation or held-out seeds, generate principles, add a
third skill, or support a statistical superiority claim.

That Demo completed all 50 initial units with 21 operational cases and failed
its gate. Budgeted recovered 15/21 versus 16/21 for the frozen rule, called the
verifier on 11/21 cases (52.4%), and made zero helpful, one harmful, and one tied
override. The guard blocked four harmful alternatives, but this did not produce
net benefit. Preserve the negative result and do not tune the ambiguity band,
posterior, coverage, contradiction, or confidence guards on seeds 4700--4749.
Do not execute reserved seeds 4750--4799 or advance to GLM, validation,
held-out execution, or principles from this result.

A subsequent no-new-rollout failure-localization audit attributed the 11 calls
to five ambiguity-band, seven recent-contradiction, and one memory-conflict
trigger occurrences, with overlaps. The two authorized overrides were one
harmful and one tied; nine blocked alternatives were one helpful, four harmful,
and four tied. This is descriptive mechanism evidence only. Do not remove a
trigger, fit a new band, or revise posterior/guard parameters from this audit.

The user subsequently authorized Calibrated Verifier v2 under
`docs/protocols/probemem_calibrated_verifier_v2.md` on the existing
`research/probemem-verifier-demo-v1` branch. Calibration may scan seeds
4800--4899 only and must stop before prospective development if population or
threshold-selection requirements fail. Prospective seeds 4900--5099 remain
blocked until a successful calibration result, frozen thresholds, hashes, and
clean committed implementation exist. Seeds 5100--5299 remain reserved. The v1
Demo artifacts and negative results are immutable. Admission, features,
distance, prior, top-k, skills, GLM prohibition, validation, held-out, and
principle boundaries remain frozen.

Calibrated Verifier v2 calibration completed all 100 seeds 4800--4899 with 37
operational and 18 exclusive-recovery cases. All integrity counters were zero,
but none of the 4,800 preregistered threshold combinations produced an override:
the default and alternative 95% posterior intervals overlapped in every case.
Weighted pooled Brier (0.167678) was also worse than unweighted v1 (0.166995).
The calibration gate failed with no selected thresholds. Preserve this result;
do not revise the interval level, prior, distance, top-k, grid, or guard on this
stream. Do not execute prospective seeds 4900--5099 or reserved 5100--5299, and
do not advance to GLM, validation, held-out, or principles.

The user subsequently authorized the ProbeMem-SciAgent v1 implementation on
the same branch. Its synthetic pathway audit is metric-ineligible, and its
first live preflight consumed zero seeds and made zero API calls. Do not report
the synthetic audit as recovery evidence or overwrite earlier verifier results.

The separately frozen API Reliability v1.1 shadow protocol in
`docs/protocols/probemem_sciagent_api_reliability_v1_1.md` executed once on
fresh seeds 5850--5899. It reached eight operational cases but produced zero
certified-valid outputs. Three of four calls failed the strict bare-JSON
transport parser; the circuit breaker prevented six later calls. No action
executed and no memory or principle was written. Preserve this failed result
and do not rerun or replace seeds 5850--5899. Seeds 5900--5999 remain reserved.

The user then authorized the single-change API Envelope v1.2 shadow successor
in `docs/protocols/probemem_sciagent_api_envelope_v1_2.md`. Its unique-object
extractor made all four calls transport-valid, including three wrapped JSON
responses, but zero of eight operational outputs passed the complete semantic
certificate. The first localized failure was an unknown probe-justification
code, after which the repair budget and circuit breaker stopped further calls.
No action executed and no memory or principle was written. Preserve this
failed result, do not rerun seeds 6000--6049, and do not execute reserved seeds
6050--6149. A successor must use a separately frozen fresh-seed protocol and
must test a complete capability-token/enum contract without weakening host
certificate validation. Online action execution, recovery claims, validation,
held-out execution, and principle promotion remain blocked.

The separately frozen Capability Contract v1.3 shadow successor in
`docs/protocols/probemem_sciagent_capability_contract_v1_3.md` then executed
once on fresh seeds 6150--6199 and passed its interface gate. All eight
operational outputs were fully certified; all nine calls, including the health
check, were transport-valid and capability-token-valid with zero repairs and
zero integrity violations. No action executed and no memory or principle was
written. All eight decisions requested a micro-probe, so this is evidence that
the complete token contract fixes structured semantic validity, not evidence
of budgeted probe allocation, action quality, or recovery. Preserve this run,
do not rerun seeds 6150--6199, and do not execute reserved seeds 6200--6299.
Under the current qualitative GLM boundary, an online successor requires a
separately frozen protocol that evaluates probe novelty and utility under the
case budget; interface-gate passage alone does not authorize model actions,
validation, held-out execution, memory claims, or principle promotion.

The separately frozen Probe Value v1.4 shadow successor in
`docs/protocols/probemem_sciagent_probe_value_v1_4.md` then executed once on
fresh seeds 6300--6349 and failed its gate. The health check passed and all four
observed API calls were transport-valid and capability-token-valid, but none of
the eight operational outputs passed the complete semantic certificate. Two
responses lacked an object-valued probe-value certificate; the single repair
produced one whose provisional skill contradicted its own probability argmax.
The circuit breaker stopped later calls. No action executed and no memory or
principle was written. Preserve this negative result, do not rerun seeds
6300--6349, and do not execute reserved seeds 6200--6299 or 6350--6449. The zero
admission rate is a fail-closed artifact, not evidence that probes lack value.
A successor requires a separately frozen fresh-seed protocol and should test a
smaller complete quantized value contract without weakening host arithmetic or
semantic validation. Online action execution, recovery claims, validation,
held-out execution, and principle promotion remain blocked.

The separately frozen Quantized Probe Value v1.5 shadow successor in
`docs/protocols/probemem_sciagent_quantized_probe_value_v1_5.md` was stopped
incomplete on fresh seeds 6450--6499 because an operational API request remained
in flight beyond the frozen 300-second SDK timeout. Seven initial trajectories
were created, four operational calls were started, and three operational outputs
were recorded. Two were fully certified. Quantization improved the narrow value
interface: three of four returned operational responses had valid value
certificates, compared with zero in v1.4. However, all three valid partial
assessments still admitted a probe, and the population gate was not evaluated.
No action executed and no memory or principle was written. Preserve this
`INCOMPLETE_TRANSPORT_TIMEOUT_ENFORCEMENT` result; do not rerun or complete seeds
6450--6499, and do not execute reserved seeds 6200--6299, 6350--6449, or
6500--6599. A successor requires a separately frozen protocol, an independently
enforced wall-clock deadline outside the compatibility SDK, and a scientific
change beyond another response-format repair. Online action execution, recovery
claims, validation, held-out execution, and principle promotion remain blocked.

The separately frozen Robust Probe Value v1.6 shadow successor in
`docs/protocols/probemem_sciagent_robust_probe_value_v1_6.md` completed eight
operational cases and all ten allowed calls on fresh seeds 6600--6649. Its
child-process deadline correctly terminated two 210-second calls. Deterministic
post-run reconstruction found 7/8 fully certified outputs, two admitted probes,
five valid rejections, a 25% admission rate, and one probe request blocked by
the robust lower-bound guard. However, the runner summary crashed on a nullable
audit boolean and the timeout output incorrectly carried the prior case's value
assessment. No action consumed that stale field, but it is an audit association
integrity violation, so the formal status is `COMPLETED_GATE_FAILED_INTEGRITY`,
not passage. Preserve the original failed status and corrected no-new-call
analysis; do not rerun seeds 6600--6649 or execute reserved 6650--6749. The code
now binds assessments to current-call audit slices and safely aggregates
optional booleans. This run supports bounded transport and selective-value
mechanism observations only. Online action execution, recovery claims, memory,
principles, validation, and held-out execution remain blocked pending a new
protocol that evaluates actual probe utility.

The user subsequently authorized the separately frozen Micro-Probe Utility
v1.7 development protocol in
`docs/protocols/probemem_sciagent_micro_probe_utility_v1_7.md`. It may scan
fresh seeds 6750--6849 once and execute only Host-admitted registered
micro-probes. Both pre-probe and post-probe decisions must be persisted before
reset-matched paired recovery candidates are collected for evaluator-only
status comparison. The unchanged robust value and capability contracts remain
frozen. Seeds 6650--6749 and all earlier reserves remain blocked; seeds
6850--6949 are newly reserved. This stage must not execute an online recovery,
write memory, update hypotheses or principles, run validation or held-out
seeds, add skills, or claim recovery improvement. Promotion requires at least
one strictly helpful probe, more helpful than harmful probes, and zero audit,
chronology, leakage, budget, or counterfactual-write violations. Failure or
incomplete population is preserved without prompt, gate, probe, or seed tuning.

The frozen v1.7 run completed 12 operational cases from 29 fresh initial
units and failed its gate. Only 7/12 pre-probe outputs were valid; five failed
closed after four audited 210-second hard timeouts, two exhausted repairs, two
value-certificate ordering errors, and the final circuit-open fallback. Two
Host-admitted compensation-response probes both left the action unchanged at
compensation, producing zero helpful, zero harmful, and two
no-decision-benefit probes. Causal-execution integrity counters were zero, and
no online recovery, memory, hypothesis, or principle update occurred. Preserve
this negative result; do not rerun or extend seeds 6750--6849 or execute
reserved 6850--6949. The immutable summary undercounted hard timeouts as zero
because it matched the wrong normalized exception field; corrected no-new-call
analysis records four and the future summarizer has a regression fix. This
reporting defect does not change the already-failed gate. Do not advance to
memory, principles, validation, held-out execution, or another API-format or
calibration revision from this result. A successor requires a new causal
question about decision-changing probe information on separately frozen fresh
seeds.

The user subsequently authorized the separately frozen evaluator-only
Distributional Probe Identifiability v1.8 protocol in
`docs/protocols/probemem_sciagent_distributional_probe_identifiability_v1_8.md`.
It may scan fresh seeds 6950--7099 once until 30 operational failures, collect
both registered micro-probes, and collect four independent paired recovery
realizations per skill. Stopping cannot inspect probe measurements or outcomes.
The fixed probe contrast and distributional decisive margin must not be fitted
or revised. Seeds 6850--6949 remain reserved and seeds 7100--7199 are newly
reserved. This is a prerequisite evidence-identifiability audit only: it must
not call an API, request an Agent decision, execute an online recovery, write
memory, update hypotheses or principles, run validation or held-out seeds, or
claim performance. Failure or incomplete population must be preserved without
score, label, realization-count, gate, or seed tuning.

That v1.8 audit completed 30 operational states from 73 fresh initial units and
failed its gate. Only 9/30 states were distributionally decisive across four
paired realizations per skill (six compensation-superior and three retry-
superior), below both population requirements. The fixed probe contrast had ROC
AUC 0.778 on those nine states, but its stratified bootstrap interval was
[0.389, 1.000] and its full-population Spearman correlation with the acceptance-
rate margin was 0.170. Ten of 30 states exhibited candidate-winner reversals.
All integrity counters were zero; API, Agent, online recovery, memory,
hypothesis, and principle counts remained zero. Preserve this negative result.
Do not rerun, extend, or fit another score on seeds 6950--7099, and do not
execute reserved seeds 7100--7199. Do not restore API calls or advance to
memory, principles, validation, or held-out execution. A successor requires a
new persistent causal evidence design under a separately frozen protocol.

The user subsequently authorized the development-only additional-experiments
protocol in `docs/protocols/probemem_additional_experiments_v1.md`. It may scan
fresh seeds 7200--7399 once in ascending order until 60 operational initial
failures and must keep seeds 7400--7499 reserved. It compares five frozen,
deterministic configurations and may reuse the immutable held-out allocation
artifacts for an evidence-acquisition-policy table. It must not call a GLM,
modify thresholds, expose Oracle fields to a method, share runtime or memory
state across methods, access future or cross-method memory, select cases from
outcomes, resample for category balance, or treat descriptive population
coverage targets as stopping rules. Only accepted, strictly prior, method-owned
records may influence actionable retrieval. The common recovery denominator is
all retained initial failed episodes. This study estimates configuration-level
marginal effects, not independent component causal effects.

The immutable additional-experiments run
`probemem_additional_ablation_20260901T031926Z_4f9fd0b4556c` completed 60
operational failures from 94 sequential initial units. Its formal status is
`COMPLETED_WITH_POPULATION_IMBALANCE`: 52 stable-bias and eight stochastic-
noise cases were observed without resampling. Adaptive acquisition matched
fixed 64-step evidence diagnosis on the 33 registered comparable historical
cases while using 13.58 rather than 64.00 mean evidence steps. Evidence
Acquisition Enabled recovered 55/60 versus 51/60 for Baseline. Adding
accepted-only chronological Memory on top of evidence acquisition recovered
52/60, with two useful and four harmful transfers. Full ProbeMem also recovered
52/60; adding the verifier on top of Probe+Memory changed no actions and
prevented zero unsafe proposals. All isolation, chronology, leakage, budget,
and invalid-skill counters were zero. Preserve this mixed/negative result. Do
not extend or replace seeds 7200--7293, execute the unused 7294--7399 stream
under this stopped protocol, resample for population balance, tune from this
stream, execute reserved seeds 7400--7499, or describe the five-row contrasts
as independent component causal effects.

## Publication-directed causal evidence successor

The user has set a continuing CCF A publication research objective. On branch
`codex/evidence-persistence-v1`, the separately frozen
`docs/protocols/evidence_persistence_crossed_development_v1.md` tests a new
causal evidence design on seeds 8000--8015. It crosses the four existing bias
contexts at probe and execution time with identical uniform marginals. All
states are included; this is evaluator-only task success, not failed-case
recovery, an online policy, or a memory-benefit claim. Existing results and all
earlier reserved seeds remain immutable. Seeds 8016--8199 are newly reserved.
No API, threshold fitting, memory writes, or policy learning occurs in this
phase. Freeze and commit before one-shot collection; preserve failure without
replacement. The protocol's feasibility gate cannot establish paper readiness.

The crossed-context run `evidence_persistence_20261013T085037Z_6b88d1b48e41`
completed all 16 task seeds, 64 probes, and 320 physical task rollouts. Probe
compensation task success was 52/64 aligned versus 101/256 under independent
contexts; the source-independent control was 34.375% in both. Its registered
interaction was +41.796875 percentage points, cluster interval
[38.671875, 45.3125], passing the development feasibility gate. The independent
audit reproduced the statistics and checked chronology, provenance, reset,
cache, population, and cost invariants. This is a mechanism signal only, not
new algorithm, memory, online recovery, or publication evidence. Preserve the
run; do not reuse seeds 8000--8015 for tuning or execute reserved 8016--8199
under this completed protocol. A subsequent method experiment needs its own
frozen design, strong baselines, and independent data.

The continuing publication objective now advances to the separately frozen
`docs/protocols/evidence_refresh_prefix_development_v1.md` on new seeds
8200--8295 (eight 12-episode streams). The candidate uses current-prefix action
agreement and method-owned accepted-only caches; it must be compared against
fixed 16/32/64-step probes, stale reuse, periodic refresh, a fixed-threshold
change detector, and uncorrected execution. Noise, cache rules, pooling,
schedule, and gate are frozen before outcomes. Only requested prefixes may
enter decisions or caches; unused suffixes are evaluator-only. Seeds
8296--8499 are reserved. Earlier freezes remain unchanged. This is task-success
development, not initial-failure recovery, a calibrated certificate, or a
novelty claim; there are no API calls or principle writes. Freeze implementation
before one-shot execution and preserve any failure without tuning or rerunning.

The prefix-refresh run `evidence_refresh_20261013T092539Z_ac3fa90f6d20`
completed all 96 episodes and failed its registered strong-baseline gate.
DECISION_STABILITY succeeded on 87/96 at 37.17 mean probe steps; FIXED_16 and
FIXED_32 each succeeded on 88/96 at lower cost. Its 41.9% probe saving against
FIXED_64 does not establish adaptive acquisition value. Independent replay
verified 768 decisions and 205 accepted cache writes, with 332 physical task
rollouts, 68,593 task steps, and 6,144 probe steps. API calls remained zero.
Preserve this negative result without tuning or rerunning seeds 8200--8295;
8296--8499 remain reserved. Do not promote this heuristic to validation or
claim a new algorithm. The continuing publication objective requires a
separately specified contribution, strong cheap baselines, and independent
data; prior studies and their reserved allocations remain immutable.

The continuing publication objective next permits the separately versioned
`docs/protocols/probe_support_identifiability_development_v1.md`. This is an
evaluator-only structural witness, not a promoted prefix selector. It uses a
constructed nonlinear fault that vanishes on the historical probe commands,
compares fixed amplitudes 0.2 and 0.8 at equal 16-step cost, and evaluates three
fixed whole-episode x corrections on push-v3 with the unchanged low-level policy.
The fault family and alternative amplitude are new to this version only.
Freeze source/config/protocol before one-shot seeds 8500--8515; reserve
8516--8699. No API, memory, training, fitted classifier, historical seed reuse,
or coefficient/amplitude sweep. Preserve gate failure without adjustments.
Constructed probe indistinguishability alone is neither realistic fault
prevalence nor a novel algorithm; downstream action relevance must be checked.

That probe-support study completed all 16 seeds, 96 probe groups, and 144
task rollouts with audit integrity PASSED but status COMPLETED_WITNESS_FAILED.
Old-amplitude transcripts were identical and alternative-amplitude transcripts
separated all context pairs, yet the unchanged policy succeeded on all 48
seed/context combinations. Disjoint successful-action witnesses were 0/16;
both context-blind and context-aware evaluator bounds were 48/48. Preserve
the negative result; do not tune the polynomial, rerun seeds 8500--8515, or
execute reserved 8516--8699. Do not promote this constructed family to a
selector study merely because its hidden parameters are identifiable. A
substantive successor requires independently specified task-relevant ambiguity
and comparisons with established task-oriented experiment design.

The continuous-probe engineering foundation in `src/probe/continuous.py` is
separate from all frozen probe executors. It exposes no reset capability and
returns the actual final state for continuation; a standard local dynamic OLS
fit is a baseline, not a calibrated or novel method. The phase uses synthetic
tests and a read-only reset-cost audit only. No new simulator seed allocation
or experiment is frozen in `docs/research/continuous_probe_baselines_v1.md`.
A later physical collection must separately freeze its protocol and must
preserve environment/actuator state across the probe/task boundary.

The continuing goal now advances to the separately frozen continuous-probe
baseline study in `docs/protocols/continuous_probe_development_v1.md`, seeds
8700--8707 crossed with four existing bias contexts and noise std 0.05. Reserve
8708--8899. This version uses 500 total steps including the probe, with 484
post-probe policy steps, and whole-episode simultaneous bounded xy corrections.
Compare no probe, probe without correction, static OLS, dynamic OLS, and the
explicitly privileged reset reference. Freeze source before execution; do not
reset environment or actuator RNG at a continuous probe/task handoff. Preserve
any failure, with no tuning, seed replacement, API calls, or memory writes.

The continuous-probe run `continuous_probe_20261013T103104Z_1092996bcf4f`
completed 32 units/160 method episodes and failed feasibility. NO_PROBE
succeeded 12/32, CONT_NO_CORRECTION 13/32, CONT_STATIC 5/32, CONT_DYNAMIC
15/32, and privileged RESET_REFERENCE 31/32. Dynamic minus probe-without-
correction was +6.25 pp with registered 97.5% seed-cluster interval
[-9.38,21.88]; numerical fit validity was not confidence. Audit replay verified
160 decisions, 96 continuous handoffs, 47,261 task-step state/RNG links, and
49,309 physical steps. Preserve this result and seeds 8700--8707; 8708--8899
remain reserved. Do not fit calibration, model order, thresholds, probe length,
or correction settings to these outcomes. A successor needs a separate
calibration/evaluation protocol, not an adaptive or memory promotion here.

The continuing objective next advances to the separately frozen
`docs/protocols/response_calibration_development_v1.md`. Known commanded offsets
in a nominal zero-bias calibration regime fit a standard affine trajectory
response on seeds 8900--8907; independent qualification uses 8908--8915.
Reserve 8916--9099. Each phase contains 72 continuous 16-step probes. The model
must be saved before qualification and never refitted from those measurements.
This phase tests identification, not task success or a new algorithm. Its known
nominal regime and full 2,304-step/144-reset calibration cost must remain explicit.
Freeze implementation before one-shot collection; preserve failure without
threshold fitting, seed reuse, API calls, or memory writes.

The response-calibration run
`response_calibration_20261013T105913Z_bfbd86c7c1dd` completed and passed its
identification gate: affine mean offset error 0.01747 and p90 0.03179 on 72
independent qualification trials; nearest-centroid mean error was 0.05365.
The training-only model was frozen before qualification and independently
reconstructed by the audit. Total cost was 2,304 steps/144 initial resets.
Preserve training seeds 8900--8907, qualification 8908--8915, and reserved
8916--9099. A task-utility study requires a separate freeze and new population;
qualification alone does not establish confidence, task benefit, or novelty.

The separately frozen task bridge is
`docs/protocols/calibrated_continuous_task_utility_v1.md`, using new seeds
9100--9115 crossed with the four existing bias contexts; reserve 9116--9399.
The immutable qualified model is compared with no-probe, probe-motion, online
dynamic OLS, and matched-calibration nearest-centroid controls. All online
episodes use a 500-step total budget and one uninterrupted actuator stream.
Both prior baselines disclose the full 2,304-step/144-reset offline cost.
Freeze source before one-shot task execution; do not refit the model or tune
on these task outcomes. Preserve failure without replacement. This is a
standard-baseline utility bridge, not a novel-method or publication gate.

The task bridge `calibrated_tasks_20261013T111017Z_972172259b89` completed all
64 units/320 physical episodes and passed feasibility. Qualified affine prior
obtained 64/64, same-data nearest prior 62/64, probe-without-correction 33/64,
dynamic OLS 22/64, and no probe 19/64. Affine minus the probe control was
+48.44 pp, 95% task-seed interval [39.06,57.81]; affine minus nearest was
+3.12 pp with interval [0,7.81], not established superiority. Audit verified
320 decisions, 256 continuous handoffs, 73,728 task-step state/RNG links, and
77,824 new physical steps. Priors disclose 2,304 offline steps/144 resets.
Preserve all task data/seeds 9100--9115; reserve 9116--9399. Do not retune
the estimator, correction, probe, or validity rule on these outcomes. This
supports standard calibrated evidence utility under fixed nominal assumptions;
it does not establish novelty, calibration-shift robustness, or publication.

## Online calibrated API development overlay

The user explicitly authorized implementation and one-shot execution of
docs/protocols/online_calibrated_agent_development_v1.md on
codex/online-calibrated-agent-v1. Use new seeds 9400--9403 crossed with four
existing bias contexts; reserve 9404--9599. The API selects registered probe or
host-computed correction candidates only, with at most 40 attempts including
preflight and repairs. All six methods share 500 online steps and uninterrupted
state/RNG handoffs. Failed calls abstain without deterministic substitution.
A failed preflight must consume zero simulator seeds. Prior-access methods pay
2,304 offline steps/144 resets amortized over 16 units. Preserve failures and
all historical freezes. This is a bounded online integration test, not memory,
calibration-shift, held-out, novelty, or publication evidence.

The one-shot run online_calibrated_agent_20261014T022239Z_e40d3b2b2c24 completed
all 16 units/96 method episodes and passed its registered interface gate.
Logical validity was 30/31 and 15 API-selected correction chains actually ran.
LLM succeeded 14/16 versus 16/16 for both calibrated priors, with one pre-probe
hard-timeout stop and one valid dynamic-OLS selection followed by task failure.
There were 35 API attempts (31 decision primary, one health, three repairs),
one hard timeout, and three rejected stale/unknown action IDs. Offline audit
verified 555 Git input hashes, 79 handoffs and 20,416 task steps; collection
cost was 21,680 steps/96 resets. Request max_tokens remained 512, but reported
output usage exceeded 512 in 31 attempts (max 7,957), with timeout usage unknown;
do not claim a verified total-token ceiling or complete resource compliance.
Preserve raw data, seeds 9400--9403 and reserve 9404--9599. Do not rerun, tune,
promote memory or claim LLM task benefit from this interface passage. Publication
still requires a separately specified competitive contribution and evaluation.

## Finite-frame action-relevance prerequisite

The continuing publication goal permits the separately frozen
docs/protocols/frame_evidence_development_v1.md on
codex/frame-evidence-validity-v1. Fresh seeds 9800--9807 cross two deliberately
constructed frame/bias contexts; reserve 9808--9999. Eleven methods share the
new version's bounded command interface, 500 total live steps and a single
environment/actuator reset. A common four-step prefix and repeated eight-step
probe are algebraically aliased; reverse commands may reveal a frame requiring
a different predefined controller. Only the original 72 nominal training
trajectories fit a standard ARX baseline, frozen before task execution. Original
qualification does not qualify that new model. Charge all prior-access methods
the complete 2,304-step/144-reset resource, amortized over 16 units. No API,
memory, outcome fitting, frame/amplitude sweep, historical seed reuse or policy
learning is allowed. Freeze source/config/protocol before one-shot collection;
preserve failure without tuning. This is a constructed action-relevance witness
and strong standard baseline, not novelty, realistic fault prevalence or paper
readiness. The API integration negative result and all previous freezes remain.

The one-shot frame run frame_evidence_20261014T041345Z_82a3dd1469d4 completed
176 method episodes and passed its prerequisite gate. All eight seeds had
identical common/repeated probes and disjoint sampled successful-action sets;
the restricted context-blind/informed evaluator bounds were 8/16 and 16/16.
Standard reverse-eight ARX and full-sixteen ARX each succeeded 16/16; repeat-eight,
no-probe and legacy affine each 8/16, legacy nearest 4/16. Reverse-eight averaged
72.125 online steps versus full-sixteen 80.25 and pays the same 2,304-step/144-reset
offline resource. Independent audit replayed 176 decisions, 160 handoffs and
45,318 physical steps, with zero violations. Sixteen complete executions exactly
matched the chosen fixed controller under the same probe/noise realization.
Preserve all 9800--9807 data and reserve 9808--9999; do not tune or rerun. This is
a constructed existence witness solved by a cheap standard method, not a new
algorithm, calibrated confidence or stable action labels. No API calls occurred.
Any successor requires a separately frozen competitive problem/method and
independent task/operator/noise evidence; publication readiness remains unmet.

## Command-support scope foundation

The continuing goal next permits the purely analytic implementation and read-only
diagnostic in docs/research/action_support_scope_v1.md on
codex/action-support-scope-v1. A standard affine-input informativity checker must
distinguish the old known-two-rotation prior from a general affine XY operator.
Exact rational command geometry decides support; numeric tolerance must not
approve small unobserved components. It does not qualify robot dynamics, noise,
safety or task success. Replay the immutable 176 frame cases with fixed-probe
and strictly past-only cumulative command support, preserving original results.
No new physics/API, seed allocation, model/outcome fitting, memory or old-policy
change occurs. Standard row-span/data-informativity results are prior art, not
our innovation. Any later deployed guard requires a separate qualification and
prospective protocol; this phase cannot authorize original-seed reruns.
The accompanying response_transfer.py prototype uses exact subset interpolation
and an explicitly assumed componentwise response-error envelope to propose
conditional reuse, precision reacquisition, or cache rejection for a query.
Declared per-coefficient drift and strictly past measurement times can add a
query-dependent age radius; recent x measurements must not certify stale y.
It must remain proposal-only with model/task/probability qualification false;
Gaussian standard deviation is not such an error envelope. Synthetic analytic
tests do not qualify MetaWorld observations or cached-model persistence.

The read-only frame support diagnosis replayed all 176 cases/43,846 task
queries with independent rational rank verification. Reverse-eight ARX had
1,026/1,026 task commands outside frozen-probe support under the broader
unrestricted affine class; its original known-rotation 16/16 result remains
valid. Causal history completed command rank after one extra independent input
per reverse-eight case. Full input support still coexisted with legacy affine
8/16 and nearest 4/16. Do not relabel these as original protocol violations,
new task failures or proof of calibrated responses. The bounded-drift reuse
prototype passed analytic tests only. A successor needs independent observable
response qualification, passive calibrated identification and strong active
design/set-membership baselines, then a fresh prospective multi-task/operator
protocol. No new simulation/API/fitting occurred and publication remains unmet.

## Independent nominal response-observer feasibility

The continuing goal advances to docs/protocols/nominal_observer_qualification_v1.md
on codex/nominal-response-qualification-v1. New seeds 10000--10015 cross push-v3,
reach-v3 and door-open-v3 with policy-only/probe-then-policy programs; reserve
10016--10199. The old training-only nominal ARX is frozen, not refitted. Use
visible xy displacement and its previous value to test inverse-response accuracy
against known commands in a declared zero-bias nominal actuator with noise 0.05.
Four-step means, p90 of per-episode maximum block error <=0.10 and six complete
16-episode strata are fixed before outcomes. Each of 96 trajectories has one
initial reset, continuous RNG and at most 500 total steps. Save passive affine
snapshots before subsequent steps/evaluator labels; they never alter commands.
No API, memory, held-out reuse, policy-weight changes or threshold/model tuning.
Full old offline costs plus new qualification costs must be disclosed. This is
an empirical feasibility gate, not a universal/probability response contract;
response_transfer qualification stays false even if it passes. Freeze/commit
before one-shot collection; preserve failure and partial traces without restart.

The one-shot nominal-observer run
nominal_observer_20261014T055743Z_9e6c6e63cc35 completed all 96 trajectories with
COMPLETED_FEASIBILITY_FAILED. All six frozen precision strata failed: episode
maximum-error p90 ranged from 0.4301 to 2.8665 against 0.10. All 96 nominal
fixed-policy tasks nevertheless succeeded; keep task success separate from
observer precision. Independent audit replayed 6,933 transitions, 48 continuous
probe handoffs and 350 passive snapshots. Numerical rank/conditioning did not
qualify response accuracy; one numerically valid door snapshot had matrix error
1,222.13. New cost was 6,933 steps/96 resets; the full old 2,304 steps/144 resets
is separate. No API, memory or frozen-model refit occurred. Preserve all
10000--10015 data, the failed 0.10 gate and the 10016--10199 reservation. Do not
deploy this inverse observer through response_transfer, retune on these seeds,
or promote publication from nominal task success. A new observable-response
contract and strong prospective passive/active identification comparison remain
required. Report: reports/nominal_observer_qualification_v1.md.

## Standard forward-prediction baseline successor

The continuing publication goal permits the separately frozen
docs/protocols/forward_prediction_baselines_v1.md on
codex/forward-prediction-baselines-v1. Fresh training seeds 10200--10215,
calibration seeds 10300--10315 and qualification seeds 10400--10415 cross the
same three fixed-policy tasks/two continuous programs. Reserve 10416--10599;
all old reservations and negative results remain. Three standard train-only
linear/state-quadratic/nearest forward predictors target visible xy displacement,
with old nominal ARX as a separately costed forward reference. Save each
prediction before its physical step. Freeze fitted models before calibration
and trajectory order-statistic bands before qualification. Whole-trajectory
coverage and 1-mm interval radius are separate empirical checks; nominal
coverage does not certify actuator responses, unknown faults or control safety.
Charge full new train/calibration/test costs and old 2,304 steps/144 resets.
Maximum 288 initial resets/144,000 physical steps; each episode has 500 total
steps and one reset, no probe-to-task reseeding. No API, memory, policy-weight
updates or new corrective controller. Freeze and commit source/config/protocol
and auditor before one-shot collection; preserve missing/failed cases and
never retune these seeds. Standard forward models/conformal prediction are
baseline work, not the required new method or publication completion.

The one-shot forward run forward_prediction_20261014T064233Z_bb812df15401
completed all 288 trajectories with COMPLETED_FEASIBILITY_FAILED. Independent
audit checked 21,010 prediction-before-execution declarations/transitions and
144 continuous handoffs, reconstructing all training sources and frozen bands.
New linear/state-quadratic/nearest predictors reduced overall mean episode-max
error versus the old forward ARX by 0.2854/1.4424/0.4121 mm, but no method passed
all six width/coverage strata. State-quadratic reach coverage was 13/16 and
14/16; a 500-step calibration failure (10314, door/policy-only) drove its
16.6392-mm radius. Only reach/probe/linear passed one individual stratum.
Nominal fixed-policy successes were train 96/96, calibration 95/96, test 96/96;
none of these is a new corrective-controller outcome. Costs were train 6,763
steps/96 resets, calibration 7,250/96, test 6,997/96, plus old 2,304/144 separately.
Preserve 10200--10215, 10300--10315, 10400--10415 and the 10416--10599 reservation;
do not retune the 1-mm/15-of-16 gate or claim qualified actuator response,
fault-transfer coverage, control benefit or publication from average accuracy.
Report: reports/forward_prediction_baselines_v1.md. A state/action-aware response
contract, matched strong identification/acquisition methods and a separately
frozen unknown-fault utility experiment remain required.

## Unknown-affine forward point-controller task bridge

The continuing publication goal permits the separately frozen simulation
docs/protocols/forward_operator_task_utility_v1.md on
codex/forward-operator-task-utility-v1. Seeds 10600--10607 cross three fixed
Sawyer tasks and nominal/coupled-gain/rotated-gain/reflected-shear actuator
conditions; reserve 10608--10799. The agent does not receive condition IDs,
actual operators/noisy actions, seeds or RNG. Twelve methods include matched
8/16-step probe-motion controls, legacy estimators, general affine input
prediction-error fits with the frozen per-task forward models, passive recent
linear updates, and an explicitly evaluator-only true-parameter reference.
These are standard point methods tested empirically, not confidence-certified
actuator estimates or the required new algorithm. Previous 1-mm/coverage
failures remain, response_transfer remains proposal-only, and no failed band
is used to authorize control. This separately versioned simulator experiment
may execute its saved point estimates under disclosed model assumptions;
physical/probability/safety qualification stays false even if tasks improve.
Each method has one initial reset and continuous state/RNG, 500 total steps;
maximum 576,000 new steps/1,152 resets. Invalid fixed-probe point fits stop and
remain in 96-unit denominators; historical/passive registered fallback is
explicitly recorded, never replaced by Oracle. Pay the full prior forward
source 21,010 steps/288 resets and legacy source 2,304/144 separately. No API,
memory, cross-case learning or policy-weight update. Freeze source/config/
protocol/auditor after required checks, commit, and collect once. Preserve
negative effects, nominal harms, cheaper-baseline dominance and all old seeds.

The one-shot forward-operator run
forward_operator_20261014T081128Z_37eee13f9943 completed 1,152 method episodes
with COMPLETED_POINT_UTILITY_PASS. Independent replay checked 235,479 visible
steps, 1,891 saved choices and 960 continuous probe handoffs. Linear sixteen
succeeded 96/96 at 91.8021 mean online steps, versus matched probe control
43/96, old affine 69/96, linear eight 84/96 and passive linear 86/96. Linear
sixteen dominates the other four same-prior point methods in success/count
and mean online/amortized steps; it is mandatory in successors. Quadratic
eight/sixteen obtained 40/96 and 54/96, with 27/25 stops and 12/5 nominal harms;
nominal forward average accuracy did not rank effective inverse control.
Preserve all 372 failed/stopped cases, 363 passive invalid updates and all
10600--10607 data; reserve 10608--10799. Total new collection was 235,479
steps/1,152 resets; full source banks remain 21,010/288 and 2,304/144. No API,
memory, policy-weight update or confidence qualification occurred. Do not
promote algorithm novelty, dynamics confidence or publication from this useful
standard task bridge. Report: reports/forward_operator_task_utility_v1.md;
literature/remaining contribution: docs/research/forward_operator_contribution_gap_v1.md.

## Input noise and model-factorization audit

The continuing goal next permits the read-only analysis in
docs/research/input_model_error_audit_v1.md on codex/input-model-error-audit-v1.
Replay the immutable 1,152 forward-operator trajectories and actuator RNG;
evaluate the frozen nominal predictors with known actual inputs only inside
the evaluator. Preserve signed-error cross terms and distinguish step-weighted
from episode-weighted summaries. Compare only saved accepted passive estimates
under the original static operators; rejected updates are not controller changes.
No new simulation, seeds, API calls, refitting, detector thresholds, memory or
policy changes are allowed. Commit the tool before analysis; use a new directory
and bind source/result hashes. Actual inputs, truths and diagnostic residuals
must never become agent evidence. Conditional factorization ambiguity and this
diagnosis are not novel algorithms, physical confidence or publication readiness.

The completed read-only replay checked all 1,152 trajectories/235,479 original
steps, with 233,175 history-qualified comparisons per model/input condition.
Known actual inputs did not eliminate NO_PROBE model residuals: linear mean
episode maxima were 1.2682/1.3078/7.3002 mm for push/reach/door; quadratic was
17.9613/25.0418/36.7183 mm. Under static truths, 288 accepted passive update
pairs across 85 cases had median/p90/max coefficient changes .3276/1.3730/3.1561.
Independent verification checked every injection against the original executor
class and 27,648 sampled predictions, not every aggregate independently.
Preserve this evaluator-only diagnosis without detector fitting or threshold
selection. Do not turn exact-input residuals into Agent View or parameter jumps
into actuator-change labels. Action-response validity needs an explicit model/
error scope, independent calibration and prospective nonstationary comparison;
the mandatory linear-sixteen baseline and prior confidence failures remain.

## Experimental action-response revalidation

The continuing goal permits the separately frozen simulator protocol
docs/protocols/action_response_development_v1.md on codex/action-response-validity-v1.
Fresh seeds 10800--10943 define eight clusters/three tasks/six cases, crossed
with stationary and hidden abrupt/gradual schedules. Sixteen methods yield
4,608 episodes, each one reset/continuous 500-step total; maximum 2,304,000 new
steps/4,608 resets. Reserve 10944--11199; all old reservations stay unchanged.
The candidate validates local mean response residuals on current visible data
against a parameter-box LP and selects registered four-step physical probes.
Nominal initial-six-step CALIBRATION-only RMS is an empirical scale, never a
qualified error bound; no qualification data or private exact-input diagnosis
enters the method. All probability/physical/safety qualification stays false.
This new empirical point-hypothesis experiment may execute its saved proposals
under disclosed assumptions; it must not deploy the old response_transfer API
or relabel prior failed confidence gates. Preserve original and wide 8/16-step
baselines, periodic 2/3, recent history, residual CUSUM, greedy G design, ablations
and a separately labeled Oracle. Methods own causal parameter caches, including
pre-outcome numerical fits; these are not accepted episodic memory records.
Pay each prior method the complete 21,010-step/288-reset source. Freeze all
source/config/protocol/auditor after required checks; collect once and preserve
failure without scale/threshold tuning or restart. No API/policy-weight updates.
Algorithm novelty and paper readiness are not established by this development gate.

## Two-stage empirical task-value learner

The continuing publication goal permits the separately frozen development reuse
in docs/protocols/task_value_learner_development_v1.md on
codex/task-value-learner-v1. Reuse only the completed postprefix acquisition study
after binding its v3 audit and unchanged raw files. Strict evidence objects end
at six policy steps or six plus the actually selected 8/16 wide probe; seeds,
streams, scenario, RNG, truth and future labels are evaluator-only metadata.
Standard RBF ridge models predict post-measurement UPDATE versus KEEP loss and
pre-measurement branch value. Fit pre targets from inner held-stream post choices,
never hindsight label minima. Exclude the whole outer operator stream from every
fit, scaler and kernel width; report all twelve old baselines and direct-value
control. Freeze source/config/extractor/auditor before one development replay;
no tuning on its results, new simulation, reserved seed, API or episodic memory.
Full paired and nominal source fees must be disclosed. This is development reuse,
not independent confirmation, new online execution or established novelty; a
competitive prototype still needs a separately frozen live independent study.

## Early actual-evidence continuation target

The continuing goal next permitted the separately frozen protocol
docs/protocols/early_evidence_development_v1.md on codex/early-evidence-target-v1.
Run early_evidence_20261015T015710Z_a9ec09feaf24, frozen at a9ec09feaf2499420a17015f3aed379d14199de0,
completed 768 method executions on fresh seeds 11500--11523: eight static
operators, three tasks and four noise realizations, with eight methods. Its
recorded-action audit passed all 278,688 events, 636 frozen Git inputs and
440 library-source bindings. This is not independent dynamics qualification.

The registered POINT16_CYCLE versus POINT8 repeatability gate FAILED: all
24 nominal contexts matched, but 8/24 reversed the task-loss direction across
noise realizations, exceeding the 25% limit. Overall success was 92/96 versus
86/96; average deadline loss improved by 25 steps, with 19 improved, 69 worse
and eight tied matched cases. Preserve this negative target gate without
changing its rule, adding a threshold or rerunning the stream. The four noise
realizations do not create 96 independent operator/task contexts.

Mandatory strong references now include GAUSS8 (92/96, mean loss 97.6354),
POINT16_CYCLE (92/96, 102.5208), POINT16_WIDE (92/96, 105.6771),
GAUSS16_CYCLE/IVR_GLOBAL16 (93/96, 100.5) and IVR_TASK16 (95/96, 92.5833).
GLOBAL chose X4/Y4 in all 96 cases and matched the fixed Gaussian cycle's
listed visible/action/RNG trace fields in every case. TASK changed 67 program
sequences and rescued two door-open cases versus GLOBAL. Against GAUSS8 it
gained four successes, lost one, and worsened deadline loss on 81/96 cases;
both-success pairs cost 7.6813 extra steps on average. Post-result contrasts
are descriptive only. Gaussian moments, bounded inversion and task IVR are
standard references with physical/probability qualification still false.

New measured costs were 97,824 Env.step, 768 controlled initial resets,
38,400 temporary goal-generation resets and 20,073,120 do_simulation requested
frames. All nominal methods pay the full old 21,010-step/288-reset source.
No API, policy-weight update or natural episodic-memory write occurred.
Keep 11524--11799 and every previous reservation unused. The next contribution
needs a distinct mechanism and separately frozen independent evidence, not
promotion of this standard reference or a retuned rule on the failed gate.
Complete results: reports/early_evidence_development_v1.md; interpretation:
reports/early_evidence_interpretation_v1.md. Historical online GLM results
remain separate and do not receive credit for the present simulator outcomes.

## Executable-support acquisition development

The continuing goal next permits the separately frozen protocol
docs/protocols/executable_support_development_v1.md on codex/executable-support-v1.
It tests a concrete input-coordinate mechanism: map frozen nominal desired
commands through the current saved bounded controller before scoring local
IVR. An eight-step-fixed support mapping is the ablation. Inverse-prediction
and control-oriented experimental design are existing ideas; the analytic
rotation witness and implementation are not established algorithm novelty.

Fresh seeds 11800--11847 define 16 static operator streams, three tasks and
two noise realizations, 96 units with nine methods/864 real executions.
Operator generation uses two eight-stream blocks with nonces 45001/45002;
only each A state is executed. Preserve the seven strong standard baselines,
500-step continuous budget, 16-step probe cap and complete nominal source fee
21,010/288 per model method. Reserve 11848--12199 and every old reservation.
Do not refit a stopping rule on the failed early-evidence gate, use current
outcomes to adjust the map, or treat 96 units as 96 independent operators.

Freeze source/config/protocol/mechanism/auditor after required checks, then
collect once. The primary contrast is EXEC versus original TASK; use the
registered parity-stratified operator-stream intervals and retain failures,
all methods, actual initialization costs and mapped-command provenance.
Keep API, natural episodic memory and policy training at zero. A development
signal does not replace independent method confirmation or novelty review.

The one-shot executable_support_20261015T082955Z_48a3e433af85 completed all
864 executions and FAILED its development-signal gate. EXEC and original TASK
both succeeded 95/96; mean loss difference -0.1875 had stratified stream 95%
interval [-0.8125, +0.4167]. GAUSS8 succeeded 96/96 at 86.1354 mean steps/loss,
versus EXEC 90.8646. POINT16_CYCLE and POINT16_WIDE also succeeded 96/96 at
88.3542 and 89.8125, respectively. All three observed baselines dominate EXEC.
Keep this negative result without query-map or Gaussian-weight tuning.

Mapping execution was real: 57/96 sequences changed versus TASK, and 58/192
same-saved-moment choices changed under the mapped support. The fixed-eight
map ablation succeeded 95/96 and differed in deadline loss on only four pairs.
The separate standard norm/ranking-bound note passed 1,500 random matrix checks,
but actual ranking-certificate coverage was 0/192 in each mapped method; never
report random algebra checks as physical confidence or online stopping evidence.

All five sixteen-step Gaussian methods failed the same push seed 11833/rep0;
GAUSS8 and both point-sixteen methods succeeded there. A post-result check
matched the listed first-sixteen visible/action/RNG fields and identical saved
point fit between POINT16_CYCLE and GAUSS16_CYCLE, followed by different sent
policy commands. Do not attribute this solely to extra probe motion or isolate
the covariance penalty without an actual ablation. No parameter fixes on this case.

Independent recorded-action audit passed 300,308 events, 644 frozen Git inputs
and 440 library bindings. New costs were 103,114 Env.step/864 controlled resets,
43,200 temporary goal-factory resets and 22,547,570 requested simulation frames.
Preserve every failure and all reservations. Reports:
reports/executable_support_development_v1.md and
reports/executable_support_interpretation_v1.md. A successor needs a new causal
evidence design or mechanism rather than another score-coordinate variant.

## Conditional continuation measurement

The continuing goal next permits the separately frozen protocol
docs/protocols/conditional_continuation_development_v1.md on
codex/conditional-continuation-v1. It fixes an actual continuous eight-step
visible prefix while varying four pre-generated future-noise realizations.
The old ACR fixed-state fresh-verification study and recent initial-noise
repeats do not directly measure this continuation quantity. Preserve their
failed gates; realized-winner reliability is not conditional mean utility.

Fresh seeds 12200--12223, eight new static A operators from nonce 46001,
three tasks and four futures define 96 units with seven fixed branches/672
real executions. Every environment actually replays its prefix, one controlled
reset, no state copying/restoration or mid-trajectory seeding. Immutable noise
arrays are evaluator-only; consumed-noise history hashes are distinct from
RNG states. Keep 12224--12599 and every old reservation unused.

Retain DIRECT_G8, keep-after-probe, Gaussian update, point-sixteen cycle,
passive policy observation/update, original wide-sixteen and NO_PROBE.
Five feasible post-prefix branches form an evaluator-only leave-one-future-out
lookup from three training-future losses. This lookup is not an online Agent,
natural experience or true optimal-policy bound. Negative lookup performance
also cannot prove that a conditional optimal policy does not exist. There is
no revised winner-stability promotion gate and no source-data threshold fit.

Freeze source/config/protocol/question/auditor after required checks, collect
once, disclose the whole counterfactual bank and complete nominal 21,010/288
source, and audit all same-method future prefixes and feasible cross-method
prefixes. New maximums are 336,000 Env.step/672 controlled resets/19,000,000
requested simulation frames. No API, episodic-memory write or policy training.
This is measurement groundwork; the competitive method and independent online
confirmation required for the full publication goal remain unfinished.

The one-shot conditional_continuation_20261015T094531Z_784d65befd08 completed
672 executions with a passed recorded-action/noise audit. The evaluator-only
lookup achieved 92/96 and 94.40625 mean loss versus DIRECT_G8 85/96 and
128.83333. Its primary loss difference -34.42708 had stream interval
[-72.65625,-3.92682]. A post-freeze descriptive comparison versus the observed
best fixed POINT16_CYCLE gave -9.29167 [-11.10417,-7.60417], equal 92/96 success.
The lookup used other futures of the exact prefix and is never an online
Agent, natural experience or true optimal-policy bound. Do not promote its
score as algorithm performance or retune its branches/noise from this cohort.

## Causal continuation selector reference study

The continuing goal next permits docs/protocols/causal_continuation_selector_development_v1.md
on codex/causal-continuation-selector-v1. It explicitly reuses the completed
24-context/four-future source as offline supervised training, not online memory.
Standard fixed RBF ridge, nearest neighbour, task-only mean and single-future
RBF references must make a saved choice after eight actual visible steps and
before physical continuation on sixteen fresh operator streams.

Freeze code/config/protocol/scope/auditor after required checks, then train once
and bind trained artifacts in the evaluation manifest. Fresh 12600--12647,
three tasks/two future-noise realizations and twelve methods define 96 units
and 1,152 actual executions. Reserve 12648--12999 and all old reservations,
including 12224--12599. Execute static A only, with two fresh generator nonces
47001/47002. No future outcomes, true mappings or random-state identities may
enter strict Agent evidence or choice. No API, natural memory or policy training.

Preserve all seven strong fixed baselines and all five supervised references. Maximums:
576,000 new Env.step/1,152 controlled resets/33,000,000 requested simulation
frames. Every learned reference pays complete 101,069/672 source and 21,010/288
nominal fees; disclose physical collection once and per-method amortization.
The frozen primary is mean-cost RBF versus POINT16_CYCLE with sixteen clustered
streams; any failure is kept without feature/kernel/threshold repair on that
evaluation population. A positive development signal establishes neither
standard-regression novelty nor independent confirmation of a new method.

TASK_FULL_PORTFOLIO is a required cheap-information baseline: choose among all
seven fixed programs from known task identity at time zero. It may select
NO_PROBE or wide-sixteen; never treat it as a shared-eight continuation branch.
The source authenticates its common initial witnesses, and audit verifies its
saved initial choice before any physical step. All five references pay full
source fees. The primary must match the highest success count of every control.

The one-shot causal_continuation_20261015T104523Z_68da2c7ef160 completed 1,152
actual executions and FAILED the registered selector development gate. Main RBF
93/96 at 96.6875 mean cutoff loss was dominated by PASSIVE_G16 94/96 at
86.98958. Primary versus POINT16_CYCLE 94/96 at 96.52083 gave +0.16667
[-7.30208,+10.05208]. Only ten decisions differed from the task-only and
single-future references: two loss improvements, seven worsenings and one tie,
with no extra success. Keep the negative result; do not tune the feature/kernel
on this cohort or substitute the old evaluator lookup's score.

The complete 391,498-event audit passed; 480 selected executions exactly matched
their separately executed fixed programs in 46,086 listed physical steps.
Costs were 133,450 new Env.step/1,152 controlled resets, 57,600 temporary factory
resets and 30,043,250 requested frames. Source/model fees were disclosed in full.
Reserve 12648--12999 and every old reservation. No API was used.

## Evaluator-only saved-inverse accounting

The continuing goal next permits docs/protocols/inverse_error_attribution_v1.md
on codex/inverse-error-attribution-v1. This is a zero-new-simulation reuse
analysis of all 192 DIRECT/PASSIVE pairs from the two completed cohorts,
not a fresh confirmation or new estimator. Freeze code/config/numeric audit
and identity note after required checks, then run once on the bound sources.

True actuator coefficients and recorded executed actions belong only to
src/analysis and evaluation scripts. Do not expose them to Agent inputs,
retrieval, training selection or new controllers. Keep saved fits unchanged.
Account for applied-input prediction residual, propagated input noise, host
roundoff, fit-residual adjustment and secant nullspace; retain covariance,
constraint/clipping qualifications, signed cross terms and all task failures.
Source-bank costs 234,519/1,824 and old nominal 21,010/288 are prior reuse;
new environment steps, API calls, reset calls and controller fits stay zero.
No new seed range is executed and no threshold or promotion gate is fitted.
Numerical identities and proximity to injected parameters are not task utility,
physical-model validity, novel theory or completion of the publication goal.

The inverse accounting completed on frozen fcaa4a0 with 192 pairs/384 prefixes
and a passed independent 13,248-field audit; results are committed in 832a98c.
All 192 covariances shrank, but 46 pairs had closer gains and worse task loss.
Keep those descriptive findings without attributing a unique physical cause.

## Randomized proximal-effect mathematical reference

The continuing goal next permits docs/protocols/relative_update_evidence_qualification_v1.md
on codex/relative-update-evidence-v1. This is a standard randomized AIPW and
normal-mixture confidence reference with a mathematical synthetic qualification,
not a new robot controller or a candidate promoted by local proxy effects.
Freeze implementation/config/note/protocol/auditor before one numerical run.

Five scenarios, 256 paths each, 64 responses per path give 81,920 synthetic
responses and 245,760 ordered request/assignment/outcome events. Strict visible
requests exclude true effects, seeds and future returns; assignment and noise
random sources are separate. Preserve all paths, empty intervals and counterexamples.
The target is the realized-history average proximal effect; never relabel it
as the current effect, continuation value or terminal-policy improvement.

New robot environment steps/resets, API calls, controller fits, policy training
and old/reserved task seed execution stay zero. Source qualification seeds are
numeric simulation only. Preserve two indistinguishable finite-prefix worlds
with opposite terminal ordering and the current-effect reversal case. Report
actual finite-budget informativeness without tuning alpha, mixture scale or
outcome normalization. Mathematical checks do not satisfy the full contribution,
independent robot evaluation or publication requirements; a physical successor
still needs a separately frozen scientific protocol and task-value justification.

That mathematical qualification completed on 10fb842 and is committed in
b42eec7: 1,280 paths/81,920 responses plus a 64-response terminal counterexample,
245,760 ordered events and a passed independent 983,040-field numeric audit.
Keep its estimand limitations; it does not certify task-policy updates.

## Post-probe identity controls

The continuing goal next permits docs/protocols/post_probe_identity_development_v1.md
on codex/post-probe-identity-v1. A read-only old-bank comparison found limited
empirical context-selection room among the five post-eight branches, while
the full initial portfolio's NO_PROBE outcome helped cases that all corrected
programs failed. Initial NO_PROBE cannot supply an unexecuted post-probe result.
Preserve the old RBF failure and do not tune it or call the old optimistic
all-outcome choice an online method or population value bound.

Freeze new versioned collector/config/question/auditor after required checks.
Fresh 13000-13047, sixteen operator streams from nonces 48001/48002, three
original tasks and two futures define 96 units/960 actual ten-method runs.
Keep 13048-13399 and every old reservation unused. Static A only; no API,
natural memory, policy training or online selector. These are fixed controls.

IDENTITY_AFTER8 and IDENTITY_AFTER16_CYCLE need no nominal model fitting or
nominal training fee; IDENTITY_AFTER16_PASSIVE must use the saved Gaussian8
for eight actual policy steps before selecting identity at sixteen, and pays
the complete 21,010/288 nominal source as do existing fitted controllers.
Do not skip the passive prefix or replace a failed fit with uncorrected control.

One controlled initial reset, continuous state/noise thereafter, 500 total
steps/run, 480,000 study steps, 960 controlled resets and 29,000,000 requested
simulation frames are maxima. Preserve factory resets, all stops/failures and
early endings. Audit 768 cross-method eight-step prefixes, 192 sixteen-step
prefixes and 480 cross-future prefixes with saved choices before execution.
The primary identity8-minus-Gaussian8 and two unadjusted secondary contrasts
are fixed. This baseline study has no algorithm promotion gate and cannot
complete contribution, independent novel-method validation or paper requirements.

## Controller-conditioned tail-value development reference

The continuing goal next permits docs/protocols/controller_tail_value_development_v1.md
on codex/controller-tail-value-v1. Freeze the new reference, extraction, config,
protocol, tests and independent audit before one fit of the completed 960-run
post-probe identity bank. This is within-source development cross-fitting, not
new robot confirmation or natural memory. Leave whole operator streams out;
do not split correlated timesteps. Keep the old selector/kernel/feature failure.

Only strict visible TailEvidence enters regression. Labels, stream/method IDs,
future indices and evaluator physical witnesses stay in src/analysis or scripts.
Reject Oracle/legacy candidate controllers. Retain every episode's metadata,
failed/stopped cutoff penalty, stable-tail eligibility and complete source fees.
New robot steps/resets, API, policy/controller training and reserved seeds are
zero; standard value-regression fits are counted separately. Do not interpret
empirical prediction errors as calibration bounds or a finite-option certificate.
The frozen component gate and fixed strong point baseline remain mandatory;
passing this component cannot satisfy the full publication objective.

The tail-value reference completed on 66d8e21, results bfa5b72. Its main
remaining-step RMSE was 80.27 versus kind-constant 125.48, but paired-difference
MAE 28.19 exceeded zero-contrast 27.73 and offline choice was 94/96 versus fixed
update 95/96. The component gate failed. Keep the frozen candidate unpromoted.

## Eight-step point baseline development

The continuing goal next permits docs/protocols/point8_baseline_development_v1.md
on codex/point8-baseline-v1. A missing cheap point8 control confounds earlier
eight-Gaussian versus sixteen-point comparisons. Freeze a versioned collector,
config, question, record auditor, statistics audit and tests before one run.
Use fresh 13400-13447, operator nonces 49001/49002, three tasks, two futures and
seven fixed methods: 672 executions. Keep 13448-13799 and all old reserves.

DIRECT_POINT8 fits at eight; KEEP_POINT8_AFTER16 saves that fit, does the same
second eight-probe and consumes the saved fit. Point invalidity stops without
substitution; incomplete matched prefixes retain reasons and all denominators.
The original Gaussian rules, fixed policy, noise .05, one continuous initial
reset and 500-step total remain. Limits: 336000 control steps, 672 controlled
resets and 20000000 requested frames; complete factory/source fees are separate.
No API, selector training or natural memory. Preserve all five registered
contrasts and distinguish self checks. This is a necessary standard baseline,
not a novel method or completion of the full publication objective.

The point8 study completed on b9506ff; results e69a22a. Point8 was 90/96 at
113.25 versus point16 94/96 at 94.604, primary +18.646 CI[-2.000,45.417].
The controlled new-data contrast was +19.979 for kept-old minus updated at a
common sixteen-step history; retain its unadjusted status and all failures.

## Controlled-reset initial evidence qualification

The continuing goal next permits docs/protocols/cold_start_evidence_qualification_v1.md
on codex/cold-start-evidence-v1. The existing AR2 history drops first-two output
likelihood terms. A training-only controlled-reset joint response may use these
real observations; never fabricate zero histories or supply hidden simulator state.
Freeze implementation/config/protocol/tests/independent auditor before new data.

Collect 384 nominal eight-step prefixes on 14000-14383; fit only TRAIN; save
and freeze model hashes before 96 qualification prefixes on 13800-13847,
nonces 50001/50002, same three tasks and two independent prefix noises. Keep
13848-13999,14384-14599 and every old reservation. No recovery task execution,
API, natural memory or policy learning. Limits are 3840 control steps,480
controlled resets,13000000 requested frames; full source/factory fees separate.

Only ColdPrefix enters inference; evaluator truth stays in scripts/analysis.
Compare FULL8 with same-data ARX8 primarily and DROP2 secondarily, retain all
96 denominators and frozen invalid penalties. Model/likelihood remain working,
not physically probability-qualified. A passed identification gate only permits
designing a separate fresh task study, not claiming task improvement or novelty.

The controlled-reset qualification completed on frozen c5b76fb and is committed
in e0ff4e4: all 96 fits were valid, joint score 0.2023 versus same-data ARX
0.7670. The early-two-response ablation interval crosses zero. The v1 auditor's
final NumPy-bool serialization error is preserved; the explicit v2 repair
replayed 58,657 events without changing data, models or gates.

## Independent cold-start task bridge

The continuing goal next permits docs/protocols/cold_start_task_bridge_development_v1.md
on codex/cold-start-task-bridge-v1. Freeze the new collector/config/protocol,
power plan, tests and record/statistics audits before one execution. Historical
paired-stream SD motivates 56 streams for a 20-step normal power-planning proxy;
the earlier unfrozen sixteen-stream sketch is superseded before any new outcome.

Use only fresh 14600-14767, seven generator sources 51001-51007, three tasks,
two futures and eight fixed programs: 2688 actual executions. Keep 14768-14999
and every previously frozen reservation unused. One controlled reset and 500
total steps per execution; caps 1344000 steps,2688 controlled resets,80000000
requested frames. No API, policy weights, memory or nominal model refitting.

Keep the full/drop-two joint models, same-data ARX, old point8, Gaussian8,
old point16-cycle, no probe and identity-after-eight. No selector, substitution
for invalid fits or retuning on this cohort. Bind complete source fees and raw
source hashes; audit saved choices consumed by execution and all failures.
Passing this standard-estimator bridge cannot complete the publication goal.

## Response-action control reference

The continuing user goal next permits the separately versioned
docs/protocols/response_action_execution_v1_zh.md on
codex/response-action-ranking-v1. Preserve the completed PI qualification failure
and zero-interaction diagnosis. Freeze the new kernel, continuous collector,
record/statistics audits, tests, seed scope and full costs before native data.
Full conditional F20 ranks five bounded float32 commands; no nominal-plant
inversion, new response training or online LLM. Keep all eight old task programs
and a same-interface kinematic score. Complete DEV can lock one global weight
only if it has lower mean capped loss than every one of the nine controls.
Otherwise stop without QUAL or sample/parameter repair. Independent own-history
QUAL retains four fixed co-primary contrasts plus every control mean. Neither
standard scoring, predictor accuracy, software checks nor a baseline result
satisfies the acquisition mechanism or CCF A publication objective. The user
authorizes source-hash-bound reuse of unchanged old tests; new tests are array
only, with native software interactions separately budgeted. Do not push/merge.

The response-action reference has completed on frozen 401a7f2, with full results
locally committed in 9f82698. Its 432-run DEV gate failed: selected F20 weight .1
was 35/36 at mean loss 96.583, behind RAW PI .5 at 36/36 and 75.917 and direct
C8+PI .5 at 36/36 and 82.972. No QUAL was started; keep 64100--64199 reserved.
Do not retune this scoring version, append samples, or promote its favorable
C8/integral comparisons. A separately sourced v2 norm-operation audit repair,
the original failed audit and 340 extra read-only refits remain explicit.
Preserve all 468 real native/DEV executions and 54 failures, raw records,
two byte parts and actual restoration. New response/policy training and online
LLM calls were zero. See reports/response_action_reference_v1_zh.md and the new
acquisition_prior_art_20261022_v1_zh.md for the still-open acquisition mechanism,
strong controls, own-history evaluation and publication requirements.

## Acquisition suffix support audit

The continuing goal next permits the zero-interaction post-hoc analysis in
docs/protocols/acquisition_support_audit_v1_zh.md on
codex/acquisition-support-audit-v1. Read all 720 old PI DEV, 432 old PI QUAL and
432 rank DEV executions, preserving every program, group, task, condition and
failure. Audit initial private witnesses and actual physical prefixes; direct
PI beginning at eight cannot label a PI suffix beginning at a movement boundary.
Catalog RAW PI's own history and actual post-movement rejection support.
Do not infer unexecuted validation/reidentification tails or use a future-outcome
minimum as a deployment method, conditional expectation or population bound.
New environment creation/reset/advance, model fits, training and online LLM are
zero. Freeze analysis/tests/source hashes, independently audit full exports and
report in Chinese. Old gates and reservations stay unchanged. This analysis,
standard Bellman formulas and new prior-art reading do not satisfy the concrete
acquisition mechanism, independent own-history deployment or CCF A objective.

That support audit completed on frozen 3fdf8c8: all 1,584 executions/204,824
saved steps, 6,336 nodes, 5,040 requested-suffix rows and 42,912 program pairs
passed an independent 840,672-field audit. New interactions, resets, fits and
online LLM were zero. Preserve all 117 source failures and the reader's earlier
legacy-guard-file preflight failure. There were no boundary-start PI suffixes
at 116 live C8 nodes and no memory-preserving MOVE suffixes at 106 live RAW PI
nodes. Existing post-movement old-C8+PI continuation was supported at 108 nodes;
remeasurement/validation-return tails remain missing. Do not impute those labels
or call missing support zero benefit. See acquisition_support_decision_v1_zh.md
and reports/acquisition_support_audit_v1_zh.md. Standard support conditions and
the descriptive future-outcome minima do not constitute the new method.

## Memory and terminal-value reference

The continuing goal next permits docs/protocols/memory_terminal_reference_v1_zh.md
on codex/memory-terminal-reference-v1. Implement an explicit task-PI memory
suspend/resume component and a standard two-stage DR full-cutoff-cost reference.
Freeze code/config/protocol/tests before one finite-model output run; disclose
the earlier same-model development arithmetic and 20 unit tests. This is not
unseen-data or robot qualification, a new algorithm, or a publication result.
Enumerate all 44 known probability atoms and 2,112 estimator rows/48 settings;
independently verify 40 rational identities and retain all 8 both-wrong cases.
No native environment/reset/step, new task seeds, model fits, training or API.
Oracle nuisance means are evaluator fixtures only. Preserve old gates/data;
do not claim preserved integral implies bumpless transfer or physical safety.
The actual correction/reidentification family, learned acquisition mechanism,
strong-control deployment and independent own-history evaluation remain open.

This component completed on frozen a3d10e7: all 44 finite-model atoms and 2,112
estimator rows/48 settings passed a separate 101,190-field rational audit.
Forty standard identities passed; all eight both-wrong biases remain. The first
audit failed before field comparison due to a reader/local-list name collision;
f5a3ba6 changes only the reader and two call-site names, with three regressions.
Preserve that failure and the original primary output (not rerun). New checks
total 23; old 1,722 are source-hash reused. Every native interaction/fit/API is
zero. See memory_terminal_reference_decision_v1_zh.md and the Chinese report.
This is known-model arithmetic, not learned-model or robot qualification.
Next define authentic continuous action/memory contracts and a separately
frozen data protocol; do not resurrect failed ARX/F20 or impute missing tails.

## Native acquisition with carried task memory

The continuing goal next permits docs/protocols/memory_acquisition_native_v1_zh.md
on codex/memory-acquisition-native-v1. Freeze the continuous RAW PI .5 actor,
authentic host, independent ledger/memory audit, array tests, allocation and
costs before one 54-execution native software cohort. Seeds 65000--65008 are
native software only; keep 65009--65099 reserved and verify the registry.
Actual CONTINUE/VALIDATE8/MOVE_MEASURE8 return to the actual current state and
KEEP. Validation commits the task integral; movement suspends it. WarmWindow
is unqualified for new parameter fitting and must not enter cold-start C8.
Caps: 27,000 control steps, 54 controlled/2,754 all resets and 1,512,000 frames.
No fits, policy training or online LLM. Keep early ends, incomplete windows,
all failures and source fees. Software coverage failure cannot be repaired by
appending samples or tuning. One-hot arms/KEEP only are not supported DR data
for other policies. This is no new acquisition method, task-gain qualification,
safety result or CCF A contribution; the correction/adoption family stays open.

This native cohort completed on frozen 1d658fe: 54 executions/8,836 control
steps/2,754 all resets/1,421,180 frames. Record audit and native coverage passed,
including 36 real common-prefix pairs and carried memory at 42 returns. Only
3/18 allocated movement cases obtained full windows (4 ended before entry,
11 missed the anchor); all 8 task failures remain. MOVE was 16/18 at mean loss
184 versus CONTINUE/VALIDATE8 15/18 at 153.444; this is descriptive software
data, no task-benefit promotion. VALIDATE8 is an executed task window without
a qualified model-validation or evidence-driven adoption rule. No fits/API.
See memory_acquisition_native_decision_v1_zh.md and the complete Chinese report.
First diagnose missing acquisition support without new interaction; new warm
identification/correction requires an independently frozen qualification design.
Do not retune movement on these 54 cases, filter the 3 windows or impute UPDATE.

## Zero-interaction acquisition position diagnosis

The continuing goal next permits docs/protocols/acquisition_anchor_diagnosis_v1_zh.md
on codex/acquisition-anchor-diagnosis-v1. Freeze evaluation/tests/config before
complete post-hoc exports of all 54 native executions/8,836 steps/8 failures.
Keep 18 assigned moves, lift/lateral stages and all four fixed step bins;
empty/short phases retain reasons. Independently audit actuator/noise order,
readiness gates, command changes and full-cost paired arithmetic. Truth-based
command-balance algebra is evaluator only, no fit or physical equilibrium claim.
New environment/reset/step/frame/fit/API and unexecuted trajectories are zero.
Disable main diagnostics during the independent rational audit and preserve all
source hashes/statistics. Do not retune or select successful windows. These
checks do not satisfy new acquisition, independent task gains or CCF A goals.

That diagnosis completed on frozen d2e04db: 468,194 independently checked fields,
all 54 executions/8,836 saved steps/8 task failures and 18 plotted assignments.
All 11 anchor misses fail position; 7 only position, 2 also motion, 2 also
clearance. Door at 32 spent 38 lift/26 lateral steps and was still moving;
door at 64 spent all 64 in lift. Actual relocation had 451/837 PD-limited
steps but zero final actuator clips. Static truth-based input balance does not
explain all failures or certify physical equilibrium. Keep all original gates.
See acquisition_anchor_diagnosis_decision_v1_zh.md and the full Chinese report.
Next independently freeze/qualify real acquisition controls and warm correction;
do not tune these 54 cases, infer unexecuted PID outcomes or train adoption
values from three successful windows/KEEP-only tails. No new interactions/fits/API.

## Independent standard acquisition and reference qualification

The continuing goal permits docs/protocols/acquisition_reference_qualification_v1_zh.md
on codex/acquisition-reference-qualification-v1. Freeze ten standard programs,
authentic collector, independent record/statistical audits, allocation, tests and
costs before 60 native software cases then 540 independent QUAL cases. QUAL has
9 groups, three per boundary. Keep RAW PI .5, DIRECT_C8, legacy MOVE_INTEGRAL,
fixed/local PD/PID KEEP, registered reference RESET/CARRY and NO_PROBE RESET.
Only old initial-reset C4/C8 infer; no warm physical identification, response or
value training, policy weights or online LLM. Reference is a standard relocation
offset, never a qualified M/b estimate or bumpless/safety result.

Caps total 600 executions/300,000 control steps/30,600 all resets/16,800,000
physical frames, 240 initial C4/C8 attempts and at most 240 read-only refits.
Use QUAL 67000--67026 and native 67200--67202 only after registry verification;
keep 67027--67199 and 67203--67299 reserved. Preserve every early end/invalid
fit/incomplete measurement/task failure; no retries/extensions or parameter repair.
Native failure blocks QUAL. All reference branches keep the actual poststate;
no-probe stops actual relocation before measurement without faking observations.

The acquisition and primary RESET-minus-KEEP task-effect gates are separate.
No CARRY replacement after a failed RESET; report all whole-program RAW/C8/
integral/NO_PROBE costs. Standard component success cannot claim new acquisition
policy gains, qualified physical predictions, independent learned own-history
deployment, safety, novelty or completion of the CCF A objective.

This standard study completed on execution freeze dc7058a: 60 native and 540
QUAL executions, 76,487 control steps, 30,600 all resets, 15,682,435 physical
frames and all 27 task failures retained. Initial C4/C8 inference was 240 and
actual audit refits 240; new response/value/policy training and online LLM zero.
QUAL v1 hit MemoryError while loading, before any refits. Preserve that attempt.
Storage-only repair b90eee7 streams cases with unchanged numerical checks; five
guarded regressions match all 60 saved-native verdicts using cached results.
Two regression runs return 96 cached fits, execute 35,836 extra fixed-policy
queries and perform zero actual fits or physical interactions. Do not retell
that storage repair as re-collection or a changed scientific protocol.

Both record/statistical audits passed, including 432 common prefixes,162
pre-probe/108 post-acquisition state pairs and 360 statistics fields/10,000
whole-group resamples. LOCAL_PID_KEEP obtains 39/54 windows versus 16/54 fixed
PD, meeting its separate acquisition gate. Primary RESET-minus-KEEP loss is
-3.740741,95%[-10.259259,+0.222222],NOT_QUALIFIED. Keep all 54 assignments and
the CARRY secondary; no threshold/sample repair or selector around this version.
RESET 54/54 at loss107.240741 still trails RAW PI53/54 at87.166667 and direct
C8 51/54 at105.018519. No overall gain, physical model or publication promotion.
Next may independently design warm response training/qualification with new
allocation and full costs; do not train/tune on this QUAL, filter its windows,
call WarmWindow ColdPrefix, or resurrect failed ARX/F20. Novel mechanism,
strong-control own-history deployment, ablations and CCF A work remain open.
See acquisition_reference_decision_v1_zh.md and the full Chinese report.

## Source-derived command-state diagnostic

The continuing goal next permits docs/protocols/command_target_diagnostic_v1_zh.md
on codex/command-target-diagnostic-v1. Read all 1,152 selected nominal TRAIN
and all 600 recent standard acquisition executions, 152,128 saved steps total.
No new environment/reset/step/frame/fit/LLM calls or seed allocation. Freeze
the public command-only working reference, analysis/config/tests and source
hashes before full exports. True transforms/applied actions are evaluator only;
source-derived targets are not measured private states, physical predictions
or task/safety qualifications. Preserve short/missing phases and full groups;
do not pool repeated MOVE prefixes or tune against old QUAL. Independent
arithmetic audit disables main diagnostics and discloses its shared reader.
The earlier selected pose/history model already failed; do not repeat it.
Any successor needs a separate collector/native-witness and TRAIN/CAL/QUAL
protocol with full costs before sampling. Novel acquisition decisions, strong
own-history task validation/ablations and the CCF A objective remain open.

This diagnosis completed after reader-only repair c231aa0: all 1,752 saved
executions/152,128 steps, 98,112 phase rows and 1,047 actual entries; independent
audit checks 14,890,179 fields. V1 stopped on legacy TASK/APPROACH labels after
75,744 output rows; preserve that partial and its missing failed-time receipt.
V2 keeps both raw labels and unchanged arithmetic/population/gates. Eighteen
unique phase tests passed, with 1,797 older checks reused by source hash.
Canonical QUAL public SENT versus source-derived APPLIED target group means
are 41.51--80.95mm across six cells. Neither is native measured state; do not
treat this legal summary as physical truth. First design native-witness and
collector qualification before a distinct response TRAIN/CAL/QUAL protocol.
No direct large collection, inverse/task promotion or privileged training.
See command_target_diagnostic_decision_v2_zh.md; the publication goal is open.

## Native command-target witness qualification

The continuing goal next permits docs/protocols/native_command_witness_v1_zh.md
on codex/native-command-witness-v1. Freeze collector, independent arithmetic
audit, strict public projection, tests, allocation and full costs before one
18-case native run, seeds70000--70008 with70009--70099 reserved after registry
verification. Keep the existing LOCAL_PID_KEEP actor and all gains; no new
controller, response/policy training, C4/C8 fits, audit refits or online LLM.
Caps9000 control steps/918 all resets/504000 frames. Read actual native target
values only into evaluator witnesses; they never enter actor/public export or
privileged model training. Audit exact float32 actuation/target recurrence,
public sent-history projection, continuity, budgets and nine paired prefixes.
Keep all eighteen assignments, early ends, missing windows, failures and costs.
Full record integrity and native conformance/coverage gates are separate.
Failure blocks training; success only permits a separately frozen response
TRAIN/CAL/QUAL design. The latent-response successor draft has no executable
allocation. Standard state-space encoders are prior art, not a novel mechanism.
Strong task controls, own-history deployment/ablations and CCF A remain open.

This native qualification completed on execution freeze9c64ab5: all18 cases,
2835 steps/918 all resets/473175 physical frames. All2835 native target updates
are bit-exact;5706 native records and nine actual paired prefixes passed audit.
Complete windows by pushU/C,reachU/C,doorU/C are3/3,3/3,3/3,2/3,3/3,2/3.
Keep the two missing windows (both eventual task success) and one500-step task
failure. No new model/C4/C8/audit fitting or online LLM. Independent replay adds
2070 fixed-policy queries without physical steps. Native contract PASSED only;
it is not learned physical prediction, task benefit or safety qualification.
Source-known nominal SENT remains31.03--163.52mm from actual entry targets.
Private values never become online or privileged training inputs/labels.
Now freeze a distinct response TRAIN/CAL/QUAL protocol before new sampling;
the latent-response draft is still DESIGN_ONLY. Strong baselines, future-data
exclusion, own-history deployment and novel acquisition mechanism remain open.
See native_command_witness_decision_v1_zh.md and the full Chinese report.

## Independent known-command latent response component

The continuing goal permits docs/protocols/latent_response_qualification_v1_zh.md
on codex/latent-response-qualification-v1. Freeze collector, strict public export,
training, array/tensor tests, independent record/model/statistics audits, allocation
and complete costs before SOFTWARE36/TRAIN216/CAL108/QUAL432 executions. Verify
71000--71999 against all used/reserved registries before assigning the new ranges.
Keep the original RAW PI .5 and LOCAL_PID acquisition; declare exogenous commands
before responses. Only known future commands enter eight-step predictions; future
feedback actions/observations and private native/fault/noise labels are forbidden.
No task tail, inverse control, policy or online LLM training. Preserve early ends,
short/missing packets, invalid predictions, partial attempts and all source costs.
Budget:112896 control steps/40392 all resets/20760480 frames. Train21 models:
12 neural fits/60000 updates and30 ridge systems; independent audit30 ridge refits,
no neural optimizer retraining. Keep all24 saved objects including3 zero references.
TRAIN support and independent integrity/native gates precede fits. CAL descriptive
only; bind models/audits before one QUAL. SS_SENT has both co-primary group-CI gates
against same-capacity NO_SENT and stronger direct MLP plus registered point and
coverage gates. No main-candidate replacement, retries, extra samples or retuning.
Software/forward component qualification is not full-task benefit, safety, novelty
or completion of CCF A. Own-history task deployment with strong controls remains open.

This study completed on execution freezee4410b8: all792 executions/59268 control
steps/40392 all resets/20492340 physical frames. Four record audits, TRAIN model
audit and independent CAL/QUAL statistics passed; actual NN training12/60000
updates, scientific ridge30 systems and independent audit30 refits. Keep all24
saved model objects, raw records, checkpoints, failed presentation attempts and
the127727617-byte public TRAIN bundle with four32MiB parts/actual restored copy.
QUAL has348/432 full windows and84 unavailable cases, zero invalid forecasts or
H8 caps. SS_SENT is NOT_QUALIFIED: versus NO_SENT full H8 difference-0.420944mm,
95%[-0.739853,-0.095010]; versus direct MLP-0.288414mm,95%[-0.629071,+0.030676].
Its valid H8 error3.482987mm trails direct ridge1.744844mm; valid H1 .799654mm
trails H10 .115545mm and F20 .226528mm. No secondary-candidate promotion, extra
sampling, inverse/controller selector or task-gain claim around this version.
Zero online LLM/policy training/C4C8 fits. Source-reused1874 unique checks plus
six tensor groups and three independent nested-seed regressions are distinct.
The original registry walker lacked explicit seed-context propagation through
nested lists; independent same-source250-JSON verification finds no old used/
reserved71000--71999 collision. Repair this class before future allocations.
See latent_response_decision_v2_zh.md and the complete Chinese report/appendixv2.
Next only read-only falsifiable diagnosis before an independently frozen successor;
do not tune this QUAL or infer complete task trajectories from XY-only known-input
forecasts. The CCF A research goal remains open.

## Read-only response and complete-task opportunity diagnosis

The continuing goal permits docs/protocols/latent_response_diagnosis_v1_zh.md
on codex/latent-response-diagnosis-v1. Freeze analysis/tests/independent audit/
configuration before a full descriptive census of792 latent-response executions
and540 old standard-reference QUAL executions. New environment/reset/step/frame,
fit/optimizer update/policy/LLM calls and seed allocation are zero. Evaluate fixed
TRAIN checkpoints only on TRAIN; CAL/QUAL only read original saved forecasts.
Do not select checkpoints, tune any old QUAL, swap failed main candidates or
infer complete feedback task trajectories from XY known-input predictors.
Keep exact TRAIN sampler weighting distinct from descriptive group weighting,
partial/empty windows, all signed error cross terms and private-native eval scope.
Old reference RAW programs share RAW PI prefix, not C8. Retain all eight RAW
programs in the realized-future oracle menu and the four-program adoption submenu;
C8/integral remain external whole-program controls. Recheck378 actual prefixes,
all54 units/all10 programs and full cutoff costs without duplicate acquisition
fees. A future-aware record minimum is not a deployable policy, learnability or
task-benefit result. Preserve every old comparison/hash, failure and negative.
New collection requires a falsifiable explanation and independent frozen design;
no inverse/selector stacking around this failed SS version. CCF A remains open.

This diagnosis completed on freeze32b4703 with1,332 saved executions/125,122
steps,100,464 fixed-weight TRAIN query-forwards per pass,103,888 prediction rows,
36,912 final-window metric rows and35,136 trajectory rows. Independent audit
checks11,145,117 fields and378 actual RAW common prefixes; new physical/reset/
step/frame/fit/optimizer/policy/online LLM activity is zero. Keep original source
hashes/comparisons, all missing support and signed cross terms. All three SS
complete TRAIN objectives are below fixed ridge; the explanation that it already
fits this full TRAIN objective worse is unsupported. Independent prediction
failure remains; this does not isolate overfitting, support, noise or optimization.

The eight-program realized-future menu loss is68.611111 versus RAW87.166667,
optimistic difference18.555556 in8/54 units, concentrated in3/9 groups. The four-
program adoption submenu difference is17.574074. Neither menu is a deployable
policy, learnability proof, independent new task gain or general optimal bound.
Keep all nine groups/all conditions/times and all ten original program summaries.
See latent_response_diagnosis_v1_zh.md and latent_response_diagnosis_followup_v1_zh.md.
Current evidence does not support immediate collection. Next complete explicit
prior-art/mechanism and falsifiable successor design with independent training,
calibration, full-cost strong-control own-history task qualification and ablations.
Do not tune old QUAL, choose checkpoints/secondary winners, restrict to favorable
times/groups or stack inverse/controllers around failed ARX/SS. This delivered
diagnosis and its source-reused1,901 checks do not complete the CCF A objective.

## Finite information and implemented-continuation reference

The continuing goal permits docs/protocols/information_scope_reference_v1_zh.md
on codex/information-scope-reference-v1. This is a constructed mathematical audit
and standard finite decision reference, not new robot data or a learned selector.
Freeze all 324 probability records (270 unique,54 deliberate overlap),216 decision
problems and12 reference policies before one census. The explicit rational witness
was derived before freezing; never call it an independent blind discovery.
Use common priors, strictly positive laws and the same coarsening channel. Compare
conditional posterior versus joint/predictive KL and the chain-rule slack bound.
Save 2592 complete policies before true finite evaluation; oracle truth access and
ideal-versus-implemented post choices must be explicit. Full cutoff charges failure
once; rejection retains acquired state. A synthetic alpha name is not live ARX.
Independently reconstruct using Fraction/80-digit Decimal with main math disabled.
No physical/reset/step/frame/fit/optimizer/policy/LLM/seed allocation is allowed.
Preserve old1901 source-reused checks, all failed development logs and negatives.
New bounds derived from standard identities, toy references or oracle gains are
not safety, a deployed robot method, strong-control task benefit or CCF A completion.
Further physical collection still requires a falsifiable learned mechanism and
independent train/calibration/own-history task protocol with full strong controls.

This finite study completed on freeze2c61703. All324 constructed probability rows
(270 unique/54 overlap),216 decision problems and2592 saved policies are retained.
Independent Fraction/80-digit audit checks104,997 fields. Conditional posterior KL
contraction fails in72/324 rows despite common prior/common coarsening and positive
support; all joint-KL/true-information contractions and corrected predictive-slack
bounds pass. This is an explicit mathematical witness, not a robot population.
The official PDF hash/appendix direction and source-reading limits are recorded;
do not generalize the witness to rejecting unrelated results or author intent.

The cost-ignoring ablation has lower grid-mean loss than WORKING_BAYES; keep that
counterevidence. Oracle gains use true synthetic laws and are not deployable gains.
An additional post-hoc standard decision-risk bound is verified exactly on216
problems; those are not216 new unit tests or independent samples. New unique arrays
20 and source-reused1901 checks total1921, with old six tensor groups separate.
See information_scope_reference_v1_zh.md and information_scope_decision_v1_zh.md.
Next define a public-data, decision-relevant joint/complete-performance reference
and actual continuation qualification; generic two-stage regression/VOI/KL is not
new. Do not start collecting without independently frozen mechanisms, allocation,
full cost, strong controls and own-history evaluation. Failed SS/ARX and all old
QUAL remain closed. Novel deployed gains, ablations and the CCF A goal stay open.

## Standard controller-memory countermechanism prerequisite

The continuing full research goal next permits
`docs/protocols/memory_reset_qualification_v1_zh.md` on
`codex/memory-reset-qualification-v1`. Old reference adoption changes both
feedforward offset and task integral; qualify the missing zero-movement
integrator-only strong control before a new learned acquisition protocol.
This is a standard countermechanism prerequisite, not the learned physical
successor required above, a revival of failed SS/ARX, or algorithm novelty.
Freeze collector, array tests, independent streaming record/numerical and
statistics audits, registered seed scope and all costs before sampling.
Native90 cases on three boundary strata precede one independent QUAL540.
Caps315000 control steps/32130 all resets/17640000 frames; initial C4/C8
attempts216 and independent replay refits216 separately counted. No response,
value or policy learning; zero online LLM API. New reset changes only task
integral, no physical reset or extra measurements; saved no-op must exactly
match the complete RAW physical/control/policy trace. Preserve all source
models, original comparisons, early ends, failures and negative results.
The only primary contrast is RAW_RESET_I minus RAW_CONTINUE full cutoff loss,
whole-group stratified bootstrap95 upper below zero. Success changes fully
disclosed, no hidden gate or secondary replacement. Native contract failure
blocks QUAL; no retry, extension, tuning or post-result candidate substitution.
Standard qualification alone cannot finish CCF A; an independently frozen
learned mechanism, own-history full-task gains, strong comparisons/ablations
and existing prior-art requirements remain necessary.

This standard memory-reset study completed on physical freeze814c7db and
reader-only extension4dca769: all90 native/540 QUAL,81042 control steps,32130
all resets,16470210 frames;37 task failures preserved. Both record audits
and independent2004-field statistics passed. Native/QUAL full no-op pairs
18/54 and all shared prefixes/movements passed; no new physical activity
from audits. Initial C4/C8 attempts216 and independent refits216 separately
charged; the original wall-duration reader failure adds1000 policy queries
and7.0277834 seconds, zero fits/physics/API. That failed reader and the
isolated plotting dependency failure remain; only explicit reader/presentation
repairs were used, with no population or scientific-source changes.

The primary RAW_RESET_I minus RAW loss is-6.851852,95%[-24.722222,7.111574],
NOT_QUALIFIED. Success50/54 versus49/54; paired harm14/help9/tie31. Post-move
reset-only is+3.055556 versusKEEP and not supported. Close this fixed-time
version; do not tune times/gains/gates or extend/reuse QUAL as final validation.
NO_PROBE and other secondary points do not replace the primary. Keep all
strong controls and full source costs. Sources for1921 reused+29 main+4 reader
checks total1954 unique, with six old tensor groups separate. New response/
value/policy training and online LLM zero. See memory_reset_decision_v1_zh.md
and both Chinese reports. Concrete learned mechanisms, distinct prior-art
claims, separate TRAIN/CAL/own-history deployment and CCF A remain open;
current evidence does not authorize another unfrozen large collection.

## Post-return supplemental-information mechanism prototype

The next step on codex/information-release-mechanism-v1 follows
docs/protocols/information_release_prototype_v1_zh.md: public state/memory,
post-return randomized supplemental-trace release, carried-integral PI-rate
receiver, complete-task signed targets and independent constructed audit.
This is software/supervision design only, no trained receiver/precritic, native
collection, robot seed allocation, fitting or online LLM. Masked views retain
actual endpoints, duration and task memory: never call this no information or
a complete physical/information mediation decomposition. Empty traces must
produce identical model inputs. Fixed receiver versions bind terminal labels;
standard AIPW, policy factorization and gain adaptation are not novelty.
Preserve all failed prior qualifications; no retuning or relabeling old QUAL.
Only a separate full native/learning/train/calibration/own-history protocol,
complete costs and strong direct-performance/information controls can support
new collection. Array/algebra success does not complete the CCF A objective.

The prototype completed on freeze eb01a32: all18 constructed public cases,
36 release views and36 algebra settings/72 assignment rows retained. The
independent scalar/Fraction audit passed with27 main functions disabled;
30 new plus1954 source-bound reused checks total1984 unique. New robot
activity, scientific fitting, policy queries, episode seeds and online LLM
are all zero. Previous41 delivered artifacts and2 actual restorations were
rehashed unchanged. See reports/information_release_prototype_v1_zh.md.
Next implement the native host and an independently frozen learning/data/cost
protocol; do not substitute more constructed examples for the required trained
mechanism, genuine randomization and independent own-history task gains.

## Authorized repository archival habit

The user explicitly authorized appropriate periodic pushes on2026-10-23.
Archive completed, checked phases without merging; this supersedes earlier
session-level no-push preferences, not the integrity or secret-scan rules.
The first verified remote snapshot is codex/archive-20261023-information-release-v2,
commit8de95c9, sourced from completed2b91c1f. Original local history contains
oversized blobs and remains intact; use separate compact snapshots with full
SHA-256/size catalogs for omitted local data, no force-push or history deletion.
Do not publish unfrozen learning code, imply that omitted records are remotely
available, or call an archival operation a scientific result. Verify remote
refs after each push; keep the original raw data, failures and restorations.

## Closed information-release learning draft

The implemented release_learning_v1 draft was rejected BEFORE collection:
same-feature/weight/ridge M and D heads with D=F-M reparameterize standard DR
complete-program risks M and F. Do not start its5940-run population, bypass
CLOSED_BEFORE_COLLECTION, call factual-Y DIRECT_RISK a sufficient DR control,
or present array checks as native/trained/robot task-benefit evidence. The
source-bound25 new checks reuse1984 unchanged prior checks; no new physics,
scientific training or online LLM. Preserve all draft code/budgets/negatives.
See reports/release_learning_precollection_review_v1_zh.md and the closed
draft protocol. This is a learning-structure rejection, not a negative robot
experiment or a proof against all post-return release designs. A successor
needs a falsifiable distinction over same-privilege standard DR, VoSI/task
acquisition and applicability methods before a fresh independent protocol;
changing ridge to a network or numerical tie behavior alone is insufficient.

## Passive continuation versus validation support audit

On codex/passive-continuation-support-v1, follow
docs/protocols/passive_continuation_support_v1_zh.md. This is post-hoc semantic
replay of immutable memory-reset records: register all630, use all72 RAW_CONTINUE
canonical traces, retain early/short windows and all36 cohort/task/condition/
boundary cells. RAW, fixed0.5 validation and full-release fixed0.5 must consume
only identical saved float32 commands before a next observation is disclosed.
No new physics, resets, fits, policy re-evaluation, episode seeds or online LLM.
Independent literal PI/readers run with main actor/replay/PI numbers disabled.
Do not impute changed-gain outcomes or treat this as active-learning task gains.
Require a same-history passive-adaptation strong control in any successor;
phase names or withholding ordinary task feedback alone do not establish a
new physical evidence action. This prerequisite does not complete CCF A.

This audit completed on41161eb: all630 cases registered,72 canonical RAW,
8921 real command steps,216 exact fixed-controller replays,59 full/5 short/
8 unavailable windows. Independent literal reconstruction checked914944
scalar fields with main actor/replay/PI disabled. No new physics/fits/API or
original-policy calls; 13 new/2009 source-reused checks. VALIDATE_FULL already
exists in the closed20-program design and is the delayed passive-history
reference; do not invent a missing control, duplicate it under DEFER8, or
claim unchanged-gain replay proves learned-gain task benefit. Preserve all
source costs/failures, window missingness and the complete Chinese report.
