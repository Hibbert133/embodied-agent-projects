# 响应模型独立训练与资格验证 v1：中文报告

资格结论：**NOT_QUALIFIED**。
本次是预先冻结的开发预测资格试验。分别检查数值合法性、当前一步预测能力与包含获取成本的任务收益；本试验仅检验前两项，不估计新纠正的任务收益。
新模型没有控制任何机器人动作。不能据此声称逆控制有效、安全保证、算法新颖性或 CCF A 目标完成。

执行编号：`response_qualification_20261020T092011Z_636d6b1f9e39`；冻结提交：`636d6b1f9e395af41a415786561e39a23e16c8c5`；manifest：`b3bd767f35c0720e8fa148097ba8f1b909da5c3d61c8a3c4398f58ae76a536e6`。
设计文件及全部旧结果保持原样。零在线 LLM API 调用；没有策略训练、控制器更新、资格后调参或替换失败种子。

## 固定人口、真实时序与成本

TRAIN 18 组、CAL 9 组、QUAL 18 组；每组包含三任务及两噪声／两条件。边界 16／32／64 按组号分层。
每条轨迹从真实初始观测开始；八步 C4/C8 前缀后由 C8 继续到边界，原 LOCAL_PID 移动至多 64 步，然后保留 C8 执行至多 32 步。提前结束、无效拟合与短轨迹不补样。
命令先进行 float32 仿射／死区变换，再对 XYZ 加入保存的实际噪声，最后裁剪。每次执行只有一次受控初始重置；工厂的 50 次重置全部计费。

| 划分 | 分配 | 已完成 | 观察到成功 | 控制步 | 全部重置 | 物理帧 | C4/C8 拟合尝试 |
|---|---:|---:|---:|---:|---:|---:|---:|
| TRAIN | 108 | 108 | 29 | 9192 | 5508 | 2799960 | 216 |
| CAL | 54 | 54 | 11 | 4762 | 2754 | 1400810 | 108 |
| QUAL | 108 | 108 | 27 | 9762 | 5508 | 2802810 | 216 |

实际成本：23,716 返回完成控制步、23,716 控制尝试，13,770 全部重置，7,003,580 请求物理帧。
冻结上限分别为 43,200 步、13,770 次重置、7,101,000 帧；受控重置上限 270 次。没有把构造／重置成本排除在预算之外。
C4/C8 计算拟合 540 次、优化器 nfev 总数 540；名义响应训练最多 6 次。复算审计单列，不算新机器人交互。
整个流水线实耗 1300.2 秒，其中采集 1141.0 秒；逐阶段耗时保存在 pipeline_completion.json。
历史 C8 来源另计 3,840 步／480 受控重置／24,480 全部重置／12,259,200 帧；旧 ARX 来源另计 23,314 步／432 受控重置，工厂重置与帧数未知，不能填零。
软件测试的原生夹具成本见冻结验证回执，未使用本次科学种子，另于本次 270 条人口计费。

观察到成功只描述同一固定采集程序在短窗口内的事件，不是三个预测模型的成功率比较，也不是 500 步完整任务效用。

## 训练与 CAL 的隔离

两个新模型分别使用原 10 维线性特征和已有 20 维状态特征的固定二阶展开（231 项含常数）。ridge＝0.001，轨迹总权重为 1，轨迹内响应权重为 1/T；均值、尺度与系数仅由 TRAIN 计算。最早两步没有两段真实历史，不进入 AR2 训练／预测。
CAL 只保存逐轨迹经验残差分位数，不选模型、不调整资格门槛、不重新拟合，不作概率覆盖或安全保证。六个模型、独立训练审计与 CAL 描述／审计在 QUAL 第一次构造环境前保存并锁定。
训练状态：`MODELS_SAVED_TRAIN_ONLY`；尝试 6 次，成功保存 6 个。

| CAL 任务 | 模型 | 可用／分配 | 轨迹 RMSE 中位数 | 90% 分位数 | 95% 分位数 |
|---|---|---:|---:|---:|---:|
| push-v3 | FROZEN_OLD_LINEAR_ARX | 18/18 | 0.00018377 | 0.00025677 | 0.00026563 |
| push-v3 | FRESH_LINEAR_ARX | 18/18 | 0.00016887 | 0.00024747 | 0.00026414 |
| push-v3 | FRESH_QUADRATIC_STATE | 18/18 | 0.00012875 | 0.00023498 | 0.00023774 |
| reach-v3 | FROZEN_OLD_LINEAR_ARX | 18/18 | 0.00015090 | 0.00018926 | 0.00018976 |
| reach-v3 | FRESH_LINEAR_ARX | 18/18 | 0.00013986 | 0.00016690 | 0.00017045 |
| reach-v3 | FRESH_QUADRATIC_STATE | 18/18 | 0.00012234 | 0.00023258 | 0.00027284 |
| door-open-v3 | FROZEN_OLD_LINEAR_ARX | 18/18 | 0.00076103 | 0.00130305 | 0.00191889 |
| door-open-v3 | FRESH_LINEAR_ARX | 18/18 | 0.00069111 | 0.00123151 | 0.00173419 |
| door-open-v3 | FRESH_QUADRATIC_STATE | 18/18 | 0.00063279 | 0.00154780 | 0.00288306 |

## 独立资格主比较

主指标为真实历史上移动后任务段的 XY 分量 RMSE，单位米。先在轨迹内计算，再对组内可用六单元等权，最后对 18 组等权；缺失保留为缺失，不填零。三种边界分层整组 bootstrap 10,000 次，固定种子 20261025。所有组必须至少有一对可用响应、六格必须非空。
主输入 TRUE_INTERFACE 是将真参数代入原有预测接口，其 XY 在输入模型前裁剪；实际执行的加噪及最终裁剪顺序仍由原生记录独立核对。APPLIED_INPUT_DIAGNOSTIC 使用实际执行动作，改变模型输入语义，其剩余误差不能称为物理无噪声误差。SENT_INPUT 使用原始发送命令。三者分别披露。

| 模型 | 18 组等权 POST_TASK 主 RMSE |
|---|---:|
| FROZEN_OLD_LINEAR_ARX | 0.00038882 |
| FRESH_LINEAR_ARX | 0.00036109 |
| FRESH_QUADRATIC_STATE | 0.00045583 |

二阶 − 新线性：**0.00009474 米**；95% 整组区间：`[5.1339592477197116e-05, 0.00013969086931907548]`。

| 任务 | 条件 | 可用／分配 | 旧线性 | 新线性 | 新二阶 |
|---|---|---:|---:|---:|---:|
| push-v3 | UNCHANGED | 14/18 | 0.00016634 | 0.00016169 | 0.00013301 |
| push-v3 | CHANGED | 14/18 | 0.00013455 | 0.00012549 | 0.00022218 |
| reach-v3 | UNCHANGED | 14/18 | 0.00010558 | 0.00009933 | 0.00015821 |
| reach-v3 | CHANGED | 14/18 | 0.00012215 | 0.00011422 | 0.00017454 |
| door-open-v3 | UNCHANGED | 18/18 | 0.00069965 | 0.00063140 | 0.00066091 |
| door-open-v3 | CHANGED | 18/18 | 0.00066344 | 0.00061783 | 0.00085077 |

| 冻结资格条件 | 结果 |
|---|---|
| all_18_groups_have_observed_primary_response | 通过 |
| all_six_cells_available | 通过 |
| primary_95_upper_below_zero | 未通过 |
| quadratic_overall_mean_below_old_linear | 未通过 |
| no_cell_worse_than_both_linears | 未通过 |

## 全阶段与输入语义

下表在轨迹内计算后按组汇总。六格 × 三模型 × 三输入 × 七阶段的完整表保存为 stage_summary.json。

| 输入 | 阶段 | 旧线性 | 新线性 | 新二阶 |
|---|---|---:|---:|---:|
| TRUE_INTERFACE | ALL_RESPONSE | 0.00031759 | 0.00028691 | 0.00031872 |
| TRUE_INTERFACE | FIXED_PROBE | 0.00016942 | 0.00010499 | 0.00017238 |
| TRUE_INTERFACE | PRE_BOUNDARY | 0.00029688 | 0.00027626 | 0.00027823 |
| TRUE_INTERFACE | MOVEMENT_ALL | 0.00029492 | 0.00023785 | 0.00031642 |
| TRUE_INTERFACE | LIFT | 0.00034884 | 0.00027873 | 0.00032478 |
| TRUE_INTERFACE | POST_LIFT | 0.00024532 | 0.00017660 | 0.00040757 |
| TRUE_INTERFACE | POST_TASK | 0.00038882 | 0.00036109 | 0.00045583 |
| APPLIED_INPUT_DIAGNOSTIC | ALL_RESPONSE | 0.00031454 | 0.00028030 | 0.00032639 |
| APPLIED_INPUT_DIAGNOSTIC | FIXED_PROBE | 0.00016208 | 0.00009443 | 0.00016988 |
| APPLIED_INPUT_DIAGNOSTIC | PRE_BOUNDARY | 0.00029488 | 0.00027145 | 0.00028606 |
| APPLIED_INPUT_DIAGNOSTIC | MOVEMENT_ALL | 0.00029032 | 0.00022762 | 0.00032842 |
| APPLIED_INPUT_DIAGNOSTIC | LIFT | 0.00034502 | 0.00027060 | 0.00033680 |
| APPLIED_INPUT_DIAGNOSTIC | POST_LIFT | 0.00023894 | 0.00016199 | 0.00040300 |
| APPLIED_INPUT_DIAGNOSTIC | POST_TASK | 0.00038439 | 0.00035343 | 0.00046263 |
| SENT_INPUT | ALL_RESPONSE | 0.00036015 | 0.00032731 | 0.00039735 |
| SENT_INPUT | FIXED_PROBE | 0.00020299 | 0.00014690 | 0.00022514 |
| SENT_INPUT | PRE_BOUNDARY | 0.00032955 | 0.00030822 | 0.00036431 |
| SENT_INPUT | MOVEMENT_ALL | 0.00034048 | 0.00027926 | 0.00040075 |
| SENT_INPUT | LIFT | 0.00039339 | 0.00031813 | 0.00040376 |
| SENT_INPUT | POST_LIFT | 0.00026959 | 0.00021073 | 0.00046447 |
| SENT_INPUT | POST_TASK | 0.00043941 | 0.00040699 | 0.00052005 |
缺失阶段的原因由 trajectory_metrics.json 逐条登记。阶段均值只作预先指定的描述，不用于修改主比较或挑选任务。

## 全部失败、缺失与审计

270 条分配、提前结束、未到边界、无任务尾段、未执行与异常统一保存在 allocation_registry.json；全部非成功／非完整条目另列 failure_registry.json。没有根据结局删除困难案例。

| 划分 | 停止原因／状态 | 数量 |
|---|---|---:|
| TRAIN | EARLY_SUCCESS_OR_ENV_END | 19 |
| TRAIN | ENDED_BEFORE_BOUNDARY | 10 |
| TRAIN | WINDOW_COMPLETE | 79 |
| CAL | EARLY_SUCCESS_OR_ENV_END | 5 |
| CAL | ENDED_BEFORE_BOUNDARY | 6 |
| CAL | WINDOW_COMPLETE | 43 |
| QUAL | EARLY_SUCCESS_OR_ENV_END | 17 |
| QUAL | ENDED_BEFORE_BOUNDARY | 10 |
| QUAL | WINDOW_COMPLETE | 81 |
- `train/audit.json`：PASSED。
- `training/audit.json`：PASSED。
- `cal/audit.json`：PASSED。
- `calibration/audit.json`：PASSED。
- `qual/audit.json`：PASSED。
- `evaluation/numeric_audit.json`：PASSED。

记录审计独立重建保存决策先于执行、C8 逆映射、固定策略输出、噪声游标、float32 执行链、时钟、全部重置及帧成本。资格条件的初始与边界状态逐对核对。它使用原生状态见证，并非独立物理重仿真或普遍隐藏状态证明。
数值审计使用独立特征展开、增广加权最小二乘复算训练模型、经验分位数及整组 bootstrap；复算不修改训练模型，不新增科学拟合或交互。

## 后续判断

本次未通过独立预测资格；封存全部负结果，停止围绕本版 ARX 添加选择规则，也不启动有限幅度更新试验。若重新研究响应模型，须提出可检验的新解释、独立训练与资格设计及新种子，不能在本 QUAL 人口上修复或降低门槛。
数值合法不等于当前预测有效，预测改善也不等于包含获取成本的任务收益。移动前获取决策仍需独立训练、校准与自身部署时序评价，明确获取改变状态和模型适用性时的决策差异，再进行强对照、消融与查新；CCF A 研究目标仍未完成。

## 复算与来源

结果根目录：`outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39`。
来源列表见 manifest.json（源码、冻结设计／配置、旧模型、原生库／资产与软件验证回执）和 report_sources.json。
复算入口：`scripts/audit_response_model_qualification_v1.py`；审计输出不可覆盖，再复算时将整套结果复制到独立目录，使用相同 manifest。报告仅从保存记录生成，不创建、重置或推进环境。

原大记录保留本地；若使用分片提交，archive 索引绑定每片哈希与原文件哈希，恢复核对记录单列。
