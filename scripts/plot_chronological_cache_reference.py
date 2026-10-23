"""Scientific figure from complete audited delivery exports, or labelled layout data."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

LABELS = {
    "NO_PROBE": "直接执行", "ALWAYS8": "每次8步", "ALWAYS16_OLD": "旧方法16步",
    "STALE": "直接复用", "PERIODIC4": "每4任务刷新", "PASSIVE_RECENT8": "任务中估计8步",
    "CUSUM4": "累计异常检查", "PLUGIN4": "点估计检查", "UNCERTAINTY4": "计入估计误差",
    "BALANCED4": "四方向检查", "TASK_IVR4": "当前动作信息需求",
}
FAMILIES = {"BIAS": "偏置", "COLUMN_Y": "y指令列变化", "DEADZONE": "死区"}
SCHEDULES = {"UNCHANGED": "不变", "ABRUPT": "突变", "GRADUAL": "渐变"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def csv_rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def inputs(folder):
    provenance = json.loads((folder / "report_provenance.json").read_text(encoding="utf-8"))
    if provenance["phase"] != "MAIN" or provenance["cases_exported"] != 4752:
        raise ValueError("complete main exports required; smoke is not a performance-selection set")
    for name, expected in provenance["export_sha256"].items():
        if sha(folder / name) != expected:
            raise ValueError("audited delivery export changed: " + name)
    methods, factors = csv_rows(folder / "methods.csv"), csv_rows(folder / "factors.csv")
    if [r["method"] for r in methods] != list(LABELS) or len(factors) != 99:
        raise ValueError("all eleven methods and nine factor cells required")
    for row in methods + factors:
        if row["manifest_id"] != provenance["manifest_id"]:
            raise ValueError("figure input identity mismatch")
    return methods, factors, provenance


def demo():
    methods = [{"method": method, "cases": 432, "successes": 320 + 5 * i, "mean_deadline_loss": 170 - 4 * i,
                "mean_total_steps": 150 - 3 * i, "mean_fixed_probe_steps": 0 if i == 0 else 4 + i % 4,
                "mean_policy_measure_steps": 8 if method == "PASSIVE_RECENT8" else 0}
               for i, method in enumerate(LABELS)]
    factors = [{"method": method, "family_oracle": family, "schedule_oracle": schedule,
                "mean_deadline_loss": 35 + ((i * 17 + j * 31) % 400)}
               for i, method in enumerate(LABELS)
               for j, (family, schedule) in enumerate((f, s) for f in FAMILIES for s in SCHEDULES)]
    return methods, factors, {"scope": "SYNTHETIC_LAYOUT_ONLY_NOT_EXPERIMENTAL_RESULTS"}


def plot(folder, output, layout_demo=False):
    if output.exists():
        raise FileExistsError("preserve existing figure output")
    rows, factors, provenance = demo() if layout_demo else inputs(folder)
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10, "axes.titlesize": 13,
                         "svg.fonttype": "path", "savefig.facecolor": "white"})
    fig = plt.figure(figsize=(18, 12.5), layout="constrained")
    grid = fig.add_gridspec(2, 3, height_ratios=(1, 1.1), hspace=.12)
    ax1, ax2, ax3 = [fig.add_subplot(grid[0, i]) for i in range(3)]
    heat = fig.add_subplot(grid[1, :])
    y = np.arange(len(rows))
    names = [LABELS[r["method"]] for r in rows]
    colors = ["#24718c" if r["method"] == "ALWAYS8" else "#be5d35" if r["method"] == "UNCERTAINTY4" else "#8e9ba6" for r in rows]
    rates = [100 * int(r["successes"]) / int(r["cases"]) for r in rows]
    ax1.barh(y, rates, color=colors, height=.64)
    for i, r in enumerate(rows):
        ax1.text(rates[i] + 1, i, f"{int(r['successes'])}/{int(r['cases'])}", va="center", fontsize=9)
    ax1.set_xlim(0, 118)
    ax1.set_xticks([0, 25, 50, 75, 100])
    ax1.set_xlabel("成功率（%）")
    ax1.set_title("A  全部方法成功率", loc="left")
    ax2.scatter([float(r["mean_deadline_loss"]) for r in rows], y, marker="o", s=42, color="#24718c", label="截止损失")
    ax2.scatter([float(r["mean_total_steps"]) for r in rows], y, marker="x", s=45, color="#be5d35", label="实际消耗")
    ax2.set_xlabel("平均步数（越低越好；停止另见正文）")
    ax2.set_xlim(left=0)
    ax2.set_title("B  损失与真实消耗分开报告", loc="left")
    ax2.legend(loc="lower right", frameon=False, fontsize=9)
    probes = np.array([float(r["mean_fixed_probe_steps"]) for r in rows])
    passive = np.array([float(r["mean_policy_measure_steps"]) for r in rows])
    ax3.barh(y, probes, color="#24718c", height=.64, label="专门探测")
    ax3.barh(y, passive, left=probes, color="#ce9865", height=.64, label="任务中测量")
    ax3.set_xlabel("平均信息获取动作数（已含在线总步数）")
    ax3.set_title("C  信息获取费用", loc="left")
    ax3.legend(loc="lower right", frameon=False, fontsize=9)
    for ax in (ax1, ax2, ax3):
        ax.set_yticks(y, names)
        ax.set_ylim(len(rows) - .4, -.7)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.grid(axis="x", alpha=.16)
        ax.set_axisbelow(True)
    factor_keys = [(f, s) for f in FAMILIES for s in SCHEDULES]
    lookup = {(r["method"], r["family_oracle"], r["schedule_oracle"]): float(r["mean_deadline_loss"]) for r in factors}
    values = np.array([[lookup[r["method"], f, s] for f, s in factor_keys] for r in rows])
    im = heat.imshow(values, cmap="YlGnBu", vmin=0, vmax=500, aspect="auto")
    heat.set_yticks(y, names)
    heat.set_xticks(np.arange(9), [FAMILIES[f] + "\n" + SCHEDULES[s] for f, s in factor_keys])
    heat.tick_params(length=0)
    heat.set_title("D  九个预注册因素格：平均截止损失（失败／停止记500）", loc="left", pad=12)
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            heat.text(j, i, f"{values[i, j]:.1f}", ha="center", va="center", color="white" if values[i, j] > 285 else "#172d3a", fontsize=9)
    fig.colorbar(im, ax=heat, fraction=.018, pad=.02, label="平均截止损失（步）")
    if layout_demo:
        fig.suptitle("布局测试示意数据，非实验结果", fontsize=20, color="#b3261e")
    else:
        fig.suptitle("连续任务中的旧参数复用：十一种标准参考\n开发实验 · 432单元／方法 · 在线API调用0次", fontsize=17)
    output.mkdir(parents=True)
    for suffix in ("png", "svg"):
        fig.savefig(output / ("figure_v1." + suffix), dpi=200)
    plt.close(fig)
    receipt = {**{k: v for k, v in provenance.items() if k in ("experiment_run_id", "manifest_id", "source_git_commit", "scope")},
               "layout_demo": layout_demo, "methods": len(rows), "factor_cells": len(factors),
               "script_sha256": sha(Path(__file__)),
               "input_report_provenance_sha256": None if layout_demo else sha(folder / "report_provenance.json"),
               "versions": {"python": sys.version.split()[0], "matplotlib": matplotlib.__version__, "numpy": np.__version__},
               "font_sha256": sha(font) if font.exists() else None,
               "figure_sha256": {p.name: sha(p) for p in output.iterdir()}, "new_environment_steps": 0, "api_calls": 0}
    (output / "figure_provenance.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"methods": len(rows), "factor_cells": len(factors), "layout_demo": layout_demo}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--exports", type=Path)
    group.add_argument("--layout-demo", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plot(args.exports, args.output, args.layout_demo)
