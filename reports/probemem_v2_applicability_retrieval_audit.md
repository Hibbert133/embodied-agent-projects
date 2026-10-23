# ProbeMem Applicability Retrieval Feasibility Audit

## Setup

The audit uses 8 decisive historical references from seeds 763--817 and 7 later decisive queries from seeds 854--895. A single nearest reference is retrieved in the full 13-feature Agent-visible signature after scaling only on historical references.

## Actual result

Nearest-reference skill agreement was 2/7 (28.6%). The frozen single-feature selector chose the accepted skill in 4/7 (57.1%).
Confusion counts: {'INDEPENDENT_STOCHASTIC_RETRY->INDEPENDENT_STOCHASTIC_RETRY': 1, 'BOUNDED_PLANAR_COMPENSATION->INDEPENDENT_STOCHASTIC_RETRY': 4, 'BOUNDED_PLANAR_COMPENSATION->BOUNDED_PLANAR_COMPENSATION': 1, 'INDEPENDENT_STOCHASTIC_RETRY->BOUNDED_PLANAR_COMPENSATION': 1}.
The seven queries retrieved 7 unique historical references; reference usage was {764: 1, 775: 1, 781: 1, 790: 1, 794: 1, 816: 1, 817: 1}.
Median standardized distance was 0.818 (correct 0.626, errors 1.088).

## Claim boundary

The query features are leakage-safe, but the historical preferred-skill labels come from evaluator-only paired counterfactual outcomes. This is therefore a post-hoc feature/retrieval feasibility audit, not operational Verified Episodic Memory, online adaptation, or a Phase-D promotion result. No rollout, API call, threshold fit, or prompt change was performed.

The directly generated visualization is stored at
`outputs/probemem_v2/figures/applicability_retrieval_audit.png`.
