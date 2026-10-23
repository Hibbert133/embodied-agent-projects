"""Static scientific figure from verified evaluator-only decomposition."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(diagnostic, verification, output):
    d = json.loads(diagnostic.read_text(encoding="utf-8"))
    v = json.loads(verification.read_text(encoding="utf-8"))
    if v["integrity"] != "PASSED" or v["diagnostic_sha256"] != sha(diagnostic):
        raise ValueError("matching independent input/feature checks required")
    if output.exists() or output == diagnostic.parent or diagnostic.parent in output.parents:
        raise FileExistsError("figure needs a new directory outside immutable diagnosis")
    tasks = ("push-v3", "reach-v3", "door-open-v3")
    labels = ("推动", "到达", "开门")
    models = ("LINEAR_ARX", "QUADRATIC_STATE")
    values = {(r["task"], r["predictor"]): r for r in d["primary_no_probe"]}
    if set(values) != {(t, k) for t in tasks for k in models}:
        raise ValueError("all primary task/model groups required")
    font_manager.findfont(font_manager.FontProperties(family="Microsoft YaHei"), fallback_to_default=False)
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei"], "axes.unicode_minus": False,
                         "font.size": 11, "svg.fonttype": "path"})
    fig, axes = plt.subplots(1, 3, figsize=(18, 6.4), gridspec_kw={"width_ratios": [1, 1, 1.25]})
    x = np.arange(3)
    for axis, field, title in (
        (axes[0], "model_mean_episode_max_m", "已知实际加噪输入后的模型残差"),
        (axes[1], "input_mean_episode_max_m", "冻结预测器对输入差异的响应"),
    ):
        for index, (kind, color, label) in enumerate(zip(models, ("#267599", "#C56C3F"), ("线性", "状态二阶"))):
            heights = [1000 * values[(task, kind)][field] for task in tasks]
            bars = axis.bar(x + (index - .5) * .34, heights, width=.32, color=color, label=label)
            axis.bar_label(bars, fmt="%.2f", padding=3, fontsize=10)
        axis.set(xticks=x, xticklabels=labels, ylabel="每轨迹最大 xy 误差的均值（mm）", title=title)
        axis.legend(frameon=False)
        axis.margins(y=.18)
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="y", alpha=.15)
    changes = [r["max_parameter_change"] for r in d["static_passive_fit_changes"]]
    axes[2].hist(changes, bins=25, color="#64875C", alpha=.8)
    summary = d["static_passive_change_summary"]
    for field, color, label in (("median_max_parameter_change", "#267599", "中位"),
                               ("p90_max_parameter_change", "#C56C3F", "p90")):
        value = summary[field]
        axes[2].axvline(value, color=color, linestyle="--", label=f"{label} {value:.3f}")
    axes[2].set(title="真实算子不变时的有效点估计跳变", xlabel="相邻有效更新的最大系数差（非变点标签）", ylabel="有效更新对数")
    axes[2].legend(frameon=False)
    axes[2].spines[["top", "right"]].set_visible(False)
    fig.suptitle("行动证据有效性：输入噪声与模型误差不能混为一谈", fontsize=18, y=.98)
    fig.text(.055, .10, "左／中：NO_PROBE 政策阶段，每任务 32 个相关轨迹；右：85 案例的 288 对有效被动更新，真实算子变化均为零。", fontsize=11)
    fig.text(.055, .047, "完整重放 1,152 轨迹／235,479 步；八个种子簇。真实输入只供评估器，分量最大值不相加；新增仿真／API／拟合均为零。", fontsize=11)
    fig.subplots_adjust(left=.055, right=.98, top=.82, bottom=.25, wspace=.30)
    output.mkdir(parents=True, exist_ok=False)
    fig.savefig(output / "figure.png", dpi=180, facecolor="white")
    fig.savefig(output / "figure.svg", facecolor="white")
    plt.close(fig)
    svg = output / "figure.svg"
    svg.write_bytes(("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n").encode("utf-8"))
    root = Path(__file__).resolve().parents[1]
    metadata = {"source_experiment_run_id": d["experiment_run_id"], "analysis_source_git_commit": d["analysis_source_git_commit"],
                "render_parent_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip(),
                "diagnostic_sha256": sha(diagnostic), "verification_sha256": sha(verification),
                "render_source_sha256": sha(Path(__file__)),
                "artifact_sha256": {name: sha(output / name) for name in ("figure.png", "figure.svg")},
                "new_environment_steps": 0, "new_api_calls": 0, "physical_response_qualified": False}
    (output / "figure.json").write_bytes((json.dumps(metadata, indent=2) + "\n").encode("utf-8"))
    print(json.dumps({"output": str(output), "source_diagnostic_sha256": metadata["diagnostic_sha256"]}))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--diagnostic", type=Path, required=True)
    p.add_argument("--verification", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    render(a.diagnostic.resolve(), a.verification.resolve(), a.output.resolve())
