"""Display only the completed, audited fixed-switch study; no simulator or fit.

Use the existing plotting Python, independently of the frozen simulator venv.
The saved confidence intervals are displayed unchanged, not re-estimated here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "outputs/delayed_switch_effects/development_v1/delayed_switch_effects_20261019T093447Z_5193855b2123"
ALLOWED = ROOT / "outputs/reproduction_reviews/delayed_switch_effects_v1"
MANIFEST_ID = "13e29ef1bf5f09dd8ea39f1f61f04293c091ed0d038293a7ea8475e13a806c3f"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
LABELS = {
    "CONTINUE_CURRENT": ("继续 C8", "Continue C8"),
    "SWITCH_SAVED": ("切换 C4", "Switch to C4"),
    "RUN_UNCORRECTED": ("取消纠正", "Remove correction"),
}


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""): h.update(block)
    return h.hexdigest()


def require(condition, message):
    if not condition: raise ValueError(message)


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def verified_data():
    manifest = read(RUN / "manifest.json")
    require(manifest["manifest_id"] == MANIFEST_ID, "different study manifest")
    audit = read(RUN / "audit/record_audit.json")
    receipt = read(RUN / "audit/report_receipt.json")
    require(audit["integrity"] == "PASSED" and audit["computations_complete"] is True,
            "completed successful record audit required")
    require(audit["statistics_audit"]["integrity"] == "PASSED", "successful numeric audit required")
    for key in IDENTITY:
        require(manifest[key] == audit[key] == receipt[key], "source identities differ")
    bindings = {ROOT / name: value for name, value in manifest["input_sha256"].items()}
    bindings.update({RUN / "collection" / name: value for name, value in audit["collection_artifact_sha256"].items()})
    bindings.update({RUN / "audit/record_audit.json": receipt["record_audit_sha256"],
                     RUN / "audit/report_zh.md": receipt["report_sha256"],
                     ROOT / "scripts/audit_delayed_switch_effects_v1.py": receipt["report_source_sha256"]})
    for path, value in bindings.items(): require(sha(path) == value, "bound source changed: " + str(path))
    bindings[RUN / "manifest.json"] = sha(RUN / "manifest.json")
    bindings[RUN / "audit/report_receipt.json"] = sha(RUN / "audit/report_receipt.json")
    rows, stats = audit["rows"], audit["statistics"]
    require(len(rows) == 648 and stats["units"] == 216 and stats["independent_generator_groups"] == 36,
            "complete registered population required")
    require([m["variant"] for m in stats["methods"]] == list(LABELS), "registered method order differs")
    require(len(stats["contrasts"]) == 2 and len(stats["paired_rows"]) == 216, "complete comparisons required")
    require(stats["failures"] == [r for r in rows if not r["success"]], "failure listing differs")
    require(len(audit["matched_boundary_comparisons"]) == 432, "complete matching audit required")
    for m in stats["methods"]:
        selected = [r for r in rows if r["variant"] == m["variant"]]
        require(len(selected) == m["executions"] == 216, "method denominator differs")
        require(sum(r["success"] for r in selected) == m["successes"], "displayed success count differs")
        require(sum(r["total_steps"] for r in selected) == m["actual_control_steps"], "displayed cost differs")
        require(sum(r["deadline_loss"] for r in selected) / 216 == m["mean_deadline_loss"], "displayed loss differs")
    for i, c in enumerate(stats["contrasts"]):
        require(c["left"] == list(LABELS)[i + 1] and c["right"] == list(LABELS)[0]
                and c["primary"] == (i == 0), "registered comparison differs")
        differences = [p["losses"][c["left"]] - p["losses"][c["right"]] for p in stats["paired_rows"]]
        require(sum(differences) / 216 == c["mean_loss_difference"], "displayed paired mean differs")
        require([sum(d < 0 for d in differences), sum(d > 0 for d in differences), sum(d == 0 for d in differences)]
                == [c["realized_better_units"], c["realized_worse_units"], c["realized_tied_units"]], "displayed signs differ")
    return audit, bindings


def draw(stats, language, output):
    zh = language == "zh"
    font_path = Path("C:/Windows/Fonts/msyh.ttc") if zh else Path(findfont("DejaVu Sans"))
    font = FontProperties(fname=str(font_path))
    plt.rcParams.update({"font.family": font.get_name(), "font.size": 11, "axes.unicode_minus": False,
                         "svg.fonttype": "path", "svg.hashsalt": "delayed-switch-effects-20261019"})
    label = lambda key: LABELS[key][0 if zh else 1]
    fig, (left, right) = plt.subplots(1, 2, figsize=(16, 6.6))
    fig.subplots_adjust(left=.12, right=.97, bottom=.27, top=.78, wspace=.72)
    losses = [m["mean_deadline_loss"] for m in stats["methods"]]
    left.barh(range(3), losses, color=["#496E8B", "#B16A38", "#929BA2"], height=.53)
    left.set_yticks(range(3), [label(m["variant"]) for m in stats["methods"]])
    left.invert_yaxis();left.set_xlim(0, max(losses) * 1.55)
    for i, m in enumerate(stats["methods"]):
        left.text(losses[i] + max(losses) * .03, i, f"{losses[i]:.2f} | {m['successes']}/216", va="center")
    left.set_title("A  平均损失与成功数" if zh else "A  Mean loss and successes", loc="left", pad=18)
    left.set_xlabel("平均截止损失 / 步（越低越好）" if zh else "Mean deadline loss (steps; lower is better)")
    for i, c in enumerate(stats["contrasts"]):
        color = "#B16A38" if c["primary"] else "#496E8B"
        lo, hi = c["ci95"];mid = c["mean_loss_difference"]
        right.plot([lo, hi], [i, i], color=color, linewidth=2.4)
        right.scatter([mid], [i], color=color, marker="D" if c["primary"] else "o", s=55, zorder=3)
        right.annotate(f"{mid:.2f} [{lo:.2f}, {hi:.2f}]", (mid, i), xytext=(0, 18),
                       textcoords="offset points", ha="center", fontsize=10)
    right.set_yticks(range(2), [label(c["left"]) + " − " + label(c["right"]) for c in stats["contrasts"]])
    right.set_ylim(1.55, -.55);right.margins(x=.23)
    right.axvline(0, color="#777777", linestyle="--", linewidth=1)
    right.set_title("B  配对差与 95% 整组区间" if zh else "B  Paired differences and 95% group intervals", loc="left", pad=18)
    right.set_xlabel("负值：左侧操作损失更低" if zh else "Negative: lower loss for the left operation")
    for axis in (left, right):
        axis.spines[["top", "right"]].set_visible(False);axis.grid(axis="x", alpha=.17);axis.set_axisbelow(True)
    fig.suptitle("第16步之后：继续 C8、切换 C4、取消纠正" if zh else
                 "After step 16: continue C8, switch to C4, or remove correction", fontsize=18, y=.96)
    fig.text(.5, .86, "216个单元 × 3种固定操作；36个独立生成组" if zh else
             "216 units × 3 fixed operations; 36 independent generator groups", ha="center", fontsize=12)
    footer = ("C4 / C8：分别由前4 / 8步试探数据估计的纠正参数；各分支都先用C8执行到第16步。\n"
              "失败和停止记500步损失；实际费用另计。橙色为主比较，蓝色为未校正的次比较。\n"
              "区间按故障族分层、整组重抽10,000次；区间跨零不代表等效。本轮没有LLM或在线选择器。" if zh else
              "C4 / C8: corrections fitted from the first 4 / 8 probe steps; all branches use C8 until step 16.\n"
              "Failures and stops receive loss 500; actual costs are separate. Orange: primary; blue: unadjusted secondary.\n"
              "10,000 family-stratified whole-group draws. Crossing zero does not imply equivalence. No LLM or online selector.")
    fig.text(.055, .065, footer, fontsize=10, linespacing=1.7)
    for ext in ("png", "svg"):
        fig.savefig(output / f"fixed_switch_{language}.{ext}", dpi=170, facecolor="white",
                    metadata={"Date": None} if ext == "svg" else None)
    plt.close(fig)
    return {"path": str(font_path), "sha256": sha(font_path)}


def report(audit, output):
    stats = audit["statistics"];costs = audit["costs"]
    text = ["# 中途切换纠正：完整结果与失败案例", "",
        "这轮测量三个固定操作的实际后果，没有训练在线选择器，也没有LLM调用。所有216个任务单元保留在每个方法的分母中。", "",
        "机器人先试探4步并保存C4，累计试探8步得到C8，再用C8执行到第16步。随后继续C8、切换C4或取消纠正。C4没有被预先验证成功；切换参数不恢复机器人位置。", "",
        "共同准备需要C4和C8都有效。因此这里的继续C8不能代替不要求C4有效的普通8步基线。准备无效和提前结束也保留。", "",
        "![完整对照](fixed_switch_zh.png)", "",
        "|操作|成功/全部|失败|停止|边界不可用|平均截止损失|实际控制步|", "|---|---:|---:|---:|---:|---:|---:|"]
    for m in stats["methods"]:
        text.append(f"|{LABELS[m['variant']][0]}|{m['successes']}/216|{m['failures']}|{m['stops']}|{m['unavailable_boundaries']}|{m['mean_deadline_loss']:.6f}|{m['actual_control_steps']}|")
    text += ["", "失败或停止的截止损失为500；成功时为全部实际步骤。实际费用不使用失败罚值。", "",
             "|比较|平均差/步|95%整组区间|改善/变差/相同|", "|---|---:|---|---|"]
    for c in stats["contrasts"]:
        text.append(f"|{LABELS[c['left']][0]} − {LABELS[c['right']][0]}|{c['mean_loss_difference']:.6f}|[{c['ci95'][0]:.6f}, {c['ci95'][1]:.6f}]|{c['realized_better_units']}/{c['realized_worse_units']}/{c['realized_tied_units']}|")
    text += ["", "切换C4减继续C8是唯一主比较；取消纠正是未作多重校正的次比较。负差有利于左侧操作。区间沿用冻结审计结果，按故障族分层、完整生成组重抽10000次。每状态只有一次未来实现；改善/变差计数不是条件期望效应，也不能冒充一个已学会选择的策略成绩。", "",
        "## 全部失败", "", "以下列出全部失败执行，不按故障、任务或边界是否可用删选。停止是失败的子集。", "",
        "|单元|任务|种子|操作|停止|到达决策边界|真实步数|截止损失|", "|---:|---|---:|---|---|---|---:|---:|"]
    for r in stats["failures"]:
        text.append(f"|{r['unit']}|{r['task']}|{r['seed']}|{LABELS[r['variant']][0]}|{'是' if r['stopped'] else '否'}|{'是' if r['boundary_ready'] else '否'}|{r['total_steps']}|{r['deadline_loss']}|")
    text += ["", "## 成本与范围", "",
        f"新增控制步{costs['new_control_steps']}；受控重置648次；全部重置{costs['lifecycle']['counts']['reset_completed']}次；请求/完成仿真帧{costs['lifecycle']['counts']['simulation_frames_attempted']}/{costs['lifecycle']['counts']['simulation_frames_completed']}。策略查询{costs['policy_queries']}，参数拟合{costs['parameter_fit_results']}次。API、选择器拟合、名义模型重训和策略权重更新均为0。", "",
        "每个方法承担完整历史名义来源：3840控制步、480受控重置、24480全部重置、12259200帧，按216单元摊销17.777778历史控制步/单元。历史设计3次枚举、432候选。先前执行资格与软件资格是已付开发费用，详见冻结协议和原审计报告；本页不把它们当成免费。", "",
        f"独立审计核对{audit['event_count']}条主事件、{audit['private_witness_records']}份私有状态记录和432对匹配前缀。采集主体{costs['collection_wall_ns']/1e9:.6f}秒，原审计{audit['audit_wall_ns']/1e9:.6f}秒；进程开销、审计重算及图表费用分别保存在各自回执。", "",
        "本图表程序只复核已保存的身份、哈希、分母、均值及符号计数，展示已经冻结的区间；它没有重新执行物理审计或构成第二次实验。", "",
        "当前只覆盖固定故障下的三种后续操作。尚缺获取新证据后重新估计的分支、任务内变化、自己形成历史的部署评价、完整强基线、消融和新方法；这些结果不能单独支持算法创新或CCF A投稿就绪。", "",
        f"冻结提交：`{audit['source_git_commit']}`。清单：`{audit['manifest_id']}`。", ""]
    with (output / "report_zh.md").open("x", encoding="utf-8", newline="\n") as handle: handle.write("\n".join(text))


def main():
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--output", type=Path, required=True)
    output = parser.parse_args().output.resolve()
    require(output.is_relative_to(ALLOWED) and output != ALLOWED and not output.exists(), "fresh dedicated output directory required")
    started = perf_counter_ns();audit, bindings = verified_data()
    output.mkdir(parents=True)
    write(output / "figure_data.json", {**{k: audit[k] for k in IDENTITY}, "method_labels": LABELS,
          "statistics": audit["statistics"], "scope": "Saved fixed-operation outcomes; no online selector, new inference or fitting."})
    fonts = {language: draw(audit["statistics"], language, output) for language in ("zh", "en")}
    report(audit, output)
    for path, value in bindings.items(): require(sha(path) == value, "source changed during rendering: " + str(path))
    write(output / "receipt.json", {**{k: audit[k] for k in IDENTITY}, "status": "GENERATED_REQUIRES_VISUAL_REVIEW",
        "generator_sha256": sha(Path(__file__)), "bound_source_files": len(bindings),
        "original_audit_sha256": sha(RUN / "audit/record_audit.json"), "fonts": fonts,
        "python": sys.version, "matplotlib": matplotlib.__version__,
        "artifact_sha256": {p.name: sha(p) for p in sorted(output.iterdir())},
        "new_environment_steps": 0, "new_api_calls": 0, "new_inference_or_fits": 0,
        "generation_wall_ns": perf_counter_ns() - started})
    print(json.dumps({"status": "GENERATED_REQUIRES_VISUAL_REVIEW", "output": str(output)}))


if __name__ == "__main__": main()
