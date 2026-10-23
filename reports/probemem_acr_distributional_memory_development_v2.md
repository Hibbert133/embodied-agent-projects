# ProbeMem-ACR Distributional Memory Development v2

## Research question

Can a chronological action-outcome posterior improve intervention selection
over accepted-only action reuse, and can posterior abstention reduce harmful
transfer without losing too much recovery coverage?

This is a development-only paired counterfactual feasibility study. It is not
an online-learning, LLM-memory, validation, held-out, or principle-learning
experiment.

## Frozen run

- source commit: `6178437d677aff08c16bd506b82f9aac01890095`;
- run: `acr_distributional_v2_20260802T131001Z_6178437d677a`;
- manifest: `5521614e7dbaf2acc2e7fbe0c7c96051754d6a581459a0d4b1bb1e131b2bb7c4`;
- development seeds available: 2200--2349;
- validation/held-out seeds 2350--2499: not executed.

The label-blind collector stopped at 40 operational cases after scanning 119
initial units. Two additional failed rollouts were ineligible because bounded
compensation could not be constructed from Agent-visible registered-probe
evidence. It executed 80 paired evaluator candidate rollouts.

## Paired candidate population

| Candidate | ACCEPTED | INCONCLUSIVE | REJECTED |
| --- | ---: | ---: | ---: |
| Bounded planar compensation | 20 | 8 | 12 |
| Independent stochastic retry | 24 | 8 | 8 |

There were 18 exclusive-recovery cases, 13 cases where both candidates were
accepted, and 9 where neither candidate was accepted.

## Chronological method results

| Method | Accepted | Harmful transfer | Abstentions | Additional steps |
| --- | ---: | ---: | ---: | ---: |
| Always compensation | 20/40 | 11 | 0 | 15,589 |
| Always retry | 24/40 | 7 | 0 | 13,668 |
| Accepted-only last | 22/40 | 9 | 0 | 14,343 |
| Posterior greedy | 22/40 | 9 | 0 | 14,343 |
| Posterior abstain | 3/40 | 4 | 32 | 5,332 |

Posterior greedy made zero intervention changes relative to accepted-only last
and therefore produced an exactly zero paired accepted-rate difference. It did
not cross the reasoning-to-action boundary.

Posterior abstention reduced harmful transfer from 9 to 4 cases, but after the
eight frozen exploration episodes it abstained on every remaining case. It
missed 24 recoverable cases, had zero post-exploration coverage, and obtained a
-47.5 percentage-point accepted difference versus accepted-only last (paired
bootstrap 95% interval: -62.5 to -32.5 points).

## Integrity

- chronology violations: 0;
- Oracle leakage events: 0;
- current-outcome pre-decision reads: 0;
- collection budget violations: 0;
- API calls: 0.

Gymnasium and MetaWorld emitted their known observation-space and action-clipping
warnings. They did not terminate the run or change the integrity audit.

## Promotion decision

Both promotion routes failed. Posterior greedy did not gain the required three
accepted cases over accepted-only last. Posterior abstention met the harmful-
transfer reduction component but failed the frozen coverage and covered-
precision requirements.

The result indicates that a global action-outcome posterior mainly captures the
population-level advantage of retry; it does not represent case-conditioned
intervention utility. A high-confidence global posterior is also too coarse for
selective abstention under this stream. No threshold is revised and no GLM,
principle, validation, or held-out phase is authorized.

## Artifacts

All run data are under
`outputs/probemem_acr/distributional_runs/acr_distributional_v2_20260802T131001Z_6178437d677a/`.
The comparison figure is
`outputs/probemem_acr/figures/acr_distributional_memory_development_v2.png`.
