"""Static complete-audit figure; imports no simulator or candidate method."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(audit_path, output):
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    if audit["integrity"] != "PASSED" or audit["episodes"] != 864 or output.exists():
        raise ValueError("complete audit and new figure directory required")
    prop = FontProperties(fname="C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({"font.family": prop.get_name(), "axes.unicode_minus": False, "font.size": 10, "svg.fonttype": "path"})
    stats = audit["statistics"]; methods = stats["methods"]; names = list(methods); rows = list(methods.values())
    colors = ["#b05e43" if n == "IVR_EXEC16" else "#bd997d" if n == "IVR_EXEC_FIXED16" else "#267f9a" if n.startswith("IVR") or n.startswith("GAUSS") else "#73818e" for n in names]
    fig, axes = plt.subplots(2, 2, figsize=(16, 11), gridspec_kw={"height_ratios": [1.3, 1]})
    ax = axes[0, 0]; y = np.arange(len(names))
    ax.barh(y, [r["successes"] for r in rows], color=colors); ax.set_yticks(y, names); ax.invert_yaxis(); ax.set_xlim(0, 112)
    for i, r in enumerate(rows): ax.text(r["successes"] + 1, i, f"{r['successes']}；停止 {r['stops']}", va="center", fontsize=8)
    ax.set_xlabel("全部成功 / 96，保留失败与停止"); ax.set_title("A  九方法完整表现", loc="left", fontweight="bold")
    ax = axes[0, 1]; maximum = max(r["mean_deadline_loss"] for r in rows)
    ax.barh(y, [r["mean_deadline_loss"] for r in rows], color=colors); ax.set_yticks(y, names); ax.invert_yaxis(); ax.set_xlim(0, maximum * 1.18)
    for i, r in enumerate(rows): ax.text(r["mean_deadline_loss"] + maximum * .015, i, f"{r['mean_deadline_loss']:.1f}", va="center", fontsize=9)
    ax.set_xlabel("平均截止损失：成功取实际总步；失败／停止取 500"); ax.set_title("B  包含探测费用的任务损失", loc="left", fontweight="bold")
    ax = axes[1, 0]; refs = ("IVR_TASK16", "GAUSS8", "IVR_EXEC_FIXED16")
    for i, name in enumerate(refs):
        r = stats["candidate_contrasts"][name]["deadline_loss"]; point = r["difference"]; low, high = r["paired_cluster_percentile_95"]
        ax.plot([low, high], [i, i], color="#b05e43", linewidth=2); ax.scatter([point], [i], color="#b05e43", s=45, zorder=3)
        ax.annotate(f"{point:.2f} [{low:.2f}, {high:.2f}]", (point, i), xytext=(0, 13), textcoords="offset points", ha="center", fontsize=8)
    ax.axvline(0, linestyle="--", color="#7c8995", linewidth=1); ax.set_yticks(range(3), refs); ax.set_ylim(2.6, -.65)
    ax.set_xlabel("IVR_EXEC16 − 对照；负值表示平均损失降低"); ax.set_title("C  主比较与关键消融的算子流配对区间", loc="left", fontweight="bold")
    ax = axes[1, 1]; adaptive = ("IVR_GLOBAL16", "IVR_TASK16", "IVR_EXEC16", "IVR_EXEC_FIXED16")
    sequences = sorted({sequence for name in adaptive for sequence in methods[name]["selected_program_sequences"]})
    matrix = np.asarray([[methods[name]["selected_program_sequences"].get(sequence, 0) for sequence in sequences] for name in adaptive])
    ax.imshow(matrix, cmap="Blues", vmin=0, vmax=96, aspect="auto")
    ax.set_yticks(range(4), adaptive); ax.set_xticks(range(len(sequences)), [s or "无程序" for s in sequences], rotation=50, ha="right", fontsize=8)
    for i in range(4):
        for j in range(len(sequences)): ax.text(j, i, str(matrix[i, j]), ha="center", va="center", color="white" if matrix[i, j] > 48 else "#273d4b", fontsize=9)
    ax.set_title("D  已保存并执行的探测程序序列", loc="left", fontweight="bold"); ax.set_xlabel("每格为案例数；完整映射与动作在原始轨迹中保存")
    for ax in (axes[0, 0], axes[0, 1], axes[1, 0]): ax.grid(axis="x", alpha=.18); ax.set_axisbelow(True)
    for ax in axes.flat:
        for side in ("top", "right"): ax.spines[side].set_visible(False)
    passed = stats["development_signal"]["passed"]
    fig.suptitle("按纠正后真实指令分配测量：前瞻开发比较", fontsize=18, fontweight="bold", y=.97)
    fig.text(.02, .025, f"16 算子流 / 3 任务 / 2 噪声实现；预登记开发信号：{'成立' if passed else '未成立'}。\n"
             "C：按反射／非反射算子流分层的 95% 配对 bootstrap 区间；全部对照及失败见中文报告。\n"
             "所有模型方法另承担完整名义来源 21,010 步 / 288 重置。当前控制器的代理方差不等于任务收益或物理概率保证。", fontsize=9, color="#4b5b68")
    fig.subplots_adjust(left=.15, right=.97, top=.90, bottom=.23, hspace=.50, wspace=.68)
    output.mkdir(parents=True, exist_ok=False); fig.savefig(output / "figure.png", dpi=220); fig.savefig(output / "figure.svg"); plt.close(fig)
    metadata = {**{k: audit[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")},
                "audit_sha256": sha(audit_path), "render_source_sha256": sha(Path(__file__)),
                "png_sha256": sha(output / "figure.png"), "svg_sha256": sha(output / "figure.svg"),
                "matplotlib_version": matplotlib.__version__, "numpy_version": np.__version__,
                "python_executable": sys.executable, "python_version": sys.version,
                "new_environment_steps": 0, "new_api_calls": 0, "scope": "Registered complete point results, selected intervals and actual probe sequences; no new inference or simulation."}
    (output / "figure.json").write_bytes((json.dumps(metadata, indent=2) + "\n").encode())
    print(json.dumps({"output": str(output), "png_sha256": metadata["png_sha256"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--audit", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); render(args.audit.resolve(), args.output.resolve())
