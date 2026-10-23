"""Display every audited pair; no new simulation, estimation or case selection."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.lines import Line2D

ROOT=Path(__file__).resolve().parents[2]
RUN=ROOT/"outputs/stale_reprobe/qualification_v1/stale_reprobe_20261019T125614Z_fdb617869c37"
OUT=ROOT/"outputs/reproduction_reviews/stale_reprobe_qualification_v1/analysis_v1"
REPORT=ROOT/"reports/stale_reprobe_execution_qualification_v1_zh.md"
LABELS={"push-v3":"推物","reach-v3":"到达","door-open-v3":"开门","UNCHANGED":"偏差不变","CHANGED":"偏差变化"}


def read(path):return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    value=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):value.update(block)
    return value.hexdigest()


def write(path,data):
    with path.open("w",encoding="utf-8",newline="\n") as f:json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False);f.write("\n")


def main():
    manifest=read(RUN/"manifest.json");audit=read(RUN/"audit/record_audit.json");receipt=read(RUN/"audit/report_receipt.json")
    assert manifest["manifest_id"]=="5ea66255714e4c3011ee21e5dbdf01b6069f3bbbb94693a33c74cd42e5390b60"
    assert audit["integrity"]=="PASSED" and audit["executions"]==18 and audit["paired_units"]==9
    for k in ("experiment_run_id","manifest_id","source_git_commit"):assert manifest[k]==audit[k]==receipt[k]
    bindings={ROOT/name:value for name,value in manifest["input_sha256"].items()}
    bindings.update({RUN/"collection"/name:value for name,value in audit["collection_artifact_sha256"].items()})
    bindings.update({RUN/"audit/record_audit.json":receipt["record_audit_sha256"],RUN/"audit/report_zh.md":receipt["report_sha256"],
                    ROOT/"scripts/audit_stale_reprobe_v1.py":receipt["report_source_sha256"]})
    for path,value in bindings.items():assert sha(path)==value,str(path)
    processes={}
    for name in ("collect","audit"):
        p=read(RUN/(name+"_process_receipt.json"));assert p["returncode"]==0
        log=RUN/(name+"_process.txt");assert sha(log)==p["output_sha256"];processes[name]=p
        for item in (log,RUN/(name+"_process_receipt.json")):bindings[item]=sha(item)
    with gzip.open(RUN/"collection/cases.jsonl.gz","rt",encoding="utf-8") as f:rows=[json.loads(line) for line in f]
    assert [{k:r[k] for k in a} for r,a in zip(rows,audit["rows"])]==audit["rows"] and len(rows)==18
    pairs=[rows[i:i+2] for i in range(0,18,2)]
    if OUT.exists():
        previous=read(OUT/"report_receipt.json")
        for name,value in previous["output_sha256"].items():assert sha(ROOT/name)==value,"derived output edited: "+name
    else:assert not REPORT.exists();OUT.mkdir(parents=True)
    font=findfont(FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.family":"Microsoft YaHei","axes.unicode_minus":False,"font.size":10})
    fig,axes=plt.subplots(3,3,figsize=(13,9),sharex=True,sharey=True);maximum=0.;curves=[]
    colors={"UNCHANGED":"#ce7e26","CHANGED":"#216f9c"}
    xmax=max(max(r["planned_boundary"],r["total_steps"]) for r in rows)+3
    for ax,pair in zip(axes.flat,pairs):
        reference=pair[0];count=reference["approach"]["public"]["completed_steps"]
        for r in pair:
            observations=[r["prefix"]["public"]["events"][0]["payload"]["initial"]["observation"]]+[p["after"]["observation"] for p in r["physical_rows"]]
            values=[max(abs(a-b) for a,b in zip(obs[:3],(0.,.6,.25))) for obs in observations]
            maximum=max(maximum,max(values));curves.append({"seed":r["seed"],"variant":r["variant"],"anchor_error_m":values})
            if r["variant"]=="UNCHANGED":ax.plot(range(count+1),values[:count+1],color="#7e8792",lw=2)
            ax.plot(range(count,len(values)),values[count:],color=colors[r["variant"]],lw=2)
            ax.scatter([len(values)-1],[values[-1]],color=colors[r["variant"]],s=24,marker="o" if r["variant"]=="UNCHANGED" else "x",zorder=3)
        flags=["有" if r["complete_window"] else "无" for r in pair]
        ax.set_title(f"{LABELS[reference['task']]} · 种子{reference['seed']} · 第{reference['planned_boundary']}步\n完整窗口：不变{flags[0]} / 变化{flags[1]}",fontsize=10)
        ax.axvline(reference["planned_boundary"],ls="--",color="#8b9299",lw=1)
        ax.axhline(.015,ls=":",color="#32485e",lw=1);ax.grid(alpha=.14);ax.set_xlim(0,xmax)
    axes[0,0].set_ylim(0,maximum*1.05)
    assert all(ax.get_ylim()[1]>=maximum for ax in axes.flat)
    for ax in axes[:,0]:ax.set_ylabel("距测量位置的最大坐标误差 / 米")
    for ax in axes[-1,:]:ax.set_xlabel("累计实际控制步")
    fig.suptitle("全部9个配对：旧纠正遇到偏差变化后能否取得新窗口",fontsize=16,y=.99)
    fig.legend([Line2D([0],[0],color=c,lw=2) for c in ("#7e8792","#ce7e26","#216f9c")],
        ["变化前相同轨迹","偏差不变","偏差变化，仍使用旧纠正"],loc="lower center",ncol=3,bbox_to_anchor=(.5,.025))
    fig.text(.5,.008,"竖虚线：预定变化/介入步；横点线：进入探测前的位置门槛，另需满足运动稳定及物体间距条件。",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.95));figure=OUT/"paired_anchor_trajectories_zh.png";fig.savefig(figure,dpi=160);plt.close(fig)
    arms={r["variant"]:r for r in audit["costs"]["per_arm"]};left,right=arms["UNCHANGED"],arms["CHANGED"]
    summary=f"**偏差不变取得{left['complete_windows']}/9个完整窗口；偏差变化取得{right['complete_windows']}/9个。执行资格：{audit['qualification']}；记录审计通过。**"
    body=(RUN/"audit/report_zh.md").read_text(encoding="utf-8").split("\n",1)[1]
    for token,label in LABELS.items():body=body.replace("|"+token+"|","|"+label+"|")
    lines=["# 旧纠正失效后的重新探测：真实配对结果","",summary,"",
        "## 名字怎么理解","",
        "C表示动作纠正方案。C4用最开始4步探测估计，C8用最开始8步探测估计；数字不是模型版本，也不代表成功次数。本轮把此前已实际使用的C8叫作旧纠正。", "",
        "重新探测（re-probe）就是工作中再测一次：先移动到规定的测量位置，再做8步测试动作。完整窗口指这8步及所需的进入状态都已取得，不表示最终任务成功，也不表示已验证新估计器。", "",
        "偏差不变（UNCHANGED）和偏差变化（CHANGED）是两种实验条件。过期纠正（stale correction）指环境偏差变了，机器人仍使用原先的纠正。冷启动（cold start）指刚初始化时的测量；中途测量（warm）指已经运动后，在连续状态上重新测量。", "",
        "记录审计通过（PASSED）表示保存的决策、实际动作、状态连续性与费用核对通过。执行资格未通过（NOT_QUALIFIED）表示未达到预先规定的完整窗口数量门槛。这两个判据回答不同问题。", "",
        "每个任务单元两次独立实际执行，在变化前核对状态和全部物理轨迹相同；变化臂在移动前把偏差从(0.12,−0.08)改为(−0.12,0.08)。代理看不到真实偏差或变化标签，继续使用先前实际执行过的C8。", "",
        "![全部9个配对轨迹](../outputs/reproduction_reviews/stale_reprobe_qualification_v1/analysis_v1/paired_anchor_trajectories_zh.png)","",
        "图中位置门槛只用于进入探测，探测后位置允许变化。所有案例都显示，包括没有安装新条件就已结束的案例；没有挑选成功轨迹。", "",body,"",
        "## 研究含义与下一步","",
        "这批配对检验原操作对既定偏差变化的适用性。窗口计数差是有限样本中的受控对照，不是任务成功率、广泛故障适用性或唯一动力学机制的证明。未到位不能用新估计器补救，因为尚未取得它需要的数据。",
        "下一步应按实际资格结果决定是否先改进获取操作。若采用积分反馈等常规抗偏差控制，必须独立版本化、重新冻结新案例，并比较移动本身积累的补偿信息；不能预设额外8步探测有额外价值。原C8、原操作及本次负结果都保留。真实中途模型校准、完整成本下的任务收益、创新性和CCF A论文要求仍未完成。", "",
        f"采集进程{processes['collect']['wall_ns']/1e9:.3f}秒；只读审计进程{processes['audit']['wall_ns']/1e9:.3f}秒。本轮API调用0。全仓库1,215项测试、编译、依赖、秘密及差异检查通过。软件夹具费用为冻结记录覆盖的子集，早先两次定向测试的费用列表未导出，不宣称完整开发阶段总费用。",
        "过程日志中的Gymnasium观测空间及MetaWorld动作裁剪提示原样保留。",
        f"[原始记录与审计](../{RUN.relative_to(ROOT).as_posix()})；[冻结协议](../docs/protocols/stale_reprobe_execution_qualification_v1.md)。", ""]
    with REPORT.open("w",encoding="utf-8",newline="\n") as f:f.write("\n".join(lines))
    metrics=OUT/"descriptive_curves.json";write(metrics,{"scope":"READ_ONLY_ALL_PAIRS_DESCRIPTION","curves":curves,"per_arm":audit["costs"]["per_arm"],"new_physical_steps":0,"new_api_calls":0})
    for path in (RUN/"manifest.json",RUN/"audit/report_receipt.json"):bindings[path]=sha(path)
    write(OUT/"report_receipt.json",{"source_sha256":sha(Path(__file__)),"input_sha256":{p.relative_to(ROOT).as_posix():v for p,v in bindings.items()},
        "output_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (REPORT,figure,metrics)},
        "plotting_python":sys.version,"matplotlib":matplotlib.__version__,"font_sha256":sha(Path(font)),"new_physical_steps":0,"new_api_calls":0})
    print(json.dumps({"report":str(REPORT),"figure":str(figure),"verified_inputs":len(bindings)}))


if __name__=="__main__":main()
