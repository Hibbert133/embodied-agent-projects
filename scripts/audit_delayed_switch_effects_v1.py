"""Stream the fixed-switch journals; independently bind choices, states and costs."""
import argparse
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import delayed_switch_effects_v1 as io
from scripts import audit_delayed_intervention_v1 as old
from src.analysis.continuous_state_witness_v1 import compare_witnesses, verify_witness
from src.analysis.short_probe_journal_audit_v1 import physical_rows_equal
from src.analysis.short_probe_public_audit_v1 import same

require, integer = old.require, old.integer
ALLOCATION = ("unit", "task", "seed", "variant")


def lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle: yield json.loads(line)


def private_case(row, group, private, identity, case_index, previous_stamp, next_source_time):
    same(row["state_witnesses"], private)
    fields = {"label", "logical_step", "source_anchor_sequence", "source_anchor_saved_ns", "started_ns", "completed_ns",
        "ledger_before", "ledger_after", "source_witness", "witness"}
    by_seq = {e["sequence"]: e for e in group}
    initial = next(e for e in group if e["event"] == "CONTROLLED_INITIAL")
    expected = [("INITIAL", 0, initial["sequence"], row["initial_witness"], row["prefix"]["initial_ledger"]),
        ("BOUNDARY", row["prefix"]["public"]["completed_steps"], row["prefix"]["end_sequence"], row["prefix"]["boundary_witness"], row["prefix"]["boundary_ledger"]),
        ("FINAL", row["total_steps"], group[-1]["sequence"], row["end_witness"], row["ledger_before_close"])]
    wall = 0
    for offset, (packet, (label, step, anchor_id, source, ledger)) in enumerate(zip(private, expected)):
        require(set(packet) == set(identity) | {"event", "sequence", "saved_ns"} | fields, "private schema differs")
        for k, v in {**identity, "event": "STATE_WITNESS", "sequence": case_index * 3 + offset, "label": label,
                "logical_step": step, "source_anchor_sequence": anchor_id, "source_witness": source,
                "ledger_before": ledger, "ledger_after": ledger}.items(): same(packet[k], v)
        anchor = by_seq[anchor_id];same(packet["source_anchor_saved_ns"], anchor["saved_ns"])
        upper = by_seq[anchor_id + 1]["saved_ns"] if anchor_id + 1 in by_seq else next_source_time
        require(max(previous_stamp, anchor["saved_ns"]) <= integer(packet["started_ns"]) <= integer(packet["completed_ns"])
            <= integer(packet["saved_ns"]) <= upper, "private witness escaped its causal boundary")
        previous_stamp = packet["saved_ns"];wall += packet["completed_ns"] - packet["started_ns"]
        same(packet["witness"]["layer_types"], io.prior.expected_layers(row["task"]))
        verify_witness(packet["witness"], full_sha256=source["python_semantic_sha256"], native_sha256=source["native_sha256"])
    return previous_stamp, wall


def matched_unit(rows):
    same([r["variant"] for r in rows], list(io.METHODS))
    left = rows[0];result = []
    for right in rows[1:]:
        for key in ("unit", "task", "seed", "boundary_ready"): same(left[key], right[key])
        count = left["prefix"]["public"]["completed_steps"]
        same(count, right["prefix"]["public"]["completed_steps"])
        initial = compare_witnesses(left["state_witnesses"][0]["witness"], right["state_witnesses"][0]["witness"])
        boundary = compare_witnesses(left["state_witnesses"][1]["witness"], right["state_witnesses"][1]["witness"])
        require(initial["comparison_equal"] and boundary["comparison_equal"], "branches did not share the actual decision state")
        require(physical_rows_equal(left["physical_rows"], right["physical_rows"], count), "pre-intervention physics differs")
        require(count == 16 if left["boundary_ready"] else count <= 16, "invalid boundary length")
        result.append({"unit": left["unit"], "variant": right["variant"], "boundary_ready": left["boundary_ready"],
            "matched_steps": count, "initial": initial, "boundary": boundary})
    return result


def audit_data(manifest, models, records, events, private, summary, computations):
    identity = {k: manifest[k] for k in io.IDENTITY};config = manifest["config"]
    specs = manifest["allocation_oracle"]
    records, events, private = iter(records), iter(events), iter(private)
    current = next(events, None)
    ledger = {"counts": {}, "by_phase": {}};sequence = stamp = private_stamp = -1
    rows = [];matching = [];witness_wall = 0;event_count = 0
    for spec in specs:
        unit_rows = []
        for method in io.METHODS:
            row = next(records, None);require(row is not None, "missing allocated execution")
            allocation = {**{k: spec[k] for k in ("unit", "task", "seed")}, "variant": method}
            for k, v in allocation.items(): same(row[k], v)
            group = []
            while current is not None and all(current.get(k) == v for k, v in allocation.items()):
                group.append(current);current = next(events, None)
            checked = old.audit_case(group, {k: v for k, v in row.items() if k != "state_witnesses"},
                {**identity, **allocation}, spec["fault_oracle"], models[spec["task"]],
                initial_ledger=ledger, previous_sequence=sequence, previous_saved_ns=stamp)
            ledger = checked["ledger"];sequence = checked["last_sequence"];stamp = checked["last_saved_ns"]
            for k in computations: computations[k] += checked[k]
            packets = [next(private, None) for _ in range(3)]
            require(all(p is not None for p in packets), "missing private state record")
            next_time = current["saved_ns"] if current is not None else summary["collection_closed_ns"]
            private_stamp, wall = private_case(row, group, packets, {**identity, **allocation}, len(rows), private_stamp, next_time)
            witness_wall += wall;event_count += len(group);rows.append(io.compact(row));unit_rows.append(row)
        matching.extend(matched_unit(unit_rows))
    require(next(records, None) is None and current is None and next(private, None) is None, "unallocated trailing journal data")
    for k in io.IDENTITY: same(summary[k], identity[k])
    same(summary["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT");same(summary["failure"], None)
    same(summary["rows"], rows);same(summary["lifecycle"], ledger)
    same(summary["completed_executions"], config["executions"]);same(len(rows), config["executions"])
    same(summary["controlled_steps"], sum(r["total_steps"] for r in rows))
    same(summary["private_witness_records"], len(rows) * 3);same(summary["event_count"], event_count)
    require(summary["controlled_steps"] <= config["maximum_environment_steps"], "step budget exceeded")
    same(ledger["counts"]["reset_completed"], 51 * len(rows))
    same(ledger["by_phase"]["CONTROLLED_RESET"]["reset_completed"], len(rows))
    require(len(rows) <= config["maximum_controlled_resets"], "controlled reset budget exceeded")
    same(ledger["counts"]["simulation_frames_completed"], 25500 * len(rows) + 5 * summary["controlled_steps"])
    require(ledger["counts"]["simulation_frames_attempted"] <= config["maximum_simulation_frames"], "frame budget exceeded")
    for k in ("new_api_calls", "new_nominal_training", "new_selector_fits", "policy_updates"): same(summary[k], 0)
    integer(summary["wall_ns"]);integer(summary["collection_closed_ns"])
    return {"rows": rows, "matched_boundary_comparisons": matching, "event_count": event_count,
        "private_witness_records": 3 * len(rows), "witness_construction_wall_ns": witness_wall,
        "costs": {"new_control_steps": summary["controlled_steps"], "lifecycle": ledger, "collection_wall_ns": summary["wall_ns"],
            **{k: sum(r[k] for r in rows) for k in ("host_attempts", "host_returned", "policy_queries", "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev")},
            "historical_nominal_cost_paid_once": config["historical_nominal_cost"],
            "historical_design_preparation": config["historical_design_preparation"],
            "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0}}


def check_statistics(rows, result):
    """Separate aggregation of complete groups, with a shared documented RNG law."""
    means = {}
    for spec in io.population():
        g = spec["group"];means.setdefault(g, {m: [] for m in io.METHODS})
        for m in io.METHODS:
            r = next(r for r in rows if r["unit"] == spec["unit"] and r["variant"] == m)
            means[g][m].append(r["deadline_loss"])
    require(all(len(v) == 6 for g in means.values() for v in g.values()), "whole six-unit group required")
    rng = np.random.default_rng(20261023)
    sampled = [rng.integers(0, 12, size=(10000, 12)) * 3 + fi for fi in range(3)]
    maximum = 0.
    for index, method in enumerate(io.METHODS[1:]):
        group_delta = {g: (sum(means[g][method]) - sum(means[g][io.METHODS[0]])) / 6 for g in means}
        estimate = sum(group_delta.values()) / 36
        boot = np.array([sum(group_delta[int(g)] for family in sampled for g in family[b]) / 36 for b in range(10000)])
        actual = np.r_[estimate, np.quantile(boot, [.025, .975])]
        saved = np.r_[result["contrasts"][index]["mean_loss_difference"], result["contrasts"][index]["ci95"]]
        difference = float(np.max(np.abs(actual - saved)));maximum = max(maximum, difference)
        require(difference <= 1e-10, "independent contrast statistics differ")
    return {"integrity": "PASSED", "contrasts_checked": 2, "numeric_fields_checked": 6, "maximum_absolute_difference": maximum,
        "scope": "Independent whole-group sums and contrast bootstrap; shared NumPy RNG and quantile definition."}


def audit(path):
    manifest, models = io.load(path);folder = path.parent / "collection";output = path.parent / "audit";output.mkdir()
    started = perf_counter_ns();identity = {k: manifest[k] for k in io.IDENTITY}
    result = {**identity, "integrity": "FAILED", "failure": None, "computations_complete": False}
    computations = {k: 0 for k in ("recomputed_policy_queries", "recomputed_parameter_fits", "recomputed_optimizer_nfev")}
    try:
        completion = io.read(folder / "completion.json")
        same(completion["status"], "COLLECTED_FOR_INDEPENDENT_AUDIT")
        for k in io.IDENTITY: same(completion[k], identity[k])
        require(set(completion["artifact_sha256"]) == {"events.jsonl.gz", "cases.jsonl.gz", "state_witnesses.jsonl.gz", "summary.json", "status.json"}, "complete artifact set required")
        for name, value in completion["artifact_sha256"].items(): same(io.sha(folder / name), value)
        summary = io.read(folder / "summary.json")
        same(io.read(folder / "status.json"), {k: v for k, v in summary.items() if k != "rows"})
        checked = audit_data(manifest, models, lines(folder / "cases.jsonl.gz"), lines(folder / "events.jsonl.gz"),
            lines(folder / "state_witnesses.jsonl.gz"), summary, computations)
        statistics = io.statistics(checked["rows"]);numeric = check_statistics(checked["rows"], statistics)
        result.update(integrity="PASSED", computations_complete=True, **checked, statistics=statistics, statistics_audit=numeric,
            collection_artifact_sha256={**completion["artifact_sha256"], "completion.json": io.sha(folder / "completion.json")})
    except BaseException as error:
        result["failure"] = {"type": type(error).__name__, "message": str(error)};raise
    finally:
        result.update(audit_wall_ns=perf_counter_ns() - started, completed_case_recomputation=computations)
        io.write(output / "record_audit.json", result)
    write_report(output, result);return result


def write_report(output, result):
    require(result["integrity"] == "PASSED", "complete independent audit required")
    s = result["statistics"];c = result["costs"]
    text = ["# 从真实中途状态比较固定纠正方式", "", "本轮是固定操作的配对效应测量，没有训练或评估在线选择器。全部结果只属于登记的三任务、三故障族、两个端点和共同16步来源行为。", "",
        f"冻结提交：`{result['source_git_commit']}`；清单：`{result['manifest_id']}`。完整性：**PASSED**。",
        "216个任务单元，每单元实际执行三个分支，共648次；36个独立生成组，每组两个扰动端点×三个任务。组内相关性保留。", "",
        "C4是四步数据估计，C8是八步数据估计；所有分支先由C8执行到第16步，随后分别继续C8、改用保存的C4或取消纠正。C4此前未被成功验证，切换参数不恢复物理状态。无效或提前结束保持原结果，没有另找成功案例补足。", "",
        "|操作|成功/全部|失败|停止|边界不可用|平均截止损失|真实控制步|", "|---|---:|---:|---:|---:|---:|---:|"]
    for r in s["methods"]:
        text.append(f"|{r['variant']}|{r['successes']}/{r['executions']}|{r['failures']}|{r['stops']}|{r['unavailable_boundaries']}|{r['mean_deadline_loss']:.6f}|{r['actual_control_steps']}|")
    text += ["", "成功的截止损失等于全部实际步骤；失败或停止为500。真实交互费用另计。", "",
        "|比较（负值有利于左侧）|平均差/步|95%整组区间|实际改善/变差/相同单元|", "|---|---:|---|---|"]
    for r in s["contrasts"]:
        text.append(f"|{r['left']} − {r['right']}|{r['mean_loss_difference']:.6f}|[{r['ci95'][0]:.6f}, {r['ci95'][1]:.6f}]|{r['realized_better_units']}/{r['realized_worse_units']}/{r['realized_tied_units']}|")
    text += ["", "主比较是切换C4减继续C8；未纠正减继续C8是未作多重校正的次比较。按故障族分层，整组重抽10000次。单个状态只有一次未来实现，改善/伤害计数不是该状态期望效应，也不能当作无噪声分类标签或在线选择收益。", "",
        f"核对{result['event_count']}条主事件、{result['private_witness_records']}份私有图和{len(result['matched_boundary_comparisons'])}对共同前缀。完整指纹差异保留，仅按先前冻结且通过资格的统计计时投影作跨实例比较。公开代理不读取私有图、真实扰动、种子或未来结果。", "",
        f"新增控制步{c['new_control_steps']}，受控重置648次，全部重置{c['lifecycle']['counts']['reset_completed']}次，请求/完成帧{c['lifecycle']['counts']['simulation_frames_attempted']}/{c['lifecycle']['counts']['simulation_frames_completed']}。策略查询{c['policy_queries']}，拟合{c['parameter_fit_results']}次，nfev {c['optimizer_nfev']}。",
        f"采集主体{c['collection_wall_ns']/1e9:.6f}秒，包含私有见证构建{result['witness_construction_wall_ns']/1e9:.6f}秒；只读审计{result['audit_wall_ns']/1e9:.6f}秒。重算次数另见record_audit.json；进程启动开销另存回执。",
        "每个方法计完整历史名义来源3840控制步/480受控重置/24480全部重置/12259200帧，按216单元摊销17.777778控制步/单元；历史设计3次枚举/432候选。既有两轮执行资格1377+1425控制步、765+765全部重置、389385+389625帧以及其软件费用是已付开发费用，单列保留，未重跑。",
        "新增API、名义训练、选择器拟合及策略权重更新均为0。全部失败及逐单元三分支损失见record_audit.json，不筛选有利病例。", "",
        "本轮没有获取新证据后重新辨识的分支，没有任务内变化或跨任务缓存策略，也未比较完整独立部署的所有强基线。样本量按覆盖和资源预定，没有小差异功效或等效声明。算法创新、基于合法历史的选择、独立部署收益及论文要求仍未完成。", ""]
    report = output / "report_zh.md"
    with report.open("x", encoding="utf-8", newline="\n") as handle: handle.write("\n".join(text))
    io.write(output / "report_receipt.json", {**{k: result[k] for k in io.IDENTITY}, "record_audit_sha256": io.sha(output / "record_audit.json"),
        "report_sha256": io.sha(report), "report_source_sha256": io.sha(Path(__file__))})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("--manifest", type=Path, required=True)
    result = audit(parser.parse_args().manifest.resolve())
    print(json.dumps({"integrity": result["integrity"], "events": result["event_count"], "contrasts": result["statistics"]["contrasts"]}))
