"""Plot completed registered reference-study results; no new inference or fit."""

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont

from replay_short_probe_results_20261019 import ROOT, STUDY, RECEIPTS, read, sha, verify_saved


LABELS = {
    "NO_PROBE": ("不探测", "No probe"),
    "ORIGINAL8_UPDATE": ("原版8步更新", "Original 8 + update"),
    "BALANCED4_UPDATE": ("均衡4步更新", "Balanced 4 + update"),
    "DOPT4_UPDATE": ("DOPT 4步更新", "DOPT 4 + update"),
    "DOPT8_UPDATE": ("DOPT 8步更新", "DOPT 8 + update"),
    "DOPT4_KEEP_AT8": ("DOPT 8步保留4步参数", "DOPT 8, keep 4-step fit"),
    "DOPT4_FALLBACK8": ("DOPT 4步优先、无效补8步", "DOPT 4, extend if invalid"),
}


def draw(data, language, output):
    chinese = language == "zh"
    font_path = Path("C:/Windows/Fonts/msyh.ttc") if chinese else Path(findfont("DejaVu Sans"))
    font = FontProperties(fname=str(font_path))
    plt.rcParams.update({"font.family": font.get_name(), "font.size": 10, "axes.unicode_minus": False,
                         "svg.fonttype": "path", "svg.hashsalt": "short-probe-reference-20261019"})
    methods, comparisons = data["methods"], data["contrasts"]
    names = list(methods)
    label = lambda name: LABELS[name][0 if chinese else 1]
    fig, (left, right) = plt.subplots(1, 2, figsize=(18, 7.2))
    fig.subplots_adjust(left=.16, right=.98, bottom=.25, top=.83, wspace=1.05)
    loss = [methods[name]["mean_deadline_loss"] for name in names]
    left.barh(range(len(names)), loss, color=["#9BA5AD" if name == "NO_PROBE" else "#496E8B" for name in names], height=.58)
    left.set_yticks(range(len(names)), [label(name) for name in names])
    left.invert_yaxis()
    left.set_xlim(0, max(loss) * 1.55)
    left.set_xlabel("平均截止损失 / 步（越低越好）" if chinese else "Mean deadline loss (steps; lower is better)")
    left.set_title("A  全部方法：损失与成功数" if chinese else "A  All methods: loss and successes", loc="left", pad=16)
    for i, name in enumerate(names):
        row = methods[name]
        text = f"{loss[i]:.2f}  |  {row['successes']}/{row['cases']}"
        left.text(loss[i] + max(loss) * .025, i, text, va="center", fontsize=9)
    for i, row in enumerate(comparisons):
        low, high = row["ci95"]
        value = row["mean_loss_difference"]
        color = "#A85A31" if row["primary"] else "#496E8B"
        right.plot([low, high], [i, i], color=color, linewidth=2)
        right.scatter([value], [i], color=color, marker="D" if row["primary"] else "o", s=40, zorder=3)
    right.set_yticks(range(len(comparisons)), [label(row["left"]) + " − " + label(row["right"]) for row in comparisons])
    right.invert_yaxis()
    right.axvline(0, color="#777777", linestyle="--", linewidth=.9)
    right.set_xlabel("左侧方法 − 右侧方法的损失 / 步" if chinese else "Left method minus right method (loss steps)")
    right.set_title("B  注册的配对比较：95%完整流区间" if chinese else "B  Registered paired contrasts: 95% stream intervals", loc="left", pad=16)
    for axis in (left, right):
        axis.spines[["top", "right"]].set_visible(False)
        axis.grid(axis="x", alpha=.18)
        axis.set_axisbelow(True)
    fig.suptitle("四步与八步标准基线：54条流，648个单元，4,536次执行" if chinese else
                 "Four- and eight-step references: 54 streams, 648 units, 4,536 executions", fontsize=17, y=.96)
    footer = ("A：数字为平均损失 | 成功数/全部。失败和停止均记500步损失；实际费用另计。\n"
              "B：负值有利于比较式左侧。橙色为唯一主比较；六个次比较未经多重校正。\n"
              "区间来自九个注册分层内的完整流配对重采样（10,000次）；不显著不表示等效。API调用为零。" if chinese else
              "A: labels show mean loss | successes/all. Failures and stops receive loss 500; actual costs are reported separately.\n"
              "B: negative favors the left method. Orange is the sole primary contrast; six secondary contrasts are unadjusted.\n"
              "Intervals use 10,000 paired whole-stream draws within nine registered strata. Non-significance does not establish equivalence. No API calls.")
    fig.text(.04, .065, footer, fontsize=10, linespacing=1.6)
    for suffix in ("png", "svg"):
        fig.savefig(output / f"short_probe_reference_{language}.{suffix}", dpi=170,
                    metadata={"Date": None} if suffix == "svg" else None, facecolor="white")
    plt.close(fig)
    return {"font_path": str(font_path), "font_sha256": sha(font_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()):
        parser.error("figure directory must be inside " + str(RECEIPTS.relative_to(ROOT)))
    started = perf_counter_ns()
    manifest, bindings, _ = verify_saved("MAIN")
    statistics = read(STUDY / "main_analysis/statistics.json")
    if list(statistics["methods"]) != list(LABELS) or len(statistics["contrasts"]) != 7:
        raise ValueError("registered plotted population differs")
    if any(row["primary"] != (i == 0) or row["ci95"] is None for i, row in enumerate(statistics["contrasts"])):
        raise ValueError("registered primary/interval metadata differs")
    output.mkdir(parents=True)
    data = {k: statistics[k] for k in ("units", "executions", "streams", "methods", "contrasts", "bootstrap_samples", "bootstrap_seed")}
    data.update(scope="Display of saved registered results. No extra intervals, tuning, or task execution.", method_labels=LABELS)
    with (output / "figure_data.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2);handle.write("\n")
    fonts = {language: draw(data, language, output) for language in ("zh", "en")}
    for path, expected in bindings.items():
        if sha(path) != expected:
            raise ValueError("bound source changed while drawing")
    receipt = {
        "schema": "short_probe_reference_figure_v1", **{k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")},
        "status": "GENERATED_REQUIRES_VISUAL_REVIEW", "generator_sha256": sha(Path(__file__)),
        "replay_helper_sha256": sha(Path(__file__).with_name("replay_short_probe_results_20261019.py")),
        "source_statistics_sha256": sha(STUDY / "main_analysis/statistics.json"),
        "artifact_sha256": {p.name: sha(p) for p in sorted(output.iterdir())}, "fonts": fonts,
        "python_version": sys.version, "matplotlib_version": matplotlib.__version__,
        "new_environment_steps": 0, "new_api_calls": 0, "new_inference_or_fits": 0,
        "generation_wall_ns": perf_counter_ns() - started,
    }
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2);handle.write("\n")
    print(json.dumps({"status": receipt["status"], "output": output.relative_to(ROOT).as_posix()}))


if __name__ == "__main__":
    main()
