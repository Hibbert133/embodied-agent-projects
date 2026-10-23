"""Chinese report with independent raw trace cost and outcome aggregation."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IDENTITY=("experiment_run_id","manifest_id","source_git_commit")


def read(path):return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    h=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()


def case(record):
    trace=record["trace"];o=record["outcome"]
    if len(trace)>500 or [r["host_calls"] for r in trace]!=list(range(1,len(trace)+1)):raise ValueError("raw chronology/budget differs")
    allowed=("PREFIX_POLICY","MICRO_PROBE","FIXED_PROBE","POLICY")
    if any(r["phase"] not in allowed for r in trace):raise ValueError("unknown physical phase")
    phases=Counter(r["phase"] for r in trace)
    success=trace[-1]["after"]["success"] if trace else record["initial"]["success"] if record["initial"] else False
    stopped=record["decisions"][-1]["controller"] is None
    result={"success":success,"stopped":stopped,"total_steps":len(trace),"deadline_loss":len(trace) if success else 500,
            "prefix_steps":phases["PREFIX_POLICY"],"micro_steps":phases["MICRO_PROBE"],"fixed_probe_steps":phases["FIXED_PROBE"],"policy_steps":phases["POLICY"],
            "point_fit_failures":sum(d.get("fit") is not None and not d["fit"]["valid"] for d in record["decisions"])}
    if type(success) is not bool or any(o[k]!=v for k,v in result.items()):raise ValueError("saved outcome/cost substitution")
    return {**{k:record[k] for k in ("stream","task","scenario","replicate","seed","method")},**result}


def aggregate(manifest,audit_path):
    m,a=read(manifest),read(audit_path)
    if a.get("integrity")!="PASSED" or a.get("episodes")!=2304 or a.get("cold_sources")!=24:
        raise ValueError("completed full audit required")
    if any(m[k]!=a[k] for k in IDENTITY):raise ValueError("foreign audit")
    for name,h in a["artifact_sha256"].items():
        if sha(manifest.parent/name)!=h:raise ValueError("audited bytes changed")
    rows=[];cold=[]
    for s in range(8):
        with gzip.open(manifest.parent/f"episodes_{s:02}.jsonl.gz","rt",encoding="utf-8") as f:
            for line in f:
                r=json.loads(line)
                if any(r[k]!=m[k] for k in IDENTITY):raise ValueError("foreign raw case")
                rows.append(case(r))
    with gzip.open(manifest.parent/"cold_sources.jsonl.gz","rt",encoding="utf-8") as f:
        for line in f:cold.append(case(json.loads(line)))
    c=m["config"];keys=("stream","task","scenario","replicate","method")
    expected={(s,t,z,v,p) for s in range(8) for t in c["tasks"] for z in c["scenarios"] for v in range(4) for p in c["methods"]}
    if len(rows)!=2304 or {tuple(r[k] for k in keys) for r in rows}!=expected or len(cold)!=24:raise ValueError("complete registered population differs")
    independent={}
    for method in c["methods"]:
        part=[r for r in rows if r["method"]==method];n=len(part)
        totals={"cases":n,"successes":sum(r["success"] for r in part),"stops":sum(r["stopped"] for r in part),
                "total_steps":sum(r["total_steps"] for r in part),"mean_steps":sum(r["total_steps"] for r in part)/n,
                "mean_deadline_loss":sum(r["deadline_loss"] for r in part)/n,
                "mean_probe_steps":sum(r["micro_steps"]+r["fixed_probe_steps"] for r in part)/n,
                "point_fit_failures":sum(r["point_fit_failures"] for r in part)}
        registered=a["statistics"]["methods"][method]
        if any(registered[k]!=v for k,v in totals.items()):raise ValueError("independent method arithmetic differs")
        independent[method]=totals
    cold_steps=sum(r["total_steps"] for r in cold)
    if sum(r["total_steps"] for r in rows)+cold_steps!=a["controlled_steps"]:raise ValueError("complete control cost differs")
    return {**{k:m[k] for k in IDENTITY},"primary_audit_sha256":sha(audit_path),"report_source_sha256":sha(Path(__file__)),
            "methods":independent,"failed_cases":[r for r in rows if not r["success"]],"cold_source_steps":cold_steps,
            "new_controlled_steps":a["controlled_steps"],"new_controlled_resets":a["controlled_resets"],
            "lifecycle":a["lifecycle"],"statistics":a["statistics"],"new_api_calls":0,
            "scope":"Independent raw trace phase, success, stop and point totals. Primary audit lifecycle, repeat and matched update contrast summaries explicitly reused; no new robot simulation or fitted selector."}


def markdown(result,manifest,audit_path,report_path,figure_dir=None):
    def link(p):return Path(os.path.relpath(p,report_path.parent)).as_posix()
    stats=result["statistics"];gate=stats["repeat_gate"];counts=result["lifecycle"]["counts"]
    lines=["# 同状态强探测、保留控制与任务收益：中文完整结果","",
           f"本轮收集并审计 2,304 次方法案例与 24 次冷源。主端点 MID16_WIDE 对 CACHE_CONTINUE 的冻结重复性门{'通过' if gate['passed'] else '未通过'}。"
           "最强固定基线 EARLY16_WIDE 成功 191/192，主候选 MID16_WIDE 为 181/192；固定基线的平均在线步和截止损失也更低。"
           "这是名义上下文上的目标测量；四重复的前缀可能不同，尚不构成固定状态收益分布、部署选择器或 CCF A 新方法证据。","",
           f"本轮新增 API 调用为零。此前的[在线 GLM-5.2 闭环报告]({link(ROOT/'reports/online_calibrated_agent_development_v1.md')})"
           "记录了真实 API 选择与执行：LLM 为 14/16，仿射和最近邻均为 16/16。当前研究结果不能算作新的 API 收益证据。","",
           f"运行 `{result['experiment_run_id']}`；清单 `{result['manifest_id']}`；冻结源 `{result['source_git_commit']}`。新任务种子 11200–11247，11248–11499 保留。","",
           "原冻结审计器因硬编码错误的模拟时钟单位未通过；读取绑定 XML 的 v2 重放完全部案例后，因冷源列表与整数同名字段的核对错误未通过。"
           "当前通过的是另存的只读 v3 审计，原轨迹、失败日志、配置、方法和阈值均保留。原冻结审计通过与事后修正审计通过不同。","",
           f"[时间单位修复说明]({link(ROOT/'docs/research/acquisition_clock_audit_repair_v2.md')}) · "
           f"[末尾汇总格式修复说明]({link(ROOT/'docs/research/acquisition_terminal_schema_audit_v3.md')})","",
           f"[冻结协议]({link(ROOT/'docs/protocols/postprefix_probe_value_development_v1.md')}) · [独立执行审计]({link(audit_path)}) · "
           f"[原始清单与分流轨迹]({link(manifest)})","",
           "## 全部方法与任务截止损失","",
           "每方法分母 192，包括无效来源、拟合停止与全部失败。deadline_loss 在成功时用真实总步，失败或停止为 500；实际物理步另外报告。"
           "旧源控制固定，不吸收别的方法、当前结局或未来案例。","",
           "| 方法 | 成功 / 192 | 停止 | 平均在线步 | 平均探测步 | 平均截止损失 | 平均含来源步 | 无效拟合 |","|---|---:|---:|---:|---:|---:|---:|---:|"]
    if figure_dir is not None:
        position=lines.index("## 全部方法与任务截止损失")
        lines[position:position]=[f"![完整任务、费用与更新作用]({link(figure_dir/'figure.png')})",""]
    for method,r in stats["methods"].items():
        lines.append(f"| {method} | {r['successes']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_probe_steps']:.4f} | {r['mean_deadline_loss']:.4f} | {r['mean_amortized_steps']:.4f} | {r['point_fit_failures']} |")
    lines.extend(["","每个使用名义模型的方法完整承担旧 21,010 登记控制步／288 控制重置，按 192 单元摊销。需要旧缓存的方法另承担本轮完整冷源费用 "
                  f"{result['cold_source_steps']} 步／24 控制重置。EARLY 宽探测不使用旧缓存；NO_PROBE 无名义模型来源费用。来源物理上分别只采集一次。","",
                  "## 主重复性端点","",
                  "| 指标 | 结果 |","|---|---:|"])
    for key in ("contexts","fully_matched_contexts","non_tie_contexts","sign_reversal_contexts","sign_reversal_fraction",
                "leave_one_out_checked","leave_one_out_correct","leave_one_out_abstained","leave_one_out_agreement","leave_one_out_coverage","passed"):
        lines.append(f"| {key} | {gate[key]} |")
    lines.extend(["","每上下文四个改善／恶化／平局符号；其余三重复的非零和预测当前非零方向，和为零则弃权。"
                  "预测覆盖和一致率同时要求 75%，非平局上下文至少 24，方向反转占比最多 25%。未按结果换主方法、权重或阈值。","",
                  "| 流 | 任务 | 情景 | 四符号 | 配对完整 | 反转 | LOOR 正确 / 已预测 |","|---:|---|---|---|---|---|---|"])
    for r in stats["primary_contexts"]:
        lines.append(f"| {r['stream']} | {r['task']} | {r['scenario']} | {r['signs']} | {r['complete']} | {r.get('sign_reversal','不可评')} | "
                     f"{r.get('leave_one_out_correct','不可评')} / {r.get('leave_one_out_checked','不可评')} |")
    lines.extend(["","## 相同探测后的更新作用","",
                  "KEEP 分支在同样六步与同样宽探测之后，预先继续旧控制。更新分支在同一观测、积分状态见证和 RNG 后使用新估计或停止。"
                  "这衡量实际更新策略的作用，包含估计拒绝风险；不把它命名为纯信息价值。探测中已结束者单列，不是更新决策成功。","",
                  "| 探测 | 可评更新决策 | 更新 / KEEP 成功 | 更新 / KEEP 停止 | 更新减 KEEP 截止损失 | KEEP 减继续旧控制 | 总差 |","|---|---:|---|---|---:|---:|---:|"])
    def show(x):return "不可评" if x is None else f"{x:.4f}"
    for method,r in stats["post_probe_update_contrasts"].items():
        lines.append(f"| {method} | {r['update_decisions']} | {r['updated_successes']} / {r['kept_successes']} | {r['updated_stops']} / {r['kept_stops']} | "
                     f"{show(r['mean_update_loss_difference'])} | {show(r['mean_probe_motion_loss_difference'])} | {show(r['mean_total_loss_difference'])} |")
    lines.append("")
    for method,r in stats["post_probe_update_contrasts"].items():
        lines.extend([f"{method} 全部配对原因：`{json.dumps(r['reasons'],ensure_ascii=False)}`。",""])
    lines.extend(["损失差是三条真实分支的代数差；其可加性不等于新定理。没有虚拟拟合失败回退，也没有把一条记录的观察喂给替代动作来伪造动力学。","",
                  "## 完整仿真初始化费用","",
                  f"新增登记控制 {result['new_controlled_steps']:,} 次 Env.step／{result['new_controlled_resets']:,} 次控制初始重置；"
                  f"实测顶层重置入口 {counts['reset_completed']:,}，完成 do_simulation 请求帧 {counts['simulation_frames_completed']:,}。"
                  "重置模型内安置帧与控制步分开计数；目标工厂在临时环境中生成五十个目标，不属于当前在线控制轨迹的重置。","",
                  "| 生命周期阶段 | 完成重置 | 完成模拟调用 | 完成模拟帧 |","|---|---:|---:|---:|"])
    for phase,r in result["lifecycle"]["by_phase"].items():
        lines.append(f"| {phase} | {r.get('reset_completed',0)} | {r.get('simulation_completed',0)} | {r.get('simulation_frames_completed',0)} |")
    lines.extend(["","该账本测量 Python 入口上的 reset 和 do_simulation 请求，不是所有 C 引擎计算、渲染或真实机器人费用。"
                  "旧名义来源的内部初始化仍属于历史条件推算；本轮仪器不修改其数据。API 调用和自然经验记忆写入均为零。","",
                  "## 完整任务、情景、流和重复分层","",
                  "| 方法／分层 | 成功 / 分母 | 停止 | 平均在线步 | 平均截止损失 |","|---|---|---:|---:|---:|"])
    for method,groups in stats["strata"].items():
        for group,cells in groups.items():
            for label,r in cells.items():
                lines.append(f"| {method}/{group}/{label} | {r['successes']} / {r['cases']} | {r['stops']} | {r['mean_steps']:.4f} | {r['mean_deadline_loss']:.4f} |")
    lines.extend(["","## 全部失败和停止案例","",
                  "| 方法 | 流 | 任务 | 情景 | 重复 | 种子 | 停止 | 实际步 | 截止损失 | 无效拟合 |","|---|---:|---|---|---:|---:|---|---:|---:|---:|"])
    for r in result["failed_cases"]:
        lines.append(f"| {r['method']} | {r['stream']} | {r['task']} | {r['scenario']} | {r['replicate']} | {r['seed']} | {r['stopped']} | "
                     f"{r['total_steps']} | {r['deadline_loss']} | {r['point_fit_failures']} |")
    lines.extend(["","本轮没有训练效用预测器或提出已确认的新采集算法。审计重放注册的求解器和数学判断，并独立核对执行、注入／RNG和费用；"
                  "没有重新仿真，也没有完整隐状态、概率或安全资格。重复性门和任务胜负分别解读，强固定基线获胜及负结果必须保留。","",
                  "后继方法需要在新冻结范围上检验任务收益估计及探测后的更新选择，并接受强固定、保留控制和标准任务相关方法的对照。"
                  "本文档是中文实验结果，不是已达 CCF A 投稿水平的算法创新证明。",""])
    return "\n".join(lines).rstrip("\n")+"\n"


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","audit","output","report_path"):p.add_argument("--"+name.replace("_","-"),type=Path,required=True)
    p.add_argument("--figure-dir",type=Path)
    args=p.parse_args();output=args.output.resolve();report=args.report_path.resolve();manifest=args.manifest.resolve()
    if output.exists() or report.exists() or manifest.parent in output.parents or manifest.parent in report.parents:raise FileExistsError("new external report required")
    figure_dir=args.figure_dir.resolve() if args.figure_dir else None
    if figure_dir is not None:
        meta=read(figure_dir/"figure.json")
        if meta["primary_audit_sha256"]!=sha(args.audit.resolve()) or meta["png_sha256"]!=sha(figure_dir/"figure.png"):
            raise ValueError("figure/audit binding differs")
    result=aggregate(manifest,args.audit.resolve());text=markdown(result,manifest,args.audit.resolve(),report,figure_dir)
    if figure_dir is not None:
        result["figure"]={"metadata_path":str(figure_dir/"figure.json"),"metadata_sha256":sha(figure_dir/"figure.json"),"png_sha256":meta["png_sha256"]}
    output.mkdir(parents=True,exist_ok=False);report.parent.mkdir(parents=True,exist_ok=True);report.write_bytes(text.encode("utf-8"))
    result["report_sha256"]=sha(report)
    (output/"metrics.json").write_bytes((json.dumps(result,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    print(json.dumps({"failed_cases":len(result['failed_cases']),"controlled_steps":result['new_controlled_steps'],"repeat_gate":result['statistics']['repeat_gate']}))
