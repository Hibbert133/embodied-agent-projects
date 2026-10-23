"""Describe fixed-rule cases using actual saved traces; never rerun a robot."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_text(path, text):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def select(summary):
    """Earliest stream/episode, without ranking effect size or visual appearance."""
    rows = summary["cases"]
    index = {(r["stream"], r["episode"], r["method"]): r for r in rows}
    units = sorted({(r["stream"], r["episode"]) for r in rows})
    selections = []
    for contrast in summary["statistics"]["contrasts"]:
        a, b = contrast["method"], contrast["reference"]
        for difference, name in ((-1, "失去成功"), (1, "挽回成功")):
            eligible = [(s, e) for s, e in units if int(index[s, e, a]["success"]) - int(index[s, e, b]["success"]) == difference]
            selections.append({"criterion": contrast["role"] + "_" + name, "method": a, "reference": b,
                               "eligible_cases": len(eligible), "selected_unit": list(eligible[0]) if eligible else None})
    for method in summary["statistics"]["methods"]:
        eligible = sorted((r["stream"], r["episode"]) for r in rows if r["method"] == method and r["stopped"])
        selections.append({"criterion": "每方法最早停止", "method": method,
                           "reference": "NO_PROBE" if method == "ALWAYS8" else "ALWAYS8",
                           "eligible_cases": len(eligible), "selected_unit": list(eligible[0]) if eligible else None})
    return selections


def arrays(record):
    trace = record["trace"]
    if [r["host_calls"] for r in trace] != list(range(1, len(trace) + 1)):
        raise ValueError("actual continuous step index required")
    observations = np.array([record["initial"]["observation"]] + [r["after"]["observation"] for r in trace], float)
    commands = np.array([r["command"] for r in trace], float).reshape((-1, 4))
    if observations.ndim != 2 or observations.shape[1] != 39 or not np.isfinite(observations).all() or not np.isfinite(commands).all():
        raise ValueError("finite actual v3 visible observations/commands required")
    return observations, commands


def draw(records, target, title, layout_demo=False):
    font = Path("C:/Windows/Fonts/msyh.ttc")
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams["font.family"] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({"axes.unicode_minus": False, "font.size": 10})
    fig, axes = plt.subplots(2, 2, figsize=(14, 9), layout="constrained")
    xy, height, ux, uy = axes.ravel()
    for number, record in enumerate(records):
        obs, commands = arrays(record)
        color = ("#be5d35", "#24718c")[number]
        outcome = record["outcome"]
        result = "成功" if outcome["success"] else "停止" if outcome["stopped"] else "失败"
        label = f"{record['method']}：{result}，实际{outcome['total_steps']}步，截止损失{outcome['deadline_loss']}"
        xy.plot(obs[:, 0], obs[:, 1], color=color, lw=1.5, label=label)
        xy.plot(obs[:, 4], obs[:, 5], color=color, lw=1, ls="--", alpha=.55)
        xy.scatter(obs[0, 0], obs[0, 1], color=color, marker="o", s=28)
        xy.scatter(obs[-1, 0], obs[-1, 1], color=color, marker="x", s=40)
        height.plot(np.arange(len(obs)), obs[:, 2], color=color, lw=1.3, label=record["method"])
        t = np.arange(1, len(commands) + 1)
        for ax, dimension in ((ux, 0), (uy, 1)):
            ax.step(t, commands[:, dimension], where="post", color=color, alpha=.88, lw=1, label=record["method"])
            probe = [i + 1 for i, r in enumerate(record["trace"]) if r["phase"] == "FIXED_PROBE"]
            passive = [i + 1 for i, r in enumerate(record["trace"]) if r["phase"] == "PASSIVE_PREFIX"]
            if probe:
                ax.scatter(probe, [1.12 - number * .07] * len(probe), s=9, marker="s", color=color, clip_on=False)
            if passive:
                ax.scatter(passive, [1.12 - number * .07] * len(passive), s=13, marker="^", color=color, clip_on=False)
            ax.set_ylim(-1.03, 1.21)
        decisions = [d["at_host_calls"] for d in record["decisions"] if d["at_host_calls"] > 0]
        for at in decisions:
            height.axvline(at, color=color, ls=":", lw=.9, alpha=.65)
    xy.set(xlabel="x（米）", ylabel="y（米）", title="A  末端实线与物体虚线的xy投影；圆点起始、叉号结束")
    xy.set_aspect("equal", adjustable="datalim")
    height.set(xlabel="实际物理步骤", ylabel="末端z（米）", title="B  实际高度；竖虚线为保存决策时刻")
    ux.set(xlabel="实际物理步骤", ylabel="发送的x指令", title="C  发送指令：上方方块为专门探测，三角为被动测量")
    uy.set(xlabel="实际物理步骤", ylabel="发送的y指令", title="D  发送指令：不含评价者注入后的隐藏动作")
    for ax in axes.ravel():
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=.16)
    height.legend(loc="best", frameon=False, fontsize=9)
    fig.suptitle(("布局测试示意数据，非实验结果\n" if layout_demo else "") + title, fontsize=15,
                 color="#b3261e" if layout_demo else "#172d3a")
    legends = []
    for record in records:
        cache = record["state_before"]["cache"]
        source = "无缓存" if cache is None else f"缓存源单元{cache['source_episode']}／{cache['source_task']}"
        outcome = record["outcome"]
        result = "成功" if outcome["success"] else "停止" if outcome["stopped"] else "失败"
        legends.append(f"{record['method']}：{result}，实际{outcome['total_steps']}步，损失{outcome['deadline_loss']}；进入单元时{source}")
    fig.supxlabel("\n".join(legends) + "\n不同方法有各自的历史；本图不能隔离单个当前决策的因果效应。停止的截止损失仍计500。", fontsize=10)
    fig.savefig(target, dpi=180)
    plt.close(fig)


def demo_records():
    result = []
    for k, method in enumerate(("UNCERTAINTY4", "ALWAYS8")):
        length = (90, 110)[k]
        initial = [0., .5, .2, 1., 0., .65, .02] + [0.] * 32
        trace = []
        for i in range(length):
            obs = list(initial)
            obs[:3] = [.045 * np.sin(i / 25 + .1 * k), .5 + .15 * i / length, .2 - .12 * min(i / 45, 1)]
            obs[4:6] = [.01 * k, .65 + max(i - 45, 0) / length * .04]
            trace.append({"host_calls": i + 1, "phase": "FIXED_PROBE" if i < 8 else "POLICY",
                          "command": [.5 * np.sin(i / 10), .4 * np.cos(i / 13), 0., 1.], "after": {"observation": obs}})
        result.append({"method": method, "initial": {"observation": initial}, "trace": trace,
                       "state_before": {"cache": None}, "decisions": [{"at_host_calls": 0}, {"at_host_calls": 8}],
                       "outcome": {"success": k == 1, "stopped": False, "total_steps": length, "deadline_loss": length if k else 500}})
    return result


def export(manifest_path, exports, output, layout_demo=False):
    if output.exists():
        raise FileExistsError("preserve case exports")
    output.mkdir(parents=True)
    if layout_demo:
        draw(demo_records(), output / "layout_demo.png", "保存观测与发送指令的案例布局", True)
        print(json.dumps({"scope": "SYNTHETIC_LAYOUT_ONLY", "new_environment_steps": 0}))
        return
    manifest = read(manifest_path)
    root = manifest_path.parent
    summary_path = root / "main/summary.json"
    summary = read(summary_path)
    identity = {k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    provenance = read(exports / "report_provenance.json")
    for name in ("audit", "statistics"):
        audit = read(root / "main_audit" / (name + ".json"))
        if audit["integrity"] != "PASSED" or audit["summary_sha256"] != sha(summary_path) or any(audit[k] != v for k, v in identity.items()):
            raise ValueError("complete matching main audits required")
    if summary["status"] != "COMPLETED_REFERENCE" or summary["executions"] != 4752 or provenance["summary_sha256"] != sha(summary_path):
        raise ValueError("complete audited main exports required")
    if any(sha(ROOT / n) != h for n, h in manifest["input_sha256"].items()):
        raise ValueError("frozen source changed")
    selections = select(summary)
    groups = {}
    for item in selections:
        if item["selected_unit"] is not None:
            key = (*item["selected_unit"], item["method"], item["reference"])
            groups.setdefault(key, []).append(item["criterion"])
    needed = {(s, e, method) for s, e, a, b in groups for method in (a, b)}
    records = {}
    raw_hashes = {}
    for stream in sorted({s for s, _, _ in needed}):
        path = root / "main" / f"episodes_{stream:02}.jsonl.gz"
        actual = sha(path)
        if provenance["raw_episode_sha256"][path.name] != actual:
            raise ValueError("raw trace changed")
        raw_hashes[path.name] = actual
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                r = json.loads(line)
                key = (r["stream"], r["episode"], r["method"])
                if key in needed:
                    records[key] = r
    if set(records) != needed:
        raise ValueError("selected actual trace missing")
    lines = ["# 固定规则选择的实际案例", "", "从完整审计结果中，对每个预注册比较选择按流、单元序号排列最早的失去／挽回成功案例；"
             "另列每方法最早停止。未出现的类别明确保留，全部失败另见上层CSV。", "",
             "每条曲线均来自本方法实际执行；各方法自己的历史缓存可能不同，不能将两条轨迹差异全部归因于当前某个检查或更新。"
             "图中只用可见观测、发送指令和已保存决策，不重放仿真，不使用隐藏执行动作。", ""]
    descriptions = []
    for number, ((stream, episode, a, b), roles) in enumerate(groups.items()):
        pair = [records[stream, episode, method] for method in (a, b)]
        if pair[0]["initial"] != pair[1]["initial"]:
            raise ValueError("paired task initial observations differ")
        filename = f"case_{number:02}_stream_{stream:02}_episode_{episode:02}.png"
        title = f"流{stream}／单元{episode}／{pair[0]['task']}\n" + "、".join(roles)
        draw(pair, output / filename, title)
        details = {"stream": stream, "episode": episode, "task": pair[0]["task"], "methods": [a, b],
                   "selection_roles": roles, "figure": filename,
                   "outcomes": [r["outcome"] for r in pair],
                   "saved_decisions": [r["decisions"] for r in pair],
                   "entering_cache_sources": [r["state_before"]["cache"] for r in pair]}
        descriptions.append(details)
        lines += [f"## {title}", "", f"![实际轨迹与指令]({filename})", ""]
    lines += ["## 未出现的类别", ""]
    missing = [s for s in selections if s["selected_unit"] is None]
    lines += [f"- {s['method']} 对 {s['reference']}：{s['criterion']}，符合案例0。" for s in missing]
    write_text(output / "index_zh.md", "\n".join(lines) + "\n")
    receipt = {**identity, "scope": "DESCRIPTIVE_FIXED_RULE_CASES_NOT_NEW_CONFIRMATORY_CONTRASTS", "selection_rule": "Lexicographically earliest stream/episode for each registered comparison success difference and each method stop; absent categories retained.",
               "selections": selections, "cases": descriptions, "script_sha256": sha(Path(__file__)),
               "summary_sha256": sha(summary_path), "raw_episode_sha256": raw_hashes,
               "report_provenance_sha256": sha(exports / "report_provenance.json"),
               "versions": {"python": sys.version.split()[0], "matplotlib": matplotlib.__version__, "numpy": np.__version__},
               "font_sha256": sha("C:/Windows/Fonts/msyh.ttc"),
               "artifact_sha256": {p.name: sha(p) for p in output.iterdir()}, "figures": len(groups),
               "visual_inspection_completed": False, "new_environment_steps": 0, "api_calls": 0}
    write_text(output / "case_provenance.json", json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"figures": len(groups), "selected_records": len(needed), "absent_categories": len(missing), "new_environment_steps": 0}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--exports", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--layout-demo", action="store_true")
    args = parser.parse_args()
    if not args.layout_demo and (args.manifest is None or args.exports is None):
        parser.error("--manifest and --exports required for actual cases")
    export(args.manifest.resolve() if args.manifest else None, args.exports, args.output, args.layout_demo)
