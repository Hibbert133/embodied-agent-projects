# From repeated measurements to informative experiments

The failed prefix-refresh study does not show that active evidence can never
help. It shows that a heuristic for repeating one already effective small probe
does not beat a cheap fixed budget on that distribution. Before inventing a
new stopping rule, we need an observation model in which additional evidence
can resolve an action-relevant uncertainty.

## Information missing from fixed input support

Suppose unknown scalar actuator response is represented by polynomial features
phi(u)=(1,u,u^2,u^3,u^4). Measurements only at {0,-m,+m} produce an excitation
matrix of rank at most three. The coefficient direction
(0,0,-m^2,0,1) lies in its nullspace, since u^4-m^2*u^2 vanishes at all three
inputs. Repeating those rows improves precision only in already excited
directions; it cannot identify this missing direction. Adding inputs {-h,+h}
with h nonzero and h different from m yields five distinct inputs and a full-rank
Vandermonde matrix in this idealized response model.

This elementary calculation does not model the entire robot transition, prove
that 0.8 is an optimal amplitude, or guarantee task improvement. It motivates
the separately frozen [physical witness protocol](../protocols/probe_support_identifiability_development_v1.md).
That protocol must additionally check whether the otherwise invisible context
changes successful actions. The fixed three-candidate menu is a limitation:
disjoint successful sets in that menu do not imply no other controller could
succeed in both contexts.

## Existing work makes the novelty bar high

[Wagenmaker, Shi, and Jamieson (2023)](https://arxiv.org/abs/2306.09210)
already formulate task-dependent parameter estimation and near-instance-optimal
exploration for nonlinear control, reducing policy optimization to experiment
design. Thus task relevance, nonlinear excitation, or a different probe amplitude
alone cannot be claimed as our contribution.

[Musavi et al., NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/9b3c956210432122aa5385c355fc7c6e-Abstract-Conference.html)
analyze point and set-membership identification for linearly parameterized
analytic nonlinear systems with random excitation. Our finite support
counterexample does not contradict their results: the excitation assumptions
are materially different. A continuously randomized probe could avoid the
constructed finite set of roots; it is an essential cheap baseline for any
future method study, not an adversary to omit.

[Sobanbabu et al., CoRL 2025](https://proceedings.mlr.press/v305/sobanbabu25a.html)
combine sampling-based system identification with active exploration for legged
sim-to-real learning. Their [project description](https://lecar-lab.github.io/spi-active_/)
uses Fisher information to optimize exploration commands. A future robotics
method must compare against suitable information-based identification, not only
the deliberately blind historical probe.

These are targeted primary-source comparisons, not a complete novelty search
or reproduced implementations. No claim is made about outperforming them.

## Decision after the witness study

If the action-relevance gate fails, retain the counterexample only as a
structural test. Do not tune its coefficient to manufacture a reward gap.
If it passes, it supplies a controlled ambiguity for method development but
still cannot carry a CCF A paper. A stronger successor would need:

- A physically motivated family, e.g. independently specified actuator response
  uncertainty, rather than only a polynomial designed around one probe.
- Several useful probe choices, interaction/reset accounting, and comparison
  to random excitation and standard experiment design at matched cost.
- A precise reason that skill-relative evidence differs from identification
  for ordinary control; any theorem must state its new content beyond existing
  decision-region and task-optimal exploration results.
- Independent training/calibration/evaluation allocations, multiple tasks, and
  real or defensibly transferable measurements. All-state simulator diagnostic
  bounds remain separate from online method scores.

This is a testable research fork, not a declaration that these requirements
have been met. It avoids treating a constructed example or an LLM interface as
the missing contribution.

The [completed witness study](../../reports/probe_support_identifiability_development_v1.md)
failed the action-relevance gate: the unchanged policy succeeded on 48/48
seed/context combinations and no seed had disjoint successful-action sets.
Accordingly, this constructed family is retained only as a negative control.
The proposed selector-development branch is not promoted.
