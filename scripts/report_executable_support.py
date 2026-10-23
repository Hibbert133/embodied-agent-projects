"""Chinese complete-population report of the registered support intervention."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_executable_support as run


def report(manifest_path, audit_path, destination):
    manifest = run.load(manifest_path)
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["integrity"] != "PASSED" or audit["episodes"] != 864 or any(manifest[k] != audit[k] for k in run.IDENTITY):
        raise ValueError("matching completed support audit required")
    for name, expected in audit["artifact_sha256"].items():
        if run.digest(manifest_path.parent / name) != expected:
            raise ValueError("audited raw output changed")
    summary = json.loads((manifest_path.parent / "summary.json").read_text(encoding="utf-8"))
    stats = audit["statistics"]; signal = stats["development_signal"]
    def link(path): return Path(os.path.relpath(path, destination.parent)).as_posix()
    lines = ["# 纠正后执行指令支持：完整中文开发结果", "",
             f"九方法、16 个算子流／三任务／两噪声实现，共 96 单元、864 次真实执行。"
             f"预登记开发信号{'成立' if signal['passed'] else '未成立'}；这不构成独立方法确认或算法新颖性。", "",
             "IVR_EXEC16 将名义原政策指令经过当前有界纠正器，再对实际会发送的命令计算 IVR。"
             "IVR_EXEC_FIXED16 只在第八步映射一次，之后仅更新评分矩与最终控制器。"
             "两者都不是完整未来任务价值规划，也没有新停止规则。", "",
             f"运行 `{audit['experiment_run_id']}`；冻结源 `{audit['source_git_commit']}`；清单 `{audit['manifest_id']}`。"
             "新种子 11800–11847；11848–12199 及全部旧保留种子未执行。API、自然经验记忆和策略权重更新为零。", "",
             f"[冻结协议]({link(ROOT/'docs/protocols/executable_support_development_v1.md')}) · "
             f"[机制与原始文献边界]({link(ROOT/'docs/research/executable_support_mechanism_v1.md')}) · "
             f"[执行审计]({link(audit_path)}) · [清单与原始数据]({link(manifest_path)})", "",
             "## 完整方法比较", "", "每方法完整分母 96。截止损失为成功的实际总步，失败／停止取 500。"
             "停止保持失败分母，真实步另外报告。", "",
             "| 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均探测步 | 平均截止损失 | 含完整来源平均步 | 点逆无效检查 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in stats["methods"].items():
        lines.append(f"| {name} | {r['successes']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_probe_steps']:.4f} | {r['mean_deadline_loss']:.4f} | {r['mean_amortized_steps']:.4f} | {r['point_fit_failures']} |")
    lines.extend(["", "全部八个名义模型方法完整承担旧 21,010 步／288 次控制重置，按 96 单元摊销为"
                  "218.8542 步／3 次重置；物理来源只采集一次。点逆无效检查不等于无有限参数或 Gaussian 停止数。", "",
                  "## 候选减各对照的配对差", "", "先在每流内平均三任务／两噪声，再在反射／非反射各八流内重采样。"
                  "主比较为 IVR_EXEC16 对 IVR_TASK16；其余为已登记次级描述，不能更换主比较。"
                  "区间为 10,000 次算子流分层配对 bootstrap 百分位 95% 区间，条件于固定名义来源和生成域。", "",
                  "| 对照 | 成功率差及区间 | 截止损失差及区间 | 实际步差及区间 |", "|---|---|---|---|"])
    for name, r in stats["candidate_contrasts"].items():
        cells = []
        for field in ("success_rate", "deadline_loss", "actual_steps"):
            v = r[field]; low, high = v["paired_cluster_percentile_95"]
            cells.append(f"{v['difference']:.4f} [{low:.4f}, {high:.4f}]")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    lines.extend(["", "## 预登记开发信号与实际程序", "", "| 指标 | 值 |", "|---|---|"])
    for name, value in signal.items(): lines.append(f"| {name} | {value} |")
    lines.extend(["", "| 方法 | 已保存并执行的两次四步程序序列 | 案例数 |", "|---|---|---:|"])
    for name, r in stats["methods"].items():
        for sequence, count in r["selected_program_sequences"].items(): lines.append(f"| {name} | {sequence} | {count} |")
    groups = defaultdict(list)
    for row in summary["cases"]:
        for label in (f"task:{row['task']}", f"stream:{row['stream']}", f"replicate:{row['replicate']}"):
            groups[(row["method"], label)].append(row)
    lines.extend(["", "## 全部分层", "", "| 方法 | 分层 | 成功 / 分母 | 停止 | 平均截止损失 |", "|---|---|---|---:|---:|"])
    for (method, label), part in sorted(groups.items()):
        lines.append(f"| {method} | {label} | {sum(r['success'] for r in part)} / {len(part)} | {sum(r['stopped'] for r in part)} | {sum(r['deadline_loss'] for r in part)/len(part):.4f} |")
    lines.extend(["", "## 全部失败与停止", "", "| 方法 | 流 | 任务 | 重复 | 种子 | 停止 | 实际步 |", "|---|---:|---|---:|---:|---|---:|"])
    for r in summary["cases"]:
        if not r["success"]: lines.append(f"| {r['method']} | {r['stream']} | {r['task']} | {r['replicate']} | {r['seed']} | {r['stopped']} | {r['total_steps']} |")
    counts = audit["lifecycle"]["counts"]
    lines.extend(["", "## 完整新增费用与资格", "",
                  f"新增 Env.step {audit['controlled_steps']:,}，控制初始重置 {audit['controlled_resets']:,}；"
                  f"全部顶层完成重置 {counts['reset_completed']:,}，完成 do_simulation 请求帧 {counts['simulation_frames_completed']:,}。", "",
                  "| 阶段 | 完成重置 | 完成模拟调用 | 完成请求帧 |", "|---|---:|---:|---:|"])
    for name, r in audit["lifecycle"]["by_phase"].items():
        lines.append(f"| {name} | {r.get('reset_completed',0)} | {r.get('simulation_completed',0)} | {r.get('simulation_frames_completed',0)} |")
    lines.extend(["", "没有探测后重置、恢复或重播种；每 Env.step 五帧／0.0125 秒。请求帧不是所有 C 引擎计算或真实机器人费用。"
                  "旧名义来源内部初始化未在本轮重新测量。", "",
                  "审计核对保存选择先于执行、支持映射摘要、逐步政策／程序、实际注入与随机数、全部费用和 Git 字节。"
                  "Gaussian／点拟合／支持映射数学辅助函数、声明配对与统计公式明确复用，没有动力学重仿真或完整隐状态验证。", "",
                  "查询测度是当前纠正器的名义命令映射，不是未来物体状态或政策占用分布；方差减少不等于任务收益。"
                  "Gaussian 局部矩、经验 RMS、饱和导数均未获物理、概率或安全资格。", "",
                  "有用的开发信号也不能替代新颖性、独立确认、多故障／变化场景和完整论文。"
                  "若无信号，保留负结果，不调整本轮映射、超参数或种子。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--audit", type=Path, required=True); parser.add_argument("--report-path", type=Path, required=True)
    args = parser.parse_args(); destination = args.report_path.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents: raise FileExistsError("new external report required")
    text = report(args.manifest.resolve(), args.audit.resolve(), destination)
    destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(text.encode("utf-8"))
    print(json.dumps({"report_path": str(destination), "report_sha256": run.digest(destination)}))
