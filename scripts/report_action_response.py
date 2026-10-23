"""Chinese results and independent trace-cost aggregation after the full audit.

No planner, estimator, environment, registered summarizer or API is invoked.
Bootstrap intervals are explicitly taken from the completed primary audit;
population, point metrics and phase costs are recomputed from immutable records.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
METHODS=("NO_PROBE","FIXED8","FIXED16","FIXED8_WIDE","FIXED16_WIDE","CACHE_ONLY","PERIODIC2","PERIODIC3",
         "RECENT_WINDOW","RESIDUAL_CUSUM","G_OPTIMAL","RESPONSE_SET","RESPONSE_POINT","RESPONSE_GEOMETRY","RESPONSE_NO_COST","ORACLE16")
TASKS=("push-v3","reach-v3","door-open-v3")
SCENARIOS=("STATIONARY","MIXED")
PHASES=("PREFIX_POLICY","MICRO_PROBE","FIXED_PROBE","POLICY")
IDENTITY=("experiment_run_id","manifest_id","source_git_commit")
ASSESSMENT_STATUSES=("COMPATIBLE","INCOMPATIBLE","UNRESOLVED","CONTRACT_REJECTED","NUMERICAL_FAILURE")


def sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def load(path):return json.loads(path.read_text(encoding="utf-8"))


def validation_summary(record):
    choices=[d for d in record["decisions"] if isinstance(d.get("validation"),dict) and "assessment" in d["validation"]]
    if not choices:return None
    statuses=[d["validation"]["assessment"]["status"] for d in choices]
    if any(status not in ASSESSMENT_STATUSES for status in statuses):raise ValueError("unknown registered response assessment")
    return {"first_status":statuses[0],"final_status":statuses[-1],"assessment_calls":len(statuses),
        "all_status_counts":dict(Counter(statuses)),"final_validation_action":choices[-1]["action"],
        "micro_program_counts":dict(Counter(d["validation"]["program_id"] for d in choices if d["action"]=="REQUEST_MICRO_PROBE"))}


def cost_ablation_issue(record):
    if record["method"]!="RESPONSE_NO_COST":return None
    validation=validation_summary(record)
    if validation is None or validation["final_validation_action"] not in ("REFRESH_FIXED16","REFRESH_NUMERICAL_DESIGN"):return None
    first_fixed=next((i for i,r in enumerate(record["trace"]) if r["phase"]=="FIXED_PROBE"),None)
    if first_fixed is None:return None
    micro=sum(r["phase"]=="MICRO_PROBE" for r in record["trace"][:first_fixed])
    if micro>=16:return None
    return {**{k:record[k] for k in ("episode_index","stream","task","scenario","episode_in_stream","seed")},
        "registered_micro_steps_before_refresh":16,"actual_micro_steps_before_refresh":micro,"micro_step_shortfall":16-micro,
        "final_validation_action":validation["final_validation_action"],"final_assessment_status":validation["final_status"],
        "issue":"Cost ablation refreshed before its declared full micro-probe budget; execution replay does not certify this semantic requirement."}


def case_metrics(record):
    trace=record["trace"];outcome=record["outcome"]
    if len(trace)>500 or [r["host_calls"] for r in trace]!=list(range(1,len(trace)+1)):
        raise ValueError("trace budget or chronological count differs")
    if any(r["phase"] not in PHASES for r in trace):raise ValueError("unregistered physical phase")
    phase=Counter(r["phase"] for r in trace)
    result={"total_steps":len(trace),"prefix_steps":phase["PREFIX_POLICY"],"micro_steps":phase["MICRO_PROBE"],
            "fixed_probe_steps":phase["FIXED_PROBE"],"policy_steps":phase["POLICY"]}
    if any(outcome[k]!=v for k,v in result.items()):raise ValueError("outcome substituted trace cost")
    final=trace[-1]["after"] if trace else record["initial"]
    if type(final["success"]) is not bool or outcome["success"]!=final["success"]:raise ValueError("final success differs")
    if outcome["environment_resets"]!=1 or outcome["actuator_resets"]!=1:raise ValueError("audited initial resets differ")
    stopped=record["decisions"][-1]["controller"] is None
    failures=sum(d.get("fit") is not None and not d["fit"]["valid"] for d in record["decisions"])
    updates=record["cache_version_after"]-record["cache_version_before"]
    if outcome["stopped"]!=stopped or outcome["point_fit_failures"]!=failures or outcome["cache_updates"]!=updates:
        raise ValueError("stop, fit or cache count differs")
    result.update(success=final["success"],stopped=stopped,point_fit_failures=failures,cache_updates=updates)
    return result


def matching_audit(manifest,audit):
    if audit.get("integrity")!="PASSED" or audit.get("episodes")!=4608 or audit.get("environment_resets")!=4608:
        raise ValueError("completed full primary audit required")
    if audit.get("status") not in ("COMPLETED_COMPETITIVE_PASS","COMPLETED_COMPETITIVE_FAILED"):
        raise ValueError("terminal competitive audit required")
    if audit.get("api_calls")!=0 or audit.get("memory_writes")!=0:raise ValueError("registered zero API/memory costs required")
    if any(audit[k]!=manifest[k] for k in IDENTITY):raise ValueError("audit identity differs")


def aggregate(manifest,audit_path):
    m=load(manifest);a=load(audit_path);matching_audit(m,a)
    for name,expected in a["artifact_sha256"].items():
        if sha(manifest.parent/name)!=expected:raise ValueError("audited raw bytes changed")
    for name,expected in m["input_sha256"].items():
        if sha(ROOT/name)!=expected:raise ValueError("frozen input bytes changed")
    source=ROOT/m["config"]["forward_audit_path"];old=load(source)
    if old["integrity"]!="PASSED" or (old["physical_steps"],old["environment_resets"])!=(21010,288):
        raise ValueError("complete prior source costs required")
    rows=[];seen=set()
    for method in METHODS:
        with gzip.open(manifest.parent/("episodes_"+method+".jsonl.gz"),"rt",encoding="utf-8") as handle:
            for line in handle:
                record=json.loads(line);metrics=case_metrics(record)
                if record["method"]!=method or any(record[k]!=m[k] for k in IDENTITY):raise ValueError("foreign method record")
                key=tuple(record[k] for k in ("stream","task","scenario","episode_in_stream","method"))
                if key in seen:raise ValueError("duplicate case")
                seen.add(key)
                row={k:record[k] for k in ("stream","task","scenario","episode_in_stream","method","seed","operator_id_oracle")}
                row.update(metrics,family_oracle=m["operators_oracle"][record["stream"]]["family_oracle"],
                           reused_cache=record["outcome"]["reused_cache"],final_action=record["outcome"]["final_action"],
                           response_validation=validation_summary(record),cost_ablation_issue=cost_ablation_issue(record))
                rows.append(row)
    expected={(s,t,c,e,p) for s in range(8) for t in TASKS for c in SCENARIOS for e in range(6) for p in METHODS}
    if seen!=expected or len(rows)!=4608:raise ValueError("complete registered population required")
    methods={};families=sorted({r["family_oracle"] for r in rows});strata={};positions={};phase_totals={};validations={}
    for method in METHODS:
        selected=[r for r in rows if r["method"]==method];n=len(selected)
        offline=0 if method in ("NO_PROBE","ORACLE16") else old["physical_steps"]
        resets=0 if not offline else old["environment_resets"]
        online=sum(r["total_steps"] for r in selected)
        methods[method]={"successes":sum(r["success"] for r in selected),"denominator":n,"stops":sum(r["stopped"] for r in selected),
            "mean_online_steps":online/n,"mean_probe_steps":sum(r["micro_steps"]+r["fixed_probe_steps"] for r in selected)/n,
            "reused_cases":sum(r["reused_cache"] for r in selected),"point_fit_failures":sum(r["point_fit_failures"] for r in selected),
            "cache_updates":sum(r["cache_updates"] for r in selected),"offline_steps":offline,"offline_resets":resets,
            "mean_amortized_steps":online/n+offline/n,
            "success_by_task":{t:sum(r["success"] for r in selected if r["task"]==t) for t in TASKS},
            "success_by_scenario":{c:sum(r["success"] for r in selected if r["scenario"]==c) for c in SCENARIOS}}
        for key,value in methods[method].items():
            registered=a["statistics"]["methods"][method][key]
            if isinstance(value,float):
                if not math.isclose(value,registered,abs_tol=1e-12,rel_tol=1e-12):raise ValueError("independent mean differs")
            elif value!=registered:raise ValueError("independent point statistics differ")
        def cell(cases):return {"successes":sum(r["success"] for r in cases),"denominator":len(cases),"stops":sum(r["stopped"] for r in cases)}
        strata[method]={"task_scenario":{t+"/"+c:cell([r for r in selected if r["task"]==t and r["scenario"]==c]) for t in TASKS for c in SCENARIOS},
                        "family_oracle":{f:cell([r for r in selected if r["family_oracle"]==f]) for f in families}}
        positions[method]=[cell([r for r in selected if r["episode_in_stream"]==e]) for e in range(6)]
        phase_totals[method]={k:sum(r[k] for r in selected) for k in ("prefix_steps","micro_steps","fixed_probe_steps","policy_steps")}
        assessed=[r["response_validation"] for r in selected if r["response_validation"] is not None]
        if assessed:
            all_status=Counter();programs=Counter()
            for item in assessed:all_status.update(item["all_status_counts"]);programs.update(item["micro_program_counts"])
            validations[method]={"cases_with_assessment":len(assessed),"assessment_calls":sum(r["assessment_calls"] for r in assessed),
                "first_status_counts":dict(Counter(r["first_status"] for r in assessed)),
                "final_status_counts":dict(Counter(r["final_status"] for r in assessed)),"all_status_counts":dict(all_status),
                "final_validation_action_counts":dict(Counter(r["final_validation_action"] for r in assessed)),"micro_program_counts":dict(programs)}
    total=sum(r["total_steps"] for r in rows)
    if total!=a["physical_steps"] or total>2304000:raise ValueError("aggregate physical cost differs")
    return {**{k:m[k] for k in IDENTITY},"primary_audit_sha256":sha(audit_path),"source_audit_sha256":sha(source),
        "report_source_sha256":sha(Path(__file__)),"methods":methods,"strata":strata,"episode_positions":positions,
        "phase_totals":phase_totals,"response_validation_summary":validations,"failed_cases":[r for r in rows if not r["success"]],
        "cost_ablation_semantic_issues":[r["cost_ablation_issue"] for r in rows if r["cost_ablation_issue"] is not None],"physical_steps":total,
        "environment_resets":len(rows),"prior_source_steps":old["physical_steps"],"prior_source_resets":old["environment_resets"],
        "api_calls":0,"new_environment_steps_in_analysis":0,"physical_response_qualified":False,
        "scope":"Independent trace phase/step and point-statistic aggregation; reset declarations and source costs bound to primary audits. Registered bootstrap intervals reused, not independently rederived."}


def markdown(result,audit,scope,figure_dir,report_path,setup=None):
    def link(path):return Path(os.path.relpath(path,report_path.parent)).as_posix()
    metrics=result["methods"];candidate=metrics["RESPONSE_SET"];gate=audit["statistics"]["strong_baseline_competitive_gate"]
    lines=["# 行动响应缓存验证与时变流：中文完整结果", "",
        f"本轮完整收集并审计了 4,608 次方法执行。候选 RESPONSE_SET 成功 {candidate['successes']}/288，停止 {candidate['stops']}；"
        f"注册强基线竞争门{'通过' if gate else '未通过'}。该结果只回答本冻结开发候选的任务竞争性，方法新颖性、独立确认与概率／物理资格仍未建立。", "",
        f"候选复用缓存 {candidate['reused_cases']} 次，平均在线 {candidate['mean_online_steps']:.4f} 步；宽十六步成功 "
        f"{metrics['FIXED16_WIDE']['successes']}/288，平均 {metrics['FIXED16_WIDE']['mean_online_steps']:.4f} 步；"
        f"宽八步成功 {metrics['FIXED8_WIDE']['successes']}/288，平均 {metrics['FIXED8_WIDE']['mean_online_steps']:.4f} 步。"
        "这轮没有建立候选的缓存复用与费用收益。", "",
        f"主审计通过的是已保存行为的执行重放。另有 {len(result['cost_ablation_semantic_issues'])} 个成本消融案例不符合先用满十六微步骤的行为，"
        "该消融不能作为完整去早停证据；初始化费用另作条件性推算，不将控制账本当作整个进程的全部物理工作量。", "",
        f"运行 `{result['experiment_run_id']}`；清单 `{result['manifest_id']}`；冻结源 `{result['source_git_commit']}`。", "",
        "新种子 10800–10943；10944–11199 及历史保留范围未用于本轮。固定政策与源模型没有按这些结果调参或重跑。", "",
        "## 完整方法与费用", "",
        "| 方法 | 成功 / 288 | 停止 | 平均在线步 | 平均探测步 | 平均含来源步 | 复用案例 | 无效点拟合 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for p in METHODS:
        r=metrics[p];lines.append(f"| {p} | {r['successes']} | {r['stops']} | {r['mean_online_steps']:.4f} | {r['mean_probe_steps']:.4f} | {r['mean_amortized_steps']:.4f} | {r['reused_cases']} | {r['point_fit_failures']} |")
    lines.extend(["",f"![全部方法与任务／情景]({link(figure_dir/'figure.png')})", "",
        f"本轮登记控制 {result['physical_steps']:,} 次 Env.step／{result['environment_resets']:,} 次控制环境初始重置。所有模型先验方法均承担已审计来源的登记控制费用 "
        f"{result['prior_source_steps']:,} 步／{result['prior_source_resets']} 次控制重置，按 288 单元摊销为每单元 72.9513889 步及一次来源控制重置；"
        "在线初始重置另计。NO_PROBE 和 ORACLE16 无该模型来源费用。源数据物理上只采集一次，不重复计成十四次新采集。", "",
        "平均探测步包括 MICRO_PROBE 和 FIXED_PROBE；六步政策前缀另外计入在线总步。停止留在分母，低步数不能单独当作效率改善。", "",
        "| 方法 | 前缀总步 | 微探测总步 | 固定探测总步 | 任务总步 |", "|---|---:|---:|---:|---:|"])
    for p in METHODS:lines.append("| "+p+" | "+" | ".join(str(v) for v in result["phase_totals"][p].values())+" |")
    lines.extend(["", "## 初始化与控制费用的统计范围", "",
        "上述登记计数没有覆盖 MT1 工厂在临时环境生成任务时的重置，也没有单独记录 reset_hand 的内部模拟器物理帧。"
        "它们对应原主审计的控制调用范围，不能写成整个进程的全部模拟器工作量。", ""])
    if setup is not None:
        counts=setup["counts"]
        lines.extend(["| 来源 | 登记控制重置 | 推算临时任务生成重置 | 两项合计的推算 reset 入口调用 |",
            "|---|---:|---:|---:|",
            f"| 本轮任务执行 | {counts['registered_controlled_resets']} | {counts['inferred_temporary_task_factory_resets']} | {counts['inferred_total_reset_entry_calls']} |",
            f"| 原前向来源 | {counts['registered_prior_controlled_resets']} | {counts['inferred_prior_temporary_task_factory_resets']} | {counts['inferred_prior_total_reset_entry_calls']} |", "",
            "当前安装源码和无模拟器替身核验每次工厂生成 50 个任务向量，使用另一个临时环境。上述历史总数依赖"
            "相同源工厂与版本的结构性推算，未在当时记录完整生命周期。未知内部物理帧不补作零费用；初始化活动"
            "发生在控制轨迹之前，不据此改变原衔接审计或注册 500 个控制步骤。", ""])
    else:lines.extend(["未提供初始化补充审计；整个进程初始化费用不能由本报告的登记控制表推出。", ""])
    lines.extend(["## 预注册主比较", "",
        "| RESPONSE_SET 相对基线 | 成功差（百分点） | 99% 流簇描述区间 | 平均在线步差 | 99% 描述区间 |", "|---|---:|---|---:|---|"])
    for p,r in audit["statistics"]["primary_contrasts"].items():
        lo,hi=r["stream_bootstrap_99_success"];cl,ch=r["stream_bootstrap_99_steps"]
        lines.append(f"| {p} | {100*r['success_difference']:.4f} | [{100*lo:.4f}, {100*hi:.4f}] | {r['mean_step_difference']:.4f} | [{cl:.4f}, {ch:.4f}] |")
    dominated=audit["statistics"]["dominating_admissible_baselines"]
    lines.extend(["","支配候选的可用基线："+("、".join(dominated) if dominated else "无满足注册支配条件的方法")+"。", "",
        "八个独立流簇保留其三任务、两情景、六案例和方法配对。固定 10,000 次 bootstrap 的 99% 区间来自主审计，"
        "不是本报告另行推导的置信保证，不把相关案例当独立样本，也不据开发竞争门宣布发表条件成立。", ""])
    for kind,title,columns in (("task_scenario","全部任务／情景",[t+"/"+c for t in TASKS for c in SCENARIOS]),
                               ("family_oracle","评估器故障族",sorted(result["strata"]["NO_PROBE"]["family_oracle"]))):
        lines.extend(["## "+title,"","| 方法 | "+" | ".join(columns)+" |","|---|"+"---:|"*len(columns)])
        for p in METHODS:
            cells=result["strata"][p][kind];lines.append("| "+p+" | "+" | ".join(f"{cells[c]['successes']}/{cells[c]['denominator']}" for c in columns)+" |")
        lines.append("")
    lines.extend(["故障族和算子只用于评估分层，不是代理证据。STATIONARY 与 MIXED 改变了物理任务分布，不能写成保持边际难度不变的纯耦合因果效应。", "",
        "## 时间位置与消融", "","| 方法 | 案例 0 | 案例 1 | 案例 2 | 案例 3 | 案例 4 | 案例 5 |","|---|---:|---:|---:|---:|---:|---:|"])
    for p in METHODS:lines.append("| "+p+" | "+" | ".join(f"{c['successes']}/{c['denominator']}" for c in result["episode_positions"][p])+" |")
    issues=result["cost_ablation_semantic_issues"]
    conformity=("该实现不能作为完整移除早停的消融证据；" if issues else "该项检查未发现提前刷新；")
    lines.extend(["", "RESPONSE_POINT 去区间；RESPONSE_GEOMETRY 在判断中去实测残差；RESPONSE_NO_COST 原拟去微探测早停。"
        "三者均保留在完整对照和所有分层中；任务差异不会自动证明误差模型或物理失效原因。", "",
        f"**成本消融语义检查：{len(issues)} 个已评估案例在未用满十六微探测步时开始固定刷新，累计少执行 "
        f"{sum(r['micro_step_shortfall'] for r in issues)} 个声明的微步骤。** 原数据和费用按实际执行保留，不补做或推测本应得到的结局。"
        +conformity+"主重放审计验证已保存行为与实际执行，未检验这一协议语义。"
        "主方法竞争失败的对照保持不变。明细保存在报告指标文件。", "",
        "## 为什么验证后没有复用", "",
        "| 方法 | 有响应评估的案例 | 首次兼容 | 首次超限 | 首次证据不足 | 首次模型不一致 | 首次数值失败 | 评估调用数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for p,r in result["response_validation_summary"].items():
        counts=r["first_status_counts"]
        lines.append("| "+p+" | "+str(r["cases_with_assessment"])+" | "+" | ".join(str(counts.get(s,0)) for s in ASSESSMENT_STATUSES)+" | "+str(r["assessment_calls"])+" |")
    lines.extend(["", "此表按每案例首次响应评估分类；同案例追加测量产生的多次调用单列，不能当作独立案例。冷启动或前缀已结束的案例可能没有响应评估。"
        "CONTRACT_REJECTED 表示注册局部残差模型和假设误差约束不一致，并不证明执行器改变或旧控制必然无用；"
        "INCOMPATIBLE 与 UNRESOLVED 分别表示注册查询的超限和证据不足。完整首次／末次／全部状态及微程序计数保存在报告指标文件。", "",
        "## 有限查询与隐含未来区间", "",
        "| 方法 | 复用案例 | 包外命令 / 全部后续命令 | 有包外命令的案例 | 首四步覆盖 / 可定义完整块 | 不完整／无法定义 |", "|---|---:|---:|---:|---:|---:|"])
    for p,r in scope["method_summaries"].items():
        lines.append(f"| {p} | {r['reuse_cases']} | {r['outside_listed_query_hull']}/{r['policy_queries']} | {r['cases_with_outside_queries']} | {r['future_four_step_blocks_covered']}/{r['future_four_step_blocks']} | {r['incomplete_or_undefined_reuse_blocks']} |")
    lines.extend(["", "此表覆盖保存查询图并最终复用的五种方法，标量 CUSUM 和周期复用等没有该查询图，未作相同区间比较。"
        "完整裁剪后的政策发送像不自动由五点查询覆盖。未来区间在已实现命令上用决策前设计事后重建；"
        "没有使用未来目标重新拟合，也不是当时已保存的新置信承诺。复用选择与轨迹依赖使该覆盖率仅具描述意义，数值兼容不是概率／物理认证。", "",
        "## 失败与执行审计", "",
        f"全部 {len(result['failed_cases'])} 个失败／停止案例见[完整失败清单]({link(figure_dir/'failure_cases.md')})，停止保留在每方法 288 分母。", "",
        f"主审计重放 {audit['replayed_choices']:,} 个保存选择与 {audit['replayed_step_intents']:,} 个执行意图；"
        f"核验 {audit['matched_git_inputs']} 个冻结输入。选择、实际发送命令、持续 RNG、缓存归属和费用均被核对。"
        "规划、预测、LP、点优化与注册 bootstrap 复用原实现；动作注入算术和 RNG 另行核对。它不重新仿真动力学，也不声明完全独立算法。", "",
        "本报告器另从完整轨迹统计步数／物理阶段、最终成功、停止、拟合与缓存计数，并重新计算所有方法点统计，与主审计一致。"
        "初始重置及来源费用绑定已通过的审计声明，统计独立核验不等于新的物理采集。", "",
        "## API、主机时间与论文边界", "",
        "本轮 API 调用为零。旧在线 API 阶段的 15 条实际闭环、LLM 14/16 和未保证的总输出 token 上限另见"
        f"[原中文报告]({link(ROOT/'reports/online_calibrated_agent_development_v1.md')})，不能把本轮结果当成 API／LLM 收益。", "",
        "保存观察完成到下一选择的滞后包含主机开销及并行测试等负载；没有隔离求解器起止时间，不能当作算法实时延迟。"
        "初始选择没有前一步完成时间，不在该统计中；缺失数据不记为零毫秒。", "",
        "| 方法 | 可核对滞后数 | 中位数 ms | P90 ms | 最大 ms |", "|---|---:|---:|---:|---:|"])
    for p in METHODS:
        r=scope["posttransition_decision_lags"].get(p)
        lines.append(f"| {p} | {r['observed_posttransition_decisions']} | {r['median_ms']:.4f} | {r['p90_ms']:.4f} | {r['max_ms']:.4f} |" if r else f"| {p} | 0 | 未测 | 未测 | 未测 |")
    lines.extend(["", "经验名义 RMS、相关分组均值、有限查询、局部仿射残差与点标签前瞻都有未验证条件。", "",
        f"[技术稿]({link(ROOT/'papers/action_response_development_draft_zh.md')})和[原始文献比较]({link(ROOT/'docs/research/action_response_prior_art_v1.md')})"
        "说明已有触发辨识与任务导向设计的重合范围。即使开发门通过，仍需实质贡献和新注册独立确认；若失败，保留负结果，不在当前任务上改方法重跑。", ""])
    return "\n".join(lines)


def report(manifest,audit_path,scope_path,figure_dir,output,report_path,setup_path=None):
    if output.exists() or report_path.exists() or output==manifest.parent or manifest.parent in output.parents or manifest.parent in report_path.parents:
        raise FileExistsError("new external report artifacts required")
    result=aggregate(manifest,audit_path);audit=load(audit_path);scope=load(scope_path);figure=load(figure_dir/"figure.json")
    for child in (scope,figure):
        if any(child[k]!=result[k] for k in IDENTITY):raise ValueError("foreign analysis identity")
    if scope["primary_audit_sha256"]!=sha(audit_path) or figure["audit_sha256"]!=sha(audit_path):raise ValueError("foreign analysis audit")
    for name,expected in figure["artifact_sha256"].items():
        if sha(figure_dir/name)!=expected:raise ValueError("rendered artifacts changed")
    setup=load(setup_path) if setup_path is not None else None
    if setup is not None:
        if any(setup[k]!=result[k] for k in IDENTITY) or setup["primary_audit_sha256"]!=sha(audit_path):raise ValueError("foreign initialization audit")
        if setup["counts"]["registered_controlled_resets"]!=result["environment_resets"] or setup["counts"]["registered_prior_controlled_resets"]!=result["prior_source_resets"]:
            raise ValueError("initialization population differs")
        if setup["counts"]["historical_initialization_calls_runtime_measured"] is not False:raise ValueError("structural initialization diagnosis required")
        result.update(setup_cost_audit_sha256=sha(setup_path),initialization_cost_scope=setup)
    result.update(scope_sha256=sha(scope_path),figure_metadata_sha256=sha(figure_dir/"figure.json"))
    text=markdown(result,audit,scope,figure_dir,report_path,setup)
    output.mkdir(parents=True,exist_ok=False);report_path.parent.mkdir(parents=True,exist_ok=True)
    report_path.write_bytes((text.rstrip("\n")+"\n").encode("utf-8"))
    result.update(report_path=str(report_path),report_sha256=sha(report_path))
    (output/"report_metrics.json").write_bytes((json.dumps(result,indent=2,ensure_ascii=False)+"\n").encode("utf-8"))
    print(json.dumps({k:result[k] for k in ("physical_steps","environment_resets","report_path")}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","audit","scope","figure-dir","output","report-path","setup-audit"):p.add_argument("--"+name,type=Path,required=True)
    a=p.parse_args();report(a.manifest.resolve(),a.audit.resolve(),a.scope.resolve(),a.figure_dir.resolve(),a.output.resolve(),a.report_path.resolve(),a.setup_audit.resolve())
