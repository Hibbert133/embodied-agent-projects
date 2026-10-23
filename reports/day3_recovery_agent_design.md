# Day 3 — Bounded Failure-Aware Recovery Agent

## 中文摘要

本阶段把 Agent 明确定义为 rollout 级高层实验规划器，而不是逐 timestep 机器人控制器。
低层 `SawyerPushV3Policy` 保持不变；当隐藏的单轴动作偏差导致任务失败时，高层 Agent
读取无扰动真值的 schema-v2 Agent View，提出下一次完整 rollout 的 x/y 固定命令补偿。
所有提案都受到候选幅值、rollout 预算和本地 schema 校验约束。

核心研究问题是：在相同故障、seed、候选空间和交互预算下，轨迹证据引导的恢复是否比
盲目随机搜索更节省 rollout？实验接口支持无恢复、随机搜索、确定性规则、OpenAI
Responses API planner 和 Oracle 上界。LLM 是额外对照组，不替代可复现的规则基线。

OpenAI planner 只能收到由 Agent View 计算的距离、进度、位移、横向漂移和三个时间切片。
它看不到注入偏差、`perturbed_action`、`executed_action` 或裁剪审计字段。模型只能返回
结构化 `ExperimentProposal`，无法执行 shell、修改仓库或直接控制环境。模型、prompt hash、
response ID、token usage 和延迟均写入审计日志；API 错误不会静默回退。

当前提交实现了实验基础设施和 mock API 测试，尚未把未经真实 API 运行的数字写入报告。
正式实验前必须冻结 prompt，并在 held-out seeds 上比较恢复成功率、成功所需 trial 数和累计
环境步数。代表性视频应从量化结果中自动选择共同成功、共同失败及方法分歧案例。

## English Summary

This stage defines the agent as a rollout-level experiment planner rather than a
per-timestep robot controller. The low-level `SawyerPushV3Policy` remains fixed.
After a hidden single-axis action bias causes a failure, the high-level agent reads
a leakage-safe schema-v2 Agent View and proposes a bounded x/y command correction
for the next complete rollout.

The research question is whether evidence-guided recovery uses fewer rollouts than
blind random search under the same faults, seeds, candidate corrections, and
interaction budget. The shared interface supports no recovery, random search, a
deterministic rule baseline, an OpenAI Responses API planner, and an Oracle upper
bound. The LLM is an additional experimental arm, not a replacement for the
reproducible baseline.

An Anthropic-compatible Messages adapter is also available for explicitly named
third-party models such as `glm-5.1`. Provider, endpoint, returned model name,
response ID, token usage, latency, and prompt hash are retained in the audit log.
Provider-specific model aliases are not used in reported experiments.

The OpenAI planner receives only compact agent-visible metrics and three temporal
snapshots. It never receives the injected bias or Oracle-only action fields. Its
structured proposal is validated locally, and it has no shell, repository-editing,
or direct environment-control capability. Live API results are intentionally not
reported until a prompt-frozen held-out evaluation has actually been run.

## Reproduction Commands

```powershell
python scripts/run_recovery_agent.py --planner none --num-episodes 3
python scripts/run_recovery_agent.py --planner random --num-episodes 3
python scripts/run_recovery_agent.py --planner rule --num-episodes 3
python scripts/run_recovery_agent.py --planner oracle --num-episodes 3
$env:OPENAI_API_KEY="your-api-key"
python scripts/run_recovery_agent.py --planner openai --num-episodes 3 --model gpt-5.6-luna
.\scripts\run_anthropic_recovery.ps1 -Model glm-5.1 -Seed 148 -MaxTrials 5
```
