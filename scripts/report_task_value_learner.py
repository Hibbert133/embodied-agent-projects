"""Chinese complete development replay report bound to the finished audit."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_task_value_learner as runner


def report(manifest, audit_path, destination):
    audit = runner.read(audit_path)
    base = manifest.parent
    if audit["integrity"] != "PASSED" or audit["decisions"] != 384:
        raise ValueError("complete audited development replay required")
    for name, expected in audit["artifact_sha256"].items():
        if runner.source.digest(base / name) != expected:
            raise ValueError("audited learner output changed")
    def link(path):
        return Path(os.path.relpath(path, destination.parent)).as_posix()
    learned, direct = audit["methods"]["TWO_STAGE"], audit["methods"]["DIRECT_VALUE"]
    strong = audit["original_all_baselines"]["EARLY16_WIDE"]
    competitive = learned["successes"] >= strong["successes"] and learned["mean_deadline_loss"] <= strong["mean_deadline_loss"]
    lines = ["# 两阶段任务分支收益学习：中文开发结果", "",
             f"两阶段候选成功 {learned['successes']}/192，直接分支值基准 {direct['successes']}/192，"
             f"最强固定宽十六步 {strong['successes']}/192。对强固定基线的描述性竞争条件{'满足' if competitive else '不满足'}"
             "（成功不减少且截止损失不增大）；这不是预注册的独立确认门或显著性结论。", "",
             "这是旧开发数据上的整流嵌套交叉拟合与真实旧分支回放，不是新在线执行。"
             "采用标准核岭回归，未确立新颖性、独立泛化或 CCF A 投稿资格。新仿真、API 与经验记忆写入均为零。", "",
             f"运行 `{audit['run_id']}`；冻结源 `{audit['source_git_commit']}`；清单 `{audit['manifest_id']}`。", "",
             f"[冻结协议]({link(ROOT/'docs/protocols/task_value_learner_development_v1.md')}) · "
             f"[原始文献边界]({link(ROOT/'docs/research/task_value_learner_prior_art_v1.md')}) · "
             f"[独立方程与决策审计]({link(audit_path)}) · [全部数据及模型]({link(manifest)})", "",
             "## 全部结果与十二个原基线", "",
             "每方法分母 192。截止损失为成功时的总步，失败或停止为 500；历史选定分支步数不是本轮新增交互。", "",
             "| 方法 | 成功 / 192 | 停止 | 历史平均在线步 | 平均截止损失 |",
             "|---|---:|---:|---:|---:|"]
    for method, r in audit["methods"].items():
        lines.append(f"| {method} | {r['successes']} | {r['stops']} | {r['mean_historical_selected_steps']:.4f} | {r['mean_deadline_loss']:.4f} |")
    for method, r in audit["original_all_baselines"].items():
        lines.append(f"| {method} | {r['successes']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_deadline_loss']:.4f} |")
    lines.extend(["", "## 真正使用的动作", "", "| 候选 | 选定真实分支 | 次数 |", "|---|---|---:|"])
    for method, selected in audit["selected_methods"].items():
        for branch, count in selected.items():
            lines.append(f"| {method} | {branch} | {count} |")
    lines.extend(["", "前模型只读取六步可见历史，后模型只读取实际所选探测的证据。"
                  "后模型估计 UPDATE 减 KEEP 的损失；无效拟合强制 KEEP。前训练目标来自内层未参与拟合流上的后选择，"
                  "包括后选择犯错；未取两个结局的最小值作标签。直接值基准固定使用原 UPDATE 分支与停止语义。", "",
                  "## 八流、任务与情景分层", "", "| 方法 | 分层 | 成功 / 分母 | 停止 | 平均截止损失 |", "|---|---|---|---:|---:|"])
    outcomes = [json.loads(line) for line in (base / "outcomes.jsonl").read_text(encoding="utf-8").splitlines()]
    groups = defaultdict(list)
    for row in outcomes:
        stream, task, scenario, repeat = row["case_id"].split("/")
        for label in (stream, task, scenario, repeat):
            groups[(row["method"], label)].append(row)
    for (method, group), values in sorted(groups.items()):
        r = runner.summary(values)
        lines.append(f"| {method} | {group} | {r['successes']} / {r['cases']} | {r['stops']} | {r['mean_deadline_loss']:.4f} |")
    lines.extend(["", "## 全部失败", "", "| 方法 | 案例 | 真实选定分支 | 停止 | 历史步 | 截止损失 |", "|---|---|---|---|---:|---:|"])
    for r in audit["failed_cases"]:
        lines.append(f"| {r['method']} | {r['case_id']} | {r['selected_method']} | {r['stopped']} | {r['steps']} | {r['loss']} |")
    lines.extend(["", "## 完整训练费用与边界", "",
                  f"本轮复用的完整 paired 原数据收集费用为 {audit['full_paired_source_steps']:,} 登记控制步／"
                  f"{audit['full_paired_source_controlled_resets']:,} 次控制初始重置（其中冷源 384／24 已在内）。"
                  "完整旧名义模型来源另为 21,010／288。原初始化仪器测得 61,257,185 请求帧，"
                  "详见原中文报告。没有按被选分支隐藏训练采集费，也没有将八折当成八次物理采集。", "",
                  "上表只描述历史所选分支表现，不能据此宣称包含训练摊销后的部署效率。"
                  "如果后续部署成立，学习方法仍需承担这笔完整训练来源费；摊销人口与实测在线表现须另行冻结。", "",
                  f"独立审计核对 {audit['ridge_equations_checked']} 组核岭方程、384 个保存选择与对应实际旧结局。"
                  "严格证据特征构造及原配对状态检查明确复用，未重新仿真动力学，也没有全隐状态或概率资格。", "",
                  "下一步需要相对于标准任务相关方法明确机制差异，并在独立新范围真实执行冻结模型。"
                  "开发回放的好结果不能代替它；负结果也不能通过调整同批特征或核参数后重新命名为确认。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    args = parser.parse_args(); destination = args.report_path.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents:
        raise FileExistsError("new external report required")
    text = report(args.manifest.resolve(), args.audit.resolve(), destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(text.encode("utf-8"))
    print(json.dumps({"report_sha256": runner.source.digest(destination), "report_path": str(destination)}))
