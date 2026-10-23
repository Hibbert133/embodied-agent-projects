# 训练受控开发的查新与边界

2026-10-22；原始来源核对。本页不证明新颖性，也不改变旧资格。

|原始来源|已读内容|本项目的使用边界|
|---|---|---|
|[Are Transformers Effective for Time Series Forecasting?](https://ojs.aaai.org/index.php/AAAI/article/download/26317/26089)，AAAI2023；[作者实现](https://github.com/cure-lab/LTSF-Linear)|摘要和引言比较长期预测架构及简单线性参考，并指出既有对照中的预测策略差异；实现说明Linear／DLinear／NLinear。|复杂模型不应预设优于强线性；同输入、目标和评价制度需要明确。该论文研究长期时间序列预测，不能推出本项目一步机器人接触响应的具体赢家。这里不把F20或归一化称为复现DLinear，也不把一次基线改进称为新贡献。|
|[Neural Robot Dynamics](https://proceedings.mlr.press/v305/xu25g.html)，CoRL2025／PMLR305|正式论文页摘要：以机器人为中心、空间不变的表示，用神经模型替代解析模拟器的低层动力学与接触求解，并检验跨任务／环境泛化。|可见表示和物理归纳偏置是已有路线。“加历史”不能代替受控表示检查。本项目只有公开39维观测、发送命令与固定策略，没有其完整刚体／接触求解权限；当前不冒充等价复现，也不由其长期仿真结果保证本工作模型。|
|[PyTorch v2.2.2 GRU实现](https://github.com/pytorch/pytorch/blob/v2.2.2/torch/nn/modules/rnn.py)|固定版本实现与本地已资格运行时相核对；GRU候选门使用重置门乘递归仿射结果，真实长度pack不消费填充帧。|软件实现资格与物理预测资格分别判断；此次同架构输入补零仅控制总参数形状，明确报告F20未激活的2208个输入参数，不宣称信息量或有效容量相同。|

本轮完整2特征×2损失×2历史×3初始化只是开发排查。它不采用旧TEST选窗口、删维度或调尺度；没有新采集与独立确认。已经看过的旧CAL／TEST不能变成后续变体的“新”验证。

原论文主线和必比路线仍见 `history_response_failure_prior_art_v1_zh.md` 与 `observable_history_prior_art_update_v1_zh.md`：模型适用域、Residual RL、OCCAM、GAUGE、Poke and Strike、任务最优探索、ASID与双重控制。潜在贡献必须落实获取后的真实状态、证据与采用／拒绝后续的联合决策区别；标准化、GRU、线性锚点或一般价值式都不足以完成该目标。
