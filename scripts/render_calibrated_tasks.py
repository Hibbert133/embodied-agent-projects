"""Plot audited task utility and disclosed amortized calibration costs."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


def render(audit,output,language="en"):
    result=json.loads(audit.read_text()); metrics=result["statistics"]["methods"]
    labels=["No probe","Probe, no correction","Online dynamic OLS","Calibrated affine","Calibrated nearest"]
    success_title="Task successes / 64"
    cost_title="Mean amortized environment steps"
    offline_label="Offline cost / 64"
    title="Does independently calibrated continuous evidence help the task?"
    caption=("16 task seeds x 4 contexts. Each prior pays 2,304 offline steps and 144 resets; shown at 64-unit amortization.\n"
             "500 online steps and one initial reset per episode. Standard identification baselines; no novelty claim.")
    if language=="zh":
        available={font.name for font in font_manager.fontManager.ttflist}
        family=next((name for name in ("Microsoft YaHei","SimHei","Noto Sans CJK SC","Source Han Sans SC") if name in available),None)
        if family is None:
            raise RuntimeError("Chinese labels require an installed CJK font (Microsoft YaHei, SimHei, or Noto Sans CJK SC).")
        plt.rcParams["font.family"]=[family]
        plt.rcParams["axes.unicode_minus"]=False
        labels=["不探测","探测但不纠正","在线动态 OLS","校准仿射先验","同数据最近邻先验"]
        success_title="任务成功数 / 64"
        cost_title="平均环境步数（含离线成本摊销）"
        offline_label="离线步数 / 64"
        title="经过独立检验的校准证据能否改善任务结果？"
        caption=("16 个任务种子 × 4 种条件；每种先验计入 2,304 个离线步和 144 次重置，按 64 个任务单元摊销。\n"
                 "每次执行在线预算 500 步、初始重置一次。当前结果支持标准辨识基线的任务收益，尚未建立算法创新。")
    colors=["#7d8b94","#7d8b94","#465e6b","#34749b","#d85a37"]
    fig,axes=plt.subplots(1,2,figsize=(12,4.9),layout="constrained")
    successes=[v["successful"] for v in metrics.values()]
    axes[0].barh(labels,successes,color=colors,height=.6); axes[0].set_xlim(0,72)
    for i,v in enumerate(successes): axes[0].text(v+1,i,str(v),va="center")
    axes[0].set_title(success_title,loc="left",fontweight="bold")
    online=[v["mean_online_steps"] for v in metrics.values()]
    offline=[v["offline_steps"]/64 for v in metrics.values()]
    axes[1].barh(labels,online,color=colors,height=.6)
    axes[1].barh(labels,offline,left=online,color="#c8d2d7",height=.6,label=offline_label)
    axes[1].set_xlim(0,560); axes[1].set_title(cost_title,loc="left",fontweight="bold")
    for i,(a,b) in enumerate(zip(online,offline)): axes[1].text(a+b+5,i,f"{a+b:.1f}",va="center")
    axes[1].legend(frameon=False,loc="lower right")
    for ax in axes:
        ax.invert_yaxis(); ax.spines[["top","right","left"]].set_visible(False); ax.tick_params(axis="y",length=0)
        ax.xaxis.grid(True,alpha=.15); ax.set_axisbelow(True)
    fig.suptitle(title,fontsize=16,fontweight="bold")
    fig.supxlabel(caption,fontsize=9)
    output.parent.mkdir(parents=True,exist_ok=True)
    provenance=(f"Run: {result['experiment_run_id']}\n"
                f"Manifest: {result['manifest_id']}\n"
                f"Source: {result['source_git_commit']}")
    for ext in (".png",".pdf"):
        metadata={"Title":title,"Description" if ext==".png" else "Subject":provenance}
        fig.savefig(output.with_suffix(ext),dpi=180,facecolor="white",metadata=metadata)
    plt.close(fig)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--audit",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    p.add_argument("--language",choices=("en","zh"),default="en")
    a=p.parse_args(); render(a.audit,a.output,a.language)
