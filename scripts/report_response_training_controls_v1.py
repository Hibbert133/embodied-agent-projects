"""Full Chinese development report; no candidate selection or qualification rewrite."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import response_training_controls_io_v1 as allocation
from src.analysis import observable_history_io_v1 as io


def number(value, scale=1):
    return "缺失" if value is None else f"{value*scale:.6g}"


def report(folder):
    manifest = allocation.load_manifest(folder)
    completion = io.read(folder/"pipeline_completion.json")
    io.require(completion["status"] == "COMPLETE" and io.read(folder/"evaluation_audit.json")["integrity"] == "PASSED", "audited complete development run required")
    stats = io.read(folder/"evaluation/statistics.json")
    training = io.read(folder/"training/completion.json")
    regression_audit = io.read(folder/"training_audit.json")
    forward_audit = io.read(folder/"forward_audit.json")
    registry = io.read(folder/"case_registry.json")
    primary = stats["primary"]
    text = ["# 响应预测训练受控开发试验 v1", "", "**仅旧 TRAIN 的开发证据；独立资格未执行，旧 NOT_QUALIFIED 保持不变。**",
        "本轮不采集物理数据、不训练底层策略、不调用在线LLM，也不选择最佳初始化或自动晋级模型。所有18个回归和144个神经模型、全部缺失与失败保留。",
        f"运行 `{manifest['experiment_run_id']}`；冻结提交 `{manifest['source_git_commit']}`；manifest `{manifest['manifest_id']}`。", "",
        "## 方法名称及受控内容", "",
        "H10 是两段历史位移和发送命令的10维线性参考；F20 是含当前状态、真实位移和相对几何的20维特征；F43 是当前39维公开观测加4维发送命令。ISO 为两轴共用目标尺度，AXIS 为两轴分别标准化；W1/W16 表示只读当前或最多16帧真实可见特征。",
        "全部GRU输入槽位43、隐藏32、总参数7458；F20标准化后补23个恒零列，2208个输入参数无数据梯度，有效可激活参数5250。两种特征都从真实t=2开始，短窗口按实际长度pack，不伪造最早位移。",
        "FIT用原0–11组144条，DEV用12–17组72条；三个边界层均整组平衡。所有标准化只用FIT，每模型5000更新；同库同重复八个变体完全相同初始化和采样时序。三个重复是固定优化随机性检查，不是三个独立物理组。", "",
        "## 预定主要开发比较", "",
        f"DEV尾段平均逐轨迹RMSE：F20_ISO_W16 − F43_AXIS_W16 = {number(primary['mean_difference_m'],1000)} mm；六组分层bootstrap95%区间 "
        f"{None if primary['group_bootstrap_95_m'] is None else [1000*x for x in primary['group_bootstrap_95_m']]} mm。完整六组可用：{primary['all_six_groups_available']}。",
        "这是开发描述性区间，不能称为新独立确认、控制收益或安全保证。指标先按同轨迹固定初始化和来源平均，再按真实组等权；不将预测数量当样本量。", "",
        "## 全部模型族与两种物理指标", "",
        "每个GRU行包含三个初始化和两个固定训练来源的完整平均。平均RMSE与平均MSE的排序可以不同，不能替换原资格指标。", "",
        "|划分|模型族|可用/分配轨迹|可用/分配组|平均尾段RMSE(mm)|平均尾段MSE(mm²)|", "|---|---|---:|---:|---:|---:|"]
    for r in stats["overall"]:
        if r["stage"] == "POST_TASK":
            text.append(f"|{r['role']}|{r['variant']}|{r['available_trajectories']}/{r['allocated_trajectories']}|{r['available_groups']}/{r['allocated_groups']}|{number(r['rmse_m'],1000)}|{number(r['mse_m2'],1e6)}|")
    text += ["", "## 每个初始化完整披露", "", "|划分|模型族|初始化重复|平均尾段RMSE(mm)|", "|---|---|---:|---:|"]
    for r in stats["initializations"]:
        if r["stage"] == "POST_TASK":
            text.append(f"|{r['role']}|{r['variant']}|{r['replicate']}|{number(r['rmse_m'],1000)}|")
    text += ["", "## 训练来源×部署程序：完整四格", "", "|划分|训练来源|实际程序|模型族|可用/分配轨迹|尾段RMSE(mm)|", "|---|---|---|---|---:|---:|"]
    for r in stats["source_program_transfer"]:
        if r["stage"] == "POST_TASK":
            text.append(f"|{r['role']}|{r['source']}|{r['program']}|{r['variant']}|{r['available_trajectories']}/{r['allocated_trajectories']}|{number(r['rmse_m'],1000)}|")
    text += ["", "## 特征、损失及历史的全部受控对比", "", "以下为各组固定变体的均值差，单位mm；均为开发描述，无多重比较确认性结论。", "",
        "|划分|对比|平均尾段RMSE差(mm)|", "|---|---|---:|"]
    overall = {(r["role"], r["variant"]): r["rmse_m"] for r in stats["overall"] if r["stage"] == "POST_TASK"}
    contrasts = [(f"F20_{loss}_W{w}",f"F43_{loss}_W{w}") for loss in allocation.LOSSES for w in allocation.WINDOWS]
    contrasts += [(f"{f}_AXIS_W{w}",f"{f}_ISO_W{w}") for f in allocation.FEATURES for w in allocation.WINDOWS]
    contrasts += [(f"{f}_{loss}_W16",f"{f}_{loss}_W1") for f in allocation.FEATURES for loss in allocation.LOSSES]
    for role in ("FIT", "DEV"):
        for a, b in contrasts:
            x, y = overall[role, a], overall[role, b]
            text.append(f"|{role}|{a} − {b}|{number(None if x is None or y is None else x-y,1000)}|")
    text += ["", "## 后续判断", ""]
    linears = [overall["DEV", "LINEAR_"+f] for f in ("H10", "F20", "F43")]
    neural = {v: value for (role, v), value in overall.items() if role == "DEV" and not v.startswith("LINEAR_")}
    competitive = [v for v, x in neural.items() if x is not None and all(y is not None and x < y for y in linears)]
    if competitive:
        text += [f"按完整开发人口均值，有{len(competitive)}个变体低于全部三条线性参考。这仅支持另行设计独立训练／资格协议；没有择优初始化、选择最终模型或开放旧CAL／TEST作确认。各任务与初始化反例必须保留。"]
    else:
        text += ["没有一个神经变体在完整开发尾段均值上低于全部三条线性参考。保留负结果，不为该版GRU添加接受门或获取选择器，也不继续以增加网络变体为研究主线。下一步应核对强线性工作模型的控制相关资格与现有C8／积分下可实现的获取决策空间；任何新任务采集另行冻结。"]
    text += ["即使受控表示改善预测，也不能自动证明逆控制合法或含获取成本的任务表现改善。公开特征、输入信息量、有效参数和固定训练预算共同作用，不能将一个因子差解释为唯一物理成因。",
        "CCF A目标仍需可测量的新决策机制、方法自身独立时序部署、DIRECT_C8与积分等强对照、全成本及机制消融；普通GRU、标准化、线性基线与本开发试验均不作为论文贡献。", "",
        "## 完整人口、提前结束及缺失", "", "收集结局仅描述旧固定C8来源，不是本轮新预测器的控制成功率。所有阶段缺失均保留null和原因，未补采。", "",
        "|划分|任务|上下文|程序|来源成功/分配|无任务尾段|", "|---|---|---|---|---:|---:|"]
    for role in ("FIT", "DEV"):
        for task in io.TASKS:
            for context in ("NOMINAL", "RANDOM"):
                for program in io.PROGRAMS:
                    cells = [r for r in registry if (r["role"],r["task"],r["context"],r["program"]) == (role,task,context,program)]
                    text.append(f"|{role}|{task}|{context}|{program}|{sum(r['success'] for r in cells)}/{len(cells)}|{sum(r['stage_response_counts']['POST_TASK']==0 for r in cells)}|")
    text += ["", "## 全任务、条件、程序与阶段附表", "", "两个训练来源先在同轨迹等权；以下始终报告真实轨迹分母。", "",
        "|划分|任务|上下文|程序|阶段|模型族|可用/分配轨迹|RMSE(mm)|", "|---|---|---|---|---|---|---:|---:|"]
    for r in stats["task_context_program"]:
        text.append(f"|{r['role']}|{r['task']}|{r['context']}|{r['program']}|{r['stage']}|{r['variant']}|{r['available_trajectories']}/{r['allocated_trajectories']}|{number(r['rmse_m'],1000)}|")
    text += ["", "## 费用、验证和复算", "",
        f"科学拟合实际{training['fits_attempted']}次，保存{training['models_saved']}模型，优化{training['optimizer_updates']}更新；独立回归审计另复算{regression_audit['independent_regression_refits']}次，神经优化器没有重训。独立Torch double前向核对{forward_audit['predictions_checked']}个预测，最大绝对差{forward_audit['maximum_absolute_error']:.3g}m；重建18个初始化和18个采样日程。",
        "软件资格另计：首次8个合成神经拟合／800更新通过计算但最终回执目录缺失而失败，未保存权重；第二次8个／800更新成功并逐个保存。纯数组测试的线性拟合次数在验证回执单列，不能计为新物理样本。所有科学／软件失败均保留。",
        f"整个开发流程墙钟{completion['wall_ns']/1e9:.3f}秒。新增环境控制步、受控／工厂重置、物理帧、在线API和固定策略训练均为0。实际复用TRAIN来源216次／20195控制步／11016全部重置／5608975帧；完整父研究756次／71773步／38556重置／19636865帧单列。既有名义C8来源480次／3840步／24480重置／12259200帧也保留，不重复摊到每条预测。",
        "来源公开文件SHA256、全部冻结源码、模型索引／锁、逐步预测和独立审计均在运行目录。计算入口 `scripts/run_response_training_controls_v1.py`；独立回归／统计审计入口 `scripts/audit_response_training_controls_v1.py`；旧模型／CAL／TEST与原资格结果保持原样。", ""]
    target = ROOT/"reports/response_training_controls_v1_zh.md"
    with target.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(text))
    io.write(folder/"report_receipt.json", {"report": target.relative_to(ROOT).as_posix(), "sha256": io.sha(target), "source_sha256": io.sha(__file__),
        "new_environment_steps": 0, "new_api_calls": 0})
    print(target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("folder", type=Path); report(parser.parse_args().folder.resolve())
