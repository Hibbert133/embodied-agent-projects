"""Descriptive paper figure from completed outcomes; no new inference or fit."""

import argparse
import csv
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont
import numpy as np

from replay_paired_probe_results_v1 import ROOT, STUDY, RECEIPTS, read, sha, verify_saved


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def data():
    manifest, bindings, _ = verify_saved("MAIN")
    folder = STUDY / "main_analysis_v1"
    statistics = read(folder / "statistics.json")["statistics"]
    contexts = csv_rows(folder / "state_effects.csv")
    executions = csv_rows(folder / "all_program_executions.csv")
    outcomes = {}
    for row in executions:
        if row["role"] == "EVAL" and row["program"] in ("REUSE_OLD", "PROBE_UPDATE_KEEP"):
            key = (int(row["stream"]), int(row["episode"]), int(row["future"]), row["program"])
            if key in outcomes:
                raise ValueError("duplicate evaluation outcome")
            outcomes[key] = row
    futures = []
    for index, context in enumerate(contexts):
        if int(context["context"]) != index:
            raise ValueError("state-effect row order differs")
        values = []
        for future in range(1, statistics["fresh_futures_per_context"] + 1):
            pair = [outcomes[(int(context["stream"]), int(context["episode"]), future, arm)]
                    for arm in ("REUSE_OLD", "PROBE_UPDATE_KEEP")]
            if any(row[k] != context[k] for row in pair for k in ("seed", "task")):
                raise ValueError("outcome owner differs from state-effect row")
            values.append(int(pair[0]["deadline_loss"]) - int(pair[1]["deadline_loss"]))
        futures.append(values)
    values = np.asarray(futures, dtype=int)
    if values.shape != (statistics["contexts"], statistics["fresh_futures_per_context"]) or len(outcomes) != values.size * 2:
        raise ValueError("incomplete or extra plotted population")
    means = values.mean(axis=1)
    mcse = values.std(axis=1, ddof=1) / np.sqrt(values.shape[1])
    mixed = (values.min(axis=1) < 0) & (values.max(axis=1) > 0)
    nested = statistics["nested"]
    if not np.allclose(means, np.asarray(nested["context_mean_contrasts"])[:, 0], rtol=0, atol=1e-12):
        raise ValueError("plotted means disagree with audited source")
    if not np.allclose(mcse, np.asarray(nested["per_context_mc_standard_error"])[:, 0], rtol=0, atol=1e-11):
        raise ValueError("reconstructed Monte Carlo errors disagree")
    if not np.array_equal(mixed, np.asarray(nested["per_context_both_strict_signs_observed"])[:, 0]):
        raise ValueError("within-state sign counts disagree")
    contributions = [means[means < 0].sum() / len(means), means[means > 0].sum() / len(means), means.mean()]
    if not np.isclose(sum(contributions[:2]), contributions[2], rtol=0, atol=1e-12):
        raise ValueError("signed contribution accounting differs")
    if not np.isclose(contributions[2], statistics["stream_bootstrap"]["point"][0], rtol=0, atol=1e-12):
        raise ValueError("overall mean differs from registered primary")
    return manifest, bindings, {
        "scope": "Post-hoc descriptive display of already audited outcomes. Sign groups and rank are defined by observed eight-future means, not decision-time evidence.",
        "contexts": [{k: r[k] for k in ("context", "stream", "episode", "seed", "task")} for r in contexts],
        "future_total_effects": values.tolist(), "observed_state_means": means.tolist(),
        "state_mcse": mcse.tolist(), "both_signs_observed": mixed.tolist(),
        "rank_order": np.argsort(means, kind="stable").tolist(),
        "negative_positive_overall_contributions": [float(x) for x in contributions],
        "negative_positive_zero_mean_state_counts": [int((means < 0).sum()), int((means > 0).sum()), int((means == 0).sum())],
        "registered_overall_stream_interval": statistics["stream_bootstrap"]["percentile_95"][0],
        "state_intervals_or_sign_certificates": False,
    }


def draw(saved, language, output):
    means = np.asarray(saved["observed_state_means"])
    order = np.asarray(saved["rank_order"])
    values = np.asarray(saved["future_total_effects"])[order]
    negative, positive, zero = saved["negative_positive_zero_mean_state_counts"]
    mixed = sum(saved["both_signs_observed"])
    counts = len(means)
    if language == "zh":
        font_path = Path("C:/Windows/Fonts/msyh.ttc")
        labels = {
            "title": "平均收益与逐状态差异：383 个暖状态，各有 8 个新未来",
            "left": "A  实际配对差与状态均值", "right": "B  对总体均值的算术贡献",
            "xlabel": "按八未来均值排序后的状态序号", "ylabel": "R−K 截止损失差 / 步（正值表示 K 较好）",
            "raw": "各未来的实际差值", "mean": "该状态的八未来均值",
            "groups": [f"负均值状态\n{negative} / {counts}", f"正均值状态\n{positive} / {counts}", f"全部状态\n{counts} / {counts}"],
            "contribution": "分组差值总和 ÷ 全部 383 个状态 / 步",
            "footer": f"R：直接复用；K：更新并回退。{zero} 个零均值状态；{mixed} 个状态的八未来同时出现正负差。\n排序与分组均在结果发生后定义，不能作为在线策略；左图灰点不是独立来源状态，右图没有分组置信区间。",
        }
    else:
        font_path = Path(findfont("DejaVu Sans"))
        labels = {
            "title": "Average benefit and state-level heterogeneity: 383 warm states, 8 fresh futures each",
            "left": "A  Paired realizations and observed state means", "right": "B  Arithmetic contributions to the overall mean",
            "xlabel": "State rank by observed eight-future mean", "ylabel": "Deadline-loss difference R−K (positive favors K)",
            "raw": "Realized paired difference", "mean": "Eight-future state mean",
            "groups": [f"Negative means\n{negative} / {counts}", f"Positive means\n{positive} / {counts}", f"All states\n{counts} / {counts}"],
            "contribution": "Group sum / all 383 states (loss steps)",
            "footer": f"R: reuse old correction; K: update with invalid-fit fallback. {zero} zero-mean states; {mixed} states have both observed signs.\nRanks and groups use realized outcomes, not online evidence. Gray dots are repeated futures, not independent source states; group bars have no confidence intervals.",
        }
    font = FontProperties(fname=str(font_path))
    plt.rcParams.update({"font.family": font.get_name(), "font.size": 10, "axes.unicode_minus": False, "svg.fonttype": "path"})
    fig, (left, right) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw={"width_ratios": [1.55, 1]})
    fig.subplots_adjust(left=.07, right=.98, top=.82, bottom=.24, wspace=.29)
    rank = np.arange(1, counts + 1)
    left.scatter(np.repeat(rank, values.shape[1]), values.ravel(), s=6, alpha=.24, color="#8C98A3", label=labels["raw"], linewidths=0)
    left.plot(rank, means[order], color="#293F50", linewidth=1.5, label=labels["mean"])
    left.axhline(0, color="#525B64", linewidth=.8, linestyle="--")
    left.set(xlim=(0, counts + 1), ylim=(-510, 510), xlabel=labels["xlabel"], ylabel=labels["ylabel"], title=labels["left"])
    left.legend(loc="upper left", frameon=False, fontsize=9)
    contribution = saved["negative_positive_overall_contributions"]
    bars = right.bar(np.arange(3), contribution, width=.58, color=["#B45E55", "#398B78", "#405D78"])
    right.axhline(0, color="#525B64", linewidth=.8)
    extent = max(abs(x) for x in contribution)
    right.set_ylim(min(0, min(contribution)) - .28 * extent, max(0, max(contribution)) + .28 * extent)
    for bar, value in zip(bars, contribution):
        right.annotate(f"{value:+.2f}", (bar.get_x() + bar.get_width() / 2, value), xytext=(0, 6 if value >= 0 else -6),
                       textcoords="offset points", ha="center", va="bottom" if value >= 0 else "top", fontsize=12)
    right.set_xticks(np.arange(3), labels["groups"])
    right.set(ylabel=labels["contribution"], title=labels["right"])
    for ax in (left, right):
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(axis="y", color="#D8DEE3", linewidth=.6, alpha=.5)
        ax.set_axisbelow(True)
    fig.suptitle(labels["title"], fontsize=15, y=.96)
    fig.text(.07, .065, labels["footer"], fontsize=9, va="bottom", linespacing=1.6)
    for extension in ("png", "svg"):
        fig.savefig(output / ("heterogeneity_" + language + "." + extension), dpi=220)
    plt.close(fig)
    return {"font_path": str(font_path), "font_sha256": sha(font_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory inside outputs/reproduction_reviews/paired_probe_v1")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    if not output.is_relative_to(RECEIPTS.resolve()) or output == RECEIPTS.resolve():
        parser.error("output must be a new subdirectory of " + str(RECEIPTS.relative_to(ROOT)))
    started = perf_counter_ns()
    manifest, bindings, saved = data()
    output.mkdir(parents=True, exist_ok=False)
    with (output / "figure_data.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(saved, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    fonts = {language: draw(saved, language, output) for language in ("zh", "en")}
    if any(sha(path) != expected for path, expected in bindings.items()):
        raise ValueError("bound source changed during figure generation")
    receipt = {
        "schema": "paired_probe_descriptive_heterogeneity_v1", "manifest_id": manifest["manifest_id"],
        "source_statistics_sha256": sha(STUDY / "main_analysis_v1/statistics.json"),
        "source_outcomes_sha256": sha(STUDY / "main_analysis_v1/all_program_executions.csv"),
        "plot_script_sha256": sha(Path(__file__)), "source_verifier_sha256": sha(Path(__file__).with_name("replay_paired_probe_results_v1.py")),
        "python": sys.version, "numpy": np.__version__, "matplotlib": matplotlib.__version__, "fonts": fonts,
        "scope": saved["scope"], "reconstructed_states_checked": len(saved["contexts"]),
        "new_simulation_steps": 0, "new_model_fits": 0, "new_api_calls": 0,
        "new_confidence_intervals": 0, "generation_body_wall_ns": perf_counter_ns() - started,
        "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
    }
    with (output / "receipt.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(receipt, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(output.relative_to(ROOT))


if __name__ == "__main__":
    main()
