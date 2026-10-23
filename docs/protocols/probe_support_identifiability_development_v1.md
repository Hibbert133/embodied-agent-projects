# Probe support identifiability: constructed development witness v1

Freeze before collection. This separately versioned diagnostic study changes
the fault family and probe amplitude, not any historical protocol or result.
It tests a prerequisite for an acquisition contribution, not an online agent,
learned method, realistic fault prevalence, or paper readiness.

## Analytic construction and limitations

For x command u, let m be the exact float32 representation of 0.2, let
v=clip(u,-1,1), and define the pre-final-clipping actuator output as

    T_k(u) = u + k v^2 (v^2 - m^2), k in {-0.5,0,+0.5}.

Other coordinates are unchanged. At u in {0,-m,+m}, the additional term is
exactly zero. The historical four-direction probe uses only this set in x.
With matched deterministic resets, its entire transcript is therefore
identical across all three contexts, regardless of repetitions or duration.
No selector using only those transcripts, common initial observations, and
context-independent randomness can distinguish the contexts. This statement
excludes earlier task outcomes and other informative histories.

Proof: all executed probe actions match; induction through the common
transition function gives identical next observations. Hence the transcript
distribution, and any randomized function of it, is context independent.
If two contexts have disjoint successful candidate sets, a uniform mixture
permits at most 1/2 success for any such selector on that pair. A separating
measurement could remove this obstruction; separation alone does not prove
that a learned selector achieves the context-aware bound.

This is an elementary identifiability argument, not a novel theorem. The
polynomial is deliberately constructed to vanish on the old probe support.
It does not show that real actuators behave this way or that historical
additive-bias results were invalid. Active system identification and
task-oriented experiment design are established; see
[Wagenmaker et al.](https://arxiv.org/abs/2306.09210) and
[Musavi et al.](https://proceedings.neurips.cc/paper_files/paper/2024/hash/9b3c956210432122aa5385c355fc7c6e-Abstract-Conference.html).
Finite discrete support here differs from their excitation assumptions.

## Fixed physical population

MetaWorld push-v3, fixed SawyerPushV3Policy, new seeds 8500--8515. All 16
states included, crossed with the three coefficients. No outcome-dependent
stopping or replacement. Seeds 8516--8699 reserved; all older reserves remain.
No Gaussian noise is added: this is an exact structural witness, not a noisy
generalization experiment. Coefficients will not be swept or tuned on results.

Each seed/context collects +x/-x/+y/-y for four steps per direction at each
amplitude 0.2 and 0.8, with fresh matched resets. Each probe costs 16 steps.
Both full transcripts are evaluator-only; there is no adaptive selector.
All probe records for a seed precede its task outcomes. Context labels never
enter an agent; all three candidate plans are fixed before any outcomes.

Evaluate whole-episode x corrections {-0.2,0,+0.2} with at most 500 task steps
each. These bounded actions use the existing compensated policy wrapper;
they are evaluator candidates, not hidden-context decisions. Do not deduplicate
across contexts: changed dynamics require distinct physical rollouts.
The perturbation caps only its nonlinear-term argument; the existing rollout
engine still performs final actuator clipping. All task resets must match
their seed's full initial-observation hash. No API, memory, or principle writes.

Maximum: 16*3*2*16 = 1,536 probe steps plus 16*3*3*500 = 72,000 task steps.
Total maximum 73,536. No prior initial-failure filter; no recovery-rate claim.

## Registered diagnostic gate

Require all: (1) cheap transcripts identical in every seed across contexts;
(2) alternative-amplitude gripper endpoints separate every context pair by
maximum coordinate difference >1e-6 for every seed; (3) at least four seeds
have nonempty but disjoint successful-action sets between negative and
positive contexts; (4) complete population and all integrity/cost checks.
The count threshold is a feasibility requirement, not a powered hypothesis test.

Report all 3x3 task counts, per-seed witnesses, and evaluator-only best common
candidate versus context-aware candidate counts. Those hindsight bounds know
sampled outcomes and may depend on seed; they are not achievable method
scores or generalization estimates. No fitted classifier or post-hoc selection.
Failure is retained without changing magnitude, coefficients, candidate set,
threshold, or seed population. Success permits designing a future method under
a new freeze; it establishes no novelty or publication claim.
