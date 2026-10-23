"""Plot audited known-command qualification; requires a plotting runtime."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def render(audit,qualification,output):
    result=json.loads(audit.read_text())
    rows=[json.loads(x) for x in qualification.read_text().splitlines()]
    actual=np.array([r["known_command_offset"] for r in rows])
    if len(rows)!=72: raise ValueError("incomplete qualification plot population")
    fig,axes=plt.subplots(1,2,figsize=(10.5,4.6),layout="constrained")
    affine=np.array([r["predictions"]["affine"] for r in rows])
    for index,label,color,marker in ((0,"x offset","#34749b","o"),(1,"y offset","#d85a37","x")):
        axes[0].scatter(actual[:,index],affine[:,index],s=28,alpha=.65,label=label,c=color,marker=marker)
    bound=max(.2,float(np.max(np.abs(affine)))+.015)
    axes[0].plot([-bound,bound],[-bound,bound],color="#888888",ls="--",lw=1)
    axes[0].set_xlim(-bound,bound); axes[0].set_ylim(-bound,bound)
    axes[0].set_xlabel("Known commanded offset"); axes[0].set_ylabel("Estimated equivalent offset")
    axes[0].set_title("Frozen affine response",loc="left",fontweight="bold"); axes[0].legend(frameon=False)
    for method,label,color in (("affine","Affine inverse","#34749b"),("nearest","Nearest centroid","#d85a37")):
        prediction=np.array([r["predictions"][method] for r in rows])
        errors=np.sort(np.linalg.norm(prediction-actual,axis=1))
        axes[1].step(errors,np.arange(1,len(errors)+1)/len(errors),where="post",label=label,color=color,lw=2)
    axes[1].axvline(.1,color="#888888",ls="--",lw=1,label="p90 error limit")
    axes[1].axhline(.9,color="#bbbbbb",ls=":",lw=1)
    axes[1].set_xlabel("Euclidean offset error"); axes[1].set_ylabel("Fraction of qualification trials")
    axes[1].set_title("Independent qualification error",loc="left",fontweight="bold")
    axes[1].set_ylim(0,1.04); axes[1].legend(frameon=False,loc="lower right")
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False); ax.grid(alpha=.13)
    fig.suptitle("Known-command response calibration",fontsize=17,fontweight="bold")
    fig.supxlabel("72 training + 72 independent qualification probes; model fixed before qualification.\n"
                  "Known nominal actuator regime; 2,304 steps and 144 resets. Task utility has not been evaluated.",fontsize=9)
    for ext in (".png",".pdf"): fig.savefig(output.with_suffix(ext),dpi=180,facecolor="white")
    plt.close(fig)


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit",type=Path,required=True); p.add_argument("--qualification",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a=p.parse_args(); render(a.audit,a.qualification,a.output)
