"""Render audited JSON only; use the separate plotting runtime, never a policy."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
LABELS = {"NO_PROBE": "直接做", "ALWAYS8": "每次重测8步", "ALWAYS16_OLD": "旧估计器测16步", "PASSIVE_RECENT8": "8步拟合无效即停",
    "PASSIVE8_KEEP": "8步无效更新则保留", "PASSIVE64_PERIODIC16_KEEP": "每16步近期64项更新保留", "UNCERTAINTY4": "考虑旧参数误差的4步检查",
    "TASK_IVR4": "当前单指令信息检查", "TASK_HISTORY_IVR4": "自己历史查询信息检查"}


def read(path): return json.loads(path.read_text(encoding="utf-8"))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main(path, phase):
    folder = path.parent/phase.lower(); summary = read(folder/"summary.json"); manifest = read(path)
    for name in ("audit.json", "statistics.json"):
        audit = read(path.parent/(phase.lower()+"_audit")/name)
        if audit["integrity"] != "PASSED" or audit["summary_sha256"] != sha(folder/"summary.json"):
            raise ValueError("matching audited summary required")
    target = path.parent/(phase.lower()+"_figure_v1"); target.mkdir()
    font = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    methods = manifest["config"]["methods"]; cells = [summary["statistics"]["methods"][m] for m in methods]
    positions = np.arange(len(methods)); names = [LABELS[m] for m in methods]
    colors = ["#576b7f", "#317f97", "#7b83a8", "#b77e71", "#45a18e", "#207b67", "#c59a45", "#a47baf", "#77519a"]
    plt.rcParams.update({"svg.fonttype": "path", "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(2, 2, figsize=(19, 13), dpi=200)
    def style(ax, title):
        ax.set_yticks(positions, names, fontproperties=font, fontsize=13)
        ax.invert_yaxis(); ax.set_title(title, fontproperties=font, fontsize=19, pad=15)
        ax.tick_params(axis="x", labelsize=12); ax.grid(axis="x", alpha=.18); ax.set_axisbelow(True)
    success = [100*c["successes"]/c["cases"] for c in cells]
    axes[0, 0].barh(positions, success, color=colors, height=.65)
    style(axes[0, 0], "任务成功率（%）")
    axes[0, 0].set_xlim(0, 116); axes[0, 0].set_xticks([0, 25, 50, 75, 100])
    for i, (value, c) in enumerate(zip(success, cells)): axes[0, 0].text(value+1, i, f"{c['successes']}/{c['cases']}", va="center", fontsize=12)
    loss = [c["mean_deadline_loss"] for c in cells]
    axes[0, 1].barh(positions, loss, color=colors, height=.65); style(axes[0, 1], "平均截止损失（失败／停止计500）")
    axes[0, 1].set_xlim(0, max(loss)*1.2)
    for i, value in enumerate(loss): axes[0, 1].text(value+max(loss)*.012, i, f"{value:.1f}", va="center", fontsize=12)
    actual = [c["mean_total_steps"] for c in cells]; amortized = [c["mean_amortized_actual_steps"] for c in cells]
    axes[1, 0].barh(positions-.17, actual, height=.3, color="#557e98", label="实际在线步数")
    axes[1, 0].barh(positions+.17, amortized, height=.3, color="#bd9458", label="加完整来源摊销")
    style(axes[1, 0], "平均实际交互成本（环境步）")
    axes[1, 0].set_xlim(0, max(amortized)*1.08)
    axes[1, 0].legend(prop=FontProperties(fname="C:/Windows/Fonts/msyh.ttc", size=12), loc="lower right")
    probes = [c["mean_fixed_probe_steps"] for c in cells]
    axes[1, 1].barh(positions, probes, height=.65, color=colors); style(axes[1, 1], "平均专门探测步数（正常任务动作不重复计费）")
    axes[1, 1].set_xlim(0, max(probes)*1.2)
    for i, value in enumerate(probes): axes[1, 1].text(value+.12, i, f"{value:.2f}", va="center", fontsize=12)
    title = "强被动与历史查询参考：主实验" if phase == "MAIN" else "主机预检：不得据此调方法"
    fig.suptitle(title, fontproperties=font, fontsize=25, y=.982)
    note = "实际MetaWorld仿真；完整流区间与全部失败见报告。标准参考，无在线API或新算法结论。"
    fig.text(.5, .015, note, ha="center", fontproperties=font, fontsize=14)
    fig.subplots_adjust(left=.15, right=.97, top=.91, bottom=.07, hspace=.26, wspace=.66)
    for suffix in ("png", "svg"): fig.savefig(target/("figure_v1."+suffix), dpi=200, facecolor="white")
    plt.close(fig)
    provenance = {"experiment_run_id": manifest["experiment_run_id"], "manifest_id": manifest["manifest_id"],
        "summary_sha256": sha(folder/"summary.json"), "script_sha256": sha(Path(__file__)), "render_python": sys.version,
        "matplotlib": matplotlib.__version__, "artifact_sha256": {p.name: sha(p) for p in target.iterdir() if p.is_file()},
        "scope": "Formatting audited saved JSON only; no environment, model inference or new scores."}
    (target/"provenance.json").write_text(json.dumps(provenance, indent=2)+"\n", encoding="utf-8")
    print(target, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--phase", choices=("SMOKE", "MAIN"), required=True)
    args = parser.parse_args(); main(args.manifest.resolve(), args.phase)
