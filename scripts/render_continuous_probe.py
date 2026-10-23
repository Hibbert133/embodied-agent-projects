"""Plot audited continuous baseline performance and actual step cost."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def render(audit,output):
    r=json.loads(audit.read_text()); metrics=r["statistics"]["methods"]
    labels=["No probe","Probe, no correction","Static OLS","Dynamic OLS","Reset reference"]
    colors=["#708090","#708090","#34749b","#d85a37","#9c8aad"]
    fig,axes=plt.subplots(1,2,figsize=(11.5,4.8),layout="constrained")
    for ax,key,title,limit in zip(axes,("successful","mean_total_steps"),
        ("Task successes / 32","Mean probe + task steps"),(36,560)):
        values=[v[key] for v in metrics.values()]
        ax.barh(labels,values,color=colors,height=.6); ax.invert_yaxis(); ax.set_xlim(0,limit)
        ax.set_title(title,loc="left",fontweight="bold",pad=12)
        for i,v in enumerate(values): ax.text(v+limit*.012,i,f"{v:.0f}" if key=="successful" else f"{v:.1f}",va="center")
        ax.spines[["top","right","left"]].set_visible(False); ax.tick_params(axis="y",length=0)
        ax.xaxis.grid(True,alpha=.15); ax.set_axisbelow(True)
    fig.suptitle("Continuous evidence with a 500-step total budget",fontsize=17,fontweight="bold")
    fig.supxlabel("8 task seeds x 4 contexts. Reset reference uses 5 resets/episode; the other methods use 1.\n"
                  "Standard identification baselines; no novelty or multi-task generalization claim.",fontsize=10)
    for ext in (".png",".pdf"): fig.savefig(output.with_suffix(ext),dpi=180,facecolor="white")
    plt.close(fig)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--audit",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); render(a.audit,a.output)
