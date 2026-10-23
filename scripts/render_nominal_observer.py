"""Chinese audited observer/error figures; post-processing only."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import NullFormatter
import numpy as np

TASK_NAMES={"push-v3":"推动","reach-v3":"到达","door-open-v3":"开门"}
PROGRAM_NAMES={"POLICY_ONLY":"直接策略","PROBE_THEN_POLICY":"探测后策略"}


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def render(manifest_path,audit_path,prefix):
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"));audit=json.loads(audit_path.read_text(encoding="utf-8"))
    fields=("experiment_run_id","manifest_id","source_git_commit")
    if audit["integrity"]!="PASSED" or any(audit[k]!=manifest[k] for k in fields):raise ValueError("matching independent audit required")
    for name,digest in audit["artifact_sha256"].items():
        if sha(manifest_path.parent/name)!=digest:raise ValueError("audited source changed")
    scores={name:[] for name in audit["statistics"]["strata"]}
    with gzip.open(manifest_path.parent/"episodes.jsonl.gz","rt",encoding="utf-8") as handle:
        for line in handle:
            record=json.loads(line);scores[record["task"]+"|"+record["program"]].append(record["outcome"]["maximum_block_error"])
    if any(len(v)!=16 or any(x is None or x<=0 for x in v) for v in scores.values()):raise ValueError("figure requires complete positive-error population")
    paths=[prefix.with_suffix(ext) for ext in (".png",".svg",".json")]
    if any(p.exists() for p in paths):raise FileExistsError("figure already exists")
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei"],"axes.unicode_minus":False,"font.size":11,
                         "svg.fonttype":"path","axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(1,2,figsize=(16,7.7),gridspec_kw={"wspace":.27})
    keys=list(scores);labels=[TASK_NAMES[k.split("|")[0]]+"\n"+PROGRAM_NAMES[k.split("|")[1]] for k in keys]
    axes[0].boxplot([scores[k] for k in keys],showfliers=True,medianprops={"color":"#233D4B"})
    axes[0].set_xticks(range(1,7),labels)
    axes[0].scatter(range(1,7),[audit["statistics"]["strata"][k]["p90_episode_max_error"] for k in keys],marker="D",color="#CE633F",label="轨迹最大误差 p90",zorder=3)
    axes[0].axhline(.1,color="#B33E38",linestyle="--",label="冻结可行性门槛 0.10")
    axes[0].set(yscale="log",ylabel="每轨迹最大四步均值误差（命令单位）",title="可见响应逆映射：六组均未达到要求")
    axes[0].legend(frameon=False,loc="upper left",fontsize=10)
    colors={"push-v3":"#23789C","reach-v3":"#D17A31","door-open-v3":"#4B8461"}
    for key,values in audit["statistics"]["passive_snapshots"].items():
        task,program=key.split("|");x=[];y=[]
        for step,row in values.items():
            if row["p90_identity_error_inf"] is not None:
                x.append(int(step));y.append(row["p90_identity_error_inf"])
        axes[1].plot(x,y,marker="o",linestyle="-" if program=="POLICY_ONLY" else "--",color=colors[task],
                     label=TASK_NAMES[task]+"·"+PROGRAM_NAMES[program])
    axes[1].set(xscale="log",yscale="log",xticks=[16,32,64],xlabel="已完成的环境步数",ylabel="数值有效拟合的矩阵误差 p90",title="被动一般仿射辨识：满秩并不等于准确")
    axes[1].set_xticklabels(["16","32","64"]);axes[1].legend(frameon=False,fontsize=9)
    axes[1].xaxis.set_minor_formatter(NullFormatter())
    for axis in axes:axis.grid(alpha=.18,which="both");axis.set_axisbelow(True)
    fig.suptitle("名义策略 96/96 完成，观察资格可行性六组全部失败",fontsize=17,y=.96)
    fig.text(.07,.105,"固定旧名义 ARX；3 任务 × 2 程序 × 16 新种子。噪声标准差 0.05；四步误差不是确定性噪声界。",fontsize=11)
    fig.text(.07,.069,"右图只使用已观察且数值有效的快照；缺失不当零。开门直接策略在第 32 步的均值受一例极端拟合影响。",fontsize=10)
    fig.text(.07,.031,f'新成本 {audit["physical_steps"]:,} 步/96 初始重置；旧离线 2,304 步/144 重置另列；API 0。冻结提交 {manifest["source_git_commit"][:12]}。',fontsize=10,color="#606B71")
    fig.subplots_adjust(left=.07,right=.98,top=.86,bottom=.23)
    prefix.parent.mkdir(parents=True,exist_ok=True);fig.savefig(paths[0],dpi=180,facecolor="white");fig.savefig(paths[1],facecolor="white");plt.close(fig)
    paths[1].write_bytes(("\n".join(line.rstrip() for line in paths[1].read_text(encoding="utf-8").splitlines())+"\n").encode("utf-8"))
    metadata={**{k:manifest[k] for k in fields},"audit_sha256":sha(audit_path),"render_tool_sha256":sha(Path(__file__)),
        "artifact_sha256":{p.name:sha(p) for p in paths[:2]},"strata":audit["statistics"]["strata"],
        "physical_collection_rerun":False,"api_calls_added":0,"svg_trailing_whitespace_removed":True}
    paths[2].write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8");print(paths[0])


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--manifest",type=Path,required=True);p.add_argument("--audit",type=Path,required=True);p.add_argument("--output",type=Path,required=True)
    args=p.parse_args();render(args.manifest.resolve(),args.audit.resolve(),args.output.resolve())
