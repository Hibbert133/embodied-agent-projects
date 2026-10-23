# Evidence refresh: contribution boundary and baseline gaps

Primary-source check: 2026-10-13. This is a targeted comparison, not an exhaustive
systematic review. It does not authorize changing the running frozen experiment.

| Prior work | Established capability | Consequence for this project |
|---|---|---|
| [Javdani et al., AISTATS 2014](https://proceedings.mlr.press/v33/javdani14.html) | Sequential tests that identify a decision region rather than resolve every hypothesis; HEC has a competitive guarantee and a robot-localization application. | Stopping when plausible models imply the same action is already established. Our leave-one-out prefix agreement is only a heuristic and inherits none of those guarantees. |
| [Gundersen et al., UAI 2021](https://arxiv.org/abs/2103.14224) | Active selection of measurement fidelity using information about changepoints while accounting for collection cost. | Cost-sensitive refresh and variable measurement fidelity are not sufficient novelty. The present threshold baseline is not this Bayesian algorithm. |
| [Steinparz et al., CoLLAs 2022](https://proceedings.mlr.press/v199/steinparz22a.html) | Reactive exploration under continuing domain shifts, with policy adaptation in lifelong reinforcement learning. | Detecting change and then exploring is established. Their policy-learning setting differs from our fixed low-level controller; comparison must match permitted adaptation. |
| [Bao et al., PBD-AG, August 2026 preprint](https://arxiv.org/abs/2608.10449) | Persistent scene representations distinguish stable fixtures from revisable object events and choose inspections balancing coverage, travel, risk, and redundancy. | Persistent robot evidence with targeted reinspection is not an untouched topic. This work concerns scene-state maintenance, not the bias-compensation experiment here; it is adjacent evidence, not a directly executable control baseline. |

These implications are our interpretation of the linked primary sources. The
2026 preprint is not presented as peer-reviewed publication evidence. Full
algorithmic reproduction would require reading and implementing each method's
technical assumptions, not relabeling a threshold or a cached action.

## What the frozen experiment can actually decide

The prefix study tests whether one concrete action-agreement heuristic improves
the cost/success tradeoff over simple, strong alternatives. Fixed 16 steps is
essential: beating 64 steps alone does not establish useful adaptive allocation.
The comparison includes method-owned accepted-only history and matched current
evidence; no hidden context or future outcome is available to the selector.

The study does not resolve novelty, calibration, choice among multiple probe
families, learning a utility model, or performance across robot tasks. Eight
streams with one fixed noise level are development evidence. Repeatedly changing
heuristics after seeing failures would be a search process, not independent
confirmation of a theory.

## Requirements for a substantive successor

1. Identify a concrete ambiguity that the strongest cheap baseline cannot
   resolve. Specify which *observable* acquisition could resolve it and why it
   changes the downstream action, before collecting another test population.
2. Separate representation error, measurement uncertainty, and environment
   change. Agreement between a few point estimates does not bound any of them.
   Any confidence statement needs assumptions and a calibration population
   independent of the evaluation streams.
3. Include a standard sequential decision-region or Bayesian acquisition method
   when its assumptions fit, plus fixed small budgets and current-state
   identification. Match observations, reset access, and all interaction costs.
4. Account for the cost of resetting to a probe state. The current simulator
   gives reset access; a physical robot usually cannot reproduce that operation
   freely. A future deployment claim needs a feasible evidence collection model.
5. Freeze a new design and seed allocation. Preserve all current outputs;
   neither reinterpreting failed gates nor selecting favorable subsets is a
   substitute for independent evidence.

The present implementation is a falsifiable engineering candidate, not the
claimed CCF A contribution. A useful negative result should narrow or reject
this candidate rather than lead directly to an LLM wrapper or a larger set of
hand-tuned thresholds.
