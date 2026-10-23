# 行动响应缓存验证：原始文献与实现差异

核查日期：2026-10-14。本次核查在 action_response_development_v1
收集过程中形成；不读取部分任务表现、不修改冻结方法、尺度、阈值、
程序库或竞争门。它补充完整论文的相关工作，不是穷尽式新颖性认证。

## 已核查的原始方法

| 原始来源与读取范围 | 已有内容 | 当前实现的关系与不能继承的结论 |
|---|---|---|
| [Solowjow 与 Trimpe，Event-triggered Learning，Automatica 2020](https://arxiv.org/html/1904.03042v2)，第 2、4 节，Theorems 4–7；[作者机构出版记录](https://is.mpg.de/ps/publications/solowjowetl19) | 根据模型诱导的通信间隔分布检验失配，并按需触发辨识；明确使用 i.i.d. 间隔及浓缩不等式。 | 检测失配、再付费获取模型早已存在。当前六步相关残差及经验 RMS 没有这些统计条件；标量 CUSUM 不是该论文的复现。 |
| [Schlüter、Solowjow 与 Trimpe，Event-triggered Learning for Linear Quadratic Control](https://arxiv.org/pdf/1910.07732)，PDF 页 3–7，Assumptions 1–2、Theorem 3 和 Section IV；[作者机构出版记录，TAC 2021](https://is.mpg.de/ics/publications/schlueteretl19) | 根据线性高斯闭环的二次代价分布触发学习。Chernoff 方案考虑窗口内相关性；均值方案另外讨论样本间隔。 | 直接用控制表现验证旧模型也不是空白。固定接触技能没有证明其稳定／稳态高斯假设，不能把 `2*sigma/sqrt(n)` 当成该代价检验或沿用其误触发保证。 |
| [Leung、Hota 与 Paré，Online Identification of Time-Varying Systems Using Excitation Sets and Change Point Detection，2025 v2 预印本](https://arxiv.org/html/2406.10349v2)，Sections III–IV、Algorithms 1–2、Assumption IV.1 | 选择有激励的数据进行递归辨识，并用预测能力变化触发历史重置。rLRT 的正向误差假设为 i.i.d. 指数分布，文中明确其启发式角色。 | 近期窗口和残差刷新已经有更明确的标准方法。当前 RECENT_WINDOW／CUSUM 不等于 GW-RLS+rLRT，也没有核验其分布假设；不能将参数变化检测自动当成任务控制失效。 |
| [Parsi 等，Dual adaptive MPC using an exact set-membership reformulation，2022 v1 预印本](https://arxiv.org/html/2211.16300v1)，Sections 2、3.1、4.1、5.1 | 对线性参数不确定性和有界扰动构造嵌套参数集，把预期辨识嵌入 MPC；稳健约束依赖其完整条件与状态管。 | 当前也是对假想测量做集合预测，但仅比较三个四步程序和局部残差宽度。它没有状态管、完整 MPC 目标或有界物理噪声，也不保持相同的嵌套更新规则。不能继承递归可行或约束保证。此处没有核实最终发表状态。 |
| [Wagenmaker、Simchowitz 与 Jamieson，Task-Optimal Exploration in Linear Dynamical Systems，ICML 2021](https://proceedings.mlr.press/v139/wagenmaker21a/wagenmaker21a.pdf)，Algorithm 1、Theorem 2.2；[正式出版记录](https://proceedings.mlr.press/v139/wagenmaker21a.html) | TOPLE 以任务损失敏感性和激励矩阵设计探索，有实例／任务相关的样本复杂度分析。 | 当前 G_OPTIMAL 是有限程序的最大预测方差贪心参考，RESPONSE_SET 是响应相对容差宽度准则；都不是 TOPLE，也没有它的损失 Hessian、稳定线性系统分析或最优样本复杂度。 |

上表最后一列是基于原文和冻结源代码的项目判断，不是原作者对本项目
的评价。这些原始研究的假设不同，未直接在本仓库复现其完整算法。
读取的是指定技术部分；不能写成全面复核了每篇文章的全部证明和实验。

## 当前代码真正计算了什么

冻结版本 `1c37985444816ad9cca434d2fe38825678fc82dd` 的
[action_response_validity.py](../../src/probe/action_response_validity.py)
和 [run_action_response.py](../../scripts/run_action_response.py) 显示：

1. 旧点映射来自标准有界前向误差拟合；当前可见残差按发送 xy 分组。
2. 参数盒内的仿射均值残差区间由标准 LP 得到，观测半径是经验假设。
3. 四个政策角点和零点先经过缓存逆映射与截断，形成有限响应查询。
4. `hypothetical_extension` 用加权最小二乘点残差预测新标签；其标签
   明确标成假想数据。候选分数求查询点上的最大归一化预测宽度。
5. “最大”只对有限查询及响应坐标取最大，并没有再对未知未来标签
   做最坏情形优化。这个分数不是稳健最坏测量收益或预计任务成功。
6. 数值兼容后实际消费已保存控制器；未确定时补测，失配时固定刷新。
   任务成败不能反过来改变已执行选择。

这些组件构成可检验的模拟器假设方法。简单地组合残差、LP、G 设计、
早停、缓存和定向命令，尚不足以区别于事件触发辨识与控制导向设计。
程序正确性和预算审计也不能代替方法贡献。

## 重复分组并不保证可行集嵌套

原集合使用每个命令**当前汇总均值**及 `2*sigma/sqrt(n)`，重复该命令
后重新计算均值，替换之前的约束。它没有与历史全部均值约束求交。
因此，更多样本即使使区间更窄，也不保证新集合包含在旧集合内。

一个不依赖任务数据的标量截距例子：令 sigma=0.0001 米，发送命令
为零，第一残差为 0 mm。原区间为 `[-0.2, 0.2]` mm。真实增加四个
残差为 0.2 mm 的同命令样本后，均值为 0.16 mm，半径为
`0.2/sqrt(5)` mm，新区间约为 `[0.0705573, 0.2494427]` mm。它更窄，
但上端超过原上端。固定真实截距 0.1 mm 同时位于两个区间中，因此
这个例子不需要违反两次的分组均值误差假设。

原点预测对 ZERO4 则补入四个 0 mm 假想标签，预测区间为
`[-0.0894427, 0.0894427]` mm。真实测量可能移出这个预测收缩方向。
这不表示有信息泄漏、原预算违规或某个实测任务失败；它限制的是
对“每次采集必定单调收缩风险”的理论表述。数值见
[解析核验](../../outputs/action_response/group_update_witness_v1/witness.json)，
以及 `test_regrouping_narrower_interval_need_not_be_nested`。

## 论文可以提出、目前不能认领的贡献

可提出的问题是：有状态、会改变接触情况的测量与固定技能竞争同一
步数预算时，哪些当前可见证据支持复用自己的旧纠正，哪些证据需要
额外物理采集？若要把它发展成方法贡献，需要明确定义测量和行动的
有效域、误差事件、依赖处理及相对于已有触发／设计的实质差别。

当前竞争门是必要的开发筛选，不是充分的论文接收标准。完成后应
保留全部十六方法、三消融和失败，核对五点范围与未来残差覆盖，再
决定这个冻结候选是否有实际竞争性。若被便宜宽探测或标准参考支配，
不在本批任务上修改尺度、幅度、阈值或标签预测后重跑。

若要做后继版本，完整行动像、适用状态变化、时间一致的误差边界与
对未知标签的采集收益都需要明确处理，并与适用的成熟方法公平比较。
这些是目前的设计义务，不是宣布已有新定理、新算法或合格物理保证。
新设计只能另行注册并使用新的数据，所有旧负结果和保留范围继续保留。
