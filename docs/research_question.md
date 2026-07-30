# Research Question / 研究问题

## Motivation

Robotic failures are partially observed. A failed rollout can reveal that progress
stopped without uniquely identifying why it stopped. Treating diagnosis as a
passive classification problem hides this ambiguity and encourages evaluation
against injected labels unavailable to a deployed agent.

机器人失败通常是部分可观测的。失败轨迹能够说明任务停止推进，却不一定能唯一解释失败
机制。将诊断简化为被动分类容易忽略这种不确定性，并诱导系统依赖部署时不可见的注入标签。

## Research question

> How can an embodied agent actively acquire diagnostic evidence after a failed
> rollout, generate hypotheses about latent execution failures, and improve
> subsequent rollouts through iterative reasoning?

> 具身 Agent 如何在 rollout 失败后主动获取诊断证据、提出潜在执行故障假设，并通过
> 迭代推理改进后续 rollout？

## Assumptions

- A mostly fixed low-level policy provides the nominal manipulation behavior.
- The research agent acts between rollouts or through bounded diagnostic probes.
- Decisions use only causally available schema-v2 Agent View evidence.
- Oracle perturbation parameters are available only to the experimental evaluator.
- Interaction, API calls, and verification rollouts have explicit budgets.

## Testable hypotheses

1. Uncertainty-gated probes improve evidence efficiency over always-probe behavior.
2. A selected probe reduces hypothesis uncertainty more than passive observation.
3. Evidence-grounded interventions improve verification outcomes over blind search.
4. Confidence calibration predicts when a hypothesis or intervention should be
   rejected rather than executed.
5. Reusing only verified experience can reduce future evidence cost without
   increasing unsafe or unsupported interventions.

## Scope

The current platform studies controlled action bias and stochastic execution noise
in MetaWorld `push-v3`. The focus is post-failure evidence acquisition, mechanism
hypotheses, bounded intervention, and verification. Success rate is a task metric,
not the sole research objective.

## Limitations

Current evidence is simulation-only, task-specific, and based on a scripted policy.
Observation semantics and controlled perturbations are cleaner than real robotics.
No present result establishes open-world diagnosis, real-robot transfer, or memory-
based continual improvement. Those claims require later tasks and hardware evidence.
