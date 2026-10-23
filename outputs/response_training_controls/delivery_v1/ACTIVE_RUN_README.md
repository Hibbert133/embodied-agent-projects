# 活动计算定位与后续交付

此文件是定位说明，**不能凭文件或PID存在认定作业仍在运行**。每次续接先查询下列同一个会话；观察超时不是终止，不得因此重启。没有冻结外的新采集／API调用。

- 工作目录：`C:/Users/Administrator/Desktop/embodied-agent-projects`。
- 分支：`codex/response-training-controls-v1`；冻结实现提交：`a7a3375`。
- 单次运行：`outputs/response_training_controls/development_v1/training_controls_20261021T191002Z_a7a33756b1c7`。
- 已启动的统一执行会话：**78349**（用 `write_stdin` 读取；不要重新执行run命令）。
- 训练子进程启动时PID为2072；若会话失效，必须检查当前系统进程的命令行与此运行完整路径，防止PID复用。`train_started.json`只提供定位，不提供实时存活证明。
- 原科学源码及配置已全部哈希绑定；**作业结束前禁止修改或增加 src/scripts/tests 中源码**，否则父流程的冻结审计将失败。可以在本交付目录准备只读交付代码，不进入训练。

父进程自动执行：训练162模型／720000更新 → 独立18回归复算与18采样日程 → 模型锁 → Torch double全前向及18初始化复算 → NumPy全量评价 → 独立逐预测／统计审计 → `pipeline_completion.json`。训练硬超时14400秒，不重试；失败保留目录，不能换配置在同一人口重启。

完成后先核对真实会话终止及pipeline状态，再执行以下已存在入口（均拒绝覆盖）：

1. 项目Python运行 `scripts/report_response_training_controls_v1.py <run-folder>`，生成完整中文报告。
2. 图形独立环境 `.venv-movement-figures/Scripts/python.exe` 运行本目录 `plot_results.py <run-folder>`；实际查看PNG，核对全部11族和缺失、坐标、三个初始化的范围。
3. 项目Python运行本目录 `assemble_delivery.py <run-folder>`：核对模型锁早于DEV前向、完整预算、所有科学guard为零，保存来源费用，分片／索引大文件并实际恢复。原始大文件及恢复副本保留在本地。
4. 使用 `validation_v1/check_index.py` 复核本次拥有的暂存文件、索引／磁盘字节、分片解码秘密及普通／暂存差异；运行全量秘密补充扫描。不重复未改源码的旧物理测试夹具；25项新测试及原1489+17项源绑定回执都已冻结。
5. 仅暂存本研究拥有的文件。大文件提交分片／索引，排除本地原大文件、恢复副本及原有无关未提交项。本地结果提交，不推送、不合并。

本轮只用旧TRAIN的组0–11拟合、12–17开发，旧CAL／TEST关闭。它不是新的独立确认，不能修改原NOT_QUALIFIED。所有八个因子组合、三个初始化、两训练来源、三个任务和两种上下文必须披露；没有候选选择或自动晋级。新的环境步／重置／帧、在线LLM API和策略训练均为0。

研究目标仍是能在独立时序部署中超过强基线、具有明确机制贡献的CCF A工作。冻结、纯数组测试、预测均值改善或本开发试验均不足以完成该目标。下一阶段约束与新近邻见 `docs/research/response_training_controls_next_stage_v1_zh.md`。
