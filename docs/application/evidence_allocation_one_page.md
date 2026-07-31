# Active Evidence Acquisition for an Embodied Research Agent

## Question

Robotic failures can look alike in a nominal task trajectory even when their
execution mechanisms differ. Given a fixed diagnostic interaction, can an
embodied Agent decide whether its information value warrants the physical cost?

## Method

I built an attempt-level decision layer above a fixed MetaWorld push policy. It
uses only causally available schema-v2 transitions to estimate phase-conditioned
response inconsistency. A threshold frozen on development cases chooses among
`CONTINUE`, `REQUEST_DIAGNOSTIC_PROBE`, and budget-driven `ABSTAIN`. The one
registered probe repeats symmetric XY motions for at most 64 environment steps.
Injected faults and post-hoc labels remain in an evaluator-only Oracle View.

## Frozen experiment

The preregistered held-out population contains 50 rollouts: seeds 330--339 across
four stable-bias conditions and one stochastic-noise condition. Thirty-three
failed rollouts required an online evidence decision. All methods shared the
same task initialization and perturbation condition. The source commit,
configuration, dependency versions, thresholds, data-source hashes, and protocol
implementations are bound into immutable manifest
`a39271db862f28574ad9eb47de4b2bf476950b58749b21baaac59117cf75981c`.

## Preliminary result

The frozen phase gate obtained 33/33 mechanism decisions correct, equal to the
Always-probe baseline, while requesting 7/33 probes instead of 33/33. Diagnostic
interaction decreased from 2,112 to 448 environment steps (78.8%). The strict
post-hoc probe-need labels contained 4 positives and 29 negatives; the frozen
score achieved ROC AUC 0.966 and PR AUC 0.830. On a 12-unit passively matched
subset, phase-versus-always accuracy tied on every unit, while paired probe-cost
difference was -32.0 steps per unit (95% stratified bootstrap interval
[-42.67, -16.0]).

## Claim boundary

This supports selective allocation of one registered diagnostic probe under
controlled execution uncertainty. It does not yet show recovery improvement,
multi-probe selection, real-time control, policy learning, or cross-task
generalization. All four probe-need positives came from stochastic noise, so the
result may partly reflect mechanism separation rather than general evidence
valuation.

## Next experiment

Freeze a matched Phase-3 intervention protocol and test the causal chain
`probe -> belief change -> intervention change -> fresh verification outcome`.
The key question is whether the 64-step evidence cost improves recovery enough to
justify itself, not merely whether it improves a mechanism label.
