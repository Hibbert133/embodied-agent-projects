"""Audited task-utility figures and complete failures; no collection or tuning."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

METHODS=("NO_PROBE","PROBE8_NO_CORRECTION","PROBE16_NO_CORRECTION","DYNAMIC_OLS16","PRIOR_AFFINE16","PRIOR_NEAREST16",
         "FWD_LINEAR8","FWD_LINEAR16","FWD_QUADRATIC8","FWD_QUADRATIC16","PASSIVE_LINEAR","ORACLE16")
LABELS=("不探测","八步运动","十六步运动","动态 OLS","旧仿射","旧近邻","线性八步","线性十六步","二阶八步","二阶十六步","被动线性","参数参照")
TASKS=("push-v3","reach-v3","door-open-v3")
OPERATORS=("NOMINAL","GAIN_COUPLED","ROTATED_GAIN","REFLECTED_SHEAR")


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def render(manifest_path,audit_path,output):
    m=json.loads(manifest_path.read_text(encoding="utf-8"));a=json.loads(audit_path.read_text(encoding="utf-8"));root=manifest_path.parent
    identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    if a["integrity"]!="PASSED" or any(a[k]!=v for k,v in identity.items()):raise ValueError("matching independent audit required")
    for name,expected in a["artifact_sha256"].items():
        if sha(root/name)!=expected:raise ValueError("audited source changed")
    if output==root or root in output.parents:raise ValueError("postprocessing must be outside collection")
    if output.exists():raise FileExistsError("postprocessing already exists")
    failures=[];cases=[];cells=np.zeros((12,12),dtype=int);interfaces={}
    for method_index,method in enumerate(METHODS):
        with gzip.open(root/("episodes_"+method+".jsonl.gz"),"rt",encoding="utf-8") as handle:
            count=0
            for line in handle:
                record=json.loads(line);outcome=record["outcome"];count+=1
                cells[method_index,TASKS.index(record["task"])*4+OPERATORS.index(record["operator_oracle"])]+=int(outcome["success"])
                case={**{k:record[k] for k in ("episode_index","seed","task","operator_oracle","method")},
                      **{k:outcome[k] for k in ("success","total_steps","probe_steps","stopped_point_fit","invalid_fit_choices","final_status","parameter_error_oracle")}}
                injected=next(o for o in m["config"]["operators_oracle"] if o["id"]==record["operator_oracle"])
                matrix=np.array(injected["matrix_xy"],dtype=np.float32);bias=np.array(injected["bias_xy"],dtype=np.float32)
                controllers={d["sequence"]:d["choice"]["controller"] for d in record["decisions"]}
                errors=[];saturations=0
                for row in record["trace"]:
                    if row["phase"]!="POLICY":continue
                    desired=np.clip(np.array(row["raw_policy"],dtype=np.float32),-1,1)
                    controller=controllers[row["decision_sequence"]]
                    unclipped=np.array(controller["matrix_xy"])@desired[:2]+np.array(controller["offset"][:2])
                    saturations+=int(np.any(np.abs(unclipped)>1))
                    # Evaluator-only, deterministic zero-noise input surrogate.
                    mean=np.clip(matrix@np.array(row["command"][:2],dtype=np.float32)+bias,-1,1)
                    errors.append(float(np.max(np.abs(mean-desired[:2]))))
                case.update(policy_steps_for_interface=len(errors),saturated_policy_steps=saturations,
                            mean_zero_noise_clipped_input_error=float(np.mean(errors)) if errors else None)
                interfaces.setdefault(method,{"steps":0,"saturated_steps":0,"error_sum":0.})
                interfaces[method]["steps"]+=len(errors);interfaces[method]["saturated_steps"]+=saturations;interfaces[method]["error_sum"]+=sum(errors)
                cases.append(case)
                if not outcome["success"] or outcome["stopped_point_fit"]:
                    last=record["decisions"][-1]["choice"]
                    failures.append({**case,"final_fit_reason":last["fit"]["reason"] if last["fit"] else None,
                                     "executed_controller":last["controller"]})
            if count!=96:raise ValueError("complete method population required")
    if len(cases)!=1152:raise ValueError("complete task population required")
    nominal_harm=[]
    for method in METHODS:
        for seed in range(10600,10608):
            for task in TASKS:
                base=next(r for r in cases if (r["method"],r["seed"],r["task"],r["operator_oracle"])==("NO_PROBE",seed,task,"NOMINAL"))
                current=next(r for r in cases if (r["method"],r["seed"],r["task"],r["operator_oracle"])==(method,seed,task,"NOMINAL"))
                if base["success"] and not current["success"]:nominal_harm.append(current)
    interface_metrics={name:{"executed_policy_steps":v["steps"],"saturated_policy_steps":v["saturated_steps"],
                             "saturation_fraction":v["saturated_steps"]/v["steps"] if v["steps"] else None,
                             "mean_zero_noise_clipped_input_error":v["error_sum"]/v["steps"] if v["steps"] else None} for name,v in interfaces.items()}
    diagnostics={**identity,"audit_sha256":sha(audit_path),"postprocess_source_sha256":sha(Path(__file__)),
        "all_cases":cases,"failures":failures,"nominal_harm_vs_no_probe":nominal_harm,"task_operator_successes":cells.tolist(),
        "evaluator_only_interface_metrics":interface_metrics,
        "new_physical_steps":0,"new_api_calls":0,"model_or_gate_retunes":0,"physical_response_qualified":False}
    output.mkdir(parents=True,exist_ok=False)
    (output/"diagnostics.json").write_text(json.dumps(diagnostics,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    lines=["# 仿射任务桥：全部失败与停止", "",f'运行 `{identity["experiment_run_id"]}`。',
           f'Manifest `{identity["manifest_id"]}`；冻结提交 `{identity["source_git_commit"]}`。',"",
           "固定点拟合停止仍在分母中。真实条件只用于以下评估分层，不进入拟合。", "",
           "| 种子 | 任务 | 真条件（评估） | 方法 | 实际步 | 停止 | 最终状态 | 拟合原因 |", "|---|---|---|---|---:|---|---|---|"]
    for r in failures:lines.append(f'| {r["seed"]} | {r["task"]} | {r["operator_oracle"]} | {r["method"]} | {r["total_steps"]} | {r["stopped_point_fit"]} | {r["final_status"]} | {r["final_fit_reason"] or "无"} |')
    lines.extend(["",f'共有 {len(nominal_harm)} 个方法／案例在未扰动条件中相对 NO_PROBE 的成功出现损害，详情在 diagnostics.json。',""])
    (output/"failure_cases.md").write_text("\n".join(lines),encoding="utf-8")
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei"],"axes.unicode_minus":False,"font.size":10,"svg.fonttype":"path"})
    fig=plt.figure(figsize=(18,13));grid=fig.add_gridspec(2,2,height_ratios=[1,1.35],hspace=.30,wspace=.24)
    online=fig.add_subplot(grid[0,0]);amortized=fig.add_subplot(grid[0,1]);heat=fig.add_subplot(grid[1,:])
    metrics=a["statistics"]["methods"]
    colors=["#6E7B82"]*6+["#267599","#267599","#C56C3F","#C56C3F","#64875C","#80658E"]
    for index,method in enumerate(METHODS):
        v=metrics[method];y=v["successes"]*100/96
        for axis,field in ((online,"mean_online_steps"),(amortized,"mean_amortized_steps")):
            axis.scatter(v[field],y,s=65,color=colors[index],marker="s" if method=="ORACLE16" else "o")
            axis.annotate(str(index+1),(v[field],y),xytext=(5,5+8*(index%2)),textcoords="offset points",fontsize=10,color=colors[index])
    online.set(title="实际在线成功率与费用",xlabel="平均在线环境步",ylabel="任务成功率（%）",ylim=(-3,105))
    amortized.set(title="计入完整先验来源的费用",xlabel="平均在线步 + 摊销来源步",ylabel="任务成功率（%）",ylim=(-3,105))
    for axis in (online,amortized):axis.grid(alpha=.18);axis.spines[["top","right"]].set_visible(False)
    image=heat.imshow(cells/8*100,vmin=0,vmax=100,cmap="YlGnBu",aspect="auto")
    for row in range(12):
        for col in range(12):heat.text(col,row,f'{cells[row,col]}/8',ha="center",va="center",color="white" if cells[row,col]>=5 else "#354A55",fontsize=9)
    xlabels=[task+"\n"+op for task in ("推动","到达","开门") for op in ("未扰动","增益耦合","旋转增益","反射剪切")]
    heat.set(xticks=range(12),yticks=range(12),title="全部任务／算子分层（每格八个种子，相关方法不增加独立样本）")
    heat.set_xticklabels(xlabels);heat.set_yticklabels([f'{i+1} {name}' for i,name in enumerate(LABELS)])
    for edge in (3.5,7.5):heat.axvline(edge,color="white",linewidth=2)
    fig.colorbar(image,ax=heat,shrink=.75,label="成功率（%）")
    fig.suptitle("未知仿射执行器：标准点辨识的真实任务对照",fontsize=19,y=.97)
    fig.text(.08,.068,"序号对应下方方法；参数参照仅属评估器。三任务 × 四条件 × 八种子，十二方法，500 总步／一次初始重置。",fontsize=11)
    fig.text(.08,.039,f'新收集 {a["physical_steps"]:,} 步/1,152 重置；前向来源 21,010/288，旧校准来源 2,304/144。API 0；置信资格仍未建立。',fontsize=11)
    fig.subplots_adjust(left=.11,right=.95,top=.91,bottom=.14)
    fig.savefig(output/"figure.png",dpi=180,facecolor="white");fig.savefig(output/"figure.svg",facecolor="white");plt.close(fig)
    svg=output/"figure.svg";svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n",encoding="utf-8")
    metadata={**identity,"audit_sha256":sha(audit_path),"render_source_sha256":sha(Path(__file__)),
              "artifact_sha256":{name:sha(output/name) for name in ("figure.png","figure.svg","diagnostics.json","failure_cases.md")},
              "new_physical_steps":0,"new_api_calls":0,"model_or_gate_retunes":0}
    (output/"figure.json").write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"failure_cases":len(failures),"nominal_harms":len(nominal_harm),"output":str(output)}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    a=p.parse_args();render(a.manifest.resolve(),a.audit.resolve(),a.output.resolve())
