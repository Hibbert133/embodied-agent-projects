"""Read-only descriptive report for the completed nine-case qualification."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs/physical_reprobe/qualification_v1/physical_reprobe_20261019T120619Z_e6ffa2f4deae"
OUT = ROOT / "outputs/reproduction_reviews/physical_reprobe_qualification_v1/analysis_v1"
REPORT = ROOT / "reports/physical_reprobe_execution_qualification_v1_zh.md"
TASKS = {"push-v3": "推物", "reach-v3": "到达", "door-open-v3": "开门"}
REASONS = {"COMPLETE_UNQUALIFIED": "取得完整窗口", "ANCHOR_NOT_REACHED": "64步内未到测量位置",
    "ENDED_DURING_REPOSITION": "移动途中任务已成功", "ENDED_BEFORE_BOUNDARY": "介入前任务已成功"}


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""): h.update(block)
    return h.hexdigest()


def read(path): return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False);f.write("\n")


def main():
    manifest = read(RUN / "manifest.json");audit = read(RUN / "audit/record_audit.json")
    receipt = read(RUN / "audit/report_receipt.json")
    assert manifest["manifest_id"] == "612f593437f5e8f6ecd00a0d1d14e009daba92b661297d89ac642ed9c3ddbf61"
    assert audit["integrity"] == "PASSED" and audit["qualification"] == "QUALIFIED"
    for k in ("experiment_run_id", "source_git_commit", "manifest_id"):
        assert manifest[k] == audit[k] == receipt[k]
    bindings = {ROOT/name:value for name,value in manifest["input_sha256"].items()}
    bindings.update({RUN/"collection"/name:value for name,value in audit["collection_artifact_sha256"].items()})
    bindings.update({RUN/"audit/record_audit.json":receipt["record_audit_sha256"],
                    RUN/"audit/report_zh.md":receipt["report_sha256"],
                    ROOT/"scripts/audit_physical_reprobe_v1.py":receipt["report_source_sha256"]})
    for path,value in bindings.items(): assert sha(path) == value, str(path)
    processes = {}
    for name in ("collect", "audit"):
        p = read(RUN / (name+"_process_receipt.json"));assert p["returncode"] == 0
        log = RUN / (name+"_process.txt");assert sha(log) == p["output_sha256"]
        processes[name] = p;bindings[log] = sha(log)
        bindings[RUN/(name+"_process_receipt.json")] = sha(RUN/(name+"_process_receipt.json"))
    with gzip.open(RUN/"collection/cases.jsonl.gz", "rt", encoding="utf-8") as f: rows = [json.loads(line) for line in f]
    assert len(rows) == audit["executions"] == 9
    assert [{k:r[k] for k in a} for r,a in zip(rows,audit["rows"])] == audit["rows"]
    assert all(r["success"] for r in rows if r["collection_stop_reason"].startswith("ENDED_"))
    metrics = []
    for r in rows:
        xyz = r["final_observation"]["observation"][:3]
        metrics.append({"seed":r["seed"], "task":r["task"], "complete_window":r["complete_window"],
            "reposition_steps":r["reposition_steps"], "probe_steps":r["probe_steps"],
            "final_anchor_max_coordinate_error_m":max(abs(a-b) for a,b in zip(xyz,(0.,.6,.25))),
            "final_hand_object_distance_m":math.dist(xyz,r["final_observation"]["observation"][4:7])})
    movement = sum(r["reposition_steps"] for r in rows);probing = sum(r["probe_steps"] for r in rows)
    total = sum(r["total_steps"] for r in rows);complete = [r for r in rows if r["complete_window"]]
    successful_cost = sum(r["reposition_steps"]+r["probe_steps"] for r in complete)/len(complete)
    assert total == audit["costs"]["new_control_steps"] and total == 691
    assert (movement,probing,len(complete)) == (320,40,5)
    if OUT.exists():
        old = read(OUT/"report_receipt.json")
        for name,value in old["output_sha256"].items(): assert sha(ROOT/name) == value, "edited derived output: "+name
    else:
        assert not REPORT.exists();OUT.mkdir(parents=True)
    font_path = findfont(FontProperties(family="Microsoft YaHei"), fallback_to_default=False)
    plt.rcParams.update({"font.family":"Microsoft YaHei", "axes.unicode_minus":False, "font.size":10})
    fig, axes = plt.subplots(3,3,figsize=(13,9),sharex=True,sharey=True)
    colors = {"FIXED_PROBE":"#747d8c", "POLICY":"#747d8c", "REPOSITION":"#d98324", "WARM_PROBE":"#246bb2"}
    maximum_distance = 0.
    for ax,r in zip(axes.flat,rows):
        observations = [r["prefix"]["public"]["events"][0]["payload"]["initial"]["observation"]]
        observations += [p["after"]["observation"] for p in r["physical_rows"]]
        distances = [max(abs(a-b) for a,b in zip(obs[:3],(0.,.6,.25))) for obs in observations]
        maximum_distance = max(maximum_distance, max(distances))
        for i,p in enumerate(r["physical_rows"]):
            ax.plot([i,i+1],distances[i:i+2],color=colors[p["phase"]],linewidth=2)
        ax.axhline(.015,color="#32485e",linestyle=":",linewidth=1)
        ax.axvline(r["planned_boundary"],color="#8b9299",linestyle="--",linewidth=1)
        ax.scatter([len(distances)-1],[distances[-1]],s=22,color=colors[r["physical_rows"][-1]["phase"]],zorder=3)
        ax.set_title(f"{TASKS[r['task']]} · 种子{r['seed']} · 第{r['planned_boundary']}步介入\n{REASONS[r['collection_stop_reason']]}",fontsize=10)
        ax.set_xlim(0,132);ax.grid(alpha=.14)
    axes[0,0].set_ylim(0,1.05*maximum_distance)
    assert all(ax.get_ylim()[1] >= maximum_distance for ax in axes.flat)
    for ax in axes[:,0]: ax.set_ylabel("距测量位置的最大坐标误差 / 米")
    for ax in axes[-1,:]: ax.set_xlabel("累计实际控制步")
    fig.suptitle("全部9个案例：任务途中移动与重新探测",fontsize=16,y=.99)
    from matplotlib.lines import Line2D
    fig.legend([Line2D([0],[0],color=c,lw=2) for c in ("#747d8c","#d98324","#246bb2")],
               ["初始探测及任务执行","移到测量位置","新的8步探测"],loc="lower center",ncol=3,bbox_to_anchor=(.5,.025))
    fig.text(.5,.008,"竖虚线：计划介入步；横点线：进入探测前的位置门槛。位置门槛还须与运动稳定、物体间距条件共同满足。",ha="center",fontsize=10)
    fig.tight_layout(rect=(0,.07,1,.95));figure=OUT/"anchor_trajectories_zh.png";fig.savefig(figure,dpi=160);plt.close(fig)
    write(OUT/"descriptive_metrics.json",{"scope":"POSTHOC_DESCRIPTION_ONLY_NO_FITS_OR_PHYSICS", "rows":metrics,
        "reposition_steps":movement,"probe_steps":probing,"before_reprobe_steps":total-movement-probing,
        "complete_window_mean_acquisition_steps":successful_cost,"new_api_calls":0,"new_physical_steps":0})
    lines=["# 中途重新探测：9案例执行验证", "",
        "**本轮通过执行可用性门：5/9个案例取得完整的新探测窗口，覆盖推物、到达、开门三种任务。记录审计通过。**",
        "这回答了‘机器人能否在任务做到一半时，实际移到测量位置再探测’；尚未证明这些数据能准确估计偏差，也未证明任务收益或算法新颖性。5/9是窗口获取数量，不是任务成功率。", "",
        "## 方法与完整结果", "",
        "每个案例从一次初始重置开始。C4/C8分别表示根据最初4/8步探测数据得到的纠正；用C8执行到计划介入时刻，再最多用64步移动、8步试动。环境和噪声状态连续。窗口完整或操作停止后即结束采集，没有后续完整任务对照，也没有在线LLM参与。", "",
        "|任务|种子|计划介入步|结果|移动步|新探测步|总控制步|", "|---|---:|---:|---|---:|---:|---:|"]
    for r in rows: lines.append(f"|{TASKS[r['task']]}|{r['seed']}|{r['planned_boundary']}|{REASONS[r['collection_stop_reason']]}|{r['reposition_steps']}|{r['probe_steps']}|{r['total_steps']}|")
    lines += ["", "两个开门案例达到移动上限；推物22406在移动途中成功，到达22407在第59步、计划介入前成功。四者均留在分母，不补选、不按探测成功计算。不同介入时刻使用不同种子，不能据此断言早探测优于晚探测。", "",
        "![全部9个案例的真实轨迹](../outputs/reproduction_reviews/physical_reprobe_qualification_v1/analysis_v1/anchor_trajectories_zh.png)", "",
        "横点线仅表示进入探测前的位置条件；探测期间允许位置变化，另按高度和物体间距检查范围。图中显示的是可见观测，并不证明隐状态与初始重置一致。", "",
        "## 成本与审计", "",
        f"新增总控制步{total}：介入前{total-movement-probing}，移动{movement}，新探测{probing}。成功取得窗口的5例，移动加探测平均{successful_cost:.1f}步；成本统计仍保留其余4例。受控初始重置9次，加工厂目标生成共459次；请求及完成仿真帧均为232,955。",
        "初始策略查询259次，C4/C8拟合18次（nfev合计18）；中途拟合、API调用、名义模型重训和策略权重更新均为0。",
        f"采集进程{processes['collect']['wall_ns']/1e9:.3f}秒；独立审计进程{processes['audit']['wall_ns']/1e9:.3f}秒。审计额外重算259次策略查询和18次初始拟合，无新增物理步。",
        "沿用C8所需完整历史名义费用：3,840控制步、480受控重置、24,480全部重置、12,259,200帧。本轮按9案例摊销426.667历史控制步/案例；旧资格与研究仍是另列的历史开发费用。软件测试夹具费用见冻结检查记录，早先一次未持久保存的定向测试费用不在该记录中，因此不把记录冒称为整个开发阶段总成本。",
        "审计核对3,703条主事件和27份私有状态见证，重建保存的选择、执行顺序、连续状态、噪声及费用；未发现协议内的预算、衔接或信息边界违规。它依赖冻结采集器的可信执行，并非外部物理真值认证。",
        "仿真日志保留Gymnasium观测空间与MetaWorld动作裁剪提示；未删改提示或通过静默重跑替换案例。", "",
        "## 下一步与结论边界", "",
        "执行可用性已得到这9例的有限支持。下一步需要独立的中途响应校准和资格数据，不能把本轮窗口直接送入仅适用于初始重置的C8模型。后续任务实验须至少比较继续C8、仅移动后继续C8、移动并探测但保持C8、移动并探测后更新，并收取全部移动和探测费用。",
        "本轮不能作为CCF A算法创新或投稿就绪证据；新方法、强基线收益、独立多任务流、消融和完整论文要求仍未完成。", "",
        f"冻结提交：`{manifest['source_git_commit']}`。清单：`{manifest['manifest_id']}`。",
        f"原始记录与独立审计：[运行目录](../{RUN.relative_to(ROOT).as_posix()})；[冻结协议](../docs/protocols/physical_reprobe_execution_qualification_v1.md)。全仓库1,187项测试及编译、依赖、秘密与差异检查通过。", ""]
    with REPORT.open("w",encoding="utf-8",newline="\n") as f:f.write("\n".join(lines))
    bindings[RUN/"manifest.json"] = sha(RUN/"manifest.json");bindings[RUN/"audit/report_receipt.json"] = sha(RUN/"audit/report_receipt.json")
    write(OUT/"report_receipt.json",{"source_sha256":sha(Path(__file__)), "input_sha256":{p.relative_to(ROOT).as_posix():v for p,v in bindings.items()},
        "output_sha256":{p.relative_to(ROOT).as_posix():sha(p) for p in (REPORT,figure,OUT/"descriptive_metrics.json")},
        "plotting_python":sys.version,"matplotlib":matplotlib.__version__,"font_sha256":sha(Path(font_path)),
        "new_physical_steps":0,"new_parameter_fits":0,"new_api_calls":0})
    print(json.dumps({"report":str(REPORT),"figure":str(figure),"verified_inputs":len(bindings)}))


if __name__ == "__main__": main()
