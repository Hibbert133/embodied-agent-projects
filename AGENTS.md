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
