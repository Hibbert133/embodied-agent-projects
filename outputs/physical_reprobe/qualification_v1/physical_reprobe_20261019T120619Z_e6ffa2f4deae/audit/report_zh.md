# 中途重新探测：连续执行资格

记录完整性：**PASSED**；执行资格：**QUALIFIED**。
测量模型资格和任务收益仍未证明。本轮仅采集到新窗口或操作停止，不继续运行完整任务。

来源提交：`e6ffa2f4deaec07d116aba031cd1d9520621fbda`；清单：`612f593437f5e8f6ecd00a0d1d14e009daba92b661297d89ac642ed9c3ddbf61`。

|任务|种子|计划介入步|边界可用|完整窗口|停止理由|移动步|新探测步|总控制步|期间任务成功|
|---|---:|---:|---|---|---|---:|---:|---:|---|
|push-v3|22400|16|True|True|COMPLETE_UNQUALIFIED|29|8|53|False|
|reach-v3|22401|16|True|True|COMPLETE_UNQUALIFIED|36|8|60|False|
|door-open-v3|22402|16|True|True|COMPLETE_UNQUALIFIED|22|8|46|False|
|push-v3|22403|32|True|True|COMPLETE_UNQUALIFIED|54|8|94|False|
|reach-v3|22404|32|True|True|COMPLETE_UNQUALIFIED|47|8|87|False|
|door-open-v3|22405|32|True|False|ANCHOR_NOT_REACHED|64|0|96|False|
|push-v3|22406|64|True|False|ENDED_DURING_REPOSITION|4|0|68|True|
|reach-v3|22407|64|False|False|ENDED_BEFORE_BOUNDARY|0|0|59|True|
|door-open-v3|22408|64|True|False|ANCHOR_NOT_REACHED|64|0|128|False|

不同介入时刻使用不同种子，不能据此宣称时间选择的因果收益。提前成功不算探测成功，所有不可用和未完成窗口保留。

核对3703条主事件、27份完整私有状态图，并重建状态图中的公开观测、初始探测数据、计数与原始噪声数组。没有以重新仿真作为审计，也不是外部物理真值认证。
新增控制步691；受控重置9次，全部重置459次；请求/完成帧232955/232955。
策略查询259次，初始参数拟合18次、nfev 18；中途参数拟合和API均为0。
采集主体37.869943秒，其中见证构建11.866406秒；只读审计主体14.819930秒。进程墙钟另存。
审计额外重算策略259次、拟合18次、nfev 18，无新增环境步。
完整历史名义费用为3840控制步、480受控重置、24480全部重置、12259200帧；本轮按9案例摊销426.666667历史控制步/案例。旧研究及资格是另列的已付开发费用，未重跑。

主机v2修复累计账本下的单案例重置检查，费用账本没有清零；原软件版本和费用仍保留。完整CCF A目标仍需可区分的新方法、独立校准与任务收益、强对照、消融及论文。
