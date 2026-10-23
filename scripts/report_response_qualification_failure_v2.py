"""Version 2 presentation repair: avoid shadowing the summary collection."""
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import response_qualification_io_v1 as io

OUTPUT=ROOT/"outputs/response_qualification_failure/analysis_v1"
SOURCE=ROOT/"outputs/response_model_qualification/development_v1/response_qualification_20261020T092011Z_636d6b1f9e39"
NAMES=("FROZEN_OLD_LINEAR_ARX","FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")


def f(v,scale=1,digits=4):return "缺失" if v is None else f"{v*scale:.{digits}f}"


def report():
    start=perf_counter_ns();done=io.read(OUTPUT/"completion.json");audit=io.read(OUTPUT/"independent_audit.json");io.require(audit["integrity"]=="PASSED","audit required")
    values=io.read(OUTPUT/"group_summaries.json");geometry=io.read(OUTPUT/"training_geometry.json");old=io.read(SOURCE/"evaluation/statistics.json")
    def cell(split,task="ALL",condition="ALL",stage="POST_TASK"):
        return next(v for v in values if (v["split"],v["task"],v["condition"],v["stage"])==(split,task,condition,stage))
    lines=["# 响应模型资格失败：只读诊断与独立后继设计","",
        "**全部新增分析均为事后描述性分析。原 NOT_QUALIFIED、三项科学门槛失败及原始记录保持不变。**",
        "本轮没有新采集、环境创建、重置、物理帧、模型拟合、参数／阈值搜索或在线 LLM／控制决策 API 调用；没有新增 ARX 选择规则。",
        "目标是找出可以独立检验的解释，不从旧 QUAL 中挑选一个新的合格模型。CCF A 的方法新颖性、强任务收益和独立部署证据仍未建立。","",
        "## 原结果与本轮复算范围","",
        f"冻结主差（二阶－新线性）仍为 {old['primary_difference']*1000:+.5f} 毫米，95% 整组区间 [{old['primary_group_bootstrap_95'][0]*1000:+.5f}, {old['primary_group_bootstrap_95'][1]*1000:+.5f}] 毫米。",
        f"本轮登记 {done['executions']} 条完整人口、{done['actual_source_steps']:,} 个已发生源控制步，其中 {done['eligible_real_history_responses']:,} 条有两段真实历史；最早两步共 {done['first_two_history_missing']} 条明确缺失。",
        f"独立复算核对 {audit['fixed_predictions_checked']:,} 个固定预测、{audit['trajectory_stage_cells_checked']:,} 个轨迹阶段单元和 {audit['summary_cells_checked']} 个组汇总；原 85,914 个资格预测与 6,804 项轨迹指标未变。",
        "所有任务、条件、阶段、短段和缺失均保留。先轨迹内再组内，最后独立组等权；相关系数只是轨迹内描述，不把时间步作为独立统计样本。","",
        "## 先分清两项设计混淆","",
        "1. QUAL 的 UNCHANGED 是“边界处不再切换”，初始映射已经是 I、偏置 [0.12,−0.08]。TRAIN/CAL 是名义 I、零偏置。因此不变条件也不等于名义分布匹配，不能把变化条件的差异单独解释成所有失败原因。",
        "2. 新线性使用 10 维历史／命令，新二阶使用 20 维状态／历史／命令并展开为 231 项。增加状态和增加非线性复杂度同时发生，缺少同数据的 20 维状态线性控制，不能据此宣布“状态无用”或“长历史一定有效”。","",
        "## 从训练到独立条件的误差","",
        "单位毫米；TRUE_INTERFACE。训练误差是固定已训练模型的拟合描述，不是重新交叉验证。每阶段可用分母完整保留。","",
        "| 划分 | 任务 | 阶段 | 可用／全部 | 旧线性 | 新线性 | 二阶状态 |","|---|---|---|---:|---:|---:|---:|"]
    for split in io.SPLITS:
        for task in io.TASKS:
            for stage in ("ALL_RESPONSE","POST_TASK"):
                c=cell(split,task,stage=stage);lines.append(f"| {split} | {task} | {stage} | {c['available']}/{c['allocated']} | "+" | ".join(f(c['rmse']['TRUE_INTERFACE'][n],1000) for n in NAMES)+" |")
    lines.extend(["","## 全部六格与全部阶段","",
        "下面为二阶－新线性 RMSE，单位毫米；正值表示二阶较差。缺失不填零。阶段均值不用于更改原主比较。","",
        "| 任务／条件 | 前缀 | 边界前 | 移动全部 | 抬升 | 抬升后 | 任务尾段 | 移动1–8 | 9–16 | 17–32 | 33–64 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    phases=("FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","POST_TASK","MOVE_1_8","MOVE_9_16","MOVE_17_32","MOVE_33_64")
    for task in io.TASKS:
        for condition in ("UNCHANGED","CHANGED"):
            data=[]
            for stage in phases:
                c=cell("QUAL",task,condition,stage);v=c["rmse"]["TRUE_INTERFACE"]
                data.append(f(None if v[NAMES[2]] is None else v[NAMES[2]]-v[NAMES[1]],1000))
            lines.append(f"| {task}／{condition} | "+" | ".join(data)+" |")
    lines.extend(["","完整分母、所有 TRAIN/CAL 条件及零长度分段见 trajectory_stages.json、group_summaries.json 和 case_registry.json。","",
        "## H1：覆盖与二阶外推是否有关","",
        "所有几何量只来自原 TRAIN 及原标准化。逐维训练范围只是观察到的样本包络，不是已验证的模型适用域。杠杆由加权设计 Gram 加原 ridge 得到，不用新响应拟合，不是预测区间或安全保证。","",
        "| 任务 | TRAIN轨迹／响应 | 二阶列数／秩 | 有效自由度 | 加罚Gram条件数 | 系数L2 |","|---|---:|---:|---:|---:|---:|"])
    for task,g in geometry.items():lines.append(f"| {task} | {g['training_trajectories']}/{g['responses']} | {g['columns']}/{g['design_rank']} | {f(g['effective_df'])} | {f(g['penalized_gram_condition'],digits=1)} | {f(g['coefficient_l2'],digits=6)} |")
    lines.extend(["","| 划分／条件 | 任务 | 尾段可用／全部 | 平均最大绝对z | 轨迹p90的组均值 | 越训练逐维范围比例 | 平均设计杠杆 |",
        "|---|---|---:|---:|---:|---:|---:|"])
    for split in io.SPLITS:
        for condition in (("ALL",) if split!="QUAL" else ("UNCHANGED","CHANGED")):
            for task in io.TASKS:
                c=cell(split,task,condition);d=c["descriptors"];lines.append(f"| {split}／{condition} | {task} | {c['available']}/{c['allocated']} | {f(d['mean_max_abs_train_z'])} | {f(d['p90_abs_train_z'])} | {f(d['mean_outside_train_range_fraction'],100)}% | {f(d['mean_regularized_leverage'])} |")
    lines.extend(["","包络越界与误差共同增加可支持覆盖假设，但不能证明它是唯一原因；名义 CAL、偏置初始、任务几何与闭环动作分布同时不同。二阶特征的秩亏／高条件数也不等于岭回归数值非法，原模型的独立系数复算仍通过。","",
        "## H2：复杂度与固定多项式分量","",
        "下表是固定二阶预测的各分量 RMS，单位毫米；不会删项形成新候选。分量可能相互抵消，分量大小不是该项的因果误差贡献。","",
        "| QUAL任务尾段 | 常数 | 状态一阶 | 历史一阶 | 命令一阶 | 命令² | 命令×历史 | 命令×状态 | 历史² | 历史×状态 | 状态² |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"])
    terms=("CONSTANT","LINEAR_STATE","LINEAR_HISTORY","LINEAR_COMMAND","COMMAND_COMMAND","COMMAND_HISTORY","COMMAND_STATE","HISTORY_HISTORY","HISTORY_STATE","STATE_STATE")
    for task in io.TASKS:
        c=cell("QUAL",task);lines.append(f"| {task} | "+" | ".join(f(c["term_rms"][t],1000) for t in terms)+" |")
    lines.extend(["","如果训练误差较小而 CAL／QUAL 尾段变差，兼容复杂度或覆盖不足的解释；但旧数据缺少 20 维线性控制和同预算覆盖随机化，无法区分二者。不能据这些分量挑一个删项模型，也不能在此 QUAL 调 ridge。","",
        "## H3：输入语义与噪声能解释多少","",
        "令 e_t＝y−f(u_true)，e_a＝y−f(u_applied)，δ＝f(u_applied)−f(u_true)。恒等式 e_t²＝e_a²＋δ²＋2e_aδ 逐步核对。这里的 δ 包括噪声、浮点和提前裁剪接口差异，历史仍是实际带噪历史，不能称为纯物理噪声分离。",
        "下表是轨迹内分量 MSE 后再组等权，单位毫米²；不是把主指标“平均 RMSE”再平方。","",
        "| 任务／条件 | 真接口误差MSE | 实际输入误差MSE | 输入差MSE | 交叉项 | 模型前映射越界比例 |","|---|---:|---:|---:|---:|---:|"])
    for task in io.TASKS:
        for condition in ("UNCHANGED","CHANGED"):
            c=cell("QUAL",task,condition);d=c["descriptors"];lines.append(f"| {task}／{condition} | {f(d['quad_error_mse'],1e6,6)} | {f(d['quad_applied_error_mse'],1e6,6)} | {f(d['input_semantics_delta_mse'],1e6,6)} | {f(d['semantics_cross_term'],1e6,6)} | {f(d['mean_transformed_outside_envelope'],100)}% |")
    lines.extend(["","| QUAL尾段输入语义 | 旧线性RMSE（毫米） | 新线性 | 二阶 |","|---|---:|---:|---:|"])
    for mode,mode_values in cell("QUAL")["rmse"].items():lines.append(f"| {mode} | "+" | ".join(f(mode_values[n],1000) for n in NAMES)+" |")
    lines.extend(["","实际输入也不自动是更合适的统计条件：模型在名义带噪响应上以发送命令训练。若改用实现动作后误差仍大，只能反对“当前输入噪声是充分解释”，不能据此排除历史噪声、模型结构或接触的作用。","",
        "## H4：历史、反馈和未观测动态","",
        "每项先在真实轨迹内计算 Pearson 系数，再组等权平均；常数或短序列标缺失，不拼接阶段或跨轨迹配对。没有显著性检验，也不据其设置检测门槛。","",
        "| QUAL任务／条件 | e与命令lag0 | e与历史lag1 | e与噪声lag0 | 二阶误差lag1 | lag2 | 线性误差lag1 | lag2 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"])
    keys=("quad_error__sent__lag0","quad_error__history__lag1","quad_error__noise__lag0","quad_error__self__lag1","quad_error__self__lag2","linear_error__self__lag1","linear_error__self__lag2")
    for task in io.TASKS:
        for condition in ("UNCHANGED","CHANGED"):
            c=cell("QUAL",task,condition);lines.append(f"| {task}／{condition} | "+" | ".join(f(c["correlations"][k]["mean"]) for k in keys)+" |")
    lines.extend(["","原始 0／1／2 滞后、有效轴／配对数与缺失原因完整保存。残差自相关兼容历史不足，但反馈会导致命令、历史、噪声与误差相关，不能把相关性直接当作估计偏差、潜在接触或唯一机制的证明。位置／物体运动只是代理，当前报告没有逐步接触力或接触对，不能识别接触机制。","",
        "## 可检验假设、反证与后续判断","",
        "| 假设 | 现有数据能支持／反对什么 | 新独立证据的判别方式 |","|---|---|---|",
        "| H1：响应迁移依赖行为产生的覆盖 | 三划分几何与误差共同披露；UNCHANGED 也有初始偏置，不能归因为边界改变 alone | 交叉初始上下文与测量程序，训练覆盖和验证上下文分别分离；若覆盖增强没有改善预定误差与分组最差格，削弱此假设 |",
        "| H2：标准二阶的复杂度与状态特征混淆 | 当前没有状态线性控制；几何与分量只描述已保存模型 | 在新 TRAIN 上同时固定历史线性、状态线性、二阶和有限历史表示；若状态线性也不能迁移，不能将问题归结为二阶容量 |",
        "| H3：输入条件和噪声语义失配 | 三输入和恒等式描述差额；不能称为纯噪声下界 | 新模型主输入统一为可见发送命令和过去历史；真参数／施加动作仅评价。用独立噪声和固定程序随机化区分输入语义与轨迹变化 |",
        "| H4：短历史不能描述接触／瞬态 | 误差自相关与代理只能提供线索，闭环相关不是因果证据 | 新的历史长度控制与采集程序随机化；真实采集接触量仅作评价见证。若长历史对匹配和迁移都无优势，不以此再加门控 |","",
        "建议先独立检验“获取程序改变可预测状态分布和可用历史”这一机制，而不是改当前 ARX 的接受阈值。新的预测表示只是工程基础；即使通过，也必须另行验证包含获取成本、拒绝更新后真实继续及强基线的任务收益。",
        "新实验设计见 docs/protocols/observable_history_transfer_design_v1_zh.md，贡献边界与原始文献核对见 docs/research/response_failure_hypotheses_prior_art_v1_zh.md。两者均为设计稿，本轮没有执行、占用种子或自动授权后续采集。","",
        "## 费用、来源与复算","",
        f"本轮分析 {done['wall_ns']/1e9:.2f} 秒，独立审计 {audit['wall_ns']/1e9:.2f} 秒。三个 TRAIN 几何矩阵构造单列；新响应拟合、策略训练、控制交互及在线 API 全为零。",
        "历史来源另计 270 次执行／23,716 步／13,770 全部重置／7,003,580 帧、540 次 C4/C8 拟合与六个 TRAIN 响应模型；旧 C8／ARX 费用仍见原报告，不重新计成新增费用。",
        "只读入口 analyze_response_qualification_failure_v1.py；独立入口 audit_response_qualification_failure_v1.py。来源哈希见 source_hashes.json；全源前后字节不变，原门槛与失败结果不动。网页原文查新属于文献只读，不是实验在线 LLM 决策 API。",
        "目标仍是 CCF A 完整研究论文，需要具体新机制区别、分析或可证伪机制证据、同权限同预算强基线、独立自身部署时序、消融和完整论文；本诊断与标准表示比较不代替任何一项。"])
    target=ROOT/"reports/response_qualification_failure_analysis_v1_zh.md"
    with target.open("x",encoding="utf-8",newline="\n") as handle:handle.write("\n".join(lines)+"\n")
    io.write(OUTPUT/"report_receipt.json",{"report":target.relative_to(ROOT).as_posix(),"report_sha256":io.sha(target),"wall_ns":perf_counter_ns()-start,
        "report_generator_sha256":io.sha(__file__),"independent_audit_sha256":io.sha(OUTPUT/"independent_audit.json"),"new_environment_steps":0,"new_api_calls":0,"new_model_fits":0})
    print(str(target))


if __name__=="__main__":report()
