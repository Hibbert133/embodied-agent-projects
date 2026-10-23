"""Chinese formatting only, from the audited immutable alignment outputs."""
import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cache_continuation_alignment_v1 as io

LABELS = {"CUSUM4": "累计异常检查", "PLUGIN4": "旧点估计检查", "UNCERTAINTY4": "考虑旧参数误差的检查", "TASK_IVR4": "当前动作的信息检查"}
STATUS = {"EXCLUDED_METHOD": "其他方法", "EXCLUDED_BALANCED_PROGRAM": "均衡检查采用不同程序",
          "EXCLUDED_NO_WARM_CHECK": "无暖缓存，实际冷启动", "EXCLUDED_ENDED_BY_CUTOFF": "第4步前或当步已经结束",
          "EXCLUDED_CHECK_STOP": "检查后停止", "CONDITIONAL_REALIZED_REUSE_PAIR": "实际复用的条件配对",
          "FACTUAL_REFRESH_NEGATIVE_CONTROL": "实际刷新的续接负控制"}


def render(path):
    manifest, _, _ = io.load(path)
    folder = path.parent/"analysis_v1"
    summary = io.read(folder/"summary.json")
    costs = io.read(folder/"costs.json")
    audit = io.read(path.parent/"audit_v1.json")
    if audit["integrity"] != "PASSED" or audit["summary_sha256"] != io.sha(folder/"summary.json"):
        raise ValueError("matching independent audit required")
    exports = folder/"tables_v1"
    exports.mkdir()
    for name in ("dispositions", "reuse_pairs", "unique_reuse_pairs", "refresh_controls"):
        rows = list(io.lines(folder/(name+".jsonl.gz")))
        if not rows:
            continue
        with (exports/(name+".csv")).open("x", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: io.canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})
    def rel(p): return p.relative_to(ROOT).as_posix()
    unique = list(io.lines(folder/"unique_reuse_pairs.jsonl.gz"))
    lines = ["# 同一4步前缀下，复用与重测的当前任务对照", "",
        "本轮是旧轨迹的条件续接核对与描述性分析，没有新增机器人仿真或在线API，也没有训练新方法。",
        "它在原时序参考结果已知后设计，不属于原注册的四项比较，也不是独立确认。", "",
        "源记录没有获得完整隐藏状态资格，不能把记录状态相同升级为完整状态证书。以下配对差只在"
        "冻结源程序、重置、噪声时钟与无旧缓存依赖的刷新合同成立时解释；不声称无条件因果识别。", "",
        "## 名字与比较目标", "",
        "把ALWAYS8记为“每次重新测8步”。另四种方法有旧参数时先检查4步，随后复用，或再测4步重新估计。"
        "参数缓存保存以前实际成功使用的纠正参数，不是LLM对话记忆。中文名字见[方法说明](../docs/research/method_names_zh.md)。", "",
        "本轮的数值为 `d = 复用的截止损失 − 重测的截止损失`。成功时损失为全部实际步数，失败／停止为500。"
        "正值表示这一次重测损失较低；负值表示复用较低。前4步公共成本抵消，重测新增4步及其状态影响仍计入。", "",
        "## 全部源案例去向", "", "| 类别 | 案例数 |", "|---|---:|"]
    for status, count in summary["disposition_counts"].items():
        lines.append(f"| {STATUS[status]}（{status}） | {count} |")
    lines += ["", f"共覆盖全部{summary['source_case_dispositions']}次源方法执行；其他类别没有被补成缺失的复用标签。", "",
        "## 实际复用区域的条件实现差", "", "| 行为方法 | 配对数 | 重测损失较低 | 复用较低 | 相等 | 平均d | 复用丢失／挽回成功 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for method, row in summary["by_behavior"].items():
        mean = "无" if row["mean_realized_reuse_minus_fresh_loss"] is None else f"{row['mean_realized_reuse_minus_fresh_loss']:.6f}"
        lines.append(f"| {LABELS[method]}（{method}） | {row['cases']} | {row['fresh_lower_realized_loss']} | {row['reuse_lower_realized_loss']} | {row['equal_realized_loss']} | {mean} | {row['lost_success_with_reuse']}／{row['rescued_success_with_reuse']} |")
    row = summary["unique_decisions"]
    mean = "无" if row["mean_realized_reuse_minus_fresh_loss"] is None else f"{row['mean_realized_reuse_minus_fresh_loss']:.6f}"
    lines += ["", f"{summary['behavior_reuse_sites']}个行为复用位置，按同一实际单元且公开证据相同去重为"
        f"{summary['unique_same_unit_decisions']}个决策，重复{summary['duplicate_reuse_sites']}个。不同实际单元不合并。"
        f"去重后重测较低{row['fresh_lower_realized_loss']}、复用较低{row['reuse_lower_realized_loss']}、相等{row['equal_realized_loss']}；"
        f"平均d为{mean}。复用丢失{row['lost_success_with_reuse']}次成功、挽回{row['rescued_success_with_reuse']}次成功。", "",
        "这里的行数不是独立样本数：多个方法共享ALWAYS8参考，缓存也依赖同一流的过去。"
        "只存在于原行为选择复用的区域，每单元只有一个未来实现；本轮不计算置信区间或选择阈值。", "",
        "## 续接负控制", "",
        f"实际选择重测的{summary['factual_refresh_controls']}个位置，核对了第4步后"
        f"{summary['factual_refresh_continuation_steps_checked']}个物理步骤。后续指令、响应、噪声、拟合及当前任务结果严格一致；"
        f"最大截止损失差为{summary['factual_refresh_control_loss_difference_max_abs']}。"
        "这检验记录程序的可替代性，没有提供这些位置未执行的复用结果，也没有替代完整隐藏状态资格。", "",
        "## 固定规则选取的示例", "", "按流、单元顺序取各类最早一例，完整逐例表同时保留。", "",
        "| 类别 | 流／单元 | 复用／重测成功 | 复用／重测损失 | d |", "|---|---|---|---:|---:|"]
    for label, predicate in (("重测损失较低", lambda r: r["realized_loss_difference_under_source_contract"] > 0),
                             ("复用损失较低", lambda r: r["realized_loss_difference_under_source_contract"] < 0),
                             ("复用丢失成功", lambda r: r["realized_success_difference"] < 0),
                             ("复用挽回成功", lambda r: r["realized_success_difference"] > 0)):
        example = next((r for r in sorted(unique, key=lambda r: (r["stream"], r["episode"])) if predicate(r)), None)
        if example is None:
            lines.append(f"| {label} | 无 | — | — | — |")
        else:
            r = example
            lines.append(f"| {label} | {r['stream']}／{r['episode']} | {r['reuse_success']}／{r['fresh_success']} | {r['reuse_deadline_loss']}／{r['fresh_deadline_loss']} | {r['realized_loss_difference_under_source_contract']} |")
    ledger = costs["source_cost_ledger"]
    main = costs["source_main_lifecycle"]
    smoke = ledger["separate_smoke_physical_cost"]
    joint = ledger["joint_source_full_lifecycle"]
    lines += ["", "## 完整成本与数据边界", "",
        f"新增环境步、受控／工厂重置、API、名义模型／控制器／选择器拟合均为0。"
        f"本地固定政策查询{costs['local_policy_queries']}次；主分析墙钟{costs['analysis_wall_seconds']:.3f}秒。独立核对只读取记录，不额外查询政策。", "",
        f"既有主实验4752次执行实际{costs['source_main_actual_environment_steps']}步、4752次受控及237600次工厂重置，"
        f"共{main['counts']['simulation_frames_attempted']}个请求仿真帧；smoke另有{smoke['controlled_steps']}步、{smoke['controlled_resets']}次受控重置。"
        f"现代联合模型来源完整3840步／480次受控重置，完整生命周期{joint['counts']['reset_completed']}次重置、"
        f"{joint['counts']['simulation_frames_attempted']}个请求帧；旧模型来源完整21010步／288次受控重置，其工厂成本未知，不能记0。", "",
        "完整来源只物理采集一次；下面延用原432单元摊销，未按本轮筛选或去重后数量重新摊薄。", "",
        "| 源方法 | 在线实际步数 | 完整离线来源步数／受控重置 | 摊销后平均实际步数 |", "|---|---:|---:|---:|"]
    for cell in ledger["per_method_source_and_online"]:
        lines.append(f"| {cell['method']} | {cell['actual_online_steps']} | {cell['offline_source_steps']}／{cell['offline_source_controlled_resets']} | {cell['mean_amortized_actual_steps']:.6f} |")
    lines += ["", "公开输入包只保存决策当时可见的观测、4步发送动作、旧参数／工作协方差、源任务／年龄／边界标志、当前政策指令及剩余预算。"
        "真实扰动、种子、流／方法身份、物理见证、噪声状态和未来结果保留在评价文件；输入和标签分开保存。", "",
        "## 结论范围", "",
        "本轮能说明记录中的刷新续接是否一致，以及已实际选择复用的那些位置在一个共同未来下的当前任务差。"
        "它没有识别条件期望收益、所有状态上的最优重测规则、整条未来任务流的收益，亦未建立新算法或CCF A投稿证据。"
        "API闭环已有独立报告，本轮没有API参与；不能把这轮核对归为LLM收益。", "",
        f"独立核对：{audit['integrity']}；重新构造{audit['source_cases']}个源案例，核对{audit['derived_rows_checked']}行派生记录。", "",
        f"运行：`{manifest['experiment_run_id']}`；清单：`{manifest['manifest_id']}`；冻结提交：`{manifest['source_git_commit']}`。", "",
        f"[清单](../{rel(path)})、[独立核对](../{rel(path.parent/'audit_v1.json')})、[成本账](../{rel(folder/'costs.json')})、"
        f"[全部去向](../{rel(exports/'dispositions.csv')})、[全部配对](../{rel(exports/'reuse_pairs.csv')})、"
        f"[去重配对](../{rel(exports/'unique_reuse_pairs.csv')})、[全部负控制](../{rel(exports/'refresh_controls.csv')})。", ""]
    report = ROOT/"reports/cache_continuation_alignment_development_v1.md"
    with report.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    io.write(folder/"report_provenance_v1.json", {"report_path": rel(report), "report_sha256": io.sha(report),
        "script_sha256": io.sha(Path(__file__)), "audit_sha256": io.sha(path.parent/"audit_v1.json"),
        "table_sha256": {p.name: io.sha(p) for p in exports.iterdir()}})
    print(report, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    render(args.manifest.resolve())
