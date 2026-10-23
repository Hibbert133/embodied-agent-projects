"""Audited chronological method outcomes, failures and scientific figures."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

METHODS=("NO_PROBE","FIXED8","FIXED16","FIXED8_WIDE","FIXED16_WIDE","CACHE_ONLY","PERIODIC2","PERIODIC3",
         "RECENT_WINDOW","RESIDUAL_CUSUM","G_OPTIMAL","RESPONSE_SET","RESPONSE_POINT","RESPONSE_GEOMETRY","RESPONSE_NO_COST","ORACLE16")
LABELS=("未纠正","原八步","原十六步","宽八步","宽十六步","旧缓存","周期二","周期三","近期辨识","残差检测","G 设计","响应集合","点消融","几何消融","成本消融*","参数参照")
TASKS=("push-v3","reach-v3","door-open-v3")
SCENARIOS=("STATIONARY","MIXED")


def sha(path):
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def place_labels(axis,points):
    """Place numeric identifiers in display space without altering data."""
    renderer=axis.figure.canvas.get_renderer();occupied=[]
    pixels=[axis.transData.transform((x,y)) for _,x,y,_ in points]
    offsets=[(radius*dx,radius*dy) for radius in (9,18,27,36,45,54,63)
             for dx,dy in ((1,1),(-1,1),(1,-1),(-1,-1),(0,1),(1,0),(0,-1),(-1,0))]
    for index,x,y,color in points:
        label=axis.annotate(str(index),(x,y),xytext=offsets[0],textcoords="offset points",ha="center",va="center",color=color,
                            bbox={"facecolor":"white","alpha":.85,"edgecolor":"none","pad":.8})
        for offset in offsets:
            label.set_position(offset);box=label.get_window_extent(renderer).padded(2)
            inside=axis.bbox.contains(box.x0,box.y0) and axis.bbox.contains(box.x1,box.y1)
            if inside and not any(box.overlaps(other) for other in occupied) and not any(box.contains(*point) for point in pixels):break
        occupied.append(label.get_window_extent(renderer).padded(2))
        axis.annotate("",(x,y),xytext=label.get_position(),textcoords="offset points",
                      arrowprops={"arrowstyle":"-","color":color,"linewidth":.65,"alpha":.6},zorder=1)


def render(manifest,audit_path,output):
    m=json.loads(manifest.read_text(encoding="utf-8"));audit=json.loads(audit_path.read_text(encoding="utf-8"))
    identity={k:m[k] for k in ("experiment_run_id","manifest_id","source_git_commit")}
    if audit["integrity"]!="PASSED" or any(audit[k]!=v for k,v in identity.items()):raise ValueError("matching completed audit required")
    for name,expected in audit["artifact_sha256"].items():
        if sha(manifest.parent/name)!=expected:raise ValueError("audited raw bytes changed")
    if output.exists() or output==manifest.parent or manifest.parent in output.parents:raise FileExistsError("new external figure directory required")
    cases=[];failures=[];choices=Counter();by_episode=np.zeros((16,6),int);strata=np.zeros((16,6),int)
    for index,method in enumerate(METHODS):
        with gzip.open(manifest.parent/("episodes_"+method+".jsonl.gz"),"rt",encoding="utf-8") as handle:
            for line in handle:
                record=json.loads(line);r=record["outcome"]
                case={k:r[k] for k in ("episode_index","stream","task","scenario","method","episode_in_stream","seed","operator_id_oracle",
                    "success","total_steps","prefix_steps","micro_steps","fixed_probe_steps","policy_steps","stopped","reused_cache","requested_fixed_refresh",
                    "point_fit_failures","cache_updates","final_action")}
                cases.append(case)
                if not r["success"]:failures.append(case)
                by_episode[index,r["episode_in_stream"]]+=int(r["success"])
                strata[index,TASKS.index(r["task"])*2+SCENARIOS.index(r["scenario"])]+=int(r["success"])
                for d in record["decisions"]:choices[(method,d["action"])]+=1
    if len(cases)!=4608 or any(sum(r["method"]==p for r in cases)!=288 for p in METHODS):raise ValueError("full chronological population required")
    diagnostic={**identity,"audit_sha256":sha(audit_path),"postprocess_source_sha256":sha(Path(__file__)),
        "cases":cases,"failed_cases":failures,"choice_counts":[{"method":p,"action":a,"count":n} for (p,a),n in sorted(choices.items())],
        "task_scenario_successes":strata.tolist(),"episode_position_successes":by_episode.tolist(),
        "new_environment_steps":0,"new_api_calls":0,"physical_response_qualified":False}
    output.mkdir(parents=True,exist_ok=False)
    (output/"diagnostics.json").write_bytes((json.dumps(diagnostic,indent=2,ensure_ascii=False)+"\n").encode("utf-8"))
    rows=["# 响应验证开发 全部失败案例","",f"原始运行 `{identity['experiment_run_id']}`。","",
          "真实情景／算子仅供评估分层；变化不自动表示缓存错误。全部失败含停止，仍留在每方法 288 分母。","",
          "| 流 | 任务 | 情景 | 案例序号 | 方法 | 算子（评估） | 实际步 | 停止 | 最后选择 |","|---|---|---|---:|---|---|---:|---|---|"]
    for r in failures:rows.append(f"| {r['stream']} | {r['task']} | {r['scenario']} | {r['episode_in_stream']} | {r['method']} | {r['operator_id_oracle']} | {r['total_steps']} | {r['stopped']} | {r['final_action']} |")
    (output/"failure_cases.md").write_bytes(("\n".join(rows)+"\n").encode("utf-8"))
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei"],"axes.unicode_minus":False,"font.size":10,"svg.fonttype":"path"})
    fig=plt.figure(figsize=(18,14),dpi=180);grid=fig.add_gridspec(2,2,height_ratios=[1,1.35],wspace=.25,hspace=.32)
    online=fig.add_subplot(grid[0,0]);amortized=fig.add_subplot(grid[0,1]);heat=fig.add_subplot(grid[1,:])
    colors=["#6E7B82"]*10+["#267599","#C56C3F","#B58B59","#64875C","#80658E","#A181B8"]
    metrics=audit["statistics"]["methods"]
    identifiers={online:[],amortized:[]}
    for i,p in enumerate(METHODS):
        r=metrics[p]
        for axis,field in ((online,"mean_online_steps"),(amortized,"mean_amortized_steps")):
            axis.scatter(r[field],r["successes"]/288*100,color=colors[i],s=60,marker="s" if p=="ORACLE16" else "o")
            identifiers[axis].append((i+1,r[field],r["successes"]/288*100,colors[i]))
    for axis,title,xlabel in ((online,"任务成功与登记控制费用","平均在线环境步"),(amortized,"计入来源登记控制费用","在线步 + 摊销来源步")):
        axis.set(title=title,xlabel=xlabel,ylabel="任务成功率（%）",ylim=(-3,105));axis.grid(alpha=.15);axis.spines[["top","right"]].set_visible(False)
    image=heat.imshow(strata/48*100,aspect="auto",vmin=0,vmax=100,cmap="YlGnBu")
    for i in range(16):
        for j in range(6):heat.text(j,i,f"{strata[i,j]}/48",ha="center",va="center",color="white" if strata[i,j]>=30 else "#354A55",fontsize=9)
    heat.set(xticks=range(6),yticks=range(16),title="全部任务／情景分层 每格 48 个相关案例")
    heat.set_xticklabels([t+"\n"+s for t in ("推动","到达","开门") for s in ("未变化","突变／渐变")])
    heat.set_yticklabels([f"{i+1} {label}" for i,label in enumerate(LABELS)])
    fig.colorbar(image,ax=heat,shrink=.7,label="成功率（%）")
    fig.suptitle("行动响应缓存验证 独立时变流的强基线比较",fontsize=19,y=.975)
    fig.text(.1,.062,"八个流簇，三任务，两情景，六案例；每方法 288 分母。* 成本消融 41 案例提前刷新。参数参照仅供评估器。",fontsize=11)
    fig.text(.1,.034,f"登记控制 {audit['physical_steps']:,} 步／4,608 初始重置；来源登记 21,010／288，工厂初始化另报。API 0，响应资格未建立。",fontsize=11)
    fig.subplots_adjust(left=.12,right=.94,top=.91,bottom=.135)
    fig.canvas.draw()
    for axis,points in identifiers.items():place_labels(axis,points)
    fig.savefig(output/"figure.png",dpi=180,facecolor="white");fig.savefig(output/"figure.svg",facecolor="white");plt.close(fig)
    svg=output/"figure.svg";svg.write_bytes(("\n".join(r.rstrip() for r in svg.read_text(encoding="utf-8").splitlines())+"\n").encode("utf-8"))
    metadata={**identity,"audit_sha256":sha(audit_path),"render_source_sha256":sha(Path(__file__)),
        "artifact_sha256":{name:sha(output/name) for name in ("diagnostics.json","failure_cases.md","figure.png","figure.svg")},
        "new_environment_steps":0,"new_api_calls":0,"physical_response_qualified":False}
    (output/"figure.json").write_bytes((json.dumps(metadata,indent=2)+"\n").encode("utf-8"))
    print(json.dumps({"failure_cases":len(failures),"output":str(output)}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    render(a.manifest.resolve(),a.audit.resolve(),a.output.resolve())
