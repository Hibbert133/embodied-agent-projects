"""Chinese complete fixed-prefix measurement report; no online-lookup claim."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_conditional_continuation as run


def report(manifest_path,audit_path,destination):
    manifest=run.load(manifest_path); audit=json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["integrity"]!="PASSED" or audit["episodes"]!=672 or any(manifest[k]!=audit[k] for k in run.IDENTITY):
        raise ValueError("matching complete conditional audit required")
    if any(run.digest(manifest_path.parent/n)!=h for n,h in audit["artifact_sha256"].items()): raise ValueError("audited bytes changed")
    summary=json.loads((manifest_path.parent/"summary.json").read_text(encoding="utf-8")); stats=audit["statistics"]; lookup=stats["lookup"]
    def link(path): return Path(os.path.relpath(path,destination.parent)).as_posix()
    primary=lookup["contrast_minus_direct"]["deadline_loss"]
    low,high=primary["paired_cluster_percentile_95"]
    lines=["# 固定八步前缀后的继续策略：完整中文测量", "",
           "本轮不是新在线 Agent 的成功率实验。七个固定分支各自真实执行，评价器随后用同一前缀的其他三个未来结果形成查询表，"
           "只在留出未来上评价所选分支。该查询表不可部署，也不是真正条件最优策略的上界。", "",
           f"24 个名义前缀上下文／四未来实现，96 单元、672 次实际执行；主查询表减 DIRECT_G8 的平均截止损失差 "
           f"{primary['difference']:.4f}，算子流分层配对 95% 区间 [{low:.4f}, {high:.4f}]。"
           "有利结果不证明新颖性或在线收益；无收益也不能证明条件最优策略不存在。", "",
           f"运行 `{audit['experiment_run_id']}`；冻结源 `{audit['source_git_commit']}`；清单 `{audit['manifest_id']}`。"
           "12200–12223 实际执行；12224–12599 和全部旧保留范围未动。", "",
           f"[冻结协议]({link(ROOT/'docs/protocols/conditional_continuation_development_v1.md')}) · "
           f"[问题与既有实验区别]({link(ROOT/'docs/research/conditional_continuation_question_v1.md')}) · "
           f"[执行审计]({link(audit_path)}) · [清单和原始轨迹]({link(manifest_path)})", "",
           "## 全部固定方法", "", "成功取实际总步；失败／停止截止损失取 500，始终保留完整分母。", "",
           "| 方法 | 成功 / 96 | 停止 | 平均在线步 | 平均专门探测步 | 平均政策观测块步 | 平均截止损失 | 含完整名义来源平均步 |",
           "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for m,r in stats["methods"].items():
        lines.append(f"| {m} | {r['successes']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_probe_steps']:.4f} | {r['mean_policy_measure_steps']:.4f} | {r['mean_deadline_loss']:.4f} | {r['mean_amortized_steps']:.4f} |")
    lines.extend(["", "DIRECT_G8 为八步后直接控制；KEEP 额外探测后仍保留第八步纠正器；UPDATE 使用十六步数据。"
                  "PASSIVE 用八步真实任务政策产生自然观测再更新，这些步是任务预算内的政策步，不能重复算成专门探测或免费交互。"
                  "POINT16_CYCLE 是两次宽八，POINT16_WIDE 是四方向各四步；后者与 NO_PROBE 不属于同八步后的可行决策组合。", "",
                  "六个名义方法各完整承担旧 21,010 步／288 次控制重置，按 96 单元摊销 218.8542 步／3 次重置；物理源只计一次。"
                  "旧来源内部初始化没有在本轮重新测量。Gaussian 参考、经验 RMS 与局部模型均没有物理／概率／安全资格。", "",
                  "## 固定前缀核查", "", "| 指标 | 结果 |", "|---|---:|"])
    for k,v in stats["prefix_checks"].items(): lines.append(f"| {k} | {v} |")
    lines.extend(["", "独立环境真实重新执行初始八步；只有一次控制初始重置，没有状态复制、恢复或轨迹内重播种。"
                  "所有噪声在交互前生成，日志的哈希只表示已消费噪声历史；未来噪声承诺是评价器字段，不进拟合。"
                  "匹配可见前缀和声明见证，不证明所有相同观测隐状态的分布相同。", "",
                  "## 评价器跨未来查询表", "", "该表依赖同一前缀的反事实训练结果，所有真实分支在分析之前已执行。"
                  "纯选择函数只接收其他三个未来的损失；这不是物理执行前的 Agent 决策或自然在线经验。", "",
                  "| 指标 | 值 |", "|---|---|"])
    for k in ("cases","decision_required_cases","successes","mean_steps","mean_deadline_loss","mean_probe_steps","selected_counts","operator_streams","strata_streams","new_online_lookup_executions"):
        lines.append(f"| {k} | {lookup[k]} |")
    lines.extend(["", "| 查询表减 DIRECT_G8 | 点差 | 算子流分层配对 95% 区间 |", "|---|---:|---|"])
    for name,r in lookup["contrast_minus_direct"].items(): lines.append(f"| {name} | {r['difference']:.4f} | {r['paired_cluster_percentile_95']} |")
    lines.extend(["", "独立单位为八个算子流，在反射／非反射各四流中重采样。查询表训练与留出重复的依赖都保留在流内；"
                  "不能把 96 单元当成独立算子，也不能从四未来样本给出逐状态分布保证。", "",
                  "## 全部条件前缀与四未来损失", "", "范围是四次实际结果的范围，不是置信区间。", "",
                  "| 流 | 任务 | 需要继续决策 | 方法 | 四未来截止损失 | 均值 | 比直接八步均值差 | 成功 / 4 |",
                  "|---:|---|---|---|---|---:|---:|---|"])
    for context in stats["conditional_contexts"]:
        for method,r in context["methods"].items():
            lines.append(f"| {context['stream']} | {context['task']} | {context['decision_required']} | {method} | {r['four_losses']} | {r['mean_loss']:.4f} | {r['mean_loss_minus_direct']:.4f} | {r['successes']} |")
    lines.extend(["", "## 全部留出查询选择", "", "| 流 | 任务 | 留出未来 | 训练未来 | 选择 | 选中分支留出损失 | 比直接八步损失差 |", "|---:|---|---:|---|---|---:|---:|"])
    for r in stats["lookup_decisions"]:
        lines.append(f"| {r['stream']} | {r['task']} | {r['held_out_future']} | {r['training_futures']} | {r['selected_branch']} | {r['selected_deadline_loss']} | {r['loss_minus_direct']} |")
    groups=defaultdict(list)
    for r in summary["cases"]:
        for label in (f"task:{r['task']}",f"stream:{r['stream']}",f"future:{r['replicate']}"): groups[(r["method"],label)].append(r)
    lines.extend(["", "## 全部分层", "", "| 方法 | 分层 | 成功 / 分母 | 停止 | 平均损失 |", "|---|---|---|---:|---:|"])
    for (m,label),part in sorted(groups.items()): lines.append(f"| {m} | {label} | {sum(r['success'] for r in part)} / {len(part)} | {sum(r['stopped'] for r in part)} | {sum(r['deadline_loss'] for r in part)/len(part):.4f} |")
    lines.extend(["", "## 全部失败／停止", "", "| 方法 | 流 | 任务 | 未来 | 种子 | 停止 | 实际步 |", "|---|---:|---|---:|---:|---|---:|"])
    for r in summary["cases"]:
        if not r["success"]: lines.append(f"| {r['method']} | {r['stream']} | {r['task']} | {r['replicate']} | {r['seed']} | {r['stopped']} | {r['total_steps']} |")
    counts=audit["lifecycle"]["counts"]
    lines.extend(["", "## 全部真实研究费用", "",
                  f"672 次真实执行共 {audit['controlled_steps']:,} 个 Env.step／672 次控制初始重置；"
                  f"顶层重置 {counts['reset_completed']:,}，完成 do_simulation 请求帧 {counts['simulation_frames_completed']:,}。", "",
                  "| 阶段 | 完成重置 | 完成模拟调用 | 完成请求帧 |", "|---|---:|---:|---:|"])
    for name,r in audit["lifecycle"]["by_phase"].items(): lines.append(f"| {name} | {r.get('reset_completed',0)} | {r.get('simulation_completed',0)} | {r.get('simulation_frames_completed',0)} |")
    lines.extend(["", f"查询表依赖的五分支源实际消耗 {lookup['portfolio_required_source_steps']:,} 个控制步；整批对照人口费用仍完整披露。"
                  "所选分支统计没有新增物理执行，不能当作部署中的真实成本节省。"
                  "每控制步五帧／0.0125 秒；请求帧不是全部 C 引擎计算或真实机器人费用。", "",
                  "审计独立重建噪声、逐步政策／程序与保存控制器；前缀配对、Gaussian／点拟合及查询表统计公式明确复用。"
                  "没有动力学重仿真或完整隐状态资格。API、自然经验记忆写入和底层政策权重更新为零。", "",
                  "单次赢家反转、查询表收益和真正条件最优策略是不同问题。三训练未来可能不足以估计期望代价；"
                  "无收益不证明不存在可学习条件策略，有收益也不证明当前有可部署方法。新颖性、强方法竞争、独立在线确认与完整论文仍未完成。", ""])
    return "\n".join(lines)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--audit",type=Path,required=True); parser.add_argument("--report-path",type=Path,required=True)
    args=parser.parse_args(); destination=args.report_path.resolve()
    if destination.exists() or args.manifest.resolve().parent in destination.parents: raise FileExistsError("new external report required")
    text=report(args.manifest.resolve(),args.audit.resolve(),destination); destination.parent.mkdir(parents=True,exist_ok=True); destination.write_bytes(text.encode("utf-8"))
    print(json.dumps({"report_path":str(destination),"report_sha256":run.digest(destination)}))
