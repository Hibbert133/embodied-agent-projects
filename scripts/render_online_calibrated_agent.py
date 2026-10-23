"""Chinese figures from the audited online API pilot; no new interaction."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager


def render(audit, output):
    r = json.loads(audit.read_text(encoding="utf-8"))
    if r["statistics"] is None:
        raise ValueError("failed preflight has no task population to plot")
    available = {font.name for font in font_manager.fontManager.ttflist}
    family = next((name for name in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC") if name in available), None)
    if family is None:
        raise RuntimeError("a Chinese font is required")
    plt.rcParams["font.family"] = [family]
    plt.rcParams["axes.unicode_minus"] = False
    labels = ["不探测", "探测但不纠正", "动态 OLS", "校准仿射", "同数据最近邻", "在线 LLM"]
    colors = ["#87959c", "#87959c", "#516a78", "#427ca1", "#ab7960", "#d85a37"]
    metrics = list(r["statistics"]["methods"].values())
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 5.2), layout="constrained")
    values = [v["successful"] for v in metrics]
    axes[0].barh(labels, values, color=colors, height=.6)
    axes[0].set_xlim(0, 18)
    axes[0].set_title("任务成功数 / 16", loc="left", fontweight="bold")
    for i, v in enumerate(values):
        axes[0].text(v+.2, i, str(v), va="center")
    online = [v["mean_online_steps"] for v in metrics]
    offline = [v["offline_steps"]/16 for v in metrics]
    axes[1].barh(labels, online, color=colors, height=.6)
    axes[1].barh(labels, offline, left=online, color="#c8d2d7", height=.6, label="离线成本 / 16")
    axes[1].set_xlim(0, 680)
    axes[1].set_title("平均环境步数（含校准摊销）", loc="left", fontweight="bold")
    for i, (a, b) in enumerate(zip(online, offline)):
        axes[1].text(a+b+6, i, f"{a+b:.1f}", va="center")
    axes[1].legend(frameon=False, loc="lower right")
    for ax in axes:
        ax.invert_yaxis()
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.xaxis.grid(True, alpha=.15)
        ax.set_axisbelow(True)
    fig.suptitle("在线 API 闭环验证：接口成立与任务收益分别评估", fontsize=15, fontweight="bold")
    fig.supxlabel(f"4 个任务种子 × 4 种条件；在线预算 500 步；校准方法和 LLM 各计入 2,304 个离线步与 144 次重置。\n"
                  f"API 尝试 {r['api']['attempts']} 次；逻辑决策有效率 {r['statistics']['logical_valid_rate']:.1%}。仅为开发验证，不构成算法创新证据。", fontsize=9)
    provenance = f"Run: {r['experiment_run_id']}\nManifest: {r['manifest_id']}\nSource: {r['source_git_commit']}"
    output.parent.mkdir(parents=True, exist_ok=True)
    for ext in (".png", ".pdf"):
        fig.savefig(output.with_suffix(ext), dpi=180, facecolor="white",
                    metadata={"Title": "在线 API 闭环验证", "Description" if ext == ".png" else "Subject": provenance})
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    render(a.audit, a.output)
