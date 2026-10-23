"""Chinese completed early-continuation report, with all cases and source fees."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_early_evidence as run


def report(manifest_path, audit_path, destination):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")); audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["integrity"] != "PASSED" or audit["episodes"] != 768 or any(manifest[k] != audit[k] for k in run.IDENTITY): raise ValueError("matching completed audit required")
    for name, expected in audit["artifact_sha256"].items():
        if run.digest(manifest_path.parent / name) != expected: raise ValueError("audited bytes changed")
    summary = json.loads((manifest_path.parent / "summary.json").read_text(encoding="utf-8")); stats = audit["statistics"]; gate = stats["repeat_gate"]
    def link(path): return Path(os.path.relpath(path, destination.parent)).as_posix()
    lines = ["# 早期八步后的继续测量：中文完整结果", "",
             f"本轮八流／三任务／四噪声实现，共 96 单元、八方法、768 次真实方法执行。主目标 POINT16_CYCLE 对 POINT8 的重复性门{'通过' if gate['passed'] else '未通过'}。"
             "目标是判断早期实际测量之后额外八步的任务作用；不是已确认的新停止算法或 CCF A 方法贡献。", "",
             f"运行 `{audit['experiment_run_id']}`；冻结源 `{audit['source_git_commit']}`；清单 `{audit['manifest_id']}`。"
             "新种子 11500–11523；11524–11799 和所有旧保留范围未执行。API、经验记忆写入与策略权重更新为零。", "",
             f"[冻结协议]({link(ROOT/'docs/protocols/early_evidence_development_v1.md')}) · [原始文献边界]({link(ROOT/'docs/research/gaussian_reference_prior_art_v1.md')}) · "
             f"[执行与费用审计]({link(audit_path)}) · [清单与原始分流轨迹]({link(manifest_path)})", "",
             "## 全部八方法", "", "每方法完整分母 96。成功用实际总步，失败或停止的截止损失为 500。"
             "实际物理步另外报告，不能把未执行任务的低步数当作效率改善。", "",
             "| 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均探测步 | 平均截止损失 | 平均含完整来源步 | 无效拟合检查 |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for method, r in stats["methods"].items():
        lines.append(f"| {method} | {r['successes']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_probe_steps']:.4f} | {r['mean_deadline_loss']:.4f} | {r['mean_amortized_steps']:.4f} | {r['point_fit_failures']} |")
    lines.extend(["", "所有名义模型方法完整承担 21,010 个旧控制步／288 次控制重置，按 96 单元摊销（218.8542 步／3 次重置）。"
                  "物理源只采集一次。名义 TASK 分布只取旧 TRAIN 的 POLICY_ONLY 原政策 xy 命令；不使用资格检验结局或当前任务结果。", "",
                  "POINT16_CYCLE 是两次宽八，POINT16_WIDE 是四方向各四步；二者真实运动顺序不同，后者作为总体强固定基线保留。"
                  "GAUSS 与 IVR 为标准近似参考：条件于名义模型、经验 RMS 和局部 Jacobian，没有已验证的物理似然或概率／安全资格。"
                  "Gaussian 构建可以使用有限但逆不稳定的点参数；无效拟合检查计数不等于停止数或案例数。", "",
                  "## 主任务收益重复性", "", "| 指标 | 结果 |", "|---|---:|"])
    for name, value in gate.items(): lines.append(f"| {name} | {value} |")
    lines.extend(["", "四次噪声实现从初始状态开始，前八步可见轨迹可能不同；这是名义上下文重复性，不能声称完全固定状态的条件收益分布。"
                  "+1 为继续八步后截止损失改善，−1 为恶化，0 为相同。其余三重复的符号和预测当前非零方向，和零弃权。", "",
                  "| 流 | 任务 | 四符号 | 共享八步完整 | 反转 | 留一正确 / 已预测 |", "|---:|---|---|---|---|---|"])
    for r in stats["primary_contexts"]:
        lines.append(f"| {r['stream']} | {r['task']} | {r['signs']} | {r['complete']} | {r.get('sign_reversal', '不可评')} | {r.get('leave_one_out_correct', '不可评')} / {r.get('leave_one_out_checked', '不可评')} |")
    groups = defaultdict(list)
    for row in summary["cases"]:
        for label in (f"task:{row['task']}", f"stream:{row['stream']}", f"replicate:{row['replicate']}"):
            groups[(row["method"], label)].append(row)
    lines.extend(["", "## 完整分层", "", "| 方法 | 分层 | 成功 / 分母 | 停止 | 平均截止损失 |", "|---|---|---|---:|---:|"])
    for (method, label), part in sorted(groups.items()):
        lines.append(f"| {method} | {label} | {sum(r['success'] for r in part)} / {len(part)} | {sum(r['stopped'] for r in part)} | {sum(r['deadline_loss'] for r in part)/len(part):.4f} |")
    lines.extend(["", "## 全部失败／停止", "", "| 方法 | 流 | 任务 | 重复 | 种子 | 停止 | 实际步 | 截止损失 |", "|---|---:|---|---:|---:|---|---:|---:|"])
    for r in summary["cases"]:
        if not r["success"]: lines.append(f"| {r['method']} | {r['stream']} | {r['task']} | {r['replicate']} | {r['seed']} | {r['stopped']} | {r['total_steps']} | {r['deadline_loss']} |")
    counts = audit["lifecycle"]["counts"]
    lines.extend(["", "## 全部新增初始化费用", "",
                  f"新增登记控制 {audit['controlled_steps']:,} 次 Env.step，控制初始重置 {audit['controlled_resets']:,} 次。"
                  f"顶层重置入口实测 {counts['reset_completed']:,}，do_simulation 完成请求帧 {counts['simulation_frames_completed']:,}。", "",
                  "| 生命周期阶段 | 完成重置 | 完成模拟调用 | 完成请求帧 |", "|---|---:|---:|---:|"])
    for name, r in audit["lifecycle"]["by_phase"].items():
        lines.append(f"| {name} | {r.get('reset_completed',0)} | {r.get('simulation_completed',0)} | {r.get('simulation_frames_completed',0)} |")
    lines.extend(["", "临时目标工厂安置与当前在线轨迹的控制初始重置分列，没有探测后重置或 RNG 重播种。"
                  "请求帧是 Python 模拟入口口径，不是全部 C 引擎计算、渲染或真实机器人费用。旧名义来源的内部初始化不由本轮仪器重新测量。", "",
                  "审计核对选择先于执行、真实注入／连续随机数、逐步政策／程序、全部费用及固定 Git 字节；"
                  "拟合／Gaussian 数学、声明状态配对与重复公式明确复用。没有重仿真动力学或完整隐状态资格。", "",
                  "标准高斯控制、任务 IVR 或普通早停本身不是本项目的新颖性。主重复性门只支持判断后继研究设计，"
                  "竞争性方法、独立确认与完整论文仍需完成。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--audit", type=Path, required=True); parser.add_argument("--report-path", type=Path, required=True)
    args = parser.parse_args(); destination = args.report_path.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents: raise FileExistsError("new external report required")
    text = report(args.manifest.resolve(), args.audit.resolve(), destination); destination.parent.mkdir(parents=True, exist_ok=True); destination.write_bytes(text.encode("utf-8"))
    print(json.dumps({"report_sha256": run.digest(destination), "report_path": str(destination)}))
