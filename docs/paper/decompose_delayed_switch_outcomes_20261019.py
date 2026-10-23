"""Post-hoc outcome decomposition and complete selected-case traces; no learner.

All task outcomes were already observed before this descriptive analysis was
designed. Case selection and curves are evaluator-only, never policy inputs.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
from time import perf_counter_ns

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HELPER_SHA = "b5b6baf5a2a917f6741f12e9bf46556a84f1379fccf143170dd8b27332e186b7"
AUDIT_SHA = "66221f94169b85784285206dc47519e9affce1b72dfb1908b69039406a4ede7c"
MANIFEST_SHA = "2a1ac6ba1bc4f2b969c9496d8dbaa9b8a2e72860d40b0f9b992bf5bc174a4285"
if hashlib.sha256((HERE / "plot_delayed_switch_effects_20261019.py").read_bytes()).hexdigest() != HELPER_SHA:
    raise ValueError("committed source verifier changed")
from plot_delayed_switch_effects_20261019 import RUN, IDENTITY, LABELS, verified_data, read, sha, write, require

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

METHODS = tuple(LABELS)
ALLOWED = ROOT / "outputs/reproduction_reviews/delayed_switch_mechanisms_v1"
CATEGORIES = ("both_success", "rescue", "harm", "both_fail")
CATEGORY_LABELS = {"both_success": "两者成功", "rescue": "C8失败、替代成功", "harm": "C8成功、替代失败", "both_fail": "两者失败"}
METRICS = {
    "push-v3": {"threshold": .05, "description": "环境记录的物体到目标距离 / 0.05", "source": "sawyer_push_v3.py"},
    "reach-v3": {"threshold": .05, "description": "环境记录的TCP到目标距离 / 0.05；不以观测前三维冒充TCP", "source": "sawyer_reach_v3.py"},
    "door-open-v3": {"threshold": .08, "description": "abs(观测[4] - 观测[-3]) / 0.08；不用恒零的obj_to_target", "source": "sawyer_door_v3.py"},
}


def decompose(audit):
    rows = audit["rows"];lookup = {(r["unit"], r["variant"]): r for r in rows}
    require(len(lookup) == 648, "complete unique allocation required")
    comparisons = []
    for method in METHODS[1:]:
        categories = {name: [] for name in CATEGORIES}
        for unit in range(216):
            current, alternative = lookup[unit, METHODS[0]], lookup[unit, method]
            category = ("both_success" if current["success"] and alternative["success"] else
                        "rescue" if alternative["success"] else "harm" if current["success"] else "both_fail")
            categories[category].append({"unit": unit, "task": current["task"], "seed": current["seed"],
                "current_loss": current["deadline_loss"], "alternative_loss": alternative["deadline_loss"],
                "difference": alternative["deadline_loss"] - current["deadline_loss"]})
        summary = {name: {"units": len(records), "difference_sum": sum(r["difference"] for r in records),
                    "contribution_to_full_population_mean": sum(r["difference"] for r in records) / 216}
                   for name, records in categories.items()}
        registered = next(c for c in audit["statistics"]["contrasts"] if c["left"] == method)
        require(sum(r["units"] for r in summary.values()) == 216, "partition lost cases")
        require(abs(sum(r["difference_sum"] for r in summary.values()) / 216 - registered["mean_loss_difference"]) < 1e-12,
                "partition does not reconstruct the registered mean")
        comparisons.append({"alternative": method, "summary": summary, "cases": categories})
    current_failures = [unit for unit in range(216) if not lookup[unit, METHODS[0]]["success"]]
    switch_harms = [r["unit"] for r in comparisons[0]["cases"]["harm"]]
    all_failed = [unit for unit in range(216) if not any(lookup[unit, m]["success"] for m in METHODS)]
    return {"evaluator_only": True, "post_hoc": True, "units": 216, "comparisons": comparisons,
            "current_failure_units": current_failures, "switch_harm_units": switch_harms,
            "all_three_failed_units": all_failed, "selected_trace_units": sorted(set(current_failures + switch_harms)),
            "scope": "Observed success transitions and additive loss decomposition; no confidence intervals, fitted selector, causal mechanism certificate, or future-aware policy score."}


def task_distance(task, record):
    obs = record["after"]["observation"]
    require(len(obs) == 39 and all(math.isfinite(v) for v in obs), "finite complete observation required")
    if task == "door-open-v3":
        distance = abs(obs[4] - obs[-3])
        require(record["info"]["obj_to_target"] == 0, "door log convention differs")
    else:
        distance = float(record["info"]["obj_to_target"])
        if task == "push-v3":
            require(abs(distance - math.dist(obs[4:7], obs[-3:])) < 1e-12, "push distance inconsistent with observation")
    require(math.isfinite(distance) and distance >= 0, "invalid task distance")
    expected_success = distance <= METRICS[task]["threshold"]
    require(expected_success == record["after"]["success"] == bool(record["info"]["success"]),
            "task-specific distance does not reproduce saved success")
    return distance


def traces(audit, composition):
    selected = set(composition["selected_trace_units"])
    result = [];all_case_metrics = [];checked_steps = 0
    with gzip.open(RUN / "collection/cases.jsonl.gz", "rt", encoding="utf-8") as handle:
        for index, line in enumerate(handle):
            row = json.loads(line)
            require(index < len(audit["rows"]), "unallocated trailing case")
            compact = audit["rows"][index]
            require(all(row[k] == v for k, v in compact.items()), "case does not match audited outcome")
            physical = row["physical_rows"]
            require(len(physical) == row["total_steps"], "incomplete physical trajectory")
            distances = [];commands = [];raw_policy = []
            for step, r in enumerate(physical):
                require(r["logical_step"] == step, "noncontiguous trajectory")
                distances.append(task_distance(row["task"], r));checked_steps += 1
                commands.append(r["command"][:2])
                raw_policy.append(None if r["raw_policy"] is None else r["raw_policy"][:2])
            metric = {k: compact[k] for k in ("unit", "task", "seed", "variant", "success", "total_steps", "deadline_loss")}
            metric.update(final_distance=distances[-1], minimum_distance=min(distances), threshold=METRICS[row["task"]]["threshold"])
            require((distances[-1] <= metric["threshold"]) == row["success"], "final success mismatch")
            all_case_metrics.append(metric)
            if row["unit"] in selected:
                result.append({**metric, "steps": list(range(1, len(physical) + 1)), "distance": distances,
                    "distance_over_threshold": [d / metric["threshold"] for d in distances],
                    "command_xy": commands, "raw_policy_xy": raw_policy})
    require(len(all_case_metrics) == 648 and checked_steps == audit["costs"]["new_control_steps"], "incomplete whole-population distance check")
    require(len(result) == 3 * len(selected), "selected unit lost a branch")
    for unit in selected:
        matched = [r for r in result if r["unit"] == unit]
        for r in matched[1:]:
            require(r["distance"][:16] == matched[0]["distance"][:16], "shared prefix distances differ")
    return {"evaluator_only": True, "post_hoc": True, "selection": "Every CONTINUE_CURRENT failure plus every C4-induced success-to-failure transition; all three branches retained.",
            "metric_definitions": METRICS, "success_flags_checked": checked_steps,
            "all_case_metrics": all_case_metrics, "trajectories": result,
            "scope": "Uses future recorded outcomes and evaluator info for descriptive verification; these arrays must not enter a decision-time selector."}


def draw(traces_data, units, title, stem, output):
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    plt.rcParams.update({"font.family": FontProperties(fname=str(font_path)).get_name(), "font.size": 10,
        "axes.unicode_minus": False, "svg.fonttype": "path", "svg.hashsalt": "delayed-switch-case-forensics-20261019"})
    columns = 3 if len(units) > 4 else 2;rows = math.ceil(len(units) / columns)
    fig, axes = plt.subplots(rows, columns, figsize=(15, 4 * rows + 2), squeeze=False)
    fig.subplots_adjust(left=.07, right=.98, top=.85, bottom=.19, hspace=.45, wspace=.28)
    colors = ("#496E8B", "#B16A38", "#929BA2")
    for axis, unit in zip(axes.flat, units):
        entries = [r for r in traces_data["trajectories"] if r["unit"] == unit]
        for index, method in enumerate(METHODS):
            r = next(x for x in entries if x["variant"] == method)
            axis.plot(r["steps"], r["distance_over_threshold"], color=colors[index], label=LABELS[method][0], linewidth=1.25)
            axis.scatter([r["steps"][-1]], [r["distance_over_threshold"][-1]], color=colors[index],
                         marker="o" if r["success"] else "x", s=36, zorder=4)
        axis.axhline(1, color="#278459", linestyle="--", linewidth=.9)
        axis.axvline(16, color="#444444", linestyle=":", linewidth=.9)
        axis.set_title(f"{entries[0]['task']} · {entries[0]['seed']}", loc="left")
        axis.set_xlim(0, 505);axis.set_ylim(bottom=0)
        axis.set_xlabel("累计实际控制步");axis.set_ylabel("任务距离 / 成功阈值")
        axis.spines[["top", "right"]].set_visible(False);axis.grid(alpha=.15)
    for axis in list(axes.flat)[len(units):]: axis.set_visible(False)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.5, .92), ncol=3, frameon=False)
    fig.suptitle(title, fontsize=17, y=.98)
    fig.text(.055, .055, "绿虚线：达到任务成功距离（≤1）；竖虚线：第16步切换点。圆点为成功结束，叉号为失败结束。\n"
             "各曲线止于实际结束，不补齐或拼接未来。图按已观察结局选例，只用于分析，不能作为可部署选择器的成绩。\n"
             "push/reach使用各自的环境评估距离；door使用把手x与目标x之差，未使用其恒零obj_to_target字段。", fontsize=10, linespacing=1.6)
    for ext in ("png", "svg"):
        fig.savefig(output / (stem + "." + ext), dpi=160, facecolor="white", metadata={"Date": None} if ext == "svg" else None)
    plt.close(fig)
    return {"path": str(font_path), "sha256": sha(font_path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ALLOWED) and output != ALLOWED and not output.exists(), "fresh dedicated output directory required")
    started = perf_counter_ns()
    require(sha(RUN / "manifest.json") == MANIFEST_SHA and sha(RUN / "audit/record_audit.json") == AUDIT_SHA, "committed source identity differs")
    audit, bindings = verified_data()
    composition = decompose(audit);trace_data = traces(audit, composition)
    sources = {name: ROOT / ".venv/Lib/site-packages/metaworld/envs" / spec["source"] for name, spec in METRICS.items()}
    source_hashes = {name: sha(path) for name, path in sources.items()}
    output.mkdir(parents=True)
    write(output / "composition.json", {**{k: audit[k] for k in IDENTITY}, **composition})
    write(output / "evaluator_traces.json", trace_data)
    fonts = {}
    for key, title, stem in (("current_failure_units", "全部6个 C8 失败任务：三个操作的真实后续轨迹", "current_failures_zh"),
                             ("switch_harm_units", "全部4个切换 C4 新增失败：三个操作的真实后续轨迹", "switch_harms_zh")):
        fonts[stem] = draw(trace_data, composition[key], title, stem, output)
    for path, expected in bindings.items(): require(sha(path) == expected, "bound source changed during analysis")
    for name, path in sources.items(): require(sha(path) == source_hashes[name], "metric reference source changed")
    write(output / "receipt.json", {**{k: audit[k] for k in IDENTITY}, "status": "COMPLETED_DESCRIPTIVE_ANALYSIS_REQUIRES_VISUAL_REVIEW",
        "post_hoc": True, "evaluator_only": True, "source_sha256": sha(Path(__file__)), "verifier_sha256": HELPER_SHA,
        "source_manifest_sha256": MANIFEST_SHA, "source_audit_sha256": AUDIT_SHA, "bound_input_count": len(bindings),
        "environment_metric_source_sha256": source_hashes, "metrics_checked_against_saved_success": trace_data["success_flags_checked"],
        "source_control_steps_paid_previously": audit["costs"]["new_control_steps"], "historical_nominal_cost": audit["costs"]["historical_nominal_cost_paid_once"],
        "new_environment_steps": 0, "new_resets": 0, "new_api_calls": 0, "model_fits": 0, "new_policy_queries": 0,
        "new_confidence_intervals": 0, "new_scientific_seeds": 0, "fonts": fonts, "python": sys.version, "matplotlib": matplotlib.__version__,
        "artifact_sha256": {p.name: sha(p) for p in sorted(output.iterdir())}, "wall_ns": perf_counter_ns() - started})
    print(json.dumps({"status": "COMPLETED_DESCRIPTIVE_ANALYSIS_REQUIRES_VISUAL_REVIEW", "steps_checked": trace_data["success_flags_checked"],
        "current_failure_units": composition["current_failure_units"], "switch_harm_units": composition["switch_harm_units"],
        "all_three_failed_units": composition["all_three_failed_units"]}))


if __name__ == "__main__": main()
