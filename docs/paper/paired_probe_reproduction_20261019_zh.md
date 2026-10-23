# 同状态探测实验的结果复核指南

本指南复核已经完成的同状态探测实验，连接论文中的方法、表格、失败案例与原始记录。复核入口只读取既有数据，把新回执写入独立目录；它不启动仿真采集，也不调用在线 LLM API。正在运行的四步与八步独立任务比较属于另一项实验。

## 结果对应的版本

采集实现冻结在提交 `591c353cd1e2a8c940be82fbcb1af97ce3f531da`；完整结果交付在提交 `f267f4dad08e40279708968baa6c97f77d1ba90b`。运行目录为：

```text
outputs/paired_probe_effects/development_v1/paired_probe_effects_20261016T191951Z_591c353cd1e2
```

清单身份为 `758755b6e0b07419c631f6c8cc83696de4d05a9be8ca1d66f334b8fd6cb7f1f7`。原始数据和依赖来源均须按仓库相对路径保留。克隆时需要包含交付提交的 Git 对象与数据文件；只有论文图表或浅克隆中缺失该提交时，不能完成本文的字节来源核对。

[复核脚本](replay_paired_probe_results_v1.py)先将八个清单、完成与审计锚点同交付提交中的 Git 对象逐字节比较，再检查冻结输入、原始采集文件、分析文件、图和报告的 SHA256。它不要求把当前分支切回旧提交；后续新增文件可以存在，但历史绑定输入必须保持原样。新回执还记录复核脚本自身哈希与实际 Python 版本。

## 运行入口

在仓库根目录使用现有 Python 3.10 虚拟环境。下面的命令都自动生成新的回执文件名，不覆盖旧结果。

```powershell
Set-Location 'C:\Users\Administrator\Desktop\embodied-agent-projects'

# 仅核对交付 Git 对象与绑定文件字节
.venv\Scripts\python.exe docs/paper/replay_paired_probe_results_v1.py --mode hashes --phase MAIN

# 从已保存的逐分支结果重新计算统计和成本
.venv\Scripts\python.exe docs/paper/replay_paired_probe_results_v1.py --mode numeric --phase MAIN

# 先用较小的预检记录检查完整事件重放入口
.venv\Scripts\python.exe docs/paper/replay_paired_probe_results_v1.py --mode records --phase SMOKE

# 需要完整 MAIN 事件重放时执行，计算量明显更大
.venv\Scripts\python.exe docs/paper/replay_paired_probe_results_v1.py --mode records --phase MAIN
```

输出位于 `outputs/reproduction_reviews/paired_probe_v1/`。可通过 `--output` 指定该目录内尚不存在的 `.json`；目标已存在或落在其他目录时，入口直接拒绝。复核失败写入 `FAILED_NOT_RETRIED`，可处理的键盘中断写入 `INTERRUPTED_NOT_RETRIED`，二者均返回非零退出码。不要删除失败回执来覆盖同一次检查。

| 模式 | 实际进行的工作 | 通过状态能支持的结论 |
|---|---|---|
| `hashes` | 核对交付提交中的八个锚点及其绑定文件 | `VERIFIED_SAVED_ARTIFACT_HASHES` 仅说明字节一致；未重算统计或验证安装的原生库 |
| `numeric` | 哈希核对后，调用既有独立数值审计器，从保存的结果重建统计与费用 | `PASSED` 说明本次重算与保存结果符合原审计容差；没有重放全部事件 |
| `records` | 哈希核对后，调用既有记录审计器，再进行数值审计 | `PASSED` 说明事件顺序、所列决策执行关系和账本检查通过；没有重新运行机器人环境 |

新增入口复用了原审计函数，不能将其称为第二套独立审计实现。`records` 模式会重算固定政策与拟合器，其次数及墙钟保存在新回执中。MAIN 原始记录审计约需数百秒，具体时间取决于主机与并发负载。各模式会在完成前再次核对绑定输入未被改动。

## 依赖与机器边界

`hashes` 只使用 Python 3.10 或更新版本的标准库及 Git。`numeric` 和 `records` 会导入仓库既有审计代码及其依赖；原实验使用 Python 3.10、NumPy 2.2.6、SciPy 1.15.3、MetaWorld 3.1.1 和 MuJoCo 3.3.0。复核入口不会安装或升级依赖。

完整事件审计沿用既有运行库绑定，其中包括恢复资格清单保存的原生库绝对路径。在另一台机器上，路径或库字节不一致可能使该检查失败。不能通过改写原清单消除失败，也不能把文件哈希或数值重算通过，表述为原生状态恢复在任意机器上获得资格。新主机上的物理复制／恢复或重新采集需要独立的运行资格与协议。

## 论文结论与数据位置

下面的路径均相对于上述运行目录。论文中的数值应取自原始保存结果；复核耗时属于新计算费用，不替换原采集耗时。

| 需要复核的内容 | 文件 | 解释范围 |
|---|---|---|
| 完整来源人口及来源政策 | `main_analysis_v1/source_units.csv` | 432 个来源单元，包含 49 个冷源与 383 个合格暖状态 |
| 四程序成功、停止与实际步数 | `main_analysis_v1/all_program_executions.csv` | 12,256 次评价续跑和 432 次来源执行；不能当成独立样本数 |
| 平均效果、噪声修正及完整流区间 | `main_analysis_v1/statistics.json` | 36 条来源流；主比较 R−K 为正表示 K 的截止损失较低 |
| 逐状态效果与 Monte Carlo 标准误 | `main_analysis_v1/state_effects.csv` | 每状态八个新未来的有限重复测量，不是真实无噪声标签 |
| 全部失败与停止 | `main_analysis_v1/failures.csv`、`stops.csv` | 427 次评价失败与 15 次来源失败；七次停止包含在失败中 |
| 全部实际费用 | `main_analysis_v1/costs.json` | 控制步、工厂重置、帧数、拟合与政策查询；名义模型和资格费用单列 |
| 原始事件与逐流记录 | `main/events.jsonl.gz`、`main/cases_*.jsonl.gz` | 完整事件审计的输入，包含仅供评价者读取的私有字段 |
| 已保存审计 | `main_audit.json`、`main_statistics_audit.json` | 读取各自范围与共享依赖；`PASSED` 不代表方法创新或任务保证 |
| 流程终态 | `main_pipeline_completion.json` | 六阶段均完成才是完整交付；历史 `main_pipeline_status.json` 的最后快照仍为 `RUNNING` |

原始脚本的命令行入口会独占写入固定审计、分析和报告路径，因此本指南通过 Python 函数调用复核，并另存新回执。不要直接重跑 `execute_paired_probe_phase_v1.py`、采集器或分析生成器来“刷新”已有目录。它们的单次执行约束和历史种子分配继续有效。

论文阅读入口为[方法附录](paired_probe_measurement_methods_draft_zh.md)、[结果与讨论](paired_probe_measurement_results_20261019_zh.md)和[相关工作](paired_probe_related_work_20261019_zh.md)。本指南覆盖既有机制实验的复核；新的获取方法、独立确认及完整论文要求仍须继续推进。
