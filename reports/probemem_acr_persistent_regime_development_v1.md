# Persistent Execution-Regime Development v1

## Question

This development-only paired feasibility study asks whether the registered
repeated probe becomes action-relevant when the latent execution regime persists
across attempts. It does not evaluate GLM, memory, validation, held-out
generalization, or online learning.

## Frozen setup

- Source commit: `282b9c5e76c82fc99d1b48dceedb4e265896d676`
- Run: `acr_persistent_regime_20260803T061354Z_282b9c5e76c8`
- Manifest: `193a741a195085e255c7baac20ce22207aa268371dd425df56f55fa73e7d1129`
- Task seeds: `3900--3949`
- Registered conditions: persistent `fault_01` stable x bias and persistent
  `fault_05` calibrated stochastic noise
- Initial units: 50 task seeds crossed with two conditions = 100
- Frozen score: repeated-probe `estimated_bias_std_norm`
- Frozen threshold: `0.11560838098372882`, reused without retuning
- Candidate skills: bounded planar compensation and independent stochastic
  retry

The Agent decision was persisted before either paired candidate outcome was
executed. Candidate outcomes used independent resets and the same paired
verification random namespace within each case. They are evaluator-only and
must not be represented as naturally available online experience.

## Real result

Forty initial failures required a decision: 25 stable-bias cases and 15
stochastic-noise cases. The run contained 32 exclusive-recovery cases.

| Method | Accepted | Rate | Harmful selections | Mean verification steps |
|---|---:|---:|---:|---:|
| Always compensation | 23/40 | 57.5% | 10 | 251.325 |
| Always retry | 11/40 | 27.5% | 22 | 392.775 |
| Frozen repeated-probe rule | 33/40 | 82.5% | 0 | 154.075 |
| Evaluator-only Oracle | 33/40 | 82.5% | 0 | 153.275 |

The frozen rule selected the accepted candidate in all 32 exclusive-recovery
cases. Its condition-level mechanism decision was also correct for all 40
operational cases. The score distributions were separated in this campaign:
stable bias ranged from 0 to approximately `1.83e-15`, while stochastic noise
ranged from `0.2087` to `1.2924`.

All integrity counters were zero: chronology, Oracle leakage, budget, and
random-namespace violations. The preregistered development promotion gate
passed.

## Interpretation

This result changes the causal evidence design, not the conclusion of the
earlier independent-realization audits. A single independently seeded retry did
not predict the next retry. In contrast, a repeated probe can distinguish two
episode-persistent execution regimes whose preferred registered interventions
differ. The result therefore establishes an identifiable development task on
which a constrained online reasoning layer can be tested.

It does **not** show that GLM improves action selection. The deterministic rule
already performs strongly, so the next GLM experiment is a bounded qualitative
pilot that tests contract validity, evidence use, disagreement, latency, and
failure handling. Validation, memory, and held-out claims remain unauthorized.

## Runtime warnings

MetaWorld/Gymnasium emitted the previously observed observation-space and
policy-clipping warnings. The campaign completed, all integrity counters were
zero, and these warnings did not invalidate the recorded outcomes.

## Artifacts

All compact artifacts are under:

`outputs/probemem_acr/persistent_regime_runs/acr_persistent_regime_20260803T061354Z_282b9c5e76c8/`

Raw initial trajectories remain local and gitignored.
