"""Analytic clipped-policy image witness; no robot experiment or data fitting."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


def render(output):
    if output.exists():raise FileExistsError("analytic figure already exists")
    matrix=np.array([[.25,-.25],[.25,.25]])
    controller=np.linalg.inv(matrix)
    actions=np.array([[-1,-1],[-1,1],[1,-1],[1,1],[0,0]])
    sent=np.clip(actions@controller.T,-1,1)
    witness=np.array([.5,0.]);actual=np.clip(controller@witness,-1,1)
    # The image is the full square: M maps every u in the square into a in [-.5,.5]^2.
    assert np.array_equal(actual,[1.,-1.])
    assert np.max(np.sum(np.abs(matrix),axis=1))==.5
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei"],"axes.unicode_minus":False,"font.size":12,"svg.fonttype":"path"})
    fig,axes=plt.subplots(1,2,figsize=(12,6.3))
    for axis in axes:
        axis.fill([-1,1,1,-1],[-1,-1,1,1],color="#EDF0F2")
        axis.axhline(0,color="#CAD0D4",linewidth=1);axis.axvline(0,color="#CAD0D4",linewidth=1)
        axis.set(xlim=(-1.18,1.18),ylim=(-1.18,1.18),aspect="equal")
        axis.spines[["top","right"]].set_visible(False)
    axes[0].scatter(actions[:,0],actions[:,1],color="#267599",s=70,label="五个注册查询")
    axes[0].scatter(*witness,color="#C56C3F",marker="*",s=190,label="合法内部动作")
    axes[0].annotate("a = (0.5, 0)",witness,xytext=(12,-27),textcoords="offset points",color="#C56C3F")
    axes[0].set(title="原始政策输入域",xlabel="政策 x",ylabel="政策 y")
    diamond=np.array([[-1,0],[0,-1],[1,0],[0,1]])
    axes[1].fill(diamond[:,0],diamond[:,1],color="#B9D7E4",label="五点发送像的凸包")
    axes[1].scatter(sent[:,0],sent[:,1],color="#267599",s=70)
    axes[1].scatter(*actual,color="#C56C3F",marker="*",s=190,label="真实发送命令")
    axes[1].annotate("u = (1, -1)",actual,xytext=(-130,20),textcoords="offset points",color="#C56C3F")
    axes[1].set(title="截断后的发送输入域",xlabel="发送 x",ylabel="发送 y")
    for axis in axes:axis.legend(loc="upper center",bbox_to_anchor=(.5,-.13),frameon=False,fontsize=10)
    fig.suptitle("角点像不自动覆盖连续政策的截断发送域",fontsize=17,y=.96)
    fig.text(.09,.072,"合法缓存 M = [[0.25, -0.25], [0.25, 0.25]]；C = inv(M)；最小奇异值约 0.3536。",fontsize=11)
    fig.text(.09,.028,"解析作用域见证，不是新任务失败、信息泄漏或预算违规；新增仿真／API／拟合均为零。",fontsize=11)
    fig.subplots_adjust(top=.84,bottom=.32,wspace=.3)
    output.mkdir(parents=True,exist_ok=False)
    fig.savefig(output/"figure.png",dpi=180,facecolor="white");fig.savefig(output/"figure.svg",facecolor="white");plt.close(fig)
    svg=output/"figure.svg";svg.write_bytes(("\n".join(s.rstrip() for s in svg.read_text(encoding="utf-8").splitlines())+"\n").encode("utf-8"))
    metadata={"analysis_id":"clipped_action_image_counterexample_v1","source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cached_matrix":matrix.tolist(),"controller":controller.tolist(),"raw_queries":actions.tolist(),"sent_queries":sent.tolist(),
        "witness_raw_action":witness.tolist(),"witness_sent_command":actual.tolist(),"minimum_singular_value":float(np.linalg.svd(matrix,compute_uv=False)[-1]),
        "full_image_area":4.,"finite_query_hull_area":2.,"claim_scope":"Exact analytic example only, not a measured robot incidence or certified response contract.",
        "new_environment_steps":0,"new_api_calls":0,
        "artifact_sha256":{name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in ("figure.png","figure.svg")}}
    (output/"figure.json").write_bytes((json.dumps(metadata,indent=2)+"\n").encode("utf-8"))
    print(json.dumps({"output":str(output),"analytic_witness":actual.tolist()}))


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output",type=Path,required=True);a=p.parse_args();render(a.output.resolve())
