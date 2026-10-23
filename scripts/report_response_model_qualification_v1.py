"""Chinese report of the entire allocation, including missing and negative outcomes."""
from collections import Counter,defaultdict
from pathlib import Path
import argparse
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analysis import response_qualification_io_v1 as io


def fmt(v):return "缺失" if v is None else f"{v:.8f}"


def report(path):
    manifest=io.load(path);root=path.parent
    target=io.ROOT/"reports/response_model_qualification_v1_zh.md"
    io.require(not target.exists(),"report already exists; never overwrite the frozen result")
    pipeline=io.read(root/"pipeline_completion.json");complete=pipeline["status"]=="COMPLETE"
    stats=io.read(root/"evaluation/statistics.json") if (root/"evaluation/statistics.json").exists() else None
    numeric=io.read(root/"evaluation/numeric_audit.json") if (root/"evaluation/numeric_audit.json").exists() else None
    qualification=stats["qualification"] if stats and complete and numeric and numeric["integrity"]=="PASSED" else "INCOMPLETE_NOT_QUALIFIED"
    names=("FROZEN_OLD_LINEAR_ARX","FRESH_LINEAR_ARX","FRESH_QUADRATIC_STATE")
    lines=["# 响应模型独立训练与资格验证 v1：中文报告","",f"资格结论：**{qualification}**。",
        "本次是预先冻结的开发预测资格试验。分别检查数值合法性、当前一步预测能力与包含获取成本的任务收益；本试验仅检验前两项，不估计新纠正的任务收益。",
        "新模型没有控制任何机器人动作。不能据此声称逆控制有效、安全保证、算法新颖性或 CCF A 目标完成。","",
        f"执行编号：`{manifest['experiment_run_id']}`；冻结提交：`{manifest['source_git_commit']}`；manifest：`{manifest['manifest_id']}`。",
        "设计文件及全部旧结果保持原样。零在线 LLM API 调用；没有策略训练、控制器更新、资格后调参或替换失败种子。","",
        "## 固定人口、真实时序与成本","",
        "TRAIN 18 组、CAL 9 组、QUAL 18 组；每组包含三任务及两噪声／两条件。边界 16／32／64 按组号分层。",
        "每条轨迹从真实初始观测开始；八步 C4/C8 前缀后由 C8 继续到边界，原 LOCAL_PID 移动至多 64 步，然后保留 C8 执行至多 32 步。提前结束、无效拟合与短轨迹不补样。",
        "命令先进行 float32 仿射／死区变换，再对 XYZ 加入保存的实际噪声，最后裁剪。每次执行只有一次受控初始重置；工厂的 50 次重置全部计费。",
        "", "| 划分 | 分配 | 已完成 | 观察到成功 | 控制步 | 全部重置 | 物理帧 | C4/C8 拟合尝试 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    registry=[];total=Counter();summaries={}
    for split in io.SPLITS:
        folder=root/split.lower();records=list(io.rows(folder/"cases.jsonl.gz")) if (folder/"completion.json").exists() else []
        summary=io.read(folder/"summary.json") if (folder/"summary.json").exists() else {};summaries[split]=summary
        costs=summary.get("lifecycle",{}).get("counts",{})
        success=sum(r["success"] for r in records);fits=sum(r["c4_c8_fit_attempts"] for r in records)
        lines.append(f"| {split} | {len(manifest['config']['population'][split])} | {len(records)} | {success} | {summary.get('control_steps',0)} | {costs.get('reset_attempts',0)} | {costs.get('simulation_frames_attempted',0)} | {fits} |")
        for k in ("control_steps","control_step_attempts","wall_ns"):total[k]+=summary.get(k,0)
        for k,v in costs.items():total[k]+=v
        total["fits"]+=fits;total["optimizer_nfev"]+=sum(r["c4_c8_optimizer_nfev"] for r in records)
        record_index={r["case_id"]:r for r in records}
        if (folder/"failed_execution.json").exists():
            failed=io.read(folder/"failed_execution.json");record_index[failed["case_id"]]=failed
            total["fits"]+=failed.get("c4_c8_fit_attempts",0);total["optimizer_nfev"]+=failed.get("c4_c8_optimizer_nfev",0)
        for spec in manifest["config"]["population"][split]:
            r=record_index.get(spec["case_id"]);registry.append({**spec,"status":"NOT_EXECUTED" if r is None else "COMPLETED" if r["completed"] else "FAILED_PARTIAL",
                "success":None if r is None else r.get("success"),"steps":None if r is None else r.get("host_returned"),
                "stop_reason":None if r is None else r.get("stop_reason"),"error":None if r is None else r.get("error"),
                "boundary_reached":None if r is None else r.get("fault_transition") is not None,
                "post_task_steps":None if r is None else r.get("task_steps"),"movement_steps":None if r is None else r.get("reposition_steps")})
    lines.extend(["",f"实际成本：{total['control_steps']:,} 返回完成控制步、{total['control_step_attempts']:,} 控制尝试，{total['reset_attempts']:,} 全部重置，{total['simulation_frames_attempted']:,} 请求物理帧。",
        "冻结上限分别为 43,200 步、13,770 次重置、7,101,000 帧；受控重置上限 270 次。没有把构造／重置成本排除在预算之外。",
        f"C4/C8 计算拟合 {total['fits']} 次、优化器 nfev 总数 {total['optimizer_nfev']}；名义响应训练最多 6 次。复算审计单列，不算新机器人交互。",
        f"整个流水线实耗 {pipeline['wall_ns']/1e9:.1f} 秒，其中采集 {total['wall_ns']/1e9:.1f} 秒；逐阶段耗时保存在 pipeline_completion.json。",
        "历史 C8 来源另计 3,840 步／480 受控重置／24,480 全部重置／12,259,200 帧；旧 ARX 来源另计 23,314 步／432 受控重置，工厂重置与帧数未知，不能填零。",
        "软件测试的原生夹具成本见冻结验证回执，未使用本次科学种子，另于本次 270 条人口计费。","",
        "观察到成功只描述同一固定采集程序在短窗口内的事件，不是三个预测模型的成功率比较，也不是 500 步完整任务效用。","",
        "## 训练与 CAL 的隔离","",
        "两个新模型分别使用原 10 维线性特征和已有 20 维状态特征的固定二阶展开（231 项含常数）。ridge＝0.001，轨迹总权重为 1，轨迹内响应权重为 1/T；均值、尺度与系数仅由 TRAIN 计算。最早两步没有两段真实历史，不进入 AR2 训练／预测。",
        "CAL 只保存逐轨迹经验残差分位数，不选模型、不调整资格门槛、不重新拟合，不作概率覆盖或安全保证。六个模型、独立训练审计与 CAL 描述／审计在 QUAL 第一次构造环境前保存并锁定。"])
    if (root/"training/completion.json").exists():
        train=io.read(root/"training/completion.json");lines.append(f"训练状态：`{train['status']}`；尝试 {train['fit_attempts']} 次，成功保存 {train['fit_results']} 个。")
    if (root/"calibration/description.json").exists():
        lines.extend(["","| CAL 任务 | 模型 | 可用／分配 | 轨迹 RMSE 中位数 | 90% 分位数 | 95% 分位数 |","|---|---|---:|---:|---:|---:|"])
        for r in io.read(root/"calibration/description.json")["summaries"]:
            q=r["empirical_rmse_quantiles"];lines.append(f"| {r['task']} | {r['method']} | {r['available_trajectories']}/{r['allocated_trajectories']} | {fmt(q['0.5'])} | {fmt(q['0.9'])} | {fmt(q['0.95'])} |")
    lines.extend(["","## 独立资格主比较","",
        "主指标为真实历史上移动后任务段的 XY 分量 RMSE，单位米。先在轨迹内计算，再对组内可用六单元等权，最后对 18 组等权；缺失保留为缺失，不填零。三种边界分层整组 bootstrap 10,000 次，固定种子 20261025。所有组必须至少有一对可用响应、六格必须非空。",
        "主输入 TRUE_INTERFACE 是将真参数代入原有预测接口，其 XY 在输入模型前裁剪；实际执行的加噪及最终裁剪顺序仍由原生记录独立核对。APPLIED_INPUT_DIAGNOSTIC 使用实际执行动作，改变模型输入语义，其剩余误差不能称为物理无噪声误差。SENT_INPUT 使用原始发送命令。三者分别披露。"])
    if stats:
        lines.extend(["","| 模型 | 18 组等权 POST_TASK 主 RMSE |","|---|---:|"]+[f"| {n} | {fmt(stats['means'][n])} |" for n in names])
        lines.extend(["",f"二阶 − 新线性：**{fmt(stats['primary_difference'])} 米**；95% 整组区间：`{stats['primary_group_bootstrap_95']}`。","",
            "| 任务 | 条件 | 可用／分配 | 旧线性 | 新线性 | 新二阶 |","|---|---|---:|---:|---:|---:|"])
        for c in stats["task_condition_cells"]:lines.append(f"| {c['task']} | {c['condition']} | {c['available']}/{c['allocated']} | "+" | ".join(fmt(c['means'][n]) for n in names)+" |")
        lines.extend(["","| 冻结资格条件 | 结果 |","|---|---|"]+[f"| {k} | {'通过' if v else '未通过'} |" for k,v in stats["requirements"].items()])
        metrics=io.read(root/"evaluation/trajectory_metrics.json");stage_rows=[]
        lines.extend(["","## 全阶段与输入语义","","下表在轨迹内计算后按组汇总。六格 × 三模型 × 三输入 × 七阶段的完整表保存为 stage_summary.json。","",
            "| 输入 | 阶段 | 旧线性 | 新线性 | 新二阶 |","|---|---|---:|---:|---:|"])
        for mode in ("TRUE_INTERFACE","APPLIED_INPUT_DIAGNOSTIC","SENT_INPUT"):
            for stage in ("ALL_RESPONSE","FIXED_PROBE","PRE_BOUNDARY","MOVEMENT_ALL","LIFT","POST_LIFT","POST_TASK"):
                for task in (*io.TASKS,"ALL"):
                    for condition in ("UNCHANGED","CHANGED","ALL"):
                        for n in names:
                            part=[r for r in metrics if r["method"]==n and r["input_mode"]==mode and r["stage"]==stage and (task=="ALL" or r["task"]==task) and (condition=="ALL" or r["condition"]==condition)]
                            grouped=defaultdict(list)
                            for r in part:
                                if r["rmse"] is not None:grouped[r["group"]].append(r["rmse"])
                            group_values=[sum(v)/len(v) for v in grouped.values()]
                            stage_rows.append({"task":task,"condition":condition,"method":n,"input_mode":mode,"stage":stage,"allocated":len(part),"available":sum(r["n"]>0 for r in part),"available_groups":len(group_values),"mean_rmse":None if not group_values else sum(group_values)/len(group_values)})
                cells=[r for r in stage_rows if r["input_mode"]==mode and r["stage"]==stage and r["task"]==r["condition"]=="ALL"]
                lines.append(f"| {mode} | {stage} | "+" | ".join(fmt(next(r['mean_rmse'] for r in cells if r['method']==n)) for n in names)+" |")
        io.write(root/"stage_summary.json",stage_rows)
        lines.append("缺失阶段的原因由 trajectory_metrics.json 逐条登记。阶段均值只作预先指定的描述，不用于修改主比较或挑选任务。")
    else:lines.append("未形成完整资格统计，不能宣称通过；全部已发生交互与未执行分配保留。")
    lines.extend(["","## 全部失败、缺失与审计","",
        "270 条分配、提前结束、未到边界、无任务尾段、未执行与异常统一保存在 allocation_registry.json；全部非成功／非完整条目另列 failure_registry.json。没有根据结局删除困难案例。","",
        "| 划分 | 停止原因／状态 | 数量 |","|---|---|---:|"])
    for split in io.SPLITS:
        for reason,n in sorted(Counter((r["stop_reason"] or r["status"]) for r in registry if r["split"]==split).items()):lines.append(f"| {split} | {reason} | {n} |")
    audits={}
    for name in ("train/audit.json","training/audit.json","cal/audit.json","calibration/audit.json","qual/audit.json","evaluation/numeric_audit.json"):
        audits[name]=io.read(root/name) if (root/name).exists() else None
        lines.append(f"- `{name}`：{('未执行' if audits[name] is None else audits[name]['integrity'])}。")
    lines.extend(["","记录审计独立重建保存决策先于执行、C8 逆映射、固定策略输出、噪声游标、float32 执行链、时钟、全部重置及帧成本。资格条件的初始与边界状态逐对核对。它使用原生状态见证，并非独立物理重仿真或普遍隐藏状态证明。",
        "数值审计使用独立特征展开、增广加权最小二乘复算训练模型、经验分位数及整组 bootstrap；复算不修改训练模型，不新增科学拟合或交互。"])
    if pipeline["failure"]:lines.extend(["",f"冻结执行失败：`{pipeline['failure']}`。没有在本人口修复后重跑。"])
    if qualification=="PASSED_PREDICTIVE_QUALIFICATION_ONLY":
        next_step="预测资格通过，可以另行制定并冻结逆估计／有限幅度任务试验；本次不自动启动新采集。必须保留 DIRECT_C8、积分、始终探测和探测不更新等强对照，完整新开发人口的平均截止损失须同时低于 DIRECT_C8 与积分，成功率变化完整披露。"
    else:
        next_step="本次未通过独立预测资格；封存全部负结果，停止围绕本版 ARX 添加选择规则，也不启动有限幅度更新试验。若重新研究响应模型，须提出可检验的新解释、独立训练与资格设计及新种子，不能在本 QUAL 人口上修复或降低门槛。"
    lines.extend(["","## 后续判断","",next_step,
        "数值合法不等于当前预测有效，预测改善也不等于包含获取成本的任务收益。移动前获取决策仍需独立训练、校准与自身部署时序评价，明确获取改变状态和模型适用性时的决策差异，再进行强对照、消融与查新；CCF A 研究目标仍未完成。","",
        "## 复算与来源","",f"结果根目录：`{root.relative_to(io.ROOT).as_posix()}`。",
        "来源列表见 manifest.json（源码、冻结设计／配置、旧模型、原生库／资产与软件验证回执）和 report_sources.json。",
        "复算入口：`scripts/audit_response_model_qualification_v1.py`；审计输出不可覆盖，再复算时将整套结果复制到独立目录，使用相同 manifest。报告仅从保存记录生成，不创建、重置或推进环境。","",
        "原大记录保留本地；若使用分片提交，archive 索引绑定每片哈希与原文件哈希，恢复核对记录单列。"])
    io.write(root/"allocation_registry.json",registry);io.write(root/"failure_registry.json",[r for r in registry if r["success"] is not True or r["status"]!="COMPLETED"])
    target.write_text("\n".join(lines)+"\n",encoding="utf-8",newline="\n")
    sources={p.relative_to(io.ROOT).as_posix():io.sha(p) for p in root.rglob("*") if p.is_file()}
    sources[target.relative_to(io.ROOT).as_posix()]=io.sha(target)
    io.write(root/"report_sources.json",{"source_sha256":sources,"qualification":qualification,"new_api_calls":0})
    print(str(target),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",required=True,type=Path);report(p.parse_args().manifest.resolve())
