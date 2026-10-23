"""Render the audited frame diagnostic in Chinese; no simulation or API calls."""
import argparse
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

LABELS = {
    "FIXED_A_PREFIX4":"共同四步 + 固定 A", "FIXED_B_PREFIX4":"共同四步 + 固定 B",
    "UNCORRECTED_PREFIX4":"共同四步 + 不纠正", "MODEL_REPEAT8":"重复八步 + 标准 ARX",
    "MODEL_REVERSE8":"反向八步 + 标准 ARX", "MODEL_SYM16":"完整十六步 + 标准 ARX",
    "LEGACY_AFFINE16":"完整十六步 + 旧仿射", "LEGACY_NEAREST16":"完整十六步 + 旧最近邻",
    "FIXED_A_REVERSE8":"反向八步 + 固定 A", "FIXED_B_REVERSE8":"反向八步 + 固定 B", "NO_PROBE":"不探测、不纠正",
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(manifest_path, audit_path, prefix):
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    fields = ("experiment_run_id","manifest_id","source_git_commit")
    if audit["integrity"] != "PASSED" or any(manifest[k] != audit[k] for k in fields):
        raise ValueError("plot requires a matching completed independent audit")
    for name, digest in audit["artifact_sha256"].items():
        if sha(manifest_path.parent/name) != digest:
            raise ValueError("audited data changed")
    methods = manifest["config"]["methods"]
    if set(methods) != set(LABELS):
        raise ValueError("plot population changed")
    paths = [prefix.with_suffix(ext) for ext in (".png",".svg",".json")]
    if any(p.exists() for p in paths):
        raise FileExistsError("figure output already exists")
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif":["Microsoft YaHei"],"axes.unicode_minus":False,
        "font.size":11,"svg.fonttype":"path","axes.spines.top":False,"axes.spines.right":False})
    stats = audit["statistics"]
    y = np.arange(len(methods)); values = [stats["methods"][name] for name in methods]
    first = np.array([v["per_context_successful"]["FRAME0"] for v in values])
    second = np.array([v["per_context_successful"]["FRAME90"] for v in values])
    online = np.array([v["mean_online_steps"] for v in values])
    offline = np.array([v["mean_amortized_steps"]-v["mean_online_steps"] for v in values])
    fig, axes = plt.subplots(1,2,figsize=(18,9.2),gridspec_kw={"width_ratios":[1,1.08],"wspace":.25})
    left,right=axes
    left.barh(y,first,color="#287DAD",height=.62,label="FRAME0（8 单元）")
    left.barh(y,second,left=first,color="#D27841",height=.62,label="FRAME90（8 单元）")
    for i,(a,b) in enumerate(zip(first,second)):
        if a: left.text(a/2,i,str(a),ha="center",va="center",color="white",fontsize=10)
        if b: left.text(a+b/2,i,str(b),ha="center",va="center",color="white",fontsize=10)
        left.text(a+b+.18,i,f"{a+b}/16",va="center",fontsize=10)
    left.set(yticks=y,yticklabels=[LABELS[n] for n in methods],xlim=(0,18.4),xticks=[0,4,8,12,16],
             xlabel="任务成功数",title="全部对照：任务成功按上下文拆分")
    left.invert_yaxis(); left.legend(loc="upper center",bbox_to_anchor=(.48,-.1),ncol=2,frameon=False)
    right.barh(y,online,color="#365B72",height=.62,label="在线总步数")
    right.barh(y,offline,left=online,color="#BEC9CF",height=.62,label="旧离线资源摊销")
    for i,(a,b) in enumerate(zip(online,offline)):
        right.text(a+b+5,i,f"{a+b:.1f}",va="center",fontsize=10)
    right.set(yticks=y,yticklabels=[],xlim=(0,max(online+offline)*1.17),
              xlabel="每单元平均环境步数",title="完整成本：在线执行 + 离线摊销")
    right.invert_yaxis(); right.legend(loc="upper center",bbox_to_anchor=(.48,-.1),ncol=2,frameon=False)
    for axis in axes:
        axis.set_axisbelow(True); axis.grid(axis="x",alpha=.17)
    structural="通过" if stats["structural_pass"] else "未通过"
    standard="通过" if stats["standard_baseline_pass"] else "未通过"
    fig.suptitle("坐标框架构造例：探测信息是否改变有用的纠正动作？",fontsize=19,x=.55,y=.965)
    fig.text(.55,.913,f'结构见证 {stats["disjoint_action_seeds"]}/8；结构门{structural}；标准基线门{standard}；API 0 次',ha="center",fontsize=12)
    fig.text(.08,.09,"先验访问方法统一加计 144 步/9 次重置：完整旧离线资源 2,304 步/144 次重置，按 16 单元摊销。",fontsize=11)
    fig.text(.08,.057,"构造例、8 个独立任务种子簇；每格一次噪声实现。成功集不是稳定行动标签；结果不是算法创新证据。",fontsize=11)
    fig.text(.08,.025,f'冻结提交 {manifest["source_git_commit"][:12]}；物理收集 {audit["physical_steps"]:,} 步/{audit["environment_resets"]} 次初始重置。',fontsize=9,color="#5F666B")
    fig.subplots_adjust(left=.18,right=.97,top=.86,bottom=.23)
    prefix.parent.mkdir(parents=True,exist_ok=True)
    fig.savefig(paths[0],dpi=200,facecolor="white")
    fig.savefig(paths[1],facecolor="white")
    # Matplotlib emits spaces before newlines in SVG path attributes. Normalize
    # that serialization before hashing; the path coordinates are unchanged.
    svg = "\n".join(line.rstrip() for line in paths[1].read_text(encoding="utf-8").splitlines())+"\n"
    paths[1].write_bytes(svg.encode("utf-8"))
    plt.close(fig)
    metadata = {**{k:manifest[k] for k in fields},"audit_sha256":sha(audit_path),"render_tool_sha256":sha(Path(__file__)),
        "labels":LABELS,"methods":stats["methods"],"artifact_sha256":{p.name:sha(p) for p in paths[:2]},
        "physical_collection_rerun":False,"api_calls":0,"language":"zh-CN","svg_trailing_whitespace_removed":True}
    paths[2].write_text(json.dumps(metadata,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(paths[0])


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,required=True); parser.add_argument("--audit",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True); args=parser.parse_args()
    render(args.manifest.resolve(),args.audit.resolve(),args.output.resolve())
