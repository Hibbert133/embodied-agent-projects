# 旧纠正失效后的重新探测：配对执行资格

记录完整性：**PASSED**；执行资格：**NOT_QUALIFIED**。
测量模型资格和任务收益仍未证明。两臂变化前相同；偏差变化在移动前安装，代理继续使用旧C8。本轮采集到窗口或停止后结束，不继续完整任务。

来源提交：`fdb617869c37a32caa69e47613786fac633f823b`；清单：`5ea66255714e4c3011ee21e5dbdf01b6069f3bbbb94693a33c74cd42e5390b60`。

|任务|种子|条件|计划介入步|边界可用|完整窗口|停止理由|移动步|新探测步|总控制步|期间任务成功|
|---|---:|---|---:|---|---|---|---:|---:|---:|---|
|push-v3|22600|UNCHANGED|16|True|True|COMPLETE_UNQUALIFIED|19|8|43|False|
|push-v3|22600|CHANGED|16|True|False|ANCHOR_NOT_REACHED|64|0|80|False|
|reach-v3|22601|UNCHANGED|16|True|True|COMPLETE_UNQUALIFIED|40|8|64|False|
|reach-v3|22601|CHANGED|16|True|False|ANCHOR_NOT_REACHED|64|0|80|False|
|door-open-v3|22602|UNCHANGED|16|True|True|COMPLETE_UNQUALIFIED|25|8|49|False|
|door-open-v3|22602|CHANGED|16|True|False|ANCHOR_NOT_REACHED|64|0|80|False|
|push-v3|22603|UNCHANGED|32|True|True|COMPLETE_UNQUALIFIED|50|8|90|False|
|push-v3|22603|CHANGED|32|True|False|ANCHOR_NOT_REACHED|64|0|96|False|
|reach-v3|22604|UNCHANGED|32|True|True|COMPLETE_UNQUALIFIED|53|8|93|False|
|reach-v3|22604|CHANGED|32|True|False|ANCHOR_NOT_REACHED|64|0|96|False|
|door-open-v3|22605|UNCHANGED|32|True|False|ANCHOR_NOT_REACHED|64|0|96|False|
|door-open-v3|22605|CHANGED|32|True|False|ANCHOR_NOT_REACHED|64|0|96|False|
|push-v3|22606|UNCHANGED|64|True|False|ENDED_DURING_REPOSITION|5|0|69|True|
|push-v3|22606|CHANGED|64|True|False|ENDED_DURING_REPOSITION|5|0|69|True|
|reach-v3|22607|UNCHANGED|64|True|True|COMPLETE_UNQUALIFIED|59|8|131|False|
|reach-v3|22607|CHANGED|64|True|False|ANCHOR_NOT_REACHED|64|0|128|False|
|door-open-v3|22608|UNCHANGED|64|True|False|ANCHOR_NOT_REACHED|64|0|128|False|
|door-open-v3|22608|CHANGED|64|True|False|ANCHOR_NOT_REACHED|64|0|128|False|

不同介入时刻使用不同种子，不能据此宣称时间选择的因果收益。提前成功不算探测成功，所有不可用和未完成窗口保留。

全部9个单元通过变化前原生及Python比较状态、初始拟合、策略和物理轨迹匹配；仅投影已登记统计包装器计时字段。变化减不变的完整窗口计数差为-6，属于这批有限配对的描述，不是泛化概率保证。
核对8372条主事件、54份完整私有状态图，并重建状态图中的公开观测、初始探测数据、计数与原始噪声数组。没有以重新仿真作为审计，也不是外部物理真值认证。
新增控制步1616；受控重置18次，全部重置918次；请求/完成帧467080/467080。
策略查询528次，初始参数拟合36次、nfev 36；中途参数拟合和API均为0。
采集主体80.434821秒，其中见证构建22.956618秒；只读审计主体19.330583秒。进程墙钟另存。
审计额外重算策略528次、拟合36次、nfev 36，无新增环境步。
完整历史名义费用为3840控制步、480受控重置、24480全部重置、12259200帧；每臂均计完整先验费用，按9任务单元摊销426.666667历史控制步/单元。历史采集实际只发生一次；方法账单分别计费，不把它说成新采集了两次。旧研究及资格费用另列，未重跑。

|条件|完整窗口|总控制步|移动步|新探测步|
|---|---:|---:|---:|---:|
|UNCHANGED|6|763|379|48|
|CHANGED|0|853|517|0|

原移动参数、位置门槛、64步上限和8步程序均保持冻结。缺少新窗口时不调用warm估计器、不代执行、不补选案例。完整CCF A目标仍需可区分的新方法、独立校准与任务收益、强对照、消融及论文。
