"""Plot saved policy modes and fitting residuals; selected retrospective case only."""

import argparse
from itertools import groupby
from pathlib import Path
import json
import sys
from time import perf_counter_ns

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
from matplotlib.patches import Patch
import numpy as np

from replay_paired_probe_results_v1 import ROOT, RECEIPTS, read, sha


SOURCE = RECEIPTS / "case_traces_v1"
COLORS = {"ALIGN_XY": "#4C78A8", "DESCEND": "#E4AE46", "PUSH_TO_GOAL": "#399176"}


def render(case, lang, output):
    if lang == "zh":
        font = Path("C:/Windows/Fonts/msyh.ttc")
        labels = {
            "title": "通过拟合检查之后：同一推物状态的八个新未来",
            "left": "A  固定底层策略请求的阶段", "right": "B  新拟合的响应残差",
            "xlabel": "已使用的总动作步数", "future": "未来编号", "ylabel": "拟合内响应 RMSE / 微米",
            "modes": ["平面对齐", "请求下降", "推向目标"], "success": "成功", "failure": "失败",
            "footer": "P：补测后保留旧参数；K：补测后更新，无效才回退。每个未来内，P/K 的前 8 步相同。\n白色尾部表示任务已经结束；下降是策略分支，不代表机械手一直在下降。案例与展示均为事后描述，不是在线规则。",
        }
    else:
        font = Path(findfont("DejaVu Sans"))
        labels = {
            "title": "After a valid fit: eight fresh futures from one push-task state",
            "left": "A  Requested fixed-policy mode", "right": "B  In-sample response residual",
            "xlabel": "Total actions already used", "future": "Future index", "ylabel": "In-sample response RMSE (micrometers)",
            "modes": ["Align XY", "Request descent", "Push to goal"], "success": "Success", "failure": "Failure",
            "footer": "P: probe, keep old correction. K: probe, update with invalid-fit fallback. P/K share the first 8 steps within each future.\nWhite tails mark completed tasks. Requested descent need not produce continuing downward motion. Retrospective case display, not an online rule.",
        }
    plt.rcParams.update({"font.family": FontProperties(fname=str(font)).get_name(), "font.size": 10, "axes.unicode_minus": False, "svg.fonttype": "path"})
    fig, (timeline, residual) = plt.subplots(1, 2, figsize=(15, 7), gridspec_kw={"width_ratios": [1.7, 1]})
    fig.subplots_adjust(left=.07, right=.98, top=.83, bottom=.20, wspace=.25)
    pairs = {(row["future"], row["program"]): row for row in case["programs"]}
    ticks = []
    for future in range(1, 9):
        for offset, (tag, program) in enumerate((("P", "PROBE_KEEP"), ("K", "PROBE_UPDATE_KEEP"))):
            row = pairs[(future, program)]
            y = (future - 1) * 2 + offset
            ticks.append(f"{tag}{future}")
            start = 8
            for mode, group in groupby(row["policy_modes"]):
                width = len(list(group))
                timeline.broken_barh([(start, width)], (y - .36, .72), facecolors=COLORS[mode])
                start += width
            if start != row["outcome"]["total_steps"]:
                raise ValueError("mode timeline does not cover actual task suffix")
            timeline.text(start + 4, y, str(start), va="center", fontsize=8,
                          color="#354D3B" if row["outcome"]["success"] else "#A43B3B")
        timeline.axhline((future - 1) * 2 + 1.5, color="#DDE2E5", linewidth=.6)
    timeline.axvspan(0, 8, color="#D9DEE2")
    timeline.set(yticks=np.arange(16), yticklabels=ticks, ylim=(15.8, -.8), xlim=(0, 535),
                 xticks=[0, 100, 200, 300, 400, 500], xlabel=labels["xlabel"], title=labels["left"])
    timeline.legend(handles=[Patch(color=COLORS[mode], label=label) for mode, label in zip(COLORS, labels["modes"])],
                    loc="lower left", bbox_to_anchor=(0, 1.03), ncol=3, frameon=False, fontsize=9)
    rows = [pairs[(future, "PROBE_UPDATE_KEEP")] for future in range(1, 9)]
    rmse = [row["fit"]["residual_rmse_m"] * 1e6 for row in rows]
    success_color, failure_color = "#6D8E82", "#B95E56"
    bars = residual.bar(np.arange(1, 9), rmse, color=[success_color if row["outcome"]["success"] else failure_color for row in rows], width=.65)
    for bar, value in zip(bars, rmse):
        residual.annotate(f"{value:.1f}", (bar.get_x() + bar.get_width()/2, value), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=9)
    residual.set(xticks=np.arange(1, 9), xlabel=labels["future"], ylabel=labels["ylabel"], ylim=(0, max(rmse)*1.22), title=labels["right"])
    residual.legend(handles=[Patch(color=success_color, label=labels["success"]), Patch(color=failure_color, label=labels["failure"])], frameon=False, loc="upper right")
    residual.grid(axis="y", alpha=.25)
    residual.set_axisbelow(True)
    for ax in (timeline, residual):
        ax.spines[["top", "right"]].set_visible(False)
    fig.suptitle(labels["title"], fontsize=16, y=.97)
    fig.text(.07, .055, labels["footer"], fontsize=9, linespacing=1.6)
    for extension in ("png", "svg"):
        fig.savefig(output / f"case_trace_{lang}.{extension}", dpi=220)
    plt.close(fig)
    return {"path": str(font), "sha256": sha(font)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output == RECEIPTS.resolve() or output.exists():
        parser.error("output must be a new subdirectory inside the replay-receipt directory")
    started = perf_counter_ns()
    source_receipt = read(SOURCE / "receipt.json")
    if sha(SOURCE / "case_traces.json") != source_receipt["artifact_sha256"]["case_traces.json"]:
        raise ValueError("source trace changed")
    if sha(Path(__file__).with_name("extract_paired_probe_case_trace_20261019.py")) != source_receipt["script_sha256"]:
        raise ValueError("source extractor changed")
    cases = read(SOURCE / "case_traces.json")["cases"]
    case = next(row for row in cases if row["seed_evaluator_only"] == 19493)
    if case["task"] != "push-v3":
        raise ValueError("unexpected descriptive population")
    output.mkdir(parents=True, exist_ok=False)
    fonts = {lang: render(case, lang, output) for lang in ("zh", "en")}
    receipt = {
        "schema": "paired_probe_case_trace_figure_v1", "source_trace_receipt_sha256": sha(SOURCE / "receipt.json"),
        "source_trace_sha256": sha(SOURCE / "case_traces.json"), "script_sha256": sha(Path(__file__)),
        "python": sys.version, "numpy": np.__version__, "matplotlib": matplotlib.__version__, "fonts": fonts,
        "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
        "generation_body_wall_ns": perf_counter_ns() - started,
        "new_simulation_steps": 0, "new_api_calls": 0, "new_fits": 0, "new_confidence_intervals": 0,
        "scope": "One retrospectively selected state, all eight futures. Policy-mode requests from saved pre-action observations; not proof of a contact cause or an online intervention.",
    }
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
