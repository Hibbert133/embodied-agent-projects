"""Chinese full-group figures and failure records from immutable audited data.

Post-processing only. Run with a plotting runtime containing Matplotlib.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

METHODS=("LEGACY_ARX","LINEAR_ARX","QUADRATIC_STATE","NEAREST_STATE")
LABELS=("旧 ARX","线性 ARX","状态二阶","同数据近邻")
TASKS=("push-v3","reach-v3","door-open-v3")
TASK_LABELS=("推动","到达","开门")
PROGRAMS=("POLICY_ONLY","PROBE_THEN_POLICY")


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def process(manifest_path,audit_path,output):
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"));audit=json.loads(audit_path.read_text(encoding="utf-8"))
    keys=("experiment_run_id","manifest_id","source_git_commit");identity={k:manifest[k] for k in keys}
    if audit["integrity"]!="PASSED" or any(audit[k]!=v for k,v in identity.items()):raise ValueError("matching independent audit required")
    for name,digest in audit["artifact_sha256"].items():
        if sha(manifest_path.parent/name)!=digest:raise ValueError("audited source changed")
    if output==manifest_path.parent or manifest_path.parent in output.parents:raise ValueError("post-processing must be outside collection")
    rows={};misses=[];nominal_failures=[]
    for stage in ("CALIBRATION","QUALIFICATION"):
        outcomes=[]
        with gzip.open(manifest_path.parent/(stage+".jsonl.gz"),"rt",encoding="utf-8") as stream:
            for line in stream:
                record=json.loads(line);outcome=record["outcome"];outcomes.append(outcome)
                key={k:record[k] for k in ("stage","seed","task","program","episode_index")}
                if not outcome["success"]:nominal_failures.append({**key,"total_steps":outcome["total_steps"],"maximum_errors_m":outcome["maximum_errors"]})
                if stage=="QUALIFICATION":
                    for name,error in outcome["maximum_errors"].items():
                        radius=audit["statistics"]["strata"][record["task"]+"|"+record["program"]][name]["radius_m"]
                        if error is None or radius is None or error>radius:
                            misses.append({**key,"method":name,"maximum_error_m":error,"frozen_radius_m":radius,"nominal_task_success":outcome["success"]})
        if len(outcomes)!=96:raise ValueError("complete audited population required")
        rows[stage]=outcomes
    drivers=[]
    for task in TASKS:
        for program in PROGRAMS:
            selected=[r for r in rows["CALIBRATION"] if r["task"]==task and r["program"]==program]
            for name in METHODS:
                valid=[r for r in selected if r["maximum_errors"][name] is not None]
                maximum=max((r["maximum_errors"][name] for r in valid),default=None)
                drivers.extend({"task":task,"program":program,"method":name,"seed":r["seed"],"total_steps":r["total_steps"],
                                "nominal_task_success":r["success"],"radius_driver_score_m":maximum}
                               for r in valid if r["maximum_errors"][name]==maximum)
    diagnostics={**identity,"audit_sha256":sha(audit_path),"analysis_tool_sha256":sha(Path(__file__)),
        "interval_misses":misses,"distinct_missed_episodes":len({r["episode_index"] for r in misses}),
        "nominal_task_failures":nominal_failures,"calibration_radius_drivers":drivers,
        "qualification_cases":rows["QUALIFICATION"],"new_physical_steps":0,"new_api_calls":0,"model_or_threshold_refits":0}
    output.mkdir(parents=True,exist_ok=False)
    (output/"diagnostics.json").write_text(json.dumps(diagnostics,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=["# 前向预测失败记录", "",f'运行 `{identity["experiment_run_id"]}`。',
        f'Manifest `{identity["manifest_id"]}`；冻结提交 `{identity["source_git_commit"]}`。',"",
        "以下为区间未覆盖，不改写任务成功；模型从未参与动作选择。", "",
        "| 种子 | 任务 | 程序 | 模型 | 最大误差 mm | 冻结半径 mm | 任务成功 |", "|---|---|---|---|---:|---:|---|"]
    def mm(value):return f"{value*1000:.4f}" if value is not None else "无测量"
    for r in misses:lines.append(f'| {r["seed"]} | {r["task"]} | {r["program"]} | {r["method"]} | {mm(r["maximum_error_m"])} | {mm(r["frozen_radius_m"])} | {r["nominal_task_success"]} |')
    lines.extend(["", "## 名义任务失败", "", "| 阶段 | 种子 | 任务 | 程序 | 实际步数 |", "|---|---|---|---|---:|"])
    for r in nominal_failures:lines.append(f'| {r["stage"]} | {r["seed"]} | {r["task"]} | {r["program"]} | {r["total_steps"]} |')
    (output/"failure_cases.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei"],"axes.unicode_minus":False,"font.size":11,"svg.fonttype":"path"})
    fig,axes=plt.subplots(3,2,figsize=(15,13),sharey=True)
    for row,task in enumerate(TASKS):
        for column,program in enumerate(PROGRAMS):
            axis=axes[row,column];values=audit["statistics"]["strata"][task+"|"+program]
            if any(values[n]["radius_m"] is None or values[n]["p90_episode_max_error_m"] is None for n in METHODS):raise ValueError("complete figure population required")
            x=list(range(4));p90=[values[n]["p90_episode_max_error_m"]*1000 for n in METHODS];radii=[values[n]["radius_m"]*1000 for n in METHODS]
            axis.bar([v-.18 for v in x],p90,width=.34,color="#25769A",label="测试轨迹最大误差 p90")
            axis.bar([v+.18 for v in x],radii,width=.34,color="#C77945",label="冻结校准半径")
            axis.axhline(1.,color="#AF3C3B",linestyle="--",label="预注册 1 mm 分辨率")
            for i,n in enumerate(METHODS):
                label_y=radii[i]*1.10
                color="#AF3C3B" if values[n]["covered"]<15 else "#4C5661"
                if .86<label_y<1.12:label_y=radii[i]*.80;color="white"
                axis.text(i+.18,label_y,f'{values[n]["covered"]}/16',ha="center",fontsize=10,color=color)
            axis.set(yscale="log",xticks=x,title=TASK_LABELS[row]+(" · 直接策略" if column==0 else " · 探测后策略"),ylabel="位移预测误差与区间半径（mm）" if column==0 else "")
            axis.set_xticklabels(LABELS);axis.grid(axis="y",alpha=.16,which="both");axis.set_axisbelow(True)
            axis.spines[["top","right"]].set_visible(False)
    axes[0,0].legend(frameon=False,fontsize=10,loc="upper left")
    fig.suptitle("前向基线：平均精度改善，六组联合可行性仍未通过",fontsize=19,y=.975)
    fig.text(.08,.055,"橙色半径来自独立校准轨迹；柱旁数字是新测试整轨迹覆盖数。每组 16 个独立种子，先按轨迹取最大误差。",fontsize=11)
    fig.text(.08,.032,f'四模型共享固定策略的实际轨迹；没有模型参与控制。新收集 {audit["physical_steps"]:,} 步/288 初始重置；API 0。',fontsize=11)
    fig.subplots_adjust(top=.92,bottom=.11,left=.08,right=.97,hspace=.28,wspace=.14)
    fig.savefig(output/"figure.png",dpi=180,facecolor="white");fig.savefig(output/"figure.svg",facecolor="white");plt.close(fig)
    svg=output/"figure.svg";svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8")
    metadata={**identity,"audit_sha256":sha(audit_path),"render_tool_sha256":sha(Path(__file__)),
        "artifact_sha256":{name:sha(output/name) for name in ("figure.png","figure.svg","diagnostics.json","failure_cases.md")},
        "new_physical_steps":0,"new_api_calls":0,"model_or_threshold_refits":0}
    (output/"figure.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"interval_misses":len(misses),"distinct_missed_episodes":diagnostics["distinct_missed_episodes"],"nominal_task_failures":nominal_failures},ensure_ascii=False))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();process(a.manifest.resolve(),a.audit.resolve(),a.output.resolve())
