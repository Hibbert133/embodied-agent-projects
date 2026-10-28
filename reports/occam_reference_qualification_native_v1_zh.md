# 独立自身历史资格：NATIVE 完整交付（中文）

174/174 次原生执行完成，两级审计均通过，29 个程序均按冻结分配实际执行。NATIVE 只有 1 个独立组，本报告是运行与数值链路交付，不构成预测、任务收益或 CCF A 资格；QUAL 使用另 9 个组，本报告不读取其结局。

全部人口为 173 个任务成功、1 个任务失败、0 技术失败；失败仍在分母与原始记录中。共有 621 个实际窗口。下面均为描述性结果，没有独立组置信区间、方法选择或择优获取动作。

|冻结程序|成功／6|平均截止损失↓|实际控制步|
|---|---:|---:|---:|
|PI_0125__CONTINUE|6/6|68.333|410|
|PI_0500__CONTINUE|6/6|67.500|405|
|PI_2000__CONTINUE|6/6|68.667|412|
|PI_8000__CONTINUE|6/6|69.167|415|
|META_ADAPT__CONTINUE|6/6|66.833|401|
|META_FROZEN__CONTINUE|6/6|66.833|401|
|ERM_ADAPT__CONTINUE|6/6|68.333|410|
|ERM_FROZEN__CONTINUE|6/6|68.333|410|
|PI_0125__VALIDATE8|6/6|67.667|406|
|PI_0500__VALIDATE8|6/6|67.500|405|
|PI_2000__VALIDATE8|6/6|67.833|407|
|PI_8000__VALIDATE8|6/6|67.833|407|
|META_ADAPT__VALIDATE8|6/6|68.500|411|
|META_FROZEN__VALIDATE8|6/6|68.500|411|
|ERM_ADAPT__VALIDATE8|6/6|67.667|406|
|ERM_FROZEN__VALIDATE8|6/6|67.667|406|
|PI_0125__MOVE_MEASURE|6/6|119.667|718|
|PI_0500__MOVE_MEASURE|6/6|112.500|675|
|PI_2000__MOVE_MEASURE|6/6|115.167|691|
|PI_8000__MOVE_MEASURE|6/6|116.500|699|
|META_ADAPT__MOVE_MEASURE|6/6|109.500|657|
|META_FROZEN__MOVE_MEASURE|6/6|115.833|695|
|ERM_ADAPT__MOVE_MEASURE|6/6|116.000|696|
|ERM_FROZEN__MOVE_MEASURE|6/6|116.000|696|
|GLOBAL_PI_0125|6/6|85.333|512|
|GLOBAL_PI_2000|6/6|70.333|422|
|GLOBAL_PI_8000|6/6|72.000|432|
|DIRECT_C8|6/6|79.000|474|
|MOVE_INTEGRAL|5/6|167.333|1004|

PI 的数字是积分纠正的时间常数 T（秒），小 T 反馈更快；META 是元训练的短窗表现预测参考，ERM 是同数据、匹配训练量的普通监督参考；ADAPT 用实际窗口反馈更新线性后验，FROZEN 保持后验参数。底层策略固定。后缀 CONTINUE／VALIDATE8／MOVE_MEASURE 分别为继续、执行 8 步正常任务验证、真实移动后测量。

同前缀程序先以 T=0.5 到预定边界；GLOBAL 从第 0 步就使用该时间常数。GLOBAL_PI_0500 是 PI_0500__CONTINUE 的精确别名，未重复执行或计费。DIRECT_C8／MOVE_INTEGRAL 保持原冻结强参考及其初始探测、估计和获取过程。不同前缀不得伪称共同移动／当前状态。

实际费用：14894 控制步；174 次受控重置，8874 次全部重置（含 8,700 次目标生成重置）；4511470 物理帧。实际固定策略查询 13104，学习参考实际窗口 274，实际后验更新 102。原 C4/C8 数值估计 24 次／优化器报告 nfev=24。新神经／响应训练及在线 LLM API 均为 0。

审计费用另计：{"environment_creations": 0, "resets": 0, "simulation": 0, "solve_attempts": 130, "lstsq_attempts": 0, "cold_fit_attempts": 24, "cold_estimator_entries": 24, "cold_linear_solve_attempts": 120, "cold_linear_lstsq_attempts": 24}。审计没有创建、重置或推进环境；共享 actor／固定策略／严格特征抽取已披露，独立标量滤波、批后验、dense 算术与动作／噪声／连续性重建不等于独立物理重仿真。

来源训练、全部失败的旧人口与 C8 离线来源费用沿用冻结 historical_source_costs.json，单独报告，不按当前程序数重复乘计。历史 TRAIN 的元／ERM 训练资格和数学审计不是本 NATIVE 的任务表现证据。

无损交付：2288 个原始文件，348 个逐案压缩成员以精确字节区间引用完整事件／见证流；12 个不超过 4 MiB 的分片，ZIP 共 47099700 字节。实际本地恢复逐文件字节一致，158286 行规范 gzip 内容经基本及补充秘密扫描；别名不重复解码扫描、不重复计环境费用。原始数据、ZIP 及恢复目录继续保留。实际 Git 分片恢复证明在数据提交后另存。

all_cases.csv 保留全部 174；task_failures.csv 保留全部任务失败。bundle_index.json 给出所有原文件大小、SHA-256、分片与压缩成员映射。导出软件 13 项文件／元数据检查通过，4 个归档／恢复算法与已验证实现的 AST 相同，仅格式版本字符串规范化；它们不是新增科学资格。导出本身环境交互、拟合、模型预测及在线 LLM 全 0。

后续判断保持冻结：继续同一 QUAL 分配，完整收集后双审计、独立整组统计与全部对照交付；不根据本表更换主程序、bank、阈值、获取动作或样本。无收益保留负结果，封存该版接收者。A 的新机制、完整 Q／DR／廉价重加权等强参考、独立完整任务优势和消融仍待完成。

科学冻结源码：7abaec83b0854f099d6f13f308cc8cd552f50e2b；manifest 19347fbe7b039fabd536c411d74e87a823bd0925cd2bee9e5705329cdb77f78d。
