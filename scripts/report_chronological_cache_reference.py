"""Export an audited, complete chronological reference study without new rollouts.

This is delivery-only postprocessing. It must not choose thresholds, drop cases,
rewrite stops, or replace the frozen summary/statistical audit.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_chronological_cache_reference as frozen

NAMES = {
    "NO_PROBE": "直接执行", "ALWAYS8": "每次探测8步",
    "ALWAYS16_OLD": "旧方法每次探测16步", "STALE": "直接复用旧参数",
    "PERIODIC4": "每4个任务刷新", "PASSIVE_RECENT8": "前8步边做边估计",
    "CUSUM4": "累计异常后刷新", "PLUGIN4": "只看点估计检查",
    "UNCERTAINTY4": "计入旧估计误差检查", "BALANCED4": "四方向均衡检查",
    "TASK_IVR4": "按当前动作的信息需求检查",
}
FAMILIES = {"BIAS": "固定偏置", "COLUMN_Y": "仅y指令列变化", "DEADZONE": "死区"}
SCHEDULES = {"UNCHANGED": "不变", "ABRUPT": "突变", "GRADUAL": "渐变", "ABRUPT_SMOKE": "预检突变"}
ID_FIELDS = ("experiment_run_id", "manifest_id", "source_git_commit")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")


def csv_out(path, rows, fields=None):
    rows = list(rows)
    if fields is None:
        if not rows:
            raise ValueError("explicit CSV schema required for an empty population")
        fields = list(rows[0])
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def link(path, report):
    return os.path.relpath(path, report.parent).replace("\\", "/")


def label(method):
    return f"{NAMES[method]}（{method}）"


def interval(statistic, scale=1):
    low, high = statistic["stratified_stream_percentile_95"]
    return f"{statistic['difference']*scale:+.3f} [{low*scale:+.3f}, {high*scale:+.3f}]"


def cached_fields(prefix, value, episode):
    return {
        prefix + "source_episode": value["source_episode"] if value else None,
        prefix + "source_task": value["source_task"] if value else None,
        prefix + "source_age": episode - value["source_episode"] if value else None,
        prefix + "evidence_sha256": value["evidence_sha256"] if value else None,
    }


def export(manifest_path, phase, output, report):
    # Reuse frozen loading only for source/runtime guards, never for new scores.
    manifest, _, _ = frozen.load(manifest_path)
    bridge = read(ROOT / manifest["config"]["source_bridge_manifest"])
    source_summary_path = (ROOT / bridge["config"]["response_model_path"]).with_name("summary.json")
    source_summary = read(source_summary_path)
    if (source_summary["models_sha256"] != bridge["config"]["response_model_sha256"] or
            source_summary["controlled_steps"] != bridge["config"]["response_source_steps"] or
            source_summary["controlled_resets"] != bridge["config"]["response_source_resets"]):
        raise ValueError("nominal joint-source cost/model identity changed")
    folder = manifest_path.parent / phase.lower()
    summary_path = folder / "summary.json"
    summary = read(summary_path)
    identity = {key: manifest[key] for key in ID_FIELDS}
    audits = {}
    for name in ("audit", "statistics"):
        path = manifest_path.parent / (phase.lower() + "_audit") / (name + ".json")
        audit = read(path)
        if audit["integrity"] != "PASSED" or any(audit[key] != value for key, value in identity.items()):
            raise ValueError("matching passed independent audits required")
        if audit["summary_sha256"] != sha(summary_path):
            raise ValueError("audited summary changed")
        audits[name] = (path, audit)
    if audits["statistics"][1]["record_audit_sha256"] != sha(audits["audit"][0]):
        raise ValueError("statistics/record audit link changed")
    expected = manifest["config"][phase.lower()]["executions"]
    if summary["status"] != "COMPLETED_REFERENCE" or summary["executions"] != expected:
        raise ValueError("complete registered population required before reporting")
    if any(summary[key] != value for key, value in identity.items()):
        raise ValueError("summary identity differs")
    if output.exists() or report.exists():
        raise FileExistsError("preserve previous exports/report; use an explicit new version")
    output.mkdir(parents=True)
    report.parent.mkdir(parents=True, exist_ok=True)
    rows = summary["cases"]
    if len(rows) != expected:
        raise ValueError("wrong summary case count")
    methods = manifest["config"]["methods"]
    cells = summary["statistics"]["methods"]
    specs = {s["stream"]: s for s in manifest["population_oracle"][phase]}
    index = {(r["stream"], r["episode"], r["method"]): r for r in rows}
    expected_keys = {(s["stream"], c["episode"], method)
                     for s in specs.values() for c in s["cases"] for method in methods}
    if len(index) != len(rows) or set(index) != expected_keys:
        raise ValueError("missing or duplicate exported case")
    csv_out(output / "case_outcomes.csv", rows)
    csv_out(output / "failures.csv", [r for r in rows if not r["success"]], list(rows[0]))
    csv_out(output / "stops.csv", [r for r in rows if r["stopped"]], list(rows[0]))
    flat = [{**identity, "phase": phase, "method": method, "name_zh": NAMES[method],
             **{k: v for k, v in cells[method].items() if k not in ("by_task", "by_factor")}}
            for method in methods]
    csv_out(output / "methods.csv", flat)
    csv_out(output / "tasks.csv", [{**identity, "phase": phase, "method": method, "task": task, **cell}
                                   for method in methods for task, cell in cells[method]["by_task"].items()])
    factors = [{**identity, "phase": phase, "method": method, **cell}
               for method in methods for cell in cells[method]["by_factor"]]
    csv_out(output / "factors.csv", factors)
    delay_fields = [*ID_FIELDS, "phase", "stream", "method", "change_episode_oracle",
                    "first_new_fit_delay", "first_new_fit_right_censored",
                    "first_verified_source_delay", "first_verified_source_right_censored"]
    csv_out(output / "refresh_delays.csv", [{**identity, "phase": phase, **r}
            for r in summary["statistics"]["refresh_delays_oracle"]], delay_fields)
    lineage = []
    diagnostics = []
    cache_errors = []
    raw_hashes = {}
    for stream, spec in specs.items():
        path = folder / f"episodes_{stream:02}.jsonl.gz"
        raw_hashes[path.name] = sha(path)
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            for line in handle:
                r = json.loads(line)
                key = (r["stream"], r["episode"], r["method"])
                row = index[key]
                if r["outcome"] != {k: row[k] for k in r["outcome"]}:
                    raise ValueError("raw/summary outcome mismatch")
                before, after = r["state_before"]["cache"], r["state_after"]["cache"]
                stale = bool(before is not None and
                             spec["cases"][before["source_episode"]]["fault_oracle"] !=
                             spec["cases"][r["episode"]]["fault_oracle"])
                lineage.append({**{k: row[k] for k in (*ID_FIELDS, "phase", "stream", "episode", "task", "method", "seed")},
                    **cached_fields("before_", before, r["episode"]),
                    **cached_fields("after_", after, r["episode"]),
                    "success": row["success"], "stopped": row["stopped"],
                    "cache_writes": row["cache_writes"], "cache_clears": row["cache_clears"],
                    "reuse_cases": row["reuse_cases"], "stale_source_oracle": stale,
                    "stale_cached_policy_steps_oracle": row["stale_cached_policy_steps_oracle"],
                    "decision_actions": ";".join(d["action"] for d in r["decisions"]),
                    "decision_sequences": ";".join(str(d["sequence"]) for d in r["decisions"]),
                    "fit_valid": r["fit"]["valid"] if r["fit"] is not None else None,
                    "cache_write_error": r["cache_write_error"]})
                if not row["success"]:
                    d = r["decisions"][-1]
                    diagnostics.append({**{k: row[k] for k in (*ID_FIELDS, "phase", "stream", "episode", "task", "method", "seed")},
                        "family_oracle": spec["family_oracle"], "schedule_oracle": spec["schedule_oracle"],
                        "stopped": row["stopped"], "total_steps": row["total_steps"], "deadline_loss": row["deadline_loss"],
                        "last_action": d["action"], "reason": d.get("reason"),
                        "decision_detail_json": json.dumps({k: d[k] for k in ("reason", "fit", "check") if k in d},
                                                           ensure_ascii=False, allow_nan=False)})
                if r["cache_write_error"] is not None:
                    cache_errors.append({**{k: row[k] for k in (*ID_FIELDS, "phase", "stream", "episode", "task", "method", "seed")},
                                         "success": row["success"], "reason": r["cache_write_error"]})
    if len(lineage) != expected or len(diagnostics) != sum(not r["success"] for r in rows):
        raise ValueError("raw export population mismatch")
    csv_out(output / "cache_lineage.csv", lineage)
    csv_out(output / "failure_details.csv", diagnostics, [*ID_FIELDS, "phase", "stream", "episode", "task", "method", "seed",
            "family_oracle", "schedule_oracle", "stopped", "total_steps", "deadline_loss", "last_action", "reason", "decision_detail_json"])
    csv_out(output / "cache_write_failures.csv", cache_errors,
            [*ID_FIELDS, "phase", "stream", "episode", "task", "method", "seed", "success", "reason"])
    contrasts = summary["statistics"]["contrasts"]
    paired = []
    contrast_rows = []
    decompositions = []
    for contrast in contrasts:
        method, reference = contrast["method"], contrast["reference"]
        part = []
        for s in specs.values():
            for case in s["cases"]:
                a, b = index[s["stream"], case["episode"], method], index[s["stream"], case["episode"], reference]
                part.append({**identity, "phase": phase, "stream": s["stream"], "episode": case["episode"], "seed": case["seed"],
                    "task": case["task"], "family_oracle": s["family_oracle"], "schedule_oracle": s["schedule_oracle"],
                    "method": method, "reference": reference, "role": contrast["role"],
                    "method_success": a["success"], "reference_success": b["success"],
                    "success_difference": int(a["success"]) - int(b["success"]),
                    **{field + "_difference": a[field] - b[field] for field in
                       ("deadline_loss", "total_steps", "fixed_probe_steps", "policy_measure_steps")},
                    "method_stale_cached_policy_steps_oracle": a["stale_cached_policy_steps_oracle"]})
        paired.extend(part)
        decompositions.append({"method": method, "reference": reference,
            "both_success": sum(r["method_success"] and r["reference_success"] for r in part),
            "both_fail": sum(not r["method_success"] and not r["reference_success"] for r in part),
            "rescued_success": sum(r["success_difference"] == 1 for r in part),
            "lost_success": sum(r["success_difference"] == -1 for r in part)})
        for metric, value in contrast["statistics"].items():
            contrast_rows.append({**identity, "phase": phase, "method": method, "reference": reference,
                "role": contrast["role"], "metric": metric, "difference": value["difference"],
                "lower_95": value["stratified_stream_percentile_95"][0],
                "upper_95": value["stratified_stream_percentile_95"][1]})
    csv_out(output / "contrasts.csv", contrast_rows,
            [*ID_FIELDS, "phase", "method", "reference", "role", "metric", "difference", "lower_95", "upper_95"])
    csv_out(output / "paired_outcomes.csv", paired, [*ID_FIELDS, "phase", "stream", "episode", "seed", "task", "family_oracle",
        "schedule_oracle", "method", "reference", "role", "method_success", "reference_success", "success_difference",
        "deadline_loss_difference", "total_steps_difference", "fixed_probe_steps_difference", "policy_measure_steps_difference",
        "method_stale_cached_policy_steps_oracle"])
    ledger = summary["lifecycle"]
    units = expected // len(methods)
    costs = {**identity, "phase": phase, "actual_executions": expected, "task_units_per_method": units,
        "physical_new_controlled_steps": summary["controlled_steps"], "physical_new_controlled_resets": summary["controlled_resets"],
        "physical_lifecycle": ledger,
        "per_method_source_and_online": [{"method": method,
            "actual_online_steps": sum(r["total_steps"] for r in rows if r["method"] == method),
            **{k: cells[method][k] for k in ("offline_source_steps", "offline_source_controlled_resets", "mean_amortized_actual_steps",
                                            "online_parameter_fits", "optimizer_nfev", "cache_writes")}}
            for method in methods],
        "source_fee_interpretation": "Full source per standalone method; shared raw source was collected once, not once per reference.",
        "old_source_factory_cost": "UNKNOWN_NOT_ZERO",
        "joint_source_summary_reference": {"path": source_summary_path.relative_to(ROOT).as_posix(), "sha256": sha(source_summary_path)},
        "joint_source_full_lifecycle": source_summary["lifecycle"],
        "new_nominal_model_fits": 0, "policy_weight_updates": 0, "api_calls": 0,
        "stops_keep_500_deadline_loss_actual_cost_not_imputed": True}
    if phase == "MAIN":
        smoke = read(manifest_path.parent / "smoke/summary.json")
        costs["separate_smoke_physical_cost"] = {"controlled_steps": smoke["controlled_steps"],
            "controlled_resets": smoke["controlled_resets"], "lifecycle": smoke["lifecycle"]}
    write_json(output / "costs.json", costs)
    write_json(output / "paired_success_decomposition.json", {**identity, "phase": phase, "comparisons": decompositions})
    lines = ["# 连续任务中的旧参数复用：标准参考实验", "",
        "本轮比较什么时候复用旧纠正参数、什么时候重新探测。所有方法属于标准参考，"
        "没有在线LLM/API参与，也未建立新算法贡献。结果保留全部任务、失败和停止。", ""]
    if phase == "SMOKE":
        lines += ["**本文件仅用于交付脚本自检，不能用于主实验方法选择或算法结论。**", ""]
    if contrasts:
        main = contrasts[0]
        lines += [f"预注册主比较是{label(main['method'])}减{label(main['reference'])}："
                  f"平均截止损失差为{interval(main['statistics']['deadline_loss'])}步，"
                  f"成功率差为{interval(main['statistics']['success_rate'], 100)}个百分点。"
                  "区间为预注册的完整流分层bootstrap 95%区间；本轮没有正式非劣效或算法晋级门槛。", ""]
    lines += ["## 数据与方法", "", f"{len(specs)}个独立时间流，{units}个任务单元，"
        f"每单元{len(methods)}种方法，共{expected:,}次实际执行。"
        "任务为push、reach、开门；主实验交叉三类扰动与不变、突变、渐变，每格四个流。"
        "扰动只在任务之间变化，同一任务途中保持固定。", "",
        "每次执行仅一次受控初始重置，探测连续接入固定策略，总预算500步。"
        "失败和停止的截止损失记500，真实消耗步数另列；提前停止不能被解释成高效率。"
        "同一任务单元各方法共享按物理步时钟排列的噪声，不在探测结束后倒带。", "",
        "方法的中文解释见[方法名称](" + link(ROOT / "docs/research/method_names_zh.md", report) + ")；"
        "具体阈值、程序和缓存事务见[冻结协议](" + link(ROOT / "docs/protocols/chronological_cache_reference_development_v1.md", report) + ")。", "",
        "## 全部方法表现", "", "下表每种方法使用全部任务单元作分母。截止损失越小越好；"
        "专门探测与被动测量均已包含在真实在线步数中。", "",
        "| 方法 | 成功 | 停止 | 平均截止损失 | 平均真实步数 | 专门探测步 | 被动测量步 | 含完整来源摊销步数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    if phase == "MAIN":
        lines[-2:-2] = [f"![全部十一方法及九因素格]({link(output / 'figures_v1/figure_v1.png', report)})", ""]
    for method in methods:
        c = cells[method]
        lines.append(f"| {label(method)} | {c['successes']}/{c['cases']} | {c['stops']} | {c['mean_deadline_loss']:.3f} | "
            f"{c['mean_total_steps']:.3f} | {c['mean_fixed_probe_steps']:.3f} | {c['mean_policy_measure_steps']:.3f} | {c['mean_amortized_actual_steps']:.3f} |")
    if contrasts:
        lines += ["", "## 预注册配对比较", "", "差值统一为前者减后者；损失／费用负值表示前者更低，"
            "成功率正值表示前者更高。次比较未作多重比较校正，不能当独立确认结论。", "",
            "| 比较 | 地位 | 截止损失差及95%区间 | 成功率差及95%区间（百分点） | 真实步数差及95%区间 | 探测步数差及95%区间 |",
            "|---|---|---:|---:|---:|---:|"]
        for c in contrasts:
            t = c["statistics"]
            lines.append(f"| {c['method']} − {c['reference']} | {'主比较' if c['role'] == 'PRIMARY' else '未校正次比较'} | "
                f"{interval(t['deadline_loss'])} | {interval(t['success_rate'], 100)} | {interval(t['actual_steps'])} | {interval(t['probe_steps'])} |")
        lines += ["", "| 比较 | 双方成功 | 双方失败 | 前者挽回成功 | 前者失去成功 |", "|---|---:|---:|---:|---:|"]
        for c in decompositions:
            lines.append(f"| {c['method']} − {c['reference']} | {c['both_success']} | {c['both_fail']} | {c['rescued_success']} | {c['lost_success']} |")
    lines += ["", "## 三个任务与全部因素格", "", "每格写为成功数/分母；平均截止损失见完整CSV。", "",
        "| 方法 | 推物体 | 到达目标 | 开门 |", "|---|---:|---:|---:|"]
    for method in methods:
        tasks = cells[method]["by_task"]
        lines.append("| " + method + " | " + " | ".join(f"{tasks[t]['successes']}/{tasks[t]['cases']}" for t in manifest["config"]["tasks"]) + " |")
    factor_keys = [(c["family_oracle"], c["schedule_oracle"]) for c in cells[methods[0]]["by_factor"]]
    for family, schedule in factor_keys:
        lines += ["", f"### {FAMILIES[family]} × {SCHEDULES[schedule]}", "",
            "| 方法 | 成功 | 平均截止损失 |", "|---|---:|---:|"]
        for method in methods:
            c = next(c for c in cells[method]["by_factor"] if (c["family_oracle"], c["schedule_oracle"]) == (family, schedule))
            lines.append(f"| {method} | {c['successes']}/{c['cases']} | {c['mean_deadline_loss']:.3f} |")
    lines += ["", "## 缓存、停止和刷新延迟", "",
        "缓存只能来自本方法本流较早实际成功的新拟合。复用成功不把旧证据伪装成新证据；"
        "失败／停止会清空缓存。参数标签陈旧只表示真实映射改变，不能单独证明任务受到损害。", "",
        "| 方法 | 新拟合次数 | 优化器函数求值 | 缓存写入 | 清除 | 复用案例 | 陈旧参数下任务步数（评价者） | 同映射刷新案例（评价者） |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for method in methods:
        c = cells[method]
        lines.append("| " + method + " | " + " | ".join(str(c[k]) for k in
            ("online_parameter_fits", "optimizer_nfev", "cache_writes", "cache_clears", "reuse_cases",
             "stale_cached_policy_steps_oracle", "same_mapping_refresh_cases_oracle")) + " |")
    stop_counts = Counter((r["method"], r["last_action"]) for r in diagnostics if r["stopped"])
    lines += ["", f"全量失败{len(diagnostics):,}例，其中停止{sum(stop_counts.values()):,}例；"
        f"成功但拒绝缓存写入{len(cache_errors):,}例。每例的任务、种子、停止动作与拟合详情均导出。", ""]
    if stop_counts:
        lines += ["| 方法 | 停止动作 | 案例数 |", "|---|---|---:|"]
        lines += [f"| {method} | {action} | {count} |" for (method, action), count in sorted(stop_counts.items())]
        lines += [""]
    lines += ["变化后的首次新拟合和首次成功缓存来源延迟按流导出，未观察到刷新者保留右删失标记。"
        "首次新拟合也可能来自任务失败清缓存后的重新启动，不能把它全部归因于检测器报警；"
        "不将删失时间当成已发生的刷新时间求平均。", "",
        "## 完整费用与审计", "",
        f"主阶段实际受控交互{summary['controlled_steps']:,}步、受控重置{summary['controlled_resets']:,}次；"
        f"工厂目标生成重置{ledger['by_phase']['GOAL_GENERATION']['reset_completed']:,}次、"
        f"全部重置{ledger['counts']['reset_completed']:,}次，"
        f"完成请求仿真帧{ledger['counts']['simulation_frames_completed']:,}。", "",
        f"联合模型各方法计完整离线来源3,840步／480次受控重置，按本轮{units}单元摊销。"
        "两个旧ARX参考各计21,010步／288次受控重置；旧来源的工厂成本未知，不能填0。"
        "不探测方法无需来源模型。表中摊销指标仅合并受控步骤，不能称含所有工厂成本的总成本。"
        "共享离线来源实际收集一次，不能把十一种方法的名义来源费重复相加当实际新开销。", ""]
    if phase == "MAIN":
        smoke = costs["separate_smoke_physical_cost"]
        lines += [f"预检另花{smoke['controlled_steps']:,}步／{smoke['controlled_resets']}次受控重置，"
            f"全部重置{smoke['lifecycle']['counts']['reset_completed']:,}次、"
            f"完成请求帧{smoke['lifecycle']['counts']['simulation_frames_completed']:,}。"
            "本轮没有新名义模型拟合、策略权重训练或API调用；在线参数优化与缓存写入已另计。", ""]
    ra, sa = audits["audit"][1], audits["statistics"][1]
    lines += [f"记录审计通过：核对{ra['events_checked']:,}条事件与{ra['frozen_inputs_checked']}个冻结输入，"
        "重放保存选择、真实连续状态／噪声时钟、缓存来源和物理费用。"
        f"独立统计审计通过：重建{sa['numeric_fields_checked']:,}个数值字段，"
        f"最大绝对差{sa['max_absolute_difference']:.3g}。记录审计仍共享部分估计／优化数学实现，"
        "统计审计独立重建费用、分层与区间；不把审计通过解释为物理概率保证。", "",
        "## 结论边界与后续贡献要求", "",
        "本轮检验真实时序复用及故障变化下的标准参考。COLUMN_Y前四个x方向动作的解析盲区"
        "属于输入支持／可观测性事实，均衡动作也属于标准试验设计，均不直接构成新算法。"
        "任务收益必须依据实际任务表与预注册比较判断。", "",
        "PASSIVE_RECENT8在缺少激励、拟合无效时停止，未实现跳过不支持更新并实际继续原控制的强参考。"
        "TASK_IVR4只看当前一个任务指令，不是完整规划查询分布或完整GAUGE复现。"
        "因此不能据本轮胜负宣称优于全部近期辨识／任务导向方法。", "",
        "每因素格仅四独立流、变化时点预先固定，本轮属于开发机制比较，没有为小幅成功率差或"
        "正式非劣效检验保证功效。高斯预测与参数协方差仍是未获物理资格的工作近似。"
        "后续需要独立的新方法、同权限强基线、冻结新样本与完整论文；CCF A目标仍未完成。", "",
        "## 可复核产物", ""]
    for filename, description in (("methods.csv", "全部方法及来源费用"), ("case_outcomes.csv", "全部实际案例"),
        ("failures.csv", "全部失败"), ("stops.csv", "全部停止"), ("failure_details.csv", "失败与停止详情"),
        ("paired_outcomes.csv", "预注册配对逐例差异"), ("cache_lineage.csv", "缓存来源与决策链"),
        ("cache_write_failures.csv", "成功后拒绝写入原因"), ("refresh_delays.csv", "刷新延迟及右删失"),
        ("factors.csv", "全部因素格"), ("tasks.csv", "三任务分层"), ("contrasts.csv", "预注册区间"), ("costs.json", "完整费用账")):
        lines.append(f"- [{description}]({link(output / filename, report)})")
    for description, path in (("冻结清单", manifest_path), ("完整原始汇总", summary_path),
                              ("记录审计", audits["audit"][0]), ("统计审计", audits["statistics"][0])):
        lines.append(f"- [{description}]({link(path, report)})")
    lines += ["", f"实验：`{identity['experiment_run_id']}`；清单：`{identity['manifest_id']}`；"
        f"冻结提交：`{identity['source_git_commit']}`。", ""]
    with report.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
    provenance = {**identity, "phase": phase, "scope": "DELIVERY_ONLY_NO_SELECTION_OR_NEW_ENVIRONMENT",
        "script_sha256": sha(Path(__file__)), "summary_sha256": sha(summary_path),
        "record_audit_sha256": sha(audits["audit"][0]), "statistics_audit_sha256": sha(audits["statistics"][0]),
        "raw_episode_sha256": raw_hashes, "cases_exported": len(rows), "failures_exported": len(diagnostics),
        "stops_exported": sum(r["stopped"] for r in rows), "lineage_rows": len(lineage),
        "paired_rows": len(paired), "report_path": str(report), "report_sha256": sha(report),
        "export_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()},
        "new_environment_steps": 0, "api_calls": 0}
    write_json(output / "report_provenance.json", provenance)
    print(json.dumps({k: provenance[k] for k in ("scope", "cases_exported", "lineage_rows", "paired_rows", "new_environment_steps")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--phase", choices=("SMOKE", "MAIN"), default="MAIN")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    export(args.manifest.resolve(), args.phase, args.output.resolve(), args.report.resolve())
