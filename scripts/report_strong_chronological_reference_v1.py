"""Chinese report of all registered strong standard references and complete costs."""
import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_strong_chronological_reference_v1 as io

LABELS = {"NO_PROBE": "直接做", "ALWAYS8": "每次重测8步", "ALWAYS16_OLD": "旧估计器测16步", "PASSIVE_RECENT8": "8步被动拟合无效即停",
    "PASSIVE8_KEEP": "8步无效更新则保留", "PASSIVE64_PERIODIC16_KEEP": "每16步近期64项更新保留",
    "UNCERTAINTY4": "考虑旧参数误差的4步检查", "TASK_IVR4": "当前单指令的信息检查", "TASK_HISTORY_IVR4": "自己历史查询的信息检查"}


def csv_out(path, rows):
    if not rows: return
    with path.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)


def report(path, phase):
    m, _, _ = io.load(path); folder = path.parent/phase.lower(); summary = io.read(folder/"summary.json")
    record_audit, numeric = (io.read(path.parent/(phase.lower()+"_audit")/name) for name in ("audit.json", "statistics.json"))
    if any(a["integrity"] != "PASSED" or a["summary_sha256"] != io.sha(folder/"summary.json") for a in (record_audit, numeric)):
        raise ValueError("matching record and independent statistics audits required")
    output = path.parent/(phase.lower()+"_analysis_v1"); output.mkdir()
    rows = summary["cases"]; stats = summary["statistics"]; identity = {k: m[k] for k in io.IDENTITY}
    csv_out(output/"all_cases.csv", rows)
    csv_out(output/"failures.csv", [r for r in rows if not r["success"]])
    csv_out(output/"stops.csv", [r for r in rows if r["stopped"]])
    method_rows, factor_rows = [], []
    for method, cell in stats["methods"].items():
        method_rows.append({"method": method, **{k: v for k, v in cell.items() if k not in ("by_task", "by_factor")}})
        factor_rows.extend({"method": method, **r} for r in cell["by_factor"])
    csv_out(output/"methods.csv", method_rows); csv_out(output/"factors.csv", factor_rows)
    previous = io.read(ROOT/m["config"]["source_costs"])
    costs = {**identity, "phase": phase, "actual_executions": len(rows), "actual_controlled_steps": summary["controlled_steps"],
        "actual_controlled_resets": summary["controlled_resets"], "physical_lifecycle": summary["lifecycle"],
        "online_parameter_fit_attempts": sum(r["online_parameter_fits"] for r in rows), "online_optimizer_nfev": sum(r["optimizer_nfev"] for r in rows),
        "online_policy_queries": sum(r["policy_queries"] for r in rows),
        "audit_policy_queries": record_audit["audit_policy_queries"], "audit_shared_fitter_attempts": record_audit["audit_shared_fitter_attempts"],
        "audit_shared_optimizer_nfev": record_audit["audit_shared_optimizer_nfev"],
        "complete_modern_nominal_steps": 3840, "complete_modern_nominal_controlled_resets": 480,
        "complete_modern_nominal_lifecycle": previous["joint_source_full_lifecycle"],
        "complete_old_nominal_steps": 21010, "complete_old_nominal_controlled_resets": 288, "old_nominal_factory_cost": "UNKNOWN_NOT_ZERO",
        "source_cost_ledger_reference": {"path": m["config"]["source_costs"], "sha256": m["config"]["source_costs_sha256"]},
        "per_method_source_and_online": method_rows, "nominal_model_fits": 0, "api_calls": 0, "policy_weight_updates": 0,
        "source_fee_interpretation": "Nominal data physically collected once; each standalone method pays its complete source amortized by its units, not all method executions. Earlier development banks are not training observations in this comparison."}
    if phase == "MAIN":
        smoke = io.read(path.parent/"smoke/summary.json")
        costs["separate_smoke"] = {"executions": smoke["executions"], "controlled_steps": smoke["controlled_steps"],
            "controlled_resets": smoke["controlled_resets"], "lifecycle": smoke["lifecycle"]}
    io.write(output/"costs.json", costs, exclusive=True)
    lines = ["# 支持无效更新保留与历史查询的连续仿真参考", "",
        "本轮在实际运行的MetaWorld仿真中补齐标准参考，没有在线LLM/API、新算法或真实机器人硬件结果。"
        "原实验及其停止保持原样，下面是新种子上的独立开发比较。", ""]
    if phase == "SMOKE": lines += ["**本文件是主机／记录预检，不能按其任务分数调方法或宣布主实验收益。**", ""]
    else:
        p = stats["contrasts"][0]["statistics"]["deadline_loss"]
        lower, upper = p["stratified_stream_percentile_95"]
        lines += [f"注册主比较是“每16步近期64项更新保留”减“每次重测8步”：平均截止损失差{p['difference']:+.6f}步，"
            f"95%分层完整流区间[{lower:+.6f}, {upper:+.6f}]。正值表示前者损失更高；区间跨0不能解释为等效或非劣效。", ""]
    lines += ["## 方法的中文含义与全部结果", "",
        "新被动方法在拟合无效后实际沿用当时已保存控制器；较晚无效更新保留最近应用的控制器。"
        "历史查询参考只用本方法较早已执行的同任务原政策指令，加当前第4步的一条查询，等权计算方差降低。"
        "它不是完整规划器或任务收益预测。", "",
        "| 方法 | 成功／全部 | 停止 | 平均截止损失 | 平均实际步数 | 平均专门探测 | 来源摊销后实际步数 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for method, c in stats["methods"].items():
        lines.append(f"| {LABELS[method]}（{method}） | {c['successes']}／{c['cases']} | {c['stops']} | {c['mean_deadline_loss']:.6f} | {c['mean_total_steps']:.6f} | {c['mean_fixed_probe_steps']:.6f} | {c['mean_amortized_actual_steps']:.6f} |")
    lines += ["", "失败／停止的截止损失均为500，实际费用仍按真实已执行步数记。"
        "多个方法进入当前单元时的缓存和查询历史可能不同，整流差不能全部归因于当前一次决定。", "",
        "## 全部注册比较", "", "| 比较 | 地位 | 成功率差 | 截止损失差及95%流区间 | 实际步数差 | 专门探测差 |", "|---|---|---:|---:|---:|---:|"]
    for contrast in stats["contrasts"]:
        values = contrast["statistics"]; d = values["deadline_loss"]; lo, hi = d["stratified_stream_percentile_95"]
        lines.append(f"| {contrast['method']} − {contrast['reference']} | {contrast['role']} | {values['success_rate']['difference']:+.6f} | {d['difference']:+.6f} [{lo:+.6f}, {hi:+.6f}] | {values['actual_steps']['difference']:+.6f} | {values['probe_steps']['difference']:+.6f} |")
    lines += ["", "主实验以18个完整流为单位，在九因素格内各2流分层bootstrap10000次。"
        "这是覆盖与资源预算下的开发参考，没有小差异80%功效、等效或非劣效资格；次比较未校正。", "",
        "## 三任务与九因素格", "", "| 方法 | push成功／全部 | reach成功／全部 | door成功／全部 |", "|---|---:|---:|---:|"]
    for method, c in stats["methods"].items():
        cells = [c["by_task"][t] for t in ("push-v3", "reach-v3", "door-open-v3")]
        lines.append(f"| {method} | "+" | ".join(f"{v['successes']}／{v['cases']}" for v in cells)+" |")
    lines += ["", "九因素格逐方法完整结果保存在 `factors.csv`，没有按表现筛除故障族。", "",
        "## 真实链路与审计", "", "| 已实际观察的链路 | 是否出现 |", "|---|---|"]
    for key, value in record_audit["coverage"].items(): lines.append(f"| {key} | {value} |")
    lines += ["", f"记录审计核对{record_audit['events_checked']}个事件；独立统计重建{numeric['numeric_fields_checked']}个数值字段，最大差{numeric['max_absolute_difference']:.3g}。"
        "记录的见证仍无完整隐藏状态资格，不能将字段匹配升级为完整状态证书。私有扰动与噪声仅供审计，不进入选择。", "",
        "## 完整费用", "",
        f"本阶段{summary['executions']}次实际执行、{summary['controlled_steps']}个控制步、{summary['controlled_resets']}次受控重置；"
        f"全部重置{summary['lifecycle']['counts']['reset_completed']}次、请求模拟帧{summary['lifecycle']['counts']['simulation_frames_attempted']}个。"
        "工厂生成、受控初始化与正常控制均逐事件记录。", "",
        f"执行侧拟合尝试{costs['online_parameter_fit_attempts']}、优化器nfev {costs['online_optimizer_nfev']}、政策查询{costs['online_policy_queries']}；"
        f"审计另重算拟合{costs['audit_shared_fitter_attempts']}、优化器nfev {costs['audit_shared_optimizer_nfev']}、政策查询{costs['audit_policy_queries']}。"
        "不把重复计算记0，也不把正常任务动作另收一遍探测费。", "",
        "四条旧ARX参考各付完整21010步／288受控重置；旧工厂费用未知不能记0。四条联合模型参考各付完整3840／480，"
        f"现代来源完整生命周期{previous['joint_source_full_lifecycle']['counts']['reset_completed']}次重置、"
        f"{previous['joint_source_full_lifecycle']['counts']['simulation_frames_attempted']}个请求帧。NO_PROBE模型费0。"
        "共享来源只物理采集一次，每条独立方法按自身单元数摊销，不能按全部方法执行数摊薄。", ""]
    if phase == "MAIN":
        sm = costs["separate_smoke"]
        lines += [f"预检另有{sm['executions']}次执行、{sm['controlled_steps']}步、{sm['controlled_resets']}受控重置、"
            f"{sm['lifecycle']['counts']['reset_completed']}全部重置及{sm['lifecycle']['counts']['simulation_frames_attempted']}请求帧。", ""]
    lines += ["## 全部失败与结论范围", "",
        f"保留全部{sum(not r['success'] for r in rows)}个失败、{sum(r['stopped'] for r in rows)}个停止，逐例见 `failures.csv` 和 `stops.csv`。"
        "拒绝更新后继续控制与任务完成是分别审计的事实，不能把未执行的分支补成成功。", "",
        "本轮只建立标准参考的实际行为和新开发人口上的比较。历史查询方差降低未获物理概率或任务价值资格。"
        "新机制、独立新方法确认与完整CCF A论文仍未建立，任何标准参考获胜均不自动完成目标。", "",
        f"运行：`{m['experiment_run_id']}`；清单：`{m['manifest_id']}`；冻结提交：`{m['source_git_commit']}`。", "",
        f"[主清单](../{path.relative_to(ROOT).as_posix()})、[全部案例](../{(output/'all_cases.csv').relative_to(ROOT).as_posix()})、"
        f"[完整费用](../{(output/'costs.json').relative_to(ROOT).as_posix()})。", ""]
    name = "strong_chronological_reference_smoke_v1.md" if phase == "SMOKE" else "strong_chronological_reference_development_v1.md"
    target = ROOT/"reports"/name
    with target.open("x", encoding="utf-8", newline="\n") as handle: handle.write("\n".join(lines))
    io.write(output/"report_provenance.json", {**identity, "report_path": target.relative_to(ROOT).as_posix(), "report_sha256": io.sha(target),
        "script_sha256": io.sha(Path(__file__)), "summary_sha256": io.sha(folder/"summary.json"),
        "record_audit_sha256": io.sha(path.parent/(phase.lower()+"_audit")/"audit.json"), "statistics_audit_sha256": io.sha(path.parent/(phase.lower()+"_audit")/"statistics.json"),
        "artifact_sha256": {p.name: io.sha(p) for p in output.iterdir() if p.is_file()}}, exclusive=True)
    print(target, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--phase", choices=("SMOKE", "MAIN"), required=True)
    args = parser.parse_args(); report(args.manifest.resolve(), args.phase)
