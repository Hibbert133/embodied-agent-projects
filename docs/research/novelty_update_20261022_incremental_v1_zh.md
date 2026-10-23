# 2026-10-22：增量控制和执行器动态的查新补充

本补充服务于已完成任务 PI 试验的**事后描述性分析**，不是新方法冻结、独立资格或新颖性证明。原有五条必比路线及双重控制、ABC、ICWM、Wiggle and Go 的比较继续保留，见[前份查新](novelty_update_20261022_zh.md)。未用旧资格人口调参，也未进行在线 LLM API 调用。

| 一手来源与阅读范围 | 可据此确认的已有内容 | 对当前工作的约束 |
|---|---|---|
| [Steffensen 等，Nonlinear Dynamic Inversion with Actuator Dynamics: an Incremental Control Perspective，2201.09805v2](https://arxiv.org/html/2201.09805v2)，摘要、引言及第2–4节 | 将执行器动态纳入反演，并讨论传统 INDI 忽略的状态变化项、执行器带宽和输入缩放。特定极限推导需要其明确假设。 | 不能把上一步响应加命令增量直接当成任意机器人的合格控制接口；需要核对延迟、带宽、输出相对阶与状态项。其理论不是本项目的安全保证。 |
| [Smeur、Chu、de Croon，Adaptive Incremental Nonlinear Dynamic Inversion for Attitude Control of Micro Air Vehicles，2016](https://research.tudelft.nl/en/publications/adaptive-incremental-nonlinear-dynamic-inversion-for-attitude-con-2/)，仅机构摘要和书目信息 | 已研究测量与执行器延迟、控制效能在线适应，并在微型飞行器上实验。 | 增量补偿、在线效能估计和延迟处理均不能直接作为本项目创新；未阅读全文推导，不能据摘要移植其条件。 |
| [Liu 等，Contact-Aware Incremental Model Predictive Control for an Underactuated Aerial Manipulator，2609.11661v1](https://arxiv.org/html/2609.11661v1)，摘要、引言与贡献列表 | 已组合接触相关 NMPC 和全身 INDI，并报告仿真与真实空中书写实验。 | 接触、增量内环与 MPC 的组合也已有研究；没有在本仓库复现该系统，不把其效果外推到 Sawyer 任务。 |

这些来源提示可检验的问题，不决定我们的失败原因。当前保存记录上的简单 XY／四维增量、单位增益上步残差延续都未超过原 F20 的八程序总体预测均值，支持先核对控制接口。它不能唯一归因为执行器带宽，也不能否定满足适用条件的 INDI。原 F20 的局部命令差成分资格仍保留，但其截距不是已经合格的无扰动物理模型。

潜在论文问题仍是：获取动作改变真实状态及模型适用性时，如何选择验证、移动重测及采用程度，并控制包含获取成本的不利更新。需要给出区别于双重控制和上述路线的具体机制，再在方法自身形成的独立时序历史中与强参考、消融比较。本次诊断、标准 PI 和增量预测均不满足 CCF A 贡献目标。

三份 HTML 快照只存于本地 `C:/Users/Administrator/Documents/ChatGPT/robotic agent/research_sources`，未把论文全文作为项目产出提交。固定版本、阅读范围、获取时间、字节数和 SHA256 记于诊断运行的 `result_delivery/literature_sources.json`：2201.09805v2 为 `9a76919f1f3b94fc3eebac42275995592980af2d67461d28893d8b3e41a4967b`；2016机构页为 `5e00ef32c29a6e94229e6764c5644a4f5abea053fc2520611965ce935bc8e4cd`；2609.11661v1 为 `ab7a06341169a38363390b5de4d207fee114d35532b5458aaf65517363439254`。三次存档 HTTP 获取另记，属于文献检索，不属于实验方法 API 调用。
