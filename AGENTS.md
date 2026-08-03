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
