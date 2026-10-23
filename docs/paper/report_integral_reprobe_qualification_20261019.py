"""Read-only Chinese reporting of every frozen four-arm reacquisition case."""
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
OUT = ROOT / "outputs/reproduction_reviews/integral_reprobe_qualification_v1/analysis_v1"
REPORT = ROOT / "reports/integral_reprobe_execution_qualification_v1_zh.md"
TASKS = {"push-v3":"推物", "reach-v3":"到达", "door-open-v3":"开门"}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def main(path):
    run = path.parent
    assert path.resolve().is_relative_to(ROOT / "outputs/integral_reprobe/qualification_v1")
    manifest = read(path)
    audit = read(run / "audit/record_audit.json")
    receipt = read(run / "audit/report_receipt.json")
    assert audit["integrity"] == "PASSED" and audit["executions"] == 36 and audit["paired_units"] == 9
    for key in ("experiment_run_id", "manifest_id", "source_git_commit"):
        assert manifest[key] == audit[key] == receipt[key]
    bindings = {ROOT / k:v for k,v in manifest["input_sha256"].items()}
    bindings.update({run / "collection" / k:v for k,v in audit["collection_artifact_sha256"].items()})
    bindings.update({run / "audit/record_audit.json":receipt["record_audit_sha256"],
                     run / "audit/report_zh.md":receipt["report_sha256"],
                     ROOT / "scripts/audit_integral_reprobe_v1.py":receipt["report_source_sha256"]})
    processes = {}
    for name in ("collect", "audit"):
        p = run / (name + "_process_receipt.json")
        processes[name] = read(p)
        assert processes[name]["returncode"] == 0
        bindings[p] = sha(p)
        bindings[run / (name + "_process.txt")] = processes[name]["output_sha256"]
    for p,v in bindings.items():
        assert sha(p) == v, str(p)
    with gzip.open(run / "collection/cases.jsonl.gz", "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert len(rows) == 36
    assert [{k:r[k] for k in a} for r,a in zip(rows, audit["rows"])] == audit["rows"]
    assert not REPORT.exists()
    OUT.mkdir(parents=True, exist_ok=False)
    font = findfont(FontProperties(family="Microsoft YaHei"), fallback_to_default=False)
    plt.rcParams.update({"font.family":"Microsoft YaHei", "axes.unicode_minus":False, "font.size":10})
    curves = []
    compensation = []
    for r in rows:
        observations = [r["prefix"]["public"]["events"][0]["payload"]["initial"]["observation"]]
        observations += [p["after"]["observation"] for p in r["physical_rows"]]
        values = [max(abs(x-y) for x,y in zip(obs[:3], (0., .6, .25))) for obs in observations]
        curves.append({"seed":r["seed"], "variant":r["variant"], "anchor_error_m":values})
        result = r["reacquisition"]
        learned = None if result is None else result["public"]["relocation_evidence"]
        compensation.append({"seed":r["seed"], "variant":r["variant"], "complete_window":r["complete_window"],
                             "preprobe_relocation_evidence":learned})
    maximum = max(max(c["anchor_error_m"]) for c in curves)
    xmax = max(max(r["planned_boundary"], r["total_steps"]) for r in rows) + 3
    lookup = {(c["seed"], c["variant"]):c["anchor_error_m"] for c in curves}
    figures = []
    for condition,label in (("UNCHANGED", "偏差不变"), ("CHANGED", "偏差变化")):
        fig,axes = plt.subplots(3,3,figsize=(13,9),sharex=True,sharey=True)
        for ax,index in zip(axes.flat,range(0,36,4)):
            pair = [r for r in rows[index:index+4] if r["variant"].startswith(condition+"_")]
            first = pair[0]
            count = first["approach"]["public"]["completed_steps"]
            for r,color,marker in zip(pair,("#ce7e26", "#216f9c"),("o","x")):
                values = lookup[r["seed"], r["variant"]]
                if r is first:
                    ax.plot(range(count+1), values[:count+1], color="#7e8792", lw=2)
                ax.plot(range(count,len(values)), values[count:], color=color, lw=2)
                ax.scatter([len(values)-1], [values[-1]], color=color, marker=marker, s=24, zorder=3)
            flags = ["有" if r["complete_window"] else "无" for r in pair]
            ax.set_title(f"{TASKS[first['task']]} · 种子{first['seed']} · 第{first['planned_boundary']}步\n完整窗口：原PD{flags[0]} / 加积分PID{flags[1]}", fontsize=10)
            ax.axvline(first["planned_boundary"], ls="--", color="#8b9299", lw=1)
            ax.axhline(.015, ls=":", color="#32485e", lw=1)
            ax.grid(alpha=.14)
            ax.set_xlim(0,xmax)
        axes[0,0].set_ylim(0,maximum*1.05)
        assert all(ax.get_ylim()[1] >= maximum for ax in axes.flat)
        for ax in axes[:,0]:ax.set_ylabel("距测量位置的最大坐标误差 / 米")
        for ax in axes[-1,:]:ax.set_xlabel("累计实际控制步")
        fig.suptitle(label+"：原PD与增加积分的PID能否完成重新探测",fontsize=16,y=.99)
        fig.legend([Line2D([0],[0],color=c,lw=2) for c in ("#7e8792","#ce7e26","#216f9c")],
                   ["相同介入前轨迹","原PD","加积分PID"],loc="lower center",ncol=3,bbox_to_anchor=(.5,.025))
        fig.text(.5,.008,"竖虚线：预定介入步；横点线：进入探测的位置门槛，另需满足运动稳定与物体间距条件。",ha="center",fontsize=10)
        fig.tight_layout(rect=(0,.07,1,.95))
        p = OUT / (condition.lower()+"_trajectories_zh.png")
        fig.savefig(p,dpi=160)
        plt.close(fig)
        figures.append(p)
    arms = {r["variant"]:r for r in audit["costs"]["per_arm"]}
    body = (run / "audit/report_zh.md").read_text(encoding="utf-8").split("\n",1)[1]
    for token,label in TASKS.items():body = body.replace("|"+token+"|", "|"+label+"|")
    summary = "；".join(f"{label}：原PD {arms[c+'_PD']['complete_windows']}/9，加积分PID {arms[c+'_PID']['complete_windows']}/9"
                       for c,label in (("UNCHANGED","偏差不变"),("CHANGED","偏差变化")))
    lines = ["# 积分反馈重新探测：全部四组结果", "", "**"+summary+"。**", "",
             "C8是用最开始8步数据算出的纠正。PD看当前偏差及最近位移；PID再记住持续偏差并累积补偿。重新探测是先移到测量位置，再做8步测试动作。完整窗口不等于任务成功。", ""]
    for p in figures:lines += [f"![全部配对轨迹](../{p.relative_to(ROOT).as_posix()})", ""]
    lines += [body, "", "两图坐标范围相同，全部9个单元及提前结束、未到位案例保留。窗口入口的位置门槛不要求在后续探测脉冲中继续满足。", "",
              f"采集进程{processes['collect']['wall_ns']/1e9:.3f}秒；只读审计进程{processes['audit']['wall_ns']/1e9:.3f}秒。未为报告新增物理步骤、拟合或API调用。", "",
              "软件检查及原生夹具费用另存于outputs/integral_reprobe/validation_v1；这些夹具费用不冒充完整开发计算账单。过程日志的Gymnasium和MetaWorld提示原样保留。", "",
              f"[冻结协议](../docs/protocols/integral_reprobe_execution_qualification_v1.md)；[原始记录与审计](../{run.relative_to(ROOT).as_posix()})。", ""]
    with REPORT.open("x",encoding="utf-8",newline="\n") as handle:handle.write("\n".join(lines))
    metrics = OUT / "descriptive_curves_and_compensation.json"
    write(metrics,{"scope":"ALL_CASES_READ_ONLY_DESCRIPTION", "curves":curves, "preprobe_compensation":compensation,
                   "per_arm":audit["costs"]["per_arm"], "new_physical_steps":0, "new_api_calls":0})
    for p in (path, run / "audit/report_receipt.json"):bindings[p] = sha(p)
    write(OUT / "report_receipt.json", {"source_sha256":sha(Path(__file__)),
        "input_sha256":{p.relative_to(ROOT).as_posix():v for p,v in bindings.items()},
        "output_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (REPORT,metrics,*figures)},
        "plotting_python":sys.version,"matplotlib":matplotlib.__version__,"font_sha256":sha(Path(font)),
        "new_physical_steps":0,"new_api_calls":0})
    print(json.dumps({"report":str(REPORT), "verified_inputs":len(bindings), "qualification":audit["qualification"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    main(parser.parse_args().manifest.resolve())
