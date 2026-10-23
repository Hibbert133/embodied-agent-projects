"""Independently verify the saved matched-branch analysis and write its Chinese report.

Standard-library, read-only raw-record arithmetic. No environment, planner,
estimator, acquisition-analysis function, API or statistical fitting is imported.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/action_response/development_v1/action_response_20261014T104928Z_1c3798544481"
PRIMARY = ROOT / "outputs/action_response/analysis_v1/audit.json"
PRIMARY_SHA = "f3309b30c8e167d148975a781da02e75013d761ca840fa6d0130cee7bcc1c0b8"
TARGETS = ("RESPONSE_SET", "G_OPTIMAL")
REFERENCE = "CACHE_ONLY"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
UNIT = ("stream", "task", "scenario", "episode_in_stream")
PREFIX_FIELDS = ("command", "raw_policy", "before", "after", "rng_before", "rng_after")
PHASES = ("PREFIX_POLICY", "MICRO_PROBE", "FIXED_PROBE", "POLICY")


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def compact(record):
    """Keep the eligibility prefix separate from the actual completed branch."""
    trace = record["trace"]
    if len(trace) > 500 or [r["host_calls"] for r in trace] != list(range(1, len(trace) + 1)):
        raise ValueError("raw chronological cost differs")
    if any(r["phase"] not in PHASES for r in trace):
        raise ValueError("unknown raw physical phase")
    phase = Counter(r["phase"] for r in trace)
    final = trace[-1]["after"] if trace else record["initial"]
    success = final["success"]
    stopped = record["decisions"][-1]["controller"] is None
    outcome = record["outcome"]
    costs = {"total_steps": len(trace), "prefix_steps": phase["PREFIX_POLICY"],
             "micro_steps": phase["MICRO_PROBE"], "fixed_probe_steps": phase["FIXED_PROBE"], "policy_steps": phase["POLICY"]}
    if type(success) is not bool or outcome["success"] != success or outcome["stopped"] != stopped:
        raise ValueError("raw success or stop substitution")
    if any(outcome[k] != v for k, v in costs.items()):
        raise ValueError("raw cost substitution")
    validations = [d for d in record["decisions"] if d.get("validation") is not None]
    return {**{k: record[k] for k in (*IDENTITY, *UNIT, "method", "seed", "operator_id_oracle", "cache_before", "initial", "initial_rng_hash")},
            "prefix": [{k: r[k] for k in (*PREFIX_FIELDS, "phase")} for r in trace[:6]],
            "branch": {"success": success, "stopped": stopped, "steps": len(trace),
                       "probes": phase["MICRO_PROBE"] + phase["FIXED_PROBE"]},
            "first_validation": {"action": validations[0]["action"], "status": validations[0]["validation"]["assessment"]["status"]}
            if validations else None}


def reason(a, b):
    if any(a[k] != b[k] for k in (*UNIT, "seed", "operator_id_oracle")):
        raise ValueError("foreign raw pair")
    if a["cache_before"] is None or b["cache_before"] is None:
        return "NO_OLD_CACHE"
    if a["cache_before"] != b["cache_before"]:
        return "UNEQUAL_OLD_CACHE"
    if a["initial"] != b["initial"] or a["initial_rng_hash"] != b["initial_rng_hash"]:
        raise ValueError("raw initialization differs")
    x, y = a["prefix"], b["prefix"]
    if len(x) != 6 or len(y) != 6:
        return "SHORT_PREFIX"
    if [r["phase"] for r in x] != ["PREFIX_POLICY"] * 6 or [r["phase"] for r in y] != ["POLICY"] * 6:
        return "DIFFERENT_PREFIX_PROGRAM"
    if [{k: r[k] for k in PREFIX_FIELDS} for r in x] != [{k: r[k] for k in PREFIX_FIELDS} for r in y]:
        return "DIFFERENT_PHYSICAL_PREFIX"
    if any(x[5]["after"][k] for k in ("success", "terminated", "truncated")):
        return "ENDED_BY_SHARED_PREFIX"
    return "MATCHED"


def actual_pair(a, b):
    if reason(a, b) != "MATCHED" or a["first_validation"] is None:
        raise ValueError("actual qualified decision required")
    x, y = a["branch"], b["branch"]
    label = "HELPFUL" if x["success"] and not y["success"] else "HARMFUL" if y["success"] and not x["success"] else "BOTH_SUCCESS" if x["success"] else "BOTH_FAILED"
    return {**{k: a[k] for k in (*UNIT, "seed", "operator_id_oracle")}, "method": a["method"],
            "target_success": x["success"], "reference_success": y["success"],
            "target_stopped": x["stopped"], "reference_stopped": y["stopped"],
            "target_total_steps": x["steps"], "reference_total_steps": y["steps"],
            "target_remaining_steps": x["steps"] - 6, "reference_remaining_steps": y["steps"] - 6,
            "step_difference": x["steps"] - y["steps"], "extra_probe_steps": x["probes"], "paired_outcome": label,
            "first_validation_action": a["first_validation"]["action"], "first_validation_status": a["first_validation"]["status"],
            "matched_prefix_steps": 6, "oracle_pairing_not_agent_evidence": True}


def totals(rows):
    n = len(rows)
    def mean(key):
        return sum(r[key] for r in rows) / n if n else None
    return {"cases": n, "target_successes": sum(r["target_success"] for r in rows), "reference_successes": sum(r["reference_success"] for r in rows),
            "target_stops": sum(r["target_stopped"] for r in rows), "reference_stops": sum(r["reference_stopped"] for r in rows),
            "paired_outcomes": dict(Counter(r["paired_outcome"] for r in rows)),
            "mean_step_difference": mean("step_difference"), "mean_extra_probe_steps": mean("extra_probe_steps"),
            "target_total_steps": sum(r["target_total_steps"] for r in rows), "reference_total_steps": sum(r["reference_total_steps"] for r in rows),
            "mean_target_total_steps": mean("target_total_steps"), "mean_reference_total_steps": mean("reference_total_steps"),
            "mean_target_remaining_steps": mean("target_remaining_steps"), "mean_reference_remaining_steps": mean("reference_remaining_steps")}


def verify(audit_path):
    data, manifest, primary = read(audit_path), read(SOURCE / "manifest.json"), read(PRIMARY)
    if digest(PRIMARY) != PRIMARY_SHA or data["primary_audit_sha256"] != PRIMARY_SHA or primary["integrity"] != "PASSED":
        raise ValueError("original execution audit differs")
    if any(data[k] != manifest[k] or primary[k] != manifest[k] for k in IDENTITY):
        raise ValueError("original identity differs")
    for name, expected in primary["artifact_sha256"].items():
        if digest(SOURCE / name) != expected:
            raise ValueError("original raw artifact differs")
    for name, expected in manifest["input_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("original frozen input differs")
    for name, field in (("scripts/audit_response_acquisition_utility.py", "analysis_source_sha256"),
                        ("docs/research/response_acquisition_utility_audit_v1.md", "protocol_sha256")):
        blob = subprocess.check_output(["git", "show", data["analysis_git_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != data[field]:
            raise ValueError("analysis was not bound to frozen source bytes")
    config = manifest["config"]
    expected_units = {(s, t, c, e) for s in range(config["streams"]) for t in config["tasks"]
                      for c in config["scenarios"] for e in range(config["episodes_per_stream_task"])}
    banks = {}
    for method in (*TARGETS, REFERENCE):
        bank = {}
        with gzip.open(SOURCE / ("episodes_" + method + ".jsonl.gz"), "rt", encoding="utf-8") as handle:
            for line in handle:
                record = compact(json.loads(line))
                key = tuple(record[k] for k in UNIT)
                if record["method"] != method or any(record[k] != manifest[k] for k in IDENTITY) or key in bank:
                    raise ValueError("duplicate or foreign raw record")
                bank[key] = record
        if set(bank) != expected_units:
            raise ValueError("full original method population required")
        banks[method] = bank
    rows, excluded, exclusions = [], [], {}
    for method in TARGETS:
        rejected = Counter()
        for key in sorted(expected_units):
            a, b = banks[method][key], banks[REFERENCE][key]
            status = reason(a, b)
            if status == "MATCHED":
                rows.append(actual_pair(a, b))
            else:
                rejected[status] += 1
                excluded.append({**{k: a[k] for k in (*UNIT, "seed", "operator_id_oracle")}, "method": method, "reason": status})
        exclusions[method] = {"original_units": len(expected_units), "reasons": dict(rejected)}
    def order(items):
        return sorted(items, key=lambda r: (r["method"], *(r[k] for k in UNIT)))
    if order(rows) != order(data["paired_cases"]) or order(excluded) != order(data["excluded_cases"]) or exclusions != data["excluded"]:
        raise ValueError("saved eligibility or actual branch outcomes differ")
    for method in TARGETS:
        selected = [r for r in rows if r["method"] == method]
        rebuilt = {"overall": totals(selected), "episode_one": totals([r for r in selected if r["episode_in_stream"] == 1]),
                   "by_task": {t: totals([r for r in selected if r["task"] == t]) for t in config["tasks"]},
                   "by_scenario": {c: totals([r for r in selected if r["scenario"] == c]) for c in config["scenarios"]},
                   "by_stream": {str(s): totals([r for r in selected if r["stream"] == s]) for s in range(config["streams"])}}
        if rebuilt != data["results"][method]:
            raise ValueError("saved stratified arithmetic differs")
    if any(data[k] != 0 for k in ("new_robot_steps", "new_api_calls", "new_resets", "new_models_or_thresholds_fitted")):
        raise ValueError("read-only scope differs")
    if data["reference"] != REFERENCE or data["registered_prior_cost_per_method"] != {"steps": 21010, "controlled_resets": 288}:
        raise ValueError("reference or registered source cost differs")
    for method in (*TARGETS, REFERENCE):
        if (primary["statistics"]["methods"][method]["offline_steps"], primary["statistics"]["methods"][method]["offline_resets"]) != (21010, 288):
            raise ValueError("original method source cost differs")
    return data, {"integrity": "PASSED", "analysis_sha256": digest(audit_path), "primary_audit_sha256": PRIMARY_SHA,
                  "source_git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                  "verifier_sha256": digest(Path(__file__)), "original_records_checked": len(expected_units) * 3,
                  "comparisons_checked": len(expected_units) * 2, "matched_pairs_checked": len(rows), "excluded_pairs_checked": len(excluded),
                  "new_robot_steps": 0, "new_api_calls": 0, "new_resets": 0,
                  "scope": "Independent eligibility, actual trace success/stop/phase cost and all saved stratified arithmetic. Original execution replay and source-cost ledger are explicitly reused; no physical, confidence or novelty qualification."}


def markdown(data, audit_path, verification_path, report_path):
    def link(path):
        return Path(os.path.relpath(path, report_path.parent)).as_posix()
    def num(value):
        return "无合格案例" if value is None else f"{value:.4f}"
    lines = ["# 同一旧缓存与连续状态上的取证收益：中文核查", "",
             "RESPONSE_SET 的 48 个精确配对中，取证分支成功 48/48，沿用同一旧缓存成功 41/48；有利 7、有害 0。"
             "全部 48 个案例都是冷启动后案例号 1。G_OPTIMAL 配对 55 个，成功 49/55 对 48/55，有利 5、有害 4；其有害分支均停止。", "",
             "这是原始开发数据上的机制解释，不是新任务或独立确认。两组共享 48 个旧状态，不能视为 103 个独立样本；"
             "原 288 单元总体中 RESPONSE_SET 被 FIXED16、FIXED8_WIDE、FIXED16_WIDE 支配的负结果保持不变。", "",
             f"原运行 `{data['experiment_run_id']}`，原冻结源 `{data['source_git_commit']}`；只读核查源 `{data['analysis_git_commit']}`。", "",
             f"[完整原实验报告]({link(ROOT/'reports/action_response_development_v3.md')}) · [核查协议]({link(ROOT/'docs/research/response_acquisition_utility_audit_v1.md')}) · "
             f"[逐案数据]({link(audit_path)}) · [独立复算]({link(verification_path)})", "",
             "## 配对人口与代价", "",
             "每个方法先检查全部 288 个原单元；资格仅使用同流／任务／情景／案例号、种子、评估器算子 ID、非空旧缓存、完整初始状态与 RNG、"
             "前六步真实命令／政策动作／前后观察／RNG。旧缓存与数值均精确匹配，没有近似匹配或按后续成败筛选。算子真值只用于本离线评估。", "",
             "| 方法 | 原单元 | 无旧缓存 | 旧缓存已不同 | 合格 | 案例号 1 | 更晚案例 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for method in TARGETS:
        ex = data["excluded"][method]; result = data["results"][method]
        reasons = ex["reasons"]
        lines.append(f"| {method} | {ex['original_units']} | {reasons.get('NO_OLD_CACHE',0)} | {reasons.get('UNEQUAL_OLD_CACHE',0)} | "
                     f"{result['overall']['cases']} | {result['episode_one']['cases']} | {result['overall']['cases']-result['episode_one']['cases']} |")
    lines.extend(["", "实际没有因前缀运动不同、历史短或六步内已结束而排除的记录。每个排除单元和原因均保存在逐案数据，不能为不同旧模型伪造刷新反事实。", "",
                  "| 方法／人口 | 成功：取证 / 缓存 | 停止：取证 / 缓存 | 有利 / 有害 / 同成 / 同败 | 平均总步：取证 / 缓存 | 平均剩余步：取证 / 缓存 | 额外探测步 |", "|---|---|---|---|---|---|---:|"])
    def row(label, r):
        c = r["paired_outcomes"]
        return f"| {label} | {r['target_successes']} / {r['reference_successes']}（n={r['cases']}） | {r['target_stops']} / {r['reference_stops']} | " \
               f"{c.get('HELPFUL',0)} / {c.get('HARMFUL',0)} / {c.get('BOTH_SUCCESS',0)} / {c.get('BOTH_FAILED',0)} | " \
               f"{num(r['mean_target_total_steps'])} / {num(r['mean_reference_total_steps'])} | " \
               f"{num(r['mean_target_remaining_steps'])} / {num(r['mean_reference_remaining_steps'])} | {num(r['mean_extra_probe_steps'])} |"
    for method in TARGETS:
        result = data["results"][method]
        lines.append(row(method + " 全部", result["overall"]))
        lines.append(row(method + " 案例 1", result["episode_one"]))
    lines.extend(["", "总步和剩余步包含停止与失败；剩余步减去共同六步前缀，额外探测同时包含微探测与固定刷新。"
                  "G_OPTIMAL 的停止降低平均步数，不能据此声称效率收益。", "",
                  "两种方法和缓存参照均承担原完整来源的 21,010 步／288 次登记控制环境重置，原实验按 288 单元摊销。"
                  "这项事后配对分析不把来源改按 48 或 55 单元重新分摊，也不新增采集成本。Env.step 与控制重置是登记口径；"
                  "MetaWorld 工厂内部初始化的条件性推算见完整报告。", "",
                  "## 完整分层", "",
                  "| 方法／分层 | 成功：取证 / 缓存 | 停止：取证 / 缓存 | 有利 / 有害 / 同成 / 同败 | 平均总步：取证 / 缓存 | 平均剩余步：取证 / 缓存 | 额外探测步 |", "|---|---|---|---|---|---|---:|"])
    for method in TARGETS:
        for group in ("by_task", "by_scenario", "by_stream"):
            for name, result in data["results"][method][group].items():
                lines.append(row(method + "/" + ("流 " if group == "by_stream" else "") + name, result))
    lines.extend(["", "STATIONARY 的 RESPONSE_SET 多消耗平均 13.0833 步、增加 1 次成功；MIXED 平均少 91.7917 步、增加 6 次成功。"
                  "同种子对应相同任务初始化，但两个情景的执行器时序分布不同。协议中“边际任务分布”在此应理解为物理执行情景，"
                  "不指任务种子另行抽样；不能据情景差宣称纯时序耦合的因果效应。", "",
                  "## 分支结局如何影响步数", "",
                  "| 方法 | 结局 | 案例数 | 取证减缓存总步 | 额外探测总步 |", "|---|---|---:|---:|---:|"])
    for method in TARGETS:
        selected = [r for r in data["paired_cases"] if r["method"] == method]
        for outcome in ("HELPFUL", "HARMFUL", "BOTH_SUCCESS", "BOTH_FAILED"):
            part = [r for r in selected if r["paired_outcome"] == outcome]
            lines.append(f"| {method} | {outcome} | {len(part)} | {sum(r['step_difference'] for r in part)} | {sum(r['extra_probe_steps'] for r in part)} |")
    lines.extend(["", "RESPONSE_SET 的 7 个新增成功使总步差减少 2,771 步；41 个共同成功案例反而总共多 882 步，"
                  "平均多 21.5122 步。整体少 1,889 步主要来自避免跑满 500 步的失败，不能解释为每次取证都省时。"
                  "这些结局分组只是描述已发生分支，不用于拟合任何在线选择器。", "",
                  "## 全部合格配对", "",
                  "案例号从 0 计数。结局标签有利／有害仅指二元成功差；两条分支均按原始物理轨迹计费。", "",
                  "| 方法 | 流 | 任务 | 情景 | 案例 | 种子 | 结局 | 取证 / 缓存步 | 额外探测 | 取证停止 | 初次状态 |", "|---|---:|---|---|---:|---:|---|---|---:|---|---|"])
    labels = {"HELPFUL": "有利", "HARMFUL": "有害", "BOTH_SUCCESS": "同成", "BOTH_FAILED": "同败"}
    for r in data["paired_cases"]:
        lines.append(f"| {r['method']} | {r['stream']} | {r['task']} | {r['scenario']} | {r['episode_in_stream']} | {r['seed']} | "
                     f"{labels[r['paired_outcome']]} | {r['target_total_steps']} / {r['reference_total_steps']} | {r['extra_probe_steps']} | "
                     f"{'是' if r['target_stopped'] else '否'} | {r['first_validation_status']} |")
    lines.extend(["", "## 研究含义与范围", "",
                  "同一缓存、同一六步状态下确实存在纠正有收益的案例；当前 RESPONSE_SET 对全部配对都继续采集，尚未实现取证的选择性费用收益。"
                  "G_OPTIMAL 的四个有害配对都在门任务刷新拟合失败后停止，表明辨识的数值风险也必须进入后继决策目标。"
                  "直接延用当前响应阈值或只优化区间宽度，不足以证明任务价值。", "",
                  "比较包含额外测量引起的真实运动、后续模型与控制变化，不能归因于纯信息价值。未测量同一状态上固定宽八／十六步的分支；"
                  "原始固定基线从初始状态开始，不能拿它们的终点结果冒充六步后刷新反事实。未训练选择器、校准新阈值或进行新 bootstrap／总体显著性检验。", "",
                  "每个分支只有一次已保存的随机实现。有利／有害标签描述这次配对，不等于稳定的期望收益或可部署的动作标签；"
                  "后继决策研究仍需独立测量重复随机实现下的收益分布。", "",
                  "核查与独立复算均新增机器人步、环境重置、API 调用为零；API 闭环证据仍来自之前单独报告的在线试验。"
                  "本结果不完成算法创新、概率资格、独立确认或 CCF A 投稿准备。后继协议需要直接比较同一决策状态的真实候选分支，"
                  "并把失败、停止、采集运动和后续任务步纳入任务相关成本，而不是只识别参数是否变化。", ""])
    return "\n".join(lines).rstrip("\n") + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    args = parser.parse_args()
    output, report_path = args.output.resolve(), args.report_path.resolve()
    if output.exists() or report_path.exists() or SOURCE in output.parents or SOURCE in report_path.parents:
        raise FileExistsError("new external verification and report paths required")
    data, result = verify(args.audit.resolve())
    report = markdown(data, args.audit.resolve(), output / "verification.json", report_path)
    output.mkdir(parents=True, exist_ok=False)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_bytes(report.encode("utf-8"))
    result["report_sha256"] = digest(report_path)
    (output / "verification.json").write_bytes((json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    print(json.dumps(result, ensure_ascii=False))
