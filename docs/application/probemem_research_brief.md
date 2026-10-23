# Selective evidence acquisition and the limits of verified memory

Application research brief — current evidence, October 2026.

## Research question

When a robot attempt fails, which additional observation is worth acquiring,
and when can a previously successful corrective action be reused? I investigate
these questions with a constrained decision layer above a fixed MetaWorld
`push-v3` policy, separating diagnostic information from recovery utility.

## Technical contribution

The project implements causally available Agent View evidence, bounded probe
allocation, discrete corrective skills, fresh verification, and method-owned
chronological memory. Evaluator-only fault labels and unselected outcomes are
excluded from agent decisions and memory. Frozen configurations, seed registries,
manifest hashes, paired outcomes, and fail-closed tests make the experiments
traceable, including failed and incomplete studies.

## Evidence

The historical frozen allocation experiment matched always-probe mechanism
diagnosis on 33/33 operational cases while using 448 rather than 2,112 probe
steps (78.8% less diagnostic interaction). This supports a narrow fixed-probe
allocation result in one simulated task; it does not establish recovery benefit.
See the [allocation brief](evidence_allocation_one_page.md) for its provenance.

A subsequent deterministic five-configuration development study retained 60
initial failures from 94 sequential units. Evidence Acquisition Enabled
recovered 55/60 versus Baseline's 51/60. Only four paired recovery outcomes
differed, and the population contained 52 stable-bias and eight noise cases.
The observed gain needs independent replication.

Adding accepted-only memory reduced the registered primary recovery count to
52/60, and adding the verifier changed no recovery outcomes. A post-hoc audit
of the four already-collected evaluator realizations found that the memory
contrast reverses sign across repetitions. This isolates an important research
problem: a successful past intervention is not sufficient evidence for reliable
transfer under stochastic execution. It does not prove memory is universally
harmful, beneficial, or equivalent to the no-memory method.

The latest prospective experiment established useful continuous evidence under
an explicit nominal-calibration assumption. An independently qualified response
prior obtained 64/64 task successes across 16 new seeds and four bias contexts,
versus 33/64 for the same continuous probe without correction. The paired
seed-cluster interval for the +48.44-percentage-point contrast was [39.06,57.81].
A same-data nearest-prior baseline obtained 62/64, so affine superiority is
not established. Both priors disclose 2,304 offline steps and 144 resets.
This is an all-state single-task baseline result, separate from recovery after
failure. See the [task-utility report](../../reports/calibrated_continuous_task_utility_v1.md).

## Scope and next question

Two subsequent prospective studies sharpened the question. A crossed-context
test isolated a 41.80-percentage-point probe/execution persistence interaction.
An eight-stream, eight-method study then rejected a concrete adaptive refresh
heuristic: it obtained 87/96 task successes at 37.17 mean probe steps, while
fixed 16-step acquisition obtained 88/96. These all-state task experiments are
distinct from the earlier failure-recovery studies. They demonstrate causal
experiment design and willingness to reject an unsupported mechanism, rather
than a proven novel algorithm. See the [refresh report](../../reports/evidence_refresh_prefix_development_v1.md).

This is a reproducible simulation research prototype, not a published result or
a new low-level robot policy. LLM integration is a separate constrained-interface
line of work; the five-configuration results above use no LLM calls. Generalization
across tasks, real robots, and independent online streams remains unestablished.
The next scientific question is whether uncertainty about an action's outcome
distribution can be distinguished from uncertainty about memory applicability.
That requires a separately preregistered prospective experiment.

## CV wording

**Embodied Agent Research — Selective Evidence Acquisition and Verified Memory**

- Built a reproducible MetaWorld research prototype with leakage-separated
  evidence, bounded diagnostic probes, fresh recovery verification, and
  chronological memory audits.
- Matched always-probe diagnosis on 33 operational held-out cases using 78.8%
  fewer diagnostic interaction steps; evaluated five configurations on 60 fresh
  development failures and audited paired recovery and stochastic sensitivity.
- Identified limits of accepted-only memory transfer and preserved negative
  results through immutable manifests and automated integrity checks.
- Evaluated a qualified continuous-evidence baseline on 16 new task seeds and
  four bias contexts, obtaining 64/64 successes versus 33/64 for the identical
  probe without correction, with explicit offline costs and state/RNG audits.

## Faculty-outreach paragraph

My recent project studies how an embodied agent should acquire evidence after
a failed attempt and decide whether verified experience applies to a new case.
I built a reproducible MetaWorld prototype with explicit causal information
boundaries and fresh intervention verification. A frozen allocation study
matched always-probe diagnosis with 78.8% fewer probe steps, while follow-up
development experiments exposed unstable memory-transfer effects under
stochastic recovery. I am interested in studying action-conditional uncertainty
and reliable experience reuse more deeply during doctoral research.

More recent work independently calibrated a continuous response model and
tested it prospectively against probe-motion and matched-data controls. This
established a useful task baseline while exposing the remaining questions of
calibration validity, stronger passive alternatives, and cross-task transfer.

## Supporting artifacts

- [Frozen additional-experiments protocol](../protocols/probemem_additional_experiments_v1.md)
- [Recovery robustness audit](../../reports/probemem_additional_robustness_v1.md)
- [Machine-readable audit and source hashes](../../outputs/probemem_additional/robustness_audit_v1/audit.json)

The additional-experiment source is run
`probemem_additional_ablation_20260901T031926Z_4f9fd0b4556c`, manifest
`759c9586f88d5bff43380b67e2bdae1931cd24e3bd57c726643e95510c6fc80f`, commit
`4f9fd0b4556c11c0b730ccef787bff4beee977d1`.
