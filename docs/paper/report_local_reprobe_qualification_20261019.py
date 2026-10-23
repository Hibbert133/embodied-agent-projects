"""Read-only eight-arm Chinese report, showing every case's actual cost."""
import argparse
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

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/reproduction_reviews/local_reprobe_qualification_v1/analysis_v1"
REPORT = ROOT / "reports/local_reprobe_execution_qualification_v1_zh.md"
METHODS = ("FIXED_PD", "FIXED_PID", "LOCAL_PD", "LOCAL_PID")
LABELS = ("固定点PD", "固定点PID", "附近点PD", "附近点PID")
TASKS = {"push-v3":"推物", "reach-v3":"到达", "door-open-v3":"开门"}


def read(path):return json.loads(path.read_text(encoding="utf-8"))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x",encoding="utf-8",newline="\n") as handle:
        json.dump(value,handle,ensure_ascii=False,indent=2,allow_nan=False);handle.write("\n")


def main(path):
    run = path.parent
    assert path.resolve().is_relative_to(ROOT / "outputs/local_reprobe/qualification_v1")
    manifest = read(path);audit = read(run / "audit/record_audit.json");receipt = read(run / "audit/report_receipt.json")
    assert audit["integrity"] == "PASSED" and audit["executions"] == 72 and audit["paired_units"] == 9
    for key in ("experiment_run_id","manifest_id","source_git_commit"):
        assert manifest[key] == audit[key] == receipt[key]
    bindings = {ROOT/k:v for k,v in manifest["input_sha256"].items()}
    bindings.update({run/"collection"/k:v for k,v in audit["collection_artifact_sha256"].items()})
    bindings.update({run/"audit/record_audit.json":receipt["record_audit_sha256"],
        run/"audit/report_zh.md":receipt["report_sha256"],
        ROOT/"scripts/audit_local_reprobe_v1.py":receipt["report_source_sha256"]})
    processes = {}
    for name in ("collect","audit"):
        p = run/(name+"_process_receipt.json");processes[name] = read(p)
        assert processes[name]["returncode"] == 0
        bindings[p] = sha(p);bindings[run/(name+"_process.txt")] = processes[name]["output_sha256"]
    for p,v in bindings.items():assert sha(p) == v, str(p)
    with gzip.open(run/"collection/cases.jsonl.gz","rt",encoding="utf-8") as handle:rows = [json.loads(line) for line in handle]
    assert len(rows) == 72 and [{k:r[k] for k in a} for r,a in zip(rows,audit["rows"])] == audit["rows"]
    assert not REPORT.exists()
    OUT.mkdir(parents=True,exist_ok=False)
    font = findfont(FontProperties(family="Microsoft YaHei"),fallback_to_default=False)
    plt.rcParams.update({"font.family":"Microsoft YaHei","axes.unicode_minus":False,"font.size":11})
    arms = {r["variant"]:r for r in audit["costs"]["per_arm"]}
    fig,axes = plt.subplots(2,2,figsize=(12,8),sharex=True,sharey="row")
    colors = ("#8493a2","#356f98","#d2a252","#278d79")
    maximum = max(r["total_steps"] for r in rows)
    for col,(condition,label) in enumerate((("UNCHANGED","偏差不变"),("CHANGED","偏差变化"))):
        counts = [arms[condition+"_"+method]["complete_windows"] for method in METHODS]
        axes[0,col].bar(range(4),counts,color=colors,width=.65)
        for j,count in enumerate(counts):axes[0,col].text(j,count+.15,str(count)+"/9",ha="center")
        axes[0,col].set_ylim(0,10);axes[0,col].set_yticks(range(0,10))
        axes[0,col].set_title(label,fontsize=14)
        for j,method in enumerate(METHODS):
            group = [r for r in rows if r["variant"] == condition+"_"+method]
            assert len(group) == 9
            for r in group:
                axes[1,col].scatter(j+(r["unit"]-4)*.025,r["total_steps"],color=colors[j],
                    marker="o" if r["complete_window"] else "x",s=38,alpha=.85)
            mean = sum(r["total_steps"] for r in group)/9
            axes[1,col].hlines(mean,j-.25,j+.25,color=colors[j],lw=2)
        axes[1,col].set_ylim(0,maximum*1.12)
        axes[1,col].set_xticks(range(4),LABELS)
        for ax in axes[:,col]:ax.grid(axis="y",alpha=.15);ax.set_axisbelow(True)
    axes[0,0].set_ylabel("完整测量窗口数 / 9次执行")
    axes[1,0].set_ylabel("实际控制步：初期任务＋移动＋探测")
    fig.suptitle("固定点与附近点：全部72次执行的测量完成情况及开销",fontsize=16,y=.98)
    handles = [Line2D([0],[0],color="#526778",marker="o",ls=""),Line2D([0],[0],color="#526778",marker="x",ls=""),Line2D([0],[0],color="#526778",lw=2)]
    fig.legend(handles,["完整窗口","未完成窗口（含提前结束）","组内平均实际步数"],loc="lower center",ncol=3,bbox_to_anchor=(.5,.04))
    fig.text(.5,.013,"每个点是一例实际执行。步数是已发生的开销，不是任务损失；失败或提前结束不会被换成500步。",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.10,1,.94))
    figure = OUT/"all_case_outcomes_and_costs_zh.png";fig.savefig(figure,dpi=160);plt.close(fig)
    case_rows = []
    for r in rows:
        result = None if r["reacquisition"] is None else r["reacquisition"]["public"]
        case_rows.append({**{k:r[k] for k in ("unit","task","seed","variant","complete_window","collection_stop_reason","total_steps","reposition_steps","probe_steps","success")},
            "anchor":None if result is None else result["measurement_anchor"],
            "preprobe_compensation":None if result is None else result["relocation_evidence"]})
    body = (run/"audit/report_zh.md").read_text(encoding="utf-8").split("\n",1)[1]
    for token,label in TASKS.items():body = body.replace("|"+token+"|","|"+label+"|")
    lines = ["# 附近测量点：执行资格与完整成本", "",
        f"**附近点PID执行资格：{audit['qualification']}；记录审计通过。新位置的测量模型与任务收益仍未验证。**", "",
        "固定点是所有任务返回同一位置；附近点根据介入时看到的手部和物体位置选择测量目标。PD使用当前位置偏差和最近位移，PID再累积持续偏差作补偿。所有方法使用同一移动步数上限和精度门槛。", "",
        "|偏差条件|固定点PD|固定点PID|附近点PD|附近点PID|", "|---|---:|---:|---:|---:|"]
    for condition,label in (("UNCHANGED","不变"),("CHANGED","变化")):
        lines.append("|"+label+"|"+"|".join(str(arms[condition+"_"+m]["complete_windows"])+"/9" for m in METHODS)+"|")
    lines += ["",f"![全部72次执行](../{figure.relative_to(ROOT).as_posix()})","",body,"",
        f"采集进程{processes['collect']['wall_ns']/1e9:.3f}秒；只读审计进程{processes['audit']['wall_ns']/1e9:.3f}秒。报告没有新增物理步骤、拟合或API调用。", "",
        "完整软件检查及仪表化夹具费用保存在outputs/local_reprobe/validation_v1；这些软件费用不冒充全部开发成本。过程中的Gymnasium与MetaWorld提示原样保留。", "",
        "后续校准与新颖性要求见[研究边界](../docs/research/selected_anchor_calibration_scope_v1_zh.md)。", "",
        f"[冻结协议](../docs/protocols/local_reprobe_execution_qualification_v1.md)；[原始记录与审计](../{run.relative_to(ROOT).as_posix()})。", ""]
    with REPORT.open("x",encoding="utf-8",newline="\n") as handle:handle.write("\n".join(lines))
    metrics = OUT/"all_case_outcomes_and_compensation.json"
    write(metrics,{"scope":"ALL_CASES_READ_ONLY_DESCRIPTION","cases":case_rows,"per_arm":audit["costs"]["per_arm"],"new_physical_steps":0,"new_api_calls":0})
    for p in (path,run/"audit/report_receipt.json"):bindings[p] = sha(p)
    write(OUT/"report_receipt.json",{"source_sha256":sha(Path(__file__)),
        "input_sha256":{p.relative_to(ROOT).as_posix():v for p,v in bindings.items()},
        "output_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (REPORT,metrics,figure)},
        "plotting_python":sys.version,"matplotlib":matplotlib.__version__,"font_sha256":sha(Path(font)),"new_physical_steps":0,"new_api_calls":0})
    print(json.dumps({"report":str(REPORT),"verified_inputs":len(bindings),"qualification":audit["qualification"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest",type=Path,required=True)
    main(parser.parse_args().manifest.resolve())
