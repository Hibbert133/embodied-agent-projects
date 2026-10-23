# Problem Definition: Active Evidence Acquisition After Embodied Failure

## Research question

> How can a self-improving embodied agent recognize that a failed rollout is
> diagnostically ambiguous, acquire the minimum additional evidence needed to
> distinguish latent failure mechanisms, and verify a corrective intervention
> without access to Oracle fault labels?

The manipulation policy is not the primary research object. The research object is
the post-failure Agent that decides whether to diagnose from existing evidence,
perform a bounded diagnostic probe, abstain, or verify an intervention.

The question decomposes into four measurable subquestions:

1. **Identifiability:** when is the nominal rollout sufficient to distinguish the
   relevant failure mechanisms?
2. **Evidence allocation:** when should the Agent spend additional environment
   steps on a probe rather than act immediately?
3. **Probe utility:** which bounded interaction most reduces uncertainty about the
   mechanism that matters for intervention selection?
4. **Verification:** can the Agent reject unsupported corrections and retain only
   interventions that improve a fresh rollout?

## Motivation

Robot failures are partially observed. A trajectory exposes commanded actions and
state transitions, but not necessarily the hidden execution process that produced
them. The same symptom—little task progress, lateral object drift, missed contact,
or timeout—can be compatible with multiple mechanisms requiring different
responses.

Passive failure classification assumes the available rollout already contains the
evidence needed for diagnosis. That assumption is often false because nominal
policies optimize task completion rather than system identification. They may issue
correlated actions, visit a narrow state range, or terminate before exposing the
fault. A calibrated Agent should be able to say that the evidence is insufficient
and request a targeted interaction instead of producing an unsupported label.

This reframes post-failure adaptation as a sequential research process:

```text
observe -> form competing hypotheses -> identify missing evidence
-> design/choose probe -> update hypothesis -> intervene -> verify
```

## Assumptions

- A mostly fixed low-level policy supplies nominal manipulation behavior.
- The environment permits bounded diagnostic interactions or additional rollouts.
- Agent decisions use only causally available schema-v2 Agent View records.
- The simulator may expose injected fault parameters to the evaluator after a
  decision, but never to the decision-making Agent.
- Environment steps, verification rollouts, wall time, and optional external-model
  calls have explicit budgets.
- A correction is not accepted merely because it is plausible; it must be tested
  in a fresh verification rollout.
- Self-improvement means accumulating verified evidence and interventions. It does
  not currently mean policy-gradient training, behavior cloning, or weight updates.

## Information boundary

### Agent-visible evidence

- observation before an action;
- commanded action;
- next observation;
- reward and task outcome flags;
- task-progress metrics derived from the next observation;
- provenance, uncertainty summaries, and remaining budgets.

### Oracle-only audit information

- injected perturbation type, axis, sign, or magnitude;
- perturbed and executed action when different from the command;
- clipping audit fields;
- simulator labels used to score a diagnosis;
- post-hoc counterfactual outcomes unavailable at decision time.

Oracle data may define controlled experimental conditions and evaluate accuracy. It
must not be serialized into prompts, Agent evidence packets, probe planners, or
corrective-intervention decisions.

## Failure taxonomy

The taxonomy separates **observable symptoms** from **latent mechanisms**. A symptom
is not a diagnosis: several mechanisms may produce the same symptom.

### Observable symptoms

- no or insufficient task progress;
- lateral drift away from the goal path;
- gripper fails to approach or maintain contact with the object;
- object moves but does not converge to the goal;
- action clipping or saturation in Oracle audit;
- episode timeout or termination without success.

### Latent execution mechanisms

| Mechanism | Experimental status | Example prediction | Potential discriminating evidence |
|---|---|---|---|
| Systematic action bias | Implemented | Repeated commands exhibit stable signed drift | Symmetric directional response |
| Stochastic action noise | Implemented | Estimated drift varies across repeated realizations | Repeated-probe consistency |
| Action-scale loss | Implemented | Response magnitude is consistently weaker than commanded | Opposed commands at known magnitudes |
| Control delay | Taxonomy only | State response is temporally shifted after the command | Time-local repeated action |
| Contact/dynamics mismatch | Taxonomy only | Free-space motion is normal but contact response differs | Low-force contact probe |
| Perception error | Taxonomy only | Observed state is inconsistent with physical response | Independent observation or viewpoint |
| Unknown / insufficient evidence | Required fallback | No supported mechanism dominates | Abstain or request evidence |

Only action bias, Gaussian noise, and action scaling are currently injected and
evaluated. Other rows define future research scope; they are not implemented
capabilities.

## Why passive diagnosis is insufficient

### Observational equivalence

Different mechanisms can generate similar task-level progress and final distances.
A single failure label can therefore hide competing causal explanations.

### Insufficient excitation

The nominal policy may not command both directions of an action dimension. Without
paired excitation, a fitted model can confuse response gain, constant drift, and
task-dependent motion.

### Stochastic confounding

A one-off noisy realization may look like a stable bias. Repetition is needed to
separate persistent drift from execution variance.

### Intervention risk

A confident but wrong mechanism can produce a correction that worsens the next
rollout. Diagnostic accuracy must therefore be linked to intervention verification,
not evaluated only against a simulator label.

### Existing counterexample

Current single-axis studies show both sides of the problem. Active probes can rescue
an individual difficult seed, but passive correction already succeeds on many
held-out single-axis failures. An always-probe or online policy that requests a
probe for every case is robust but evidence-inefficient. The next scientific test
must use ambiguity pairs where passive evidence genuinely cannot determine the
correct intervention.

## Testable hypotheses

1. Repeated directional evidence distinguishes stable bias from stochastic noise
   more accurately than a single passive rollout.
2. An uncertainty-gated Agent matches always-probe diagnostic accuracy while using
   fewer probe environment steps on a frozen held-out split.
3. Mechanism-aware intervention selection improves verification success over a
   correction chosen from task progress alone.
4. Confidence is useful only if it predicts diagnosis error or failed verification;
   uncalibrated confidence should not authorize memory updates.

## Non-goals for the current milestone

- learning a new manipulation policy;
- reinforcement learning, behavior cloning, or VLA training;
- direct unconstrained action generation by a language model;
- operational episodic-memory retrieval;
- real-robot or cross-task generalization claims;
- adding failure mechanisms without a specific identifiability experiment.
