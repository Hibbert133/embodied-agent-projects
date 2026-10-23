"""Chinese complete prospective selector report, preserving standard-method scope."""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_continuation_selector as run

LABELS={"DIRECT_G8":"八步后直接执行","KEEP_G8_AFTER16":"十六步保留旧估计","UPDATE_G16":"十六步更新",
        "POINT16_CYCLE":"循环十六步点估计","PASSIVE_G16":"边做边观测更新","POINT16_WIDE":"宽十六步点估计",
        "NO_PROBE":"不探测不纠正","MEAN_COST_RBF":"四未来均值核回归","MEAN_COST_NEAREST":"四未来均值最近邻",
        "TASK_MEAN":"八步组合的任务均值","SINGLE_FUTURE_RBF":"单未来核回归","TASK_FULL_PORTFOLIO":"初始任务标签七分支选择"}


def report(manifest_path,audit_path,destination):
    manifest=run.load(manifest_path); audit=json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["integrity"]!="PASSED" or audit["episodes"]!=1152 or any(audit[k]!=manifest[k] for k in run.IDENTITY):
        raise ValueError("matching complete audited population required")
    if any(run.digest(manifest_path.parent/n)!=h for n,h in audit["artifact_sha256"].items()): raise ValueError("audited bytes changed")
    summary=json.loads((manifest_path.parent/"summary.json").read_text(encoding="utf-8")); stats=audit["statistics"]
    primary=stats["main_minus_each_baseline"]["POINT16_CYCLE"]["deadline_loss"]
    def link(path): return Path(os.path.relpath(path,destination.parent)).as_posix()
    lines=["# 八步历史条件代价选择器的前瞻结果","",
           "本轮是标准经验代价选择基准的开发验证。四个八步选择器用当前可见历史保存分支选择，再真实执行该分支；"
           "另一个基准只凭任务名称在初始时刻选择完整七分支。它们不接收当前测试的其他分支结果或未来噪声。"
           "核回归、最近邻和按任务选择均不是本项目的新算法。","",
           f"状态 `{audit['status']}`；主核回归减预定循环十六步的平均截止损失差 {primary['difference']:.4f}，"
           f"算子流分层配对 95% 区间 {primary['paired_cluster_percentile_95']}。开发信号：{stats['development_signal']}。", "",
           f"运行 `{audit['experiment_run_id']}`；冻结源 `{audit['source_git_commit']}`；清单 `{audit['manifest_id']}`。", "",
           f"[协议]({link(ROOT/'docs/protocols/causal_continuation_selector_development_v1.md')}) · "
           f"[已有方法与贡献边界]({link(ROOT/'docs/research/causal_continuation_selector_scope_v1.md')}) · "
           f"[审计]({link(audit_path)}) · [清单及轨迹]({link(manifest_path)})", "",
           "## 全部真实执行方法","","成功损失为包含探测的实际总步；失败／停止记 500。每方法完整分母 96。", "",
           "| 中文简称 | 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均专门探测步 | 平均任务观测步 | 平均截止损失 | 含全部来源摊销步 |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for m,r in stats["methods"].items():
        lines.append(f"| {LABELS[m]} | {m} | {r['successes']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_probe_steps']:.4f} | {r['mean_policy_measure_steps']:.4f} | {r['mean_deadline_loss']:.4f} | {r['mean_amortized_steps']:.4f} |")
    lines.extend(["","Gaussian 参考的 G 表示纠正时也考虑估计不确定性，POINT 是点估计。PASSIVE 的额外八步是任务内真实动作，"
                  "不是免费观察。主 RBF 和最近邻用四未来平均监督；单未来对照只用源未来 0；任务均值不使用当前历史特征。", "",
                  "## 主候选减全部基准","","仅循环十六步为冻结主对比；其余为未做多重比较校正的补充。独立单位是十六算子流，反射与非反射各八。", "",
                  "| 基准 | 成功率差 | 95% 区间 | 截止损失差 | 95% 区间 |", "|---|---:|---|---:|---|"])
    for m,r in stats["main_minus_each_baseline"].items():
        a,b=r["success_rate"],r["deadline_loss"]
        lines.append(f"| {m} | {a['difference']:.4f} | {a['paired_cluster_percentile_95']} | {b['difference']:.4f} | {b['paired_cluster_percentile_95']} |")
    lines.extend(["",f"在成功与在线损失上支配主候选的其他方案：{stats['main_dominated_by']}。该开发判据不能授予算法新颖性或独立方法确认。", "",
                  "## 真实选择与时延","","四个八步选择器的时延从参考构造开始至保存选择之前，包含输入构造与模型验证／预测，不含环境执行；初始任务标签基准在第零步直接查询七分支来源均值。", "",
                  "| 选择器 | 实际选择数 | 所选分支计数 | 中位毫秒 | p90 毫秒 | 最大毫秒 |", "|---|---:|---|---:|---:|---:|"])
    for m in run.LEARNED_METHODS:
        part=[r for r in audit["choices"] if r["method"]==m and r["selection"] is not None]
        ms=np.array([r["latency_ns"]/1e6 for r in part])
        if len(ms):
            lines.append(f"| {m} | {len(part)} | {dict(Counter(r['selected_branch'] for r in part))} | {np.median(ms):.4f} | {np.quantile(ms,.9):.4f} | {ms.max():.4f} |")
        else: lines.append(f"| {m} | 0 | {{}} | N/A | N/A | N/A |")
    lines.extend(["", "## 全部选择记录", "", "| 流 | 任务 | 未来 | 方法 | 实际分支 | 选择证据摘要 |", "|---:|---|---:|---|---|---|"])
    for row in audit["choices"]:
        lines.append(f"| {row['stream']} | {row['task']} | {row['replicate']} | {row['method']} | {row['selected_branch']} | {row['selection'].get('evidence_sha256','仅任务标签／初始时刻') if row['selection'] else '无需选择或无有效参考'} |")
    groups=defaultdict(list)
    for r in summary["cases"]:
        for group in (f"task:{r['task']}",f"stream:{r['stream']}",f"future:{r['replicate']}"): groups[(r["method"],group)].append(r)
    lines.extend(["", "## 全部分层", "", "| 方法 | 分层 | 成功 / 分母 | 平均损失 |", "|---|---|---|---:|"])
    for (m,g),part in sorted(groups.items()): lines.append(f"| {m} | {g} | {sum(r['success'] for r in part)} / {len(part)} | {np.mean([r['deadline_loss'] for r in part]):.4f} |")
    lines.extend(["", "## 全部失败和停止", "", "| 方法 | 流 | 任务 | 未来 | 种子 | 停止 | 实际步 |", "|---|---:|---|---:|---:|---|---:|"])
    for r in summary["cases"]:
        if not r["success"]: lines.append(f"| {r['method']} | {r['stream']} | {r['task']} | {r['replicate']} | {r['seed']} | {r['stopped']} | {r['total_steps']} |")
    counts=audit["lifecycle"]["counts"]
    lines.extend(["", "## 所有来源和实际费用", "",
                  f"新 1,152 次执行消耗 {audit['controlled_steps']:,} 环境步／1,152 控制初始重置；工厂和控制合计 "
                  f"{counts['reset_completed']:,} 次顶层重置／{counts['simulation_frames_completed']:,} 个完成的请求帧。", "",
                  "六个原名义方法各承担完整 21,010 步／288 控制重置。五个监督选择基准另各承担完整训练源 101,069 步／672 控制重置。"
                  "按每方法 96 单元摊销已列入表中，两个来源的物理采集各只计一次。少量在线节省不能冒充本批总费用减少。", "",
                  f"审计检查 {audit['events_checked']:,} 条事件、{audit['frozen_git_inputs_checked']} 个冻结输入、24 个训练上下文及 "
                  f"{audit['training_ridge_equations_checked']} 个核方程输出，并核对 864 对跨方法和 576 对跨未来前缀。"
                  "训练投影和选择重建，固定分支保存动作核对、Gaussian／点估计数学和部分配对函数明确复用；噪声独立重建。"
                  "不进行动力学重仿真，也没有完整隐藏状态或物理／概率资格。", "",
                  "12600–12647 已执行；12648–12999 与全部旧保留范围不动。API、自然经验记忆写入和固定政策权重更新均为零。"
                  "即使开发信号有利，也仍需新颖机制、更广独立评价和完整论文；若失败，保留本轮，不在该人口调参或补跑。", ""])
    return "\n".join(lines)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--audit",type=Path,required=True); parser.add_argument("--report-path",type=Path,required=True)
    args=parser.parse_args(); destination=args.report_path.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents: raise FileExistsError("new report required")
    text=report(args.manifest.resolve(),args.audit.resolve(),destination); destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(text.encode("utf-8"))
    print(json.dumps({"report_path":str(destination),"sha256":run.digest(destination)}))
