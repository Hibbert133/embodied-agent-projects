"""Static scientific plot of the complete, audited early-evidence experiment."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(audit_path, output):
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["integrity"] != "PASSED" or audit["episodes"] != 768 or output.exists():
        raise ValueError("complete audit and a new figure directory required")
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if not font.is_file():
        raise FileNotFoundError("Chinese scientific-figure font unavailable")
    prop = FontProperties(fname=str(font))
    plt.rcParams.update({"font.family": prop.get_name(), "axes.unicode_minus": False,
                         "font.size": 10, "svg.fonttype": "path"})
    methods = audit["statistics"]["methods"]; names = list(methods); rows = list(methods.values())
    colors = ["#6d7885" if n.startswith("POINT") or n == "NO_PROBE" else "#277c9e" if n.startswith("GAUSS") else "#208577" for n in names]
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), gridspec_kw={"height_ratios": [1.2, 1]})
    y = np.arange(len(names)); ax = axes[0, 0]
    ax.barh(y, [r["successes"] for r in rows], color=colors); ax.set_yticks(y, names); ax.invert_yaxis(); ax.set_xlim(0, 110)
    for i, row in enumerate(rows):
        ax.text(row["successes"] + 1, i, f"{row['successes']}；停止 {row['stops']}", va="center", fontsize=8)
    ax.set_xlabel("成功案例 / 96，包含所有失败和停止"); ax.set_title("A  全部方法任务表现", loc="left", fontweight="bold")
    ax = axes[0, 1]
    ax.barh(y, [r["mean_deadline_loss"] for r in rows], color=colors); ax.set_yticks(y, names); ax.invert_yaxis()
    maximum = max(r["mean_deadline_loss"] for r in rows); ax.set_xlim(0, maximum * 1.2)
    for i, row in enumerate(rows): ax.text(row["mean_deadline_loss"] + maximum * .015, i, f"{row['mean_deadline_loss']:.1f}", va="center", fontsize=9)
    ax.set_xlabel("平均截止损失：成功取总步，失败／停止取 500"); ax.set_title("B  固定任务截止损失", loc="left", fontweight="bold")
    ax = axes[1, 0]; contexts = audit["statistics"]["primary_contexts"]
    matrix = np.asarray([[np.nan if s is None else s for s in r["signs"]] for r in contexts])
    ax.imshow(matrix.T, cmap=plt.matplotlib.colors.ListedColormap(["#c96356", "#d5dce1", "#208577"]), vmin=-1, vmax=1, aspect="auto")
    ax.set_xticks(np.arange(24), [f"{r['stream']}:{r['task'].replace('-v3','')}" for r in contexts], rotation=75, ha="right", fontsize=7)
    ax.set_yticks(np.arange(4), [f"噪声 {i}" for i in range(4)]); ax.set_title("C  继续八步相对初始八步的损失方向", loc="left", fontweight="bold")
    for x, row in enumerate(contexts):
        for v, sign in enumerate(row["signs"]): ax.text(x, v, "?" if sign is None else "+" if sign == 1 else "−" if sign == -1 else "0", ha="center", va="center", color="white" if sign in (-1, 1) else "#333333", fontsize=9)
    ax.set_xlabel("流:任务；绿色 + 改善，红色 − 恶化，灰色 0 相同")
    ax = axes[1, 1]; phases = audit["lifecycle"]["by_phase"]
    order = [p for p in ("GOAL_GENERATION", "CONTROLLED_RESET", "CONTROL") if p in phases]
    labels = {"GOAL_GENERATION": "目标工厂临时环境", "CONTROLLED_RESET": "控制初始安置", "CONTROL": "实际探测与政策"}
    frames = [phases[p]["simulation_frames_completed"] / 1e6 for p in order]
    ax.barh(np.arange(len(order)), frames, color=["#6d7885", "#9eafbd", "#277c9e"]); ax.set_yticks(np.arange(len(order)), [labels[p] for p in order]); ax.invert_yaxis(); ax.set_xlim(0, max(frames) * 1.2)
    for i, value in enumerate(frames): ax.text(value + max(frames) * .015, i, f"{value:.3f}", va="center", fontsize=9)
    ax.set_xlabel("实际 do_simulation 完成请求帧（百万）"); ax.set_title("D  完整仿真初始化与控制费用", loc="left", fontweight="bold")
    for ax in (axes[0, 0], axes[0, 1], axes[1, 1]):
        ax.grid(axis="x", alpha=.18); ax.set_axisbelow(True)
    for ax in axes.flat:
        for side in ("top", "right"): ax.spines[side].set_visible(False)
    gate = audit["statistics"]["repeat_gate"]
    fig.suptitle("早期实际证据之后，额外测量是否改善任务？", fontsize=19, fontweight="bold", y=.97)
    fig.text(.02, .022, f"8 流 / 24 名义上下文 / 4 噪声实现；目标重复性门：{'通过' if gate['passed'] else '未通过'}。\n"
             "四重复的初始噪声与八步状态可能不同；高斯／IVR 是未获物理或概率资格的标准近似参考。\n"
             "图中在线损失与模拟请求帧分别计量；完整名义来源 21,010 步／288 重置另见中文报告，不是已确认的新算法。", fontsize=9, color="#4d5964")
    fig.subplots_adjust(left=.14, right=.97, top=.90, bottom=.20, hspace=.48, wspace=.60)
    output.mkdir(parents=True, exist_ok=False); fig.savefig(output / "figure.png", dpi=220); fig.savefig(output / "figure.svg"); plt.close(fig)
    metadata = {**{k: audit[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")},
                "audit_sha256": sha(audit_path), "render_source_sha256": sha(Path(__file__)),
                "png_sha256": sha(output / "figure.png"), "svg_sha256": sha(output / "figure.svg"),
                "new_environment_steps": 0, "new_api_calls": 0, "scope": "Static registered point results, all repeat signs and measured simulator frames; no new interval, fit or simulation."}
    (output / "figure.json").write_bytes((json.dumps(metadata, indent=2) + "\n").encode())
    print(json.dumps({"output": str(output), "png_sha256": metadata["png_sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--audit", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); render(args.audit.resolve(), args.output.resolve())
