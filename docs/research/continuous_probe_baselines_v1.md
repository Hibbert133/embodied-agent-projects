# Continuous probing: remove a privileged reset assumption

This is an implemented engineering foundation and a prospective study design,
not a frozen experiment, new algorithm, or performance result. No fresh
simulator seeds were executed for this phase. Historical protocols, their
probe implementations, and their results remain unchanged.

## The concrete limitation

`run_symmetric_probes` resets the environment and actuator random stream at
each of four directions. `run_episode` resets again before task execution.
Consequently the historical procedure acquires measurements from multiple
matched initial states and then discards the physical state reached during
measurement. This is useful controlled evaluation, but a physical robot
cannot generally obtain those resets without interaction or instrumentation.

The [read-only cost audit](../../outputs/evidence_refresh/reset_cost_audit_v1/report.md)
derives 1,964 explicit collection reset calls in the 96-episode prefix study:
96 initial inspections, 1,536 directional starts, and 332 physical task
branches. Constructor-internal calls are excluded; these are source-derived
counts, not instrumented robot repositioning time.

Let R be a uniform reset cost in step-equivalent units. Omitting the common
task-start reset, candidate minus fixed-16 mean cost is

    24.4791667 + 5.2916667 R.

The candidate has one fewer success. Its observed dominance failure therefore
persists for every R >= 0. The audit does not invalidate the registered
step-count result or convert simulation resets into measured latency.

## Implemented causal interface

`src/probe/continuous.py` provides a collector that receives only a live step
callback, a current visible observation, an explicit command sequence, and a
budget. It has no environment factory, reset method, hidden fault parameter,
or random-seed argument. The host must preserve the same environment and
actuator RNG in the callback and subsequent task execution.

The entire command sequence and reserved task budget are checked before the
first action. Every transition stores the commanded action and consecutive
visible observations, never the hidden perturbed action. Termination,
truncation, or success stops immediately. The final observation is returned
for continuation, not replaced by an initial-state replay. Observation values
are copied to immutable tuples; unknown fields are rejected by the schema.

The included 16-step program uses +x/-x/+y/-y at magnitude 0.2 for four steps
each. Its input count matches the cheap historical probe, but its transitions
are different because the state and actuator random stream continue between
directions. Historical probe estimates cannot simply be relabeled as results
of this procedure.

## A standard identification baseline, not a certificate

The local fit uses observed xy increments and commanded xy inputs:

    delta[t] = A delta[t-1] + B command[t] + c.

It estimates A, B, c by ordinary least squares with column scaling for numerical
conditioning. The equivalent command offset is solve(B,c). Insufficient data,
rank-deficient excitation, or an unidentifiable response returns no estimate.
These checks ensure numerical usability; they do not establish statistical
confidence, physical-model correctness, out-of-distribution validity, or task
utility. A nonzero intercept can absorb effects other than actuator bias.
Errors in observed increments and model misspecification can bias OLS.

Synthetic tests recover known cross-coupled dynamics and offsets, reject
discontinuous trajectories, preserve state continuity, stop on terminal
events, and verify budget reservation before interaction. They are software
evidence only. There is no MetaWorld calibration or success claim yet.

## Prospective evaluation needed next

Before collection, freeze an independent protocol, source commit, sample size,
fresh seed allocation, observation model, estimator, fallback, and all metrics.
Do not execute earlier reserved seeds. Required comparisons are:

1. Uncorrected fixed policy from the initial state, as the zero-probe baseline.
2. Continuous probe followed by uncorrected policy, to isolate probe motion
   and state disturbance from correction information.
3. Continuous probe with a simple static response fit, followed by bounded
   correction from its actual final state.
4. Continuous probe with the implemented dynamic response fit and the same
   correction set and fallback. No extra simulator state access.
5. Historical matched-reset probe as an explicitly privileged reference,
   reporting reset count separately; do not call it interaction-equivalent.

Each realizable episode must use one initial reset, one persistent actuator
noise stream, and no reset at the probe/task boundary. Count all probe and task
actions, including terminal probe outcomes. Compare both total-budget and
task-reserve semantics explicitly; an extra 16-step allowance is not free.
Record the exact handoff observation, terminal state, and random-stream
continuation to verify this contract from artifacts.

Report task success, total steps, probe-induced object displacement, estimator
validity/error (hidden parameters evaluator-only), and independent-seed paired
uncertainty. A diagnostic fit alone cannot pass a task-performance gate. An
adaptive acquisition method or memory layer should wait until useful
continuous evidence is demonstrated against these baselines.

## Prior work and publication boundary

Reset-free operation itself is established. [Reset-Free Guided Policy Search](https://arxiv.org/abs/1610.01112)
addresses learning with stochastic rather than repeatable initial states.
[Reset-Free Reinforcement Learning via Multi-Task Learning](https://arxiv.org/abs/2104.11203)
addresses autonomous dexterous learning without explicit reset intervention.
Their training settings differ from this fixed-policy diagnostic layer;
the distinction is scope, not evidence of novelty.

[Receding Horizon Curiosity](https://proceedings.mlr.press/v100/schultheis20a.html)
already interleaves exploration with Bayesian nonlinear identification. A
local ARX fit or a continuous probe is therefore an engineering baseline.
The CCF A objective still requires a defensible new contribution, competitive
method evidence, independent tasks, and a paper. This phase closes a concrete
evaluation/implementation gap without claiming those requirements are met.

The separately frozen [subsequent simulator study](../../reports/continuous_probe_development_v1.md)
has now completed. It verified continuous state/RNG handoff but failed its
utility gate: dynamic OLS 15/32 versus probe-without-correction 13/32, with an
interval including zero. This preserves the foundation's baseline status;
it does not promote the estimator or authorize tuning those evaluation seeds.
