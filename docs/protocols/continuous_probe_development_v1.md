# Continuous evidence under a matched total budget

Freeze source and this protocol before one-shot collection. This tests standard
identification baselines under a realistic state-continuation constraint. It
does not claim an original algorithm, calibrated uncertainty, memory benefit,
or publication readiness. Earlier results and source executors are unchanged.

## Population and methods

Eight new task seeds 8700--8707, crossed with the four historical planar bias
vectors fault_01--fault_04 and independent per-step xyz Gaussian noise std 0.05.
All 32 initial states/contexts included; no failure filter. Keep 8708--8899
reserved. Fixed MetaWorld push-v3/SawyerPushV3Policy, one realization per cell.
The same seed/context noise namespace is shared across methods, but each
method owns its environment, perturbation, and policy. No branch deduplication.

- NO_PROBE: unchanged policy, up to 500 steps.
- CONT_NO_CORRECTION: 16-step continuous probe, unchanged policy from its final
  observation. This controls probe motion, elapsed noise, and task disturbance.
- CONT_STATIC: same probe; standard OLS delta=B*u+c, then bounded correction.
- CONT_DYNAMIC: same probe; previously implemented OLS delta=A*prior_delta+B*u+c,
  then bounded correction. First transition is excluded from dynamic fitting.
- RESET_REFERENCE: historical four-direction matched-reset probe, then policy
  from the initial state. This is explicitly privileged, not reset-equivalent.

The continuous program is +x/-x/+y/-y, magnitude 0.2, four steps each. It uses
one live environment and actuator RNG, with no reset/reseed at any direction
or probe/task boundary. All continuous methods must have identical probe
transcripts for each seed/context. A terminal or successful probe ends the
episode immediately; count its steps and success rather than probing further.

Corrections are whole-episode simultaneous xy offsets derived from solve(B,c),
quantized with the existing DEFAULT_CORRECTION_MAGNITUDES and bounded by 0.2
per axis. RESET_REFERENCE uses the existing symmetric drift/gain estimator
and the same quantization. Invalid fits fall back to zero correction. All
commands still receive the registered perturbation and final actuator clipping.
The point estimate is not a physical-bias certificate or a learned controller.

## Budget and chronology

Primary budget is 500 total physical environment steps per method episode,
including all probe steps; continuous methods reserve 484 policy steps after
a complete probe. This separately versioned budget differs from historical
500-task-step reserves and fits MetaWorld's 500-step episode horizon without
extending it. NO_PROBE gets all 500. RESET_REFERENCE spends 16 probe steps and
up to 484 task steps, with five resets instead of one.

Also report success with an equal 484-policy-step cap: NO_PROBE is truncated
analytically at its first 484 task steps; probe methods already have that cap.
This secondary comparison allows 16 extra probe steps and is labeled as such.
Do not pool these budget semantics or use the secondary metric for promotion.
Maximum physical steps = 8*4*5*500 = 80,000. Count simulator-side resets and
actuator reset/apply calls separately. API and memory writes remain zero.

The decision log is written after the visible probe and before the first task
step. Record full visible probe transitions, initial/handoff hashes, a digest
of actuator RNG state at handoff, and consecutive task before/after hashes with
cumulative actuator-call counters. The host creates/reset its actuator once
and continues the same instance. RNG digests are evaluator metadata only.
Task-state changes caused by probing are part of the realizable intervention.

## Metrics and development gate

Report all five success counts, mean total steps, reset counts, terminal probe
outcomes, object displacement during probe, fit validity, and evaluator-only
equivalent-offset error against injected bias. Error is diagnostic, not an
agent input or a task-performance substitute. No correction tuning, selected
subsets, extra realizations, or magnitude/threshold sweeps.

The primary evidence-utility contrasts are CONT_STATIC and CONT_DYNAMIC each
minus CONT_NO_CORRECTION. Bootstrap eight whole task-seed clusters, retaining
all four contexts within each, for 10,000 draws with seed 20261013. Use 97.5%
two-sided percentile intervals (two prespecified comparisons; Bonferroni-style
development screening). Eight clusters and bootstrap discreteness preclude
a definitive powered superiority claim.

The feasibility gate passes if at least one estimator has a lower contrast
endpoint >0 and at least as many successes as NO_PROBE under the primary total
budget, with the complete population and zero integrity violations. Passage
establishes useful continuous evidence on this development task, not superiority
of dynamic over static, a novel method, validation eligibility, or publication.
Preserve failure without tuning/rerunning these seeds. A future method requires
its own contribution, strong baselines, independent protocol, and data.
