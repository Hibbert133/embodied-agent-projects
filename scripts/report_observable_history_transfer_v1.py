"""Chinese report including complete denominators, failures and costs."""
import argparse
from collections import Counter
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.analysis import observable_history_io_v1 as io


def number(value):return "缺失" if value is None else f"{1000*value:.6f}"


def report(path):
    m=io.load(path);root=path.parent;pipeline=io.read(root/"pipeline_completion.json")
    text=["# 可见历史与获取程序迁移：独立训练与资格报告 v1", "",
        "本次是响应预测组件的开发资格试验。数值合法性、当前预测能力和含获取成本的任务收益分别评价；本次没有训练获取决策，也没有让新预测器控制机器人。", "",
        f"运行：`{m['experiment_run_id']}`；冻结提交：`{m['source_git_commit']}`；manifest：`{m['manifest_id']}`。",
        f"流程状态：**{pipeline['status']}**；在线 LLM API 调用0，网络尝试{pipeline['attempted_network_calls']}。", "",
        "## 预登记方法与信息边界", "",
        "三个任务，固定底层策略，噪声标准差0.05；原八步C4/C8、C8至16/32/64边界、相同LOCAL_PID移动至多64步，再真实执行8步测量及至多32步C8任务。FEEDBACK8用固定策略+C8；BALANCED8用预先确定的四方向等量命令+C8。测量后从实际状态继续。",
        "每任务、每个测量来源各训练五个固定参考：10维历史线性、20维状态线性、20维二阶、同43维输入的1帧GRU与16帧GRU。前二者区分状态特征作用，后两者区分历史作用；GRU和门控本身均非新颖性主张。",
        "所有方法使用相同实际t≥2目标，输入仅含当前公开观测、发送命令和过去历史；种子、真扰动、施加动作及私有状态不进训练。两GRU相同初始化/采样日程、7458参数、各5000更新；CAL不选择或修复模型。", "",
        "## 完整人口与费用", "", "|划分|分配执行|已完成|控制步|全部重置|物理帧|记录审计|", "|---|---:|---:|---:|---:|---:|---|"]
    totals=Counter();audits=[]
    for split in io.SPLITS:
        f=root/split.lower();s=io.read(f/"summary.json") if (f/"summary.json").exists() else None
        audit=io.read(f/"audit.json") if (f/"audit.json").exists() else None;audits.append(audit)
        if s:
            count=s["lifecycle"]["counts"];text.append(f"|{split}|{s['allocated_executions']}|{s['executions']}|{s['control_steps']}|{count.get('reset_attempts',0)}|{count.get('simulation_frames_attempted',0)}|{audit['integrity'] if audit else '未通过/未完成'}|")
            totals.update(executions=s["executions"],control_steps=s["control_steps"],all_resets=count.get("reset_attempts",0),physical_frames=count.get("simulation_frames_attempted",0),
                c4_c8_fit_attempts=sum(r["c4_c8_fit_attempts"] for r in s["rows"]),measurement_steps=sum(r["measurement_steps"] for r in s["rows"]))
        else:text.append(f"|{split}|{len(io.population(split))}|0|0|0|0|未进入|")
    text += ["",f"实际合计：{dict(totals)}。本项上限756次、127008控制步、38556全部重置、19913040帧、1512次C4/C8尝试、30个响应模型和60000优化更新。提前成功或无效C8不替换、不补采。",
        "前序资格来源费用单列：270次执行、23716控制步、13770全部重置、7003580帧、540次C4/C8、6个响应模型；未用于本次训练。更早C8来源及未知费用保留原报告口径。软件夹具、依赖安装和来源复算另见freeze_validation_v1及runtime_v1，不冒充科学采集。",
        f"全流程分析/采集/训练墙钟合计：{pipeline['wall_ns']/1e9:.3f}秒。训练数值审计额外重建18个回归并检查12个GRU前向/采样，没有重跑优化训练。", ""]
    if pipeline["failure"] is not None:
        text += ["## 中止与保留", "",f"失败记录：`{pipeline['failure']}`。本次不自动重跑或换种子。已发生物理工作、部分模型和全部日志原样保留；未进入划分没有资格结果。", ""]
    stats=io.read(root/"evaluation/statistics.json") if (root/"evaluation/statistics.json").exists() else None
    if stats:
        integrity=(root/"evaluation/numeric_audit.json").exists() and io.read(root/"evaluation/numeric_audit.json")["integrity"]=="PASSED"
        text += ["## 独立TEST资格", "",f"结果：**{stats['qualification']}**；独立数值审计：**{'PASSED' if integrity else '未通过/未完成'}**。主响应可用{stats['available_primary_trajectories']}/432；18组、24格均保留。缺失按原分母报告，预测量只在实际可观察响应上计算，不能推广到缺失响应。", "",
            "单位为毫米，组内实际轨迹等权、两个固定训练来源等权、18组等权。", "", "|表示|平均尾段RMSE(mm)↓|", "|---|---:|"]
        text.extend(f"|{name}|{number(stats['means'][name])}|" for name in io.MODELS)
        ci=stats["primary_group_bootstrap_95"];text += ["",f"预登记主差GRU16−GRU1：{number(stats['primary_difference'])} mm；按边界分层的整组bootstrap95%区间：{None if ci is None else [1000*x for x in ci]} mm。",
            f"各项门槛：`{stats['requirements']}`。", "", "|任务|上下文|测量程序|可用/18|历史线性|状态线性|二阶|GRU1|GRU16|", "|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for c in stats["task_context_program_cells"]:text.append(f"|{c['task']}|{c['context']}|{c['measurement_program']}|{c['available']}|"+"|".join(number(c["means"][n]) for n in io.MODELS)+"|")
        text += ["", "## 训练来源×部署程序：全部四格", "", "以下是预登记的描述性交互，不将两份模型当成独立物理重复。单位mm。", "", "|表示|反馈→反馈|反馈→均衡|均衡→反馈|均衡→均衡|差中差|", "|---|---:|---:|---:|---:|---:|"]
        for r in stats["source_transfer"]:text.append("|"+r["method"]+"|"+"|".join(number(r["crosses"][a+"->"+b]["mean"]) for a,b in (("FEEDBACK8","FEEDBACK8"),("FEEDBACK8","BALANCED8"),("BALANCED8","FEEDBACK8"),("BALANCED8","BALANCED8")))+"|"+number(r["descriptive_interaction_mean"])+"|")
    text += ["", "## 全部结束原因与实际执行结局", "", "成功只描述固定收集程序，168步窗口不能冒充500步任务截止损失，也不能证明新预测器改善任务。所有逐案结局见各划分summary及TEST case_registry；所有短阶段有null及缺失原因。", "", "|划分|任务|上下文|程序|成功/已完成|结束原因计数|", "|---|---|---|---|---:|---|"]
    for split in io.SPLITS:
        f=root/split.lower()/"summary.json"
        if not f.exists():continue
        grouped={}
        for r in io.read(f)["rows"]:grouped.setdefault((r["task"],r["context"],r["measurement_program"]),[]).append(r)
        for (task,context,program),part in grouped.items():text.append(f"|{split}|{task}|{context}|{program}|{sum(r['success'] for r in part)}/{len(part)}|{dict(Counter(r['stop_reason'] for r in part))}|")
    text += ["", "## 衔接、审计与可解释范围", ""]
    for a in audits:
        if a:text.append(f"{a['split']}：{a['events_checked']}条事件，{a['witness_records_checked']}个状态见证；{a['common_pre_measurement_pairs']}对共同测量前状态，{a['common_pre_context_change_pairs']}对共同改变前状态；测量后{a['post_measurement_diverged_pairs']}对实际状态分化。")
    text += ["", "独立解析器核对保存命令先于执行、逐步float32仿射/死区→实际XYZ噪声→最终裁剪、连续噪声游标/时钟、每次50工厂+1受控重置；未重置或恢复撤销测量位移。状态见证由源程序生成，不是独立物理复现或普遍隐状态等价保证。",
        "回归审计使用独立增广最小二乘；GRU在全部公开轨迹上由NumPy与独立Torch前向核对，另查采样日程，没有独立重跑60000步优化。源码、依赖、数据和候选冻结哈希见manifest及审计文件。",
        "拟合数值合法不代表分布外预测可靠；预测提升不代表可逆纠正或含获取成本的任务收益。经验分位数、限幅和回退均不自动提供安全保证。", "", "## 后续判断", ""]
    if stats and stats["qualification"]=="PASSED_PREDICTIVE_QUALIFICATION_ONLY" and (root/"evaluation/numeric_audit.json").exists():
        text.append("该表示仅通过独立预测资格，可以据此单独冻结新的纠正与任务收益试验；仍须先超过DIRECT_C8和积分等强基线，再研究移动前获取决策。不能将本项结果当作论文贡献或安全证明。")
    else:text.append("本项没有建立长历史表示的完整独立资格，当前不进入新逆控制或获取选择器采集。不改本次门槛、不筛任务救活；保留失败与负结果，后续若要变更表示/获取机制，须先提出可检验新解释和独立训练/评价协议。")
    text += ["CCF A研究目标仍未完成。潜在主线仍是获取动作改变实际状态和模型适用性时的获取—采用联合决策；需与模型适用范围、Residual RL、OCCAM、GAUGE、Poke and Strike及新查到的双重控制工作逐项区分，经过强对照、独立时序部署和消融验证。", ""]
    target=io.ROOT/"reports/observable_history_transfer_v1_zh.md"
    with target.open("x",encoding="utf-8",newline="\n") as handle:handle.write("\n".join(text))
    io.write(root/"report_receipt.json",{"report":target.relative_to(io.ROOT).as_posix(),"sha256":io.sha(target),"new_environment_steps":0,"new_api_calls":0,"new_model_fits":0})
    return target


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--manifest",required=True,type=Path);report(p.parse_args().manifest.resolve())
