"""Independent v2 journal binding and whole-state comparison audit.

The unchanged v1 grammar checks physical commands/costs. This layer checks a
separate private journal, its phase timing and full-hash anchors, then applies
the declared shared graph projection. No actor or environment is executed.
"""
import argparse
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1];sys.path.insert(0, str(ROOT))
from scripts import audit_delayed_intervention_v1 as previous
from src.analysis import delayed_qualification_io_v2 as io
from src.analysis.continuous_state_witness_v1 import compare_witnesses, verify_witness
from src.analysis.short_probe_journal_audit_v1 import physical_rows_equal
from src.analysis.short_probe_public_audit_v1 import same
from src.probe.cache_acquisition_evidence_v1 import digest

require, integer = previous.require, previous.integer


def audit_private(records, events, private, identity, summary):
    require(len(private) == len(records) * 3 == summary["private_witness_records"], "three private records per execution required")
    by_sequence = {e["sequence"]: e for e in events};private_stamp = -1;wall_ns = 0
    fields = {"label", "logical_step", "source_anchor_sequence", "source_anchor_saved_ns", "started_ns", "completed_ns",
              "ledger_before", "ledger_after", "source_witness", "witness"}
    for index, row in enumerate(records):
        saved = private[index * 3:index * 3 + 3];same(row["state_witnesses"], saved)
        initial_anchor = next(e for e in events if e["event"] == "CONTROLLED_INITIAL" and all(e[k] == row[k] for k in ("unit", "task", "seed", "variant")))
        final_anchor = max(e["sequence"] for e in events if all(e[k] == row[k] for k in ("unit", "task", "seed", "variant")))
        expected = [
            ("INITIAL", 0, initial_anchor["sequence"], row["initial_witness"], row["prefix"]["initial_ledger"]),
            ("BOUNDARY", row["prefix"]["public"]["completed_steps"], row["prefix"]["end_sequence"], row["prefix"]["boundary_witness"], row["prefix"]["boundary_ledger"]),
            ("FINAL", row["total_steps"], final_anchor, row["end_witness"], row["ledger_before_close"])]
        for offset, (packet, (label, step, anchor_id, source, ledger)) in enumerate(zip(saved, expected)):
            require(set(packet) == set(identity) | {"unit", "task", "seed", "variant", "event", "sequence", "saved_ns"} | fields,
                    "strict private record schema required")
            for key, value in {**identity, **{k: row[k] for k in ("unit", "task", "seed", "variant")},
                    "event": "STATE_WITNESS", "sequence": index * 3 + offset, "label": label, "logical_step": step,
                    "source_anchor_sequence": anchor_id, "source_witness": source, "ledger_before": ledger, "ledger_after": ledger}.items():
                same(packet[key], value)
            anchor = by_sequence[anchor_id];same(packet["source_anchor_saved_ns"], anchor["saved_ns"])
            next_time = by_sequence[anchor_id + 1]["saved_ns"] if anchor_id + 1 in by_sequence else summary["collection_closed_ns"]
            require(max(private_stamp, anchor["saved_ns"]) <= integer(packet["started_ns"]) <= integer(packet["completed_ns"])
                    <= integer(packet["saved_ns"]) <= next_time, "private witness was not saved inside its actual phase boundary")
            private_stamp = packet["saved_ns"];wall_ns += packet["completed_ns"] - packet["started_ns"]
            same(packet["witness"]["layer_types"], io.expected_layers(row["task"]))
            verify_witness(packet["witness"], full_sha256=source["python_semantic_sha256"], native_sha256=source["native_sha256"])
    return {"private_witness_records": len(private), "witness_construction_wall_ns": wall_ns}


def compare_population(records, config):
    legacy = previous.compare_population([{k: v for k, v in row.items() if k != "state_witnesses"} for row in records], config)
    task_checks = [];pairs = []
    for unit, spec in enumerate(config["tasks_and_seeds"]):
        group = {r["variant"]: r for r in records if r["unit"] == unit};left = group["CONTINUE_CURRENT"]
        ready = all(r["boundary_ready"] for r in group.values());matched = ready
        for variant, right in group.items():
            if variant == "CONTINUE_CURRENT": continue
            first = compare_witnesses(left["state_witnesses"][0]["witness"], right["state_witnesses"][0]["witness"])
            boundary = compare_witnesses(left["state_witnesses"][1]["witness"], right["state_witnesses"][1]["witness"])
            same_initial = digest(left["prefix"]["public"]["events"][0]["payload"]["initial"]) == digest(right["prefix"]["public"]["events"][0]["payload"]["initial"])
            same_prefix = physical_rows_equal(left["physical_rows"], right["physical_rows"], 16)
            matched = matched and first["comparison_equal"] and boundary["comparison_equal"] and same_initial and same_prefix
            pair = {**spec, "variant": variant, "initial": first, "boundary": boundary,
                    "initial_observation_equal": same_initial, "physical_prefix16_equal": same_prefix}
            if variant == "DIRECT_CURRENT":
                ending = compare_witnesses(left["state_witnesses"][2]["witness"], right["state_witnesses"][2]["witness"])
                physical = left["total_steps"] == right["total_steps"] and physical_rows_equal(left["physical_rows"], right["physical_rows"], left["total_steps"])
                final_fields = all(digest(left[k]) == digest(right[k]) for k in ("final_observation", "host_attempts", "host_returned", "policy_queries"))
                direct = ready and ending["comparison_equal"] and physical and final_fields
                pair.update(ending=ending, complete_physical_trajectory_equal=physical, final_observation_and_counts_equal=final_fields)
            pairs.append(pair)
        base = legacy["task_checks"][unit]
        task_checks.append({**spec, "all_boundaries_ready": ready, "matched_prefixes": bool(matched), "direct_loop_equal": bool(direct),
            "three_distinct_first_commands": base["three_distinct_first_commands"], "stop_has_zero_suffix": base["stop_has_zero_suffix"]})
    qualified = all(row[k] for row in task_checks for k in ("all_boundaries_ready", "matched_prefixes", "direct_loop_equal", "stop_has_zero_suffix"))
    qualified = qualified and sum(r["three_distinct_first_commands"] for r in task_checks) >= config["minimum_tasks_with_three_distinct_first_commands"]
    return {"qualification": "QUALIFIED" if qualified else "NOT_QUALIFIED", "task_checks": task_checks,
        "legacy_full_fingerprint_checks": legacy["task_checks"], "witness_pair_diagnostics": pairs,
        **{k: legacy[k] for k in ("methods", "execution_rows", "failures", "unavailable_boundaries")}}


def audit_records(manifest, models, records, events, private, summary):
    config = manifest["config"];identity = {k: manifest[k] for k in io.IDENTITY}
    expected = [(unit, spec["task"], spec["seed"], variant) for unit, spec in enumerate(config["tasks_and_seeds"]) for variant in config["variants"]]
    same([(r["unit"], r["task"], r["seed"], r["variant"]) for r in records], expected)
    ledger = {"counts": {}, "by_phase": {}};sequence = stamp = -1;position = 0;computations = []
    for key, row in zip(expected, records):
        allocation = dict(zip(("unit", "task", "seed", "variant"), key));group = []
        while position < len(events) and all(events[position].get(k) == v for k, v in allocation.items()):
            group.append(events[position]);position += 1
        # The old immutable grammar rejects every unregistered public/host key.
        old_record = {k: v for k, v in row.items() if k != "state_witnesses"}
        checked = previous.audit_case(group, old_record, {**identity, **allocation}, config["fault_oracle"], models[row["task"]],
            initial_ledger=ledger, previous_sequence=sequence, previous_saved_ns=stamp)
        ledger = checked["ledger"];sequence = checked["last_sequence"];stamp = checked["last_saved_ns"]
        computations.append({k: v for k, v in checked.items() if k.startswith("recomputed_")})
    same(position, len(events));same(summary["lifecycle"], ledger)
    same(summary["rows"], [{k: row[k] for k in previous.ROW_KEYS} for row in records])
    for key in io.IDENTITY: same(summary[key], identity[key])
    same(summary["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT");same(summary["failure"], None)
    same(summary["completed_executions"], 15);same(summary["controlled_steps"], sum(r["total_steps"] for r in records))
    require(summary["controlled_steps"] <= config["maximum_environment_steps"], "control budget exceeded")
    same(ledger["counts"]["reset_completed"], 765);same(ledger["by_phase"]["CONTROLLED_RESET"]["reset_completed"], 15)
    same(ledger["counts"]["simulation_frames_completed"], 15 * 25500 + summary["controlled_steps"] * 5)
    require(ledger["counts"]["simulation_frames_attempted"] <= config["maximum_simulation_frames"], "frame budget exceeded")
    for key in ("new_api_calls", "new_nominal_training", "new_selector_fits", "policy_updates"): same(summary[key], 0)
    integer(summary["wall_ns"]);integer(summary["collection_closed_ns"])
    private_costs = audit_private(records, events, private, identity, summary)
    return {**compare_population(records, config), "event_count": len(events), "executions": len(records),
        "costs": {"new_control_steps": summary["controlled_steps"], "lifecycle": ledger, "collection_wall_ns": summary["wall_ns"],
            **{key: sum(r[key] for r in records) for key in ("host_attempts", "host_returned", "policy_queries", "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev")},
            **private_costs, "historical_nominal_cost_paid_once": config["historical_nominal_cost"],
            "historical_design_preparation": config["historical_design_preparation"], "historical_qualification_v1_cost": config["historical_qualification_v1_cost"],
            "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0},
        "audit_computations": {k: sum(c[k] for c in computations) for k in computations[0]}}


def audit(path):
    manifest, models = io.load(path);folder = path.parent / "collection";output = path.parent / "audit";output.mkdir()
    started = perf_counter_ns();identity = {k: manifest[k] for k in io.IDENTITY}
    result = {**identity, "integrity": "FAILED", "qualification": "NOT_ESTABLISHED", "failure": None}
    try:
        completion = io.read(folder / "completion.json")
        same(completion["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT")
        for key in io.IDENTITY: same(completion[key], identity[key])
        require(set(completion["artifact_sha256"]) == {"events.jsonl.gz", "cases.jsonl.gz", "state_witnesses.jsonl.gz", "summary.json", "status.json"}, "complete v2 file bindings required")
        for name, expected in completion["artifact_sha256"].items(): same(io.sha(folder / name), expected)
        records, events, private = [previous.read_lines(folder / name) for name in ("cases.jsonl.gz", "events.jsonl.gz", "state_witnesses.jsonl.gz")]
        summary = io.read(folder / "summary.json");same(io.read(folder / "status.json"), {k: v for k, v in summary.items() if k != "rows"})
        computed = audit_records(manifest, models, records, events, private, summary)
        result.update(integrity="PASSED", **computed,
            collection_artifact_sha256={**completion["artifact_sha256"], "completion.json": io.sha(folder / "completion.json")},
            source_v1_qualification_unchanged="NOT_QUALIFIED", comparison_contract="EXACT_STATISTICS_TIMING_VALUES_ONLY",
            limitations=["SOURCE_GENERATED_STATE_WITNESSES_NOT_EXTERNAL_PHYSICS", "SHARED_GRAPH_SERIALIZER_AND_PROJECTION",
                "ONLY_THREE_QUALIFICATION_STATES_NOT_ALGORITHM_UTILITY", "NO_RETROSPECTIVE_PROMOTION_OF_V1"])
    except BaseException as error:
        result["failure"] = {"type": type(error).__name__, "message": str(error)};raise
    finally:
        result["audit_wall_ns"] = perf_counter_ns() - started;io.write(output / "record_audit.json", result)
    write_report(output, result)
    return result


def write_report(output, result):
    require(result["integrity"] == "PASSED", "complete audit required for report")
    costs = result["costs"]
    lines = ["# 中途干预执行资格 v2", "", f"日志完整性：**{result['integrity']}**；按新登记的状态见证合同，资格：**{result['qualification']}**。",
        "本轮只验证连续执行与可检查的状态比对，没有在线决策器或LLM，不是算法收益研究。旧v1结论仍为NOT_QUALIFIED，不用新标准回改旧数据。", "",
        f"提交：`{result['source_git_commit']}`；清单：`{result['manifest_id']}`。", "",
        "## 状态证据", "",
        f"保存并重建{costs['private_witness_records']}份私有状态图，分别在初始、16步边界及结束时落盘。完整指纹保留；比较指纹仅规范化准确类型统计包装器的episode_start_time和time_queue中的计时值，保留初始化标志、队列长度/容量及全部其他状态。",
        "公开准备器和干预器不接收状态图。独立日志审计检查原始完整指纹绑定、组件哈希、投影、双日志时间顺序和物理费用；共享序列化/投影数学已披露。主机状态见证不是外部真实性或通用行为等价证明。", "",
        "|任务|全部边界可用|前缀及比较见证匹配|普通循环一致|三种首命令不同|停止后零步|", "|---|---|---|---|---|---|"]
    for r in result["task_checks"]:
        lines.append("|" + r["task"] + "|" + "|".join("是" if r[k] else "否" for k in ("all_boundaries_ready", "matched_prefixes", "direct_loop_equal", "three_distinct_first_commands", "stop_has_zero_suffix")) + "|")
    lines += ["", "完整指纹差异仍逐项保存在record_audit.json的legacy_full_fingerprint_checks和witness_pair_diagnostics中；没有删除不一致字段来隐藏差异。", "",
        "## 全部任务结果", "", "|任务|种子|操作|成功|停止|边界可用|实际步数|截止损失|", "|---|---:|---|---|---|---|---:|---:|"]
    for r in result["execution_rows"]:
        lines.append(f"|{r['task']}|{r['seed']}|{r['variant']}|{r['success']}|{r['stopped']}|{r['boundary_ready']}|{r['total_steps']}|{r['deadline_loss']}|")
    lines += ["", "|操作|成功/分母|停止|实际控制步|平均截止损失|", "|---|---:|---:|---:|---:|"]
    for r in result["methods"]: lines.append(f"|{r['variant']}|{r['successes']}/{r['executions']}|{r['stops']}|{r['control_steps']}|{r['deadline_loss_total']/r['executions']:.6f}|")
    lines += ["", "失败、停止及边界不可用均保留；三个资格状态不能支持方法优越性、等效或非劣结论。", "", "## 完整费用", "",
        f"本次控制步{costs['new_control_steps']}，尝试/返回{costs['host_attempts']}/{costs['host_returned']}，政策查询{costs['policy_queries']}，参数拟合尝试/完成{costs['parameter_fit_attempts']}/{costs['parameter_fit_results']}，nfev {costs['optimizer_nfev']}。",
        f"受控初始重置15次，全部重置{costs['lifecycle']['counts']['reset_completed']}次，请求/完成帧{costs['lifecycle']['counts']['simulation_frames_attempted']}/{costs['lifecycle']['counts']['simulation_frames_completed']}。",
        f"采集主体{costs['collection_wall_ns']/1e9:.6f}秒，其中状态见证构建{costs['witness_construction_wall_ns']/1e9:.6f}秒；只读审计主体{result['audit_wall_ns']/1e9:.6f}秒。进程启动费用见单独进程回执。",
        f"只读审计另付{result['audit_computations']['recomputed_policy_queries']}次策略查询、{result['audit_computations']['recomputed_parameter_fits']}次拟合、{result['audit_computations']['recomputed_optimizer_nfev']}次nfev和45份状态图重建，不产生新环境步骤。",
        "各变体都计完整历史名义数据3840控制步、480受控重置、24480全部重置、12259200帧，按各自3个单元摊销为1280控制步/单元。历史设计3次枚举/432候选。",
        "先前v1资格实际花费1377控制步、15受控重置、765全部重置、389385帧，作为历史开发费用另外保留，不重复收集。软件物理夹具费用见冻结前软件回执；新增API、名义训练、选择器拟合、策略更新均为0。", "",
        "## 结论范围", "", "C4是同一任务内保存但此前未用于任务动作的参数。切换保存参数不代表恢复物理状态或跨任务记忆；本轮也不进行中途重新辨识。资格即使通过，仍需新的合法历史决策方法、强基线、独立任务验证、消融和完整论文，不能作为CCF A发表证据。", ""]
    report = output / "report_zh.md"
    with report.open("x", encoding="utf-8", newline="\n") as handle: handle.write("\n".join(lines))
    io.write(output / "report_receipt.json", {**{k: result[k] for k in io.IDENTITY}, "integrity": result["integrity"], "qualification": result["qualification"],
        "record_audit_sha256": io.sha(output / "record_audit.json"), "report_sha256": io.sha(report), "report_source_sha256": io.sha(Path(__file__))})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest", type=Path, required=True)
    result = audit(parser.parse_args().manifest.resolve());print(json.dumps({k: result[k] for k in ("integrity", "qualification", "executions", "event_count")}))
