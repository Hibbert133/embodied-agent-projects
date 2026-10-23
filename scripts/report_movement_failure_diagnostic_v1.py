"""Chinese posthoc report and complete stratified CSV exports from audited diagnostics."""
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import movement_failure_diagnostic_v1 as d
from src.analysis.movement_diagnostic_guard_v1 import read_only_analysis_guard


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1048576), b""):
            h.update(b)
    return h.hexdigest()


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def gzrows(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            yield json.loads(line)


def csv_write(path, values):
    with path.open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(values[0]))
        writer.writeheader(); writer.writerows(values)


def n(value, scale=1):
    return "缺失" if value is None else f"{value*scale:.3f}"


def means(rows, get):
    groups = sorted({r["group"] for r in rows})
    values = [get(r) for r in rows]
    grouped = [d.mean([get(r) for r in rows if r["group"] == g]) for g in groups]
    return d.mean(grouped), sum(v is not None for v in values), sum(v is not None for v in grouped)


def main():
    start = perf_counter_ns()
    base = ROOT/"outputs/movement_task/diagnostic_v1"
    supp = ROOT/"outputs/movement_task/diagnostic_supplement_v1"
    audit_path = ROOT/"outputs/movement_task/diagnostic_audit_v1/check_v2.json"
    audit, complete = read(audit_path), read(base/"completion.json")
    d.require(audit["integrity"] == "PASSED" and audit["diagnostic_completion_sha256"] == sha(base/"completion.json"), "authoritative independent audit required")
    d.require(audit["auditor_sha256"] == sha(ROOT/"scripts/audit_movement_failure_diagnostic_v1.py"), "audit source changed")
    supp_audit = read(supp/"independent_audit.json")
    d.require(supp_audit["integrity"] == "PASSED" and supp_audit["completion_sha256"] == sha(supp/"completion.json"), "supplement audit required")
    output = ROOT/"outputs/movement_task/diagnostic_reporting_v1"
    output.mkdir(parents=True, exist_ok=False)
    report = ROOT/"reports/movement_failure_diagnostic_v1_zh.md"
    link = lambda p: os.path.relpath(p, report.parent).replace("\\", "/")
    registry = read(base/"trajectory_registry.json")
    canonical = [r for r in registry if r["method"] == "MOVE_ARX_KEEP"]
    paired = read(base/"paired_task_outcomes.json")
    strata = read(base/"stratified_summary.json")
    associations = read(base/"group_associations.json")
    clips = read(supp/"clip_axes.json")
    flat_strata = []
    for r in strata:
        base_row = {k:r[k] for k in ("task", "condition", "period", "method", "stage", "bin", "trajectories_total", "empty_trajectories", "steps_descriptive_only")}
        for metric, value in r["metrics"].items():
            flat_strata.append({**base_row, "metric":metric, **value, "missing_reason": "NO_AVAILABLE_TRAJECTORIES" if value["mean"] is None else ""})
    csv_write(output/"all_stratified_metrics.csv", flat_strata)
    corr_buckets = defaultdict(list)
    corr_keys = ("task", "condition", "stage", "bin", "pair", "lag", "axis")
    for path in (base/"lag_correlations.jsonl.gz", supp/"reverse_lag_correlations.jsonl.gz"):
        for r in gzrows(path):
            corr_buckets[tuple(r[k] for k in corr_keys)].append(r)
    corr_summary = []
    for key, rows in sorted(corr_buckets.items()):
        avg, available, groups = means(rows, lambda r:r["r"])
        absolute, _, _ = means(rows, lambda r:None if r["r"] is None else abs(r["r"]))
        corr_summary.append({**dict(zip(corr_keys,key)), "mean_r":avg, "mean_absolute_r":absolute,
            "available_trajectories":available, "full_trajectories":len(rows), "available_groups":groups,
            "missing_short":sum(r["reason"] == "FEWER_THAN_THREE_PAIRED_VALUES" for r in rows),
            "missing_constant":sum(r["reason"] == "CONSTANT_VARIABLE" for r in rows)})
    csv_write(output/"all_lag_correlation_summary.csv", corr_summary)
    csv_write(output/"all_group_associations.csv", associations)
    flat_inventory = [{k:r[k] for k in ("unit", "group", "task", "condition", "method", "success", "total_steps", "deadline_loss", "action", "boundary_ready", "fit_available", "fit_valid", "missing_or_fit_reason", "record_rows", "history_unavailable_steps")} for r in registry]
    csv_write(output/"all_1296_cases.csv", flat_inventory)
    lines = ["# 移动 ARX 失败诊断 v1", "", "**全部新增分析均为事后描述性分析。** 本报告使用已完成的旧人口，不训练模型、不调参数／阈值、不执行未发生的轨迹。", "",
        "建议下一步先独立制定并冻结响应模型的训练与资格验证，暂不进入 324 次限幅采集。保存估计能降低移动段拟合残差，但真参数及实际施加动作代入后仍有误差；数值有效不等于当前预测有效。命令更新幅度较大，却没有证据支持把全部任务损失归因于裁剪。", "",
        f"来源 `{complete['source_run_id']}`；原冻结提交 `{complete['source_git_commit']}`。原报告、原六项比较和原始文件哈希保持不变。", "",
        "## 全人口、费用与可复算入口", "",
        f"共登记 1,296 次执行／54 个独立组，逐步核对 {audit['actuator_steps_checked']:,} 个已发生的控制步；共同移动采用 ARX 程序作为规范来源，324 个单元与条件中 292 个实际进入移动。648 对共同轨迹及私有状态比较一致；273 个移动后任务入口可比较，得到 546 对首个任务原始动作及当前观测一致性检查。", "",
        "新增环境创建、重置、控制步、物理帧、策略查询、在线 LLM API 调用和模型拟合均为 **0**。噪声从原冻结私有生成规则复原，仅用于评价。重复读取旧记录不增加独立样本。", "",
        f"主诊断耗时 {complete['wall_ns']/1e9:.3f} 秒；最终独立复算 {audit['wall_ns']/1e9:.3f} 秒；相关性／裁剪轴补充 {read(supp/'completion.json')['wall_ns']/1e9:.3f} 秒，其独立复算 {supp_audit['wall_ns']/1e9:.3f} 秒。另保留首次失败与被替代的审计回执；进程存在重叠，耗时相加不等于实际经过时间。", "",
        f"[全案例 CSV]({link(output/'all_1296_cases.csv')})；[逐轨迹完整登记]({link(base/'trajectory_registry.json')})；[逐步记录（54 个组分片）]({link(base/'steps')})；[分段记录]({link(base/'trajectory_segments.jsonl.gz')})；[缺失原因]({link(base/'missing_reasons.json')})。", "",
        "| 任务 | 条件 | 全部 | 有移动 | 有拟合 | 数值有效 | 无边界 | 移动提前结束 | 无效原因 |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for task in d.TASKS:
        for condition in d.CONDITIONS:
            part = [r for r in canonical if r["task"] == task and r["condition"] == condition]
            reasons = Counter(r["missing_or_fit_reason"] for r in part if r["fit_valid"] is False)
            lines.append(f"| {task} | {condition} | {len(part)} | {sum(r['movement']['n']>0 for r in part)} | {sum(r['fit_available'] for r in part)} | {sum(r['fit_valid'] is True for r in part)} | {sum(not r['boundary_ready'] for r in part)} | {sum(r['missing_or_fit_reason']=='ENDED_BEFORE_FIT' for r in part)} | {dict(reasons)} |")
    lines += ["", "总计：32 个 ARX 案例无活跃边界、19 个移动中成功、3 个样本不足、28 个估计逆不稳定、242 个数值有效并实际采用 ARX。四方法最早两步均无两段真实历史，共 2,592 步记缺失，不补零。短移动、无效估计及零长度分段均保留。", "",
        "## 三个不同判断", "", "数值合法性：使用原冻结秩、条件数、参数范围与奇异值规则，未新增接受阈值。预测能力：分别检查样本内拟合与保存参数在后续真实状态的一步预测。任务收益：只用实际配对的完整截止损失，包含已发生的获取费用。三者不能互相替代。", "",
        "## 响应模型、实际噪声与移动阶段", "",
        "现有 LINEAR_ARX 输入为两段真实 XYZ 位移和四维命令，不含绝对手部位置、物体相对位置、接触力或接触对。下表单位均为 **毫米／步的 XY 分量 RMSE**，先在轨迹内计算，再对独立组等权汇总；每个任务与条件有 54 条规范轨迹。括号是该项可用轨迹数。", "",
        "“保存参数”在移动段使用移动结束时保存的估计，属于样本内事后诊断，包含有参数但逆不稳定的估计；不足三例没有参数，保持缺失。它不能被描述为移动前已有的预测。", "",
        "“真参数接口”沿用现有预测接口的仿射变换后提前裁剪；真正执行顺序是 float32 仿射／死区 → 加实际 XYZ 噪声 → 最终裁剪。“实际输入”使用实际施加动作，改变了训练时名义发送命令的输入语义，剩余误差不是物理无噪声误差。", "",
        "固定预测器的恒等式为 e_true=e_applied+[F(applied)−F(zero_clip)]+[F(zero_clip)−F(true_interface)]。逐步独立复算通过。第二项含输入噪声与裁剪作用；第三项含接口和 float32 差异，不能从中唯一识别物理噪声或模型误差。", "",
        "| 任务 | 条件 | 控制阶段 | 移动步段 | 有记录／54 | 保存参数 RMSE（n） | 真参数接口 RMSE（n） | 实际输入 RMSE（n） | 输入噪声项 RMSE（n） |",
        "|---|---|---|---|---:|---:|---:|---:|---:|"]
    for r in strata:
        if r["period"] != "COMMON_MOVEMENT":
            continue
        values = []
        for metric in ("error_saved_rmse", "error_true_rmse", "error_applied_rmse", "input_noise_component_rmse"):
            v = r["metrics"][metric]; values.append(f"{n(v['mean'],1000)}（{v['available_trajectories']}）")
        stage = {"ALL":"全部", "LIFT":"抬升", "POST_LIFT":"抬升后"}[r["stage"]]
        lines.append(f"| {r['task']} | {r['condition']} | {stage} | {r['bin']} | {r['trajectories_total']-r['empty_trajectories']}/54 | "+" | ".join(values)+" |")
    lines += ["", f"完整指标及所有缺失分母见 [分层 CSV]({link(output/'all_stratified_metrics.csv')})。空分段的单元格为缺失，不等于零误差。抬升状态按原控制器的粘滞阶段判断重建，未根据残差划分阶段。", "",
        "## 保存参数的后续预测及全部实际程序", "",
        "后续预测只在 ARX 程序中使用决定前已保存的参数（也包括有参数的无效估计），每步读取真实历史；不重拟合、不生成任何未执行轨迹。其他方法的真参数和实际输入误差只描述其自己访问的状态，不能拿它们当成未执行混合控制器的结局。", "",
        "| 任务 | 条件 | 实际程序 | 成功／54 | 平均截止损失 | 后续保存参数 RMSE（n） | 后续真参数 RMSE（n） | 后续实际输入 RMSE（n） |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for task in d.TASKS:
        for condition in d.CONDITIONS:
            for method in d.METHODS:
                part = [r for r in registry if r["task"] == task and r["condition"] == condition and r["method"] == method]
                vals = []
                for metric in ("error_saved_rmse", "error_true_rmse", "error_applied_rmse"):
                    value, available, _ = means(part, lambda r:r["own_task"][metric]); vals.append(f"{n(value,1000)}（{available}）")
                lines.append(f"| {task} | {condition} | {method} | {sum(r['success'] for r in part)}/54 | {n(d.mean([r['deadline_loss'] for r in part]))} | "+" | ".join(vals)+" |")
    lines += ["", "## 输入支持、参数与闭环相关性", "",
        "| 任务 | 条件 | 平均秩 | 平均缩放条件数 | 矩阵相对真值误差（n） | 偏置 L2 误差（n） |", "|---|---|---:|---:|---:|---:|"]
    for task in d.TASKS:
        for condition in d.CONDITIONS:
            part = [r for r in canonical if r["task"] == task and r["condition"] == condition]
            rank, _, _ = means(part, lambda r:r["input_design"]["rank"])
            cond, _, _ = means(part, lambda r:r["input_design"]["condition"])
            matrix, nav, _ = means(part, lambda r:None if r["parameter_error"] is None else r["parameter_error"]["matrix_relative"])
            bias, nb, _ = means(part, lambda r:None if r["parameter_error"] is None else r["parameter_error"]["bias_l2"])
            lines.append(f"| {task} | {condition} | {n(rank)} | {n(cond)} | {n(matrix)}（{nav}） | {n(bias)}（{nb}） |")
    lines += ["", "矩阵误差按 Frobenius 范数相对真值计算；真值只在评价端使用。输入秩和条件数不能证明对当前状态、动作或接触具有预测能力。", "",
        f"[完整滞后相关汇总]({link(output/'all_lag_correlation_summary.csv')}) 包含 6 个任务／条件、15 个控制阶段／步段、全部正反方向变量对及滞后 0、1、2，逐格保留有效数、常量和短序列缺失数；均值及平均绝对相关均报告。原始逐轨迹值见两个压缩相关表。", "",
        "滞后定义是 left_(t−lag) 与 right_t，配对必须位于同一连续分段。正反方向都列出，特别包括过去噪声与当前反馈命令，避免只检查当前噪声与过去命令。相关性只作证据，不证明唯一估计偏差来源。", "",
        "| 任务 | 条件 | 过去噪声→当前命令 | lag=0 X/Y | lag=1 X/Y | lag=2 X/Y |", "|---|---|---|---:|---:|---:|"]
    for task in d.TASKS:
        for condition in d.CONDITIONS:
            vals = []
            for lag in (0,1,2):
                pair = [next(x for x in corr_summary if x['task']==task and x['condition']==condition and x['stage']=='ALL' and x['bin']=='ALL' and x['pair']=='noise_past__command_current' and x['lag']==lag and x['axis']==axis) for axis in (0,1)]
                vals.append(" / ".join(f"{n(x['mean_r'])}（n={x['available_trajectories']}）" for x in pair))
            lines.append(f"| {task} | {condition} | 平均相关 | "+" | ".join(vals)+" |")
    lines += ["", "## 逆控制：共同入口与各自访问状态", "",
        "下面的命令差是同一原始策略动作下两控制器有界发送命令 XY 的 L2 差。首命令在共同移动后的相同观测比较；后续在 ARX 实际访问的状态比较。ARX 子命令只在数值有效时定义，完整分母仍为每格 54；无有效新纠正不填零。其他两个 MOVE 的离线同状态子命令也已保存，不能解释为在线已知参数或任务结果。", "",
        "| 任务 | 条件 | 有效子命令 n／54 | 首命令差 | 后续发送命令差 | C8 命令裁剪比例 | ARX 命令裁剪比例 | 实际纠正裁剪比例 | 最终执行 XY／Z 裁剪比例 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for task in d.TASKS:
        for condition in d.CONDITIONS:
            part = [r for r in canonical if r["task"] == task and r["condition"] == condition]
            first, available, _ = means(part, lambda r:r["first_command_delta"])
            metric = lambda key:means(part, lambda r:r["own_task"][key])[0]
            paired_c8_clip = means([r for r in part if r["fit_valid"] is True], lambda r:r["own_task"]["c8_clip_mean"])[0]
            axes = [r for r in clips if r["task"]==task and r["condition"]==condition and r["method"]=='MOVE_ARX_KEEP' and r['period']=='OWN_TASK']
            xy, _, _ = means(axes,lambda r:r['actuator_clip_xy']); z, _, _ = means(axes,lambda r:r['actuator_clip_z'])
            lines.append(f"| {task} | {condition} | {available}/54 | {n(first)} | {n(metric('command_delta_mean'))} | {n(paired_c8_clip,100)}% | {n(metric('arx_clip_mean'),100)}% | {n(metric('correction_clip_mean'),100)}% | {n(xy,100)}% / {n(z,100)}% |")
    lines += ["", "策略原始动作裁剪、纠正命令裁剪及执行器最终裁剪分别保存。最终裁剪还可能出现在 Z 轴，不能把其全部比例归因于 XY 更新。表中 C8／ARX 子命令裁剪率限制在同一批有效估计案例及相同实际访问状态；实际纠正与最终执行裁剪保留全部有后续任务的案例。逐步记录同时保留未裁剪命令、策略裁剪和各自可用分母。", "",
        "## 实际配对的不利更新与完整失败", "",
        "L_ARX−L_MOVE_KEEP_C8>0 是评价端实际不利更新标签，包含移动费用；不增加任何反事实结局。", "",
        "| 任务 | 条件 | 全部 | 损失更高 | 损失更低 | 平局 | 平均损失差 | 不利案例平均增加 | 保留成功→ARX失败 | 保留失败→ARX成功 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    subsets = [("全部","全部",paired)] + [(t,c,[r for r in paired if r['task']==t and r['condition']==c]) for t in d.TASKS for c in d.CONDITIONS]
    for task, condition, part in subsets:
        lines.append(f"| {task} | {condition} | {len(part)} | {sum(r['harmful_update'] for r in part)} | {sum(r['improvement'] for r in part)} | {sum(r['tie'] for r in part)} | {n(d.mean([r['delta_loss'] for r in part]))} | {n(d.mean([r['delta_loss'] for r in part if r['harmful_update']]))} | {sum(r['success_to_failure'] for r in part)} | {sum(r['failure_to_success'] for r in part)} |")
    lines += ["", "实际采用 ARX 的 242 个案例有 112 成功、130 失败；拒绝的 31 个为 29 成功、2 失败。接受／拒绝与历史状态相关，不能据此识别分支因果效果。所有不利、改善、平局、失败和提前结束均保留。", "",
        f"[完整配对严重度及案例指标]({link(base/'paired_task_outcomes.json')})；[原失败／拒绝／早结束列表]({link(ROOT/'outputs/movement_task/development_v1/movement_task_20261019T191708Z_eee0803df5bf/analysis/failures_and_rejections.json')})。", "",
        "以下相关先把组内六个单元的指标及损失分别平均，再以独立组作为样本；缺失指标的组内可用集合与完整损失集合可能不同，因此仅是描述性关联，不是因果效应。全部六个任务／条件的分项及三个任务端点见完整 CSV。", "",
        "| 特征 | 与组平均损失差的相关 | 可用独立组／54 |", "|---|---:|---:|"]
    for r in associations:
        if r['stratum']=='ALL' and r['target']=='delta_loss':
            lines.append(f"| {r['feature']} | {n(r['r'])} | {r['n']}/54 |")
    lines += ["", "## 对三个假设的支持、反证与不能区分的原因", "",
        "**响应模型／建模条件。** 六个任务／条件格中，真参数接口与实际输入残差仍存在；保存参数的后续误差普遍高于移动段拟合误差。当前模型没有位置与物体／接触状态特征，因而适用条件需要重新资格验证。反证与限制：实际输入残差仍混有训练输入语义、观测／隐藏状态、未建模响应及随机性，不能据此认定唯一是位置、瞬态或接触。逐轨迹位置、物体位移及抓取代理与误差相关值保留在登记表；没有逐步接触力／接触对，不能识别具体接触机制。", "",
        "**闭环数据。** 命令、历史位移、残差与噪声具有可检验的时序关系，输入秩完整也可能有较大的参数误差。完整相关表同时给出有符号与绝对相关，避免符号抵消。反证与限制：过去噪声→当前命令的平均相关没有给出一致强信号，组间符号不同；相关性既不能证明也不能排除模型误差与闭环估计影响。未执行开环随机激励或工具变量对照，无法唯一识别偏差来源。", "",
        "**逆控制。** 在共同移动后的同一观测／原始策略动作上，新的有界发送命令已发生明显变化；小拟合残差并未保证参数或任务效果。反证与限制：ARX 裁剪比例并非普遍高于 C8，命令差与损失差的组关联接近零，不能把全部失败简单解释为“过度裁剪”或“变化越大越差”。后续状态与误差也受已经采用的控制器影响，不能倒推未执行混合的结局。", "",
        "## 后续判断", "",
        "选择：**先制定并独立冻结响应模型训练／资格协议**。此建议基于模型适用性尚未建立、后续预测与拟合误差分离、参数误差及命令变化；并非证明某个新模型一定有效，也不以预测误差代替任务收益。不要在旧人口上修补该版 ARX 的阈值、输入或参数。", "",
        "有限幅度更新仍是待验证的工程基线，当前不启动新采集。若之后具备进入条件，保留六程序、固定 α=0.25／0.50、相同拟合与无效保留 C8、同一当前观测和每步一次固定策略查询；只混合各自有界发送命令的 XY。最大 9 组／324 次／162,000 控制步／16,524 全部重置／9,072,000 物理帧，训练费用另列。候选完整新开发平均截止损失必须同时低于 DIRECT_C8 和积分补偿，成功率完整披露；失败则封存该版 ARX，不继续叠加选择规则。", "",
        "移动前的获取决策仍须建立在有效基线上，保留直接继续、积分、始终探测、探测不更新、标准变化检测、历史辨识与任务相关获取参考。获取动作真实执行、全费用一次计入，回退从当前状态继续；训练、校准、最终评价分别分配，最终评价使用新方法自身的时序历史。限幅、回退或经验预测区间均不自动构成安全保证。LLM 若后续参与，须给出可测量角色与同预算无 LLM 对照。", "",
        "门控、命令混合、收益预测与任务相关探测已有研究。查新表及独立后续协议另存文档；本次交付、诊断及标准预测模型／限幅基线均不视为 CCF A 目标完成。", "",
        "## 来源与复算", "", f"[诊断协议]({link(ROOT/'docs/protocols/movement_failure_diagnostic_v1.md')})；[配置]({link(ROOT/'configs/movement_task/diagnostic_v1.json')})；[完成清单及全部来源 SHA-256]({link(base/'completion.json')})；[独立审计]({link(audit_path)})；[补充独立审计]({link(supp/'independent_audit.json')})。", "",
        "从仓库根目录运行下面命令。默认目录拒绝覆盖；复算时指定新的输出目录并在审计中使用相同路径。不得运行原收集器来替代诊断。", "", "```powershell", ".venv\\Scripts\\python.exe scripts/diagnose_movement_failure_v1.py --output outputs/movement_task/diagnostic_replay_v1", ".venv\\Scripts\\python.exe scripts/audit_movement_failure_diagnostic_v1.py --input outputs/movement_task/diagnostic_replay_v1 --output outputs/movement_task/diagnostic_replay_audit_v1/check.json", "```", ""]
    with report.open("x", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    receipt = {"status":"GENERATED_FROM_AUDITED_POSTHOC_DIAGNOSTICS", "report":report.relative_to(ROOT).as_posix(), "report_sha256":sha(report),
        "renderer_sha256":sha(Path(__file__)), "sources":{p.relative_to(ROOT).as_posix():sha(p) for p in (base/'completion.json',audit_path,supp/'completion.json',supp/'independent_audit.json')},
        "exports":{p.name:sha(p) for p in output.iterdir()}, "wall_ns":perf_counter_ns()-start,
        "new_environment_steps":0,"new_all_resets":0,"new_api_calls":0,"new_model_fits":0}
    (output/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == "__main__":
    with read_only_analysis_guard():
        main()
