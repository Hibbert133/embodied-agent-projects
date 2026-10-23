"""Offline audit of saved API choices, control commands and continuous state."""
from __future__ import annotations
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_online_calibrated_agent import (
    load, load_model, METHODS, IDENTITY, ACTION_METHOD, baseline_plan, candidate_plans, summarize, api_metrics)
from scripts.run_response_calibration import restore
from scripts.run_continuous_probe import state_hash, normalized
from src.probe.continuous import StepObservation, symmetric_program
from src.probe.online_calibrated_agent import OnlineClient, payload, sha, validate_payload, canonical
from src.rollout import create_push_policy


def rng_hash(rng):
    return hashlib.sha256(json.dumps(rng.bit_generator.state, sort_keys=True).encode()).hexdigest()


def replay_api(api, config):
    rows = api["attempts"]
    cursor = 0
    def transport(outgoing, settings):
        nonlocal cursor
        if cursor >= len(rows):
            raise ValueError("API replay exhausted recorded attempts")
        row = rows[cursor]
        cursor += 1
        if outgoing != row["payload"] or sha(outgoing) != row["request_sha256"]:
            raise ValueError("API request/repair replay mismatch")
        if row["status"] == "TIMEOUT":
            raise TimeoutError(row["error"].split(": ", 1)[-1])
        if row["status"] == "TRANSPORT_ERROR":
            raise RuntimeError(row["error"])
        return {"raw": row["raw_response"], "usage": row["usage"]}
    client = OnlineClient(config, transport=transport)
    for saved in api["decisions"]:
        validate_payload(saved["payload"])
        rebuilt = client.decide(saved["payload"])
        if normalized(rebuilt) != saved:
            raise ValueError("saved API decision does not match response/circuit replay")
    if cursor != len(rows) or len(rows) != len(client.attempts):
        raise ValueError("unused/duplicated API attempts")
    for saved, rebuilt in zip(rows, client.attempts):
        skip = {"latency_ms"} | ({"error"} if saved["status"] == "TRANSPORT_ERROR" else set())
        if {k: v for k, v in saved.items() if k not in skip} != {k: v for k, v in rebuilt.items() if k not in skip}:
            raise ValueError("API attempt accounting/response replay mismatch")
        if not np.isfinite(saved["latency_ms"]) or saved["latency_ms"] < 0:
            raise ValueError("invalid API latency")
        if any(k not in ("input_tokens", "output_tokens") or type(v) is not int or v < 0 for k, v in saved["usage"].items()):
            raise ValueError("invalid token usage")
    proxy = SimpleNamespace(attempts=rows, decisions=client.decisions, primary_calls=client.primary_calls,
                            repairs=client.repairs, health_calls=client.health_calls)
    if api_metrics(proxy) != api["metrics"]:
        raise ValueError("API cost/timeout accounting mismatch")
    return proxy


def verify(m, records, events, declarations, status, summary, api, model):
    c = m["config"]
    identity = {k: m[k] for k in IDENTITY}
    all_items = records + events + declarations + [status, summary, api]
    if any(any(row.get(k) != value for k, value in identity.items()) for row in all_items):
        raise ValueError("artifact provenance mismatch")
    if [event["seq"] for event in events] != list(range(1, len(events)+1)):
        raise ValueError("event chronology mismatch")
    by_seq = {event["seq"]: event for event in events}
    client = replay_api(api, c["api"])
    api_decisions = {d["request_id"]: d for d in api["decisions"]}
    if len(api_decisions) != len(api["decisions"]):
        raise ValueError("duplicate logical API decision")
    decision_events = {}
    begins, ends = {}, {}
    for event in events:
        kind = event["event"]
        if kind == "API_REQUEST_STARTED":
            number = event["api"]["attempt"]
            if number in begins:
                raise ValueError("duplicate API request event")
            begins[number] = event
        elif kind == "API_ATTEMPT_COMPLETED":
            number = event["api"]["attempt"]
            if number in ends:
                raise ValueError("duplicate API completion event")
            ends[number] = event
        elif kind == "API_DECISION_PERSISTED":
            decision = event["api"]
            if decision["request_id"] in decision_events or api_decisions.get(decision["request_id"]) != decision:
                raise ValueError("persisted API decision mismatch")
            decision_events[decision["request_id"]] = event
    if set(begins) != set(ends) or set(begins) != set(range(1, len(api["attempts"])+1)) or set(decision_events) != set(api_decisions):
        raise ValueError("incomplete API request/response journal")
    for row in api["attempts"]:
        start, end = begins[row["attempt"]], ends[row["attempt"]]
        expected_start = {k: row[k] for k in ("attempt", "request_id", "stage", "repair", "payload", "request_sha256")}
        if start["api"] != expected_start or end["api"] != row or not start["seq"] < end["seq"] < decision_events[row["request_id"]]["seq"]:
            raise ValueError("API request/response/decision order mismatch")
    health = api["decisions"][0]
    if health["payload"] != payload("HEALTH", "q000"):
        raise ValueError("health check contract mismatch")
    if not health["valid"]:
        if status["status"] != "FAILED_API_PREFLIGHT" or records or declarations or any(not e["event"].startswith("API_") for e in events):
            raise ValueError("simulator execution after failed preflight")
        counts = {"complete_units": 0, "episodes": 0, "physical_steps": 0, "environment_resets": 0,
                  "api_attempts": len(api["attempts"]), "memory_writes": 0}
        if summary["statistics"] is not None or summary["api"] != api["metrics"] or any(status.get(k) != v or summary.get(k) != v for k, v in counts.items()):
            raise ValueError("preflight failure accounting mismatch")
        return {**identity, **counts, "status": status["status"], "integrity": "PASSED", "statistics": None,
                "api": api["metrics"], "replayed_api_decisions": len(api_decisions), "verified_task_steps": 0,
                "continuous_handoffs": 0, "audit_scope": "Saved API interface and zero-simulator preflight boundary."}
    expected = [(s, k, method) for s in range(9400, 9404) for k in c["conditions"] for method in METHODS]
    if [(r["seed"], r["condition_oracle"], r["method"]) for r in records] != expected or len(declarations) != 96:
        raise ValueError("complete 96-episode population mismatch")
    prefixes, initials = {}, {}
    used_requests = ["q000"]
    steps = handoffs = 0
    previous_episode_end = decision_events["q000"]["seq"]
    for index, (record, declaration) in enumerate(zip(records, declarations), 1):
        key = {**identity, "episode_index": index, "seed": record["seed"], "condition_oracle": record["condition_oracle"],
               "method": record["method"], "model_sha256": m["model_sha256"]}
        if any(record.get(k) != v or declaration.get(k) != v for k, v in key.items()):
            raise ValueError("episode/model association mismatch")
        sequences = record["sequences"]
        initial = StepObservation(**record["initial"])
        handoff = StepObservation(**record["handoff"])
        initial_event = by_seq[sequences["begin"]]
        if initial_event["event"] != "EPISODE_STARTED" or initial_event["initial"] != record["initial"] or initial_event["rng_initial"] != record["rng_initial"]:
            raise ValueError("initial state journal mismatch")
        if not previous_episode_end < sequences["begin"]:
            raise ValueError("episode chronology overlaps")
        for seq in (v for v in sequences.values() if v is not None):
            if any(by_seq[seq].get(k) != v for k, v in key.items()):
                raise ValueError("event associated with another episode")
        rng = np.random.default_rng(int(np.random.SeedSequence(
            [record["seed"], c["conditions"].index(record["condition_oracle"]), c["noise_namespace"]]).generate_state(1)[0]))
        if record["rng_initial"] != rng_hash(rng):
            raise ValueError("initial RNG mismatch")
        initials.setdefault(record["seed"], set()).add(state_hash(initial.observation))
        evidence = restore(record["probe"]) if record["probe"] else None
        method = record["method"]
        pre, post = record["pre_decision"], record["post_decision"]
        if method == "LLM_AGENT":
            if pre is None or api_decisions.get(pre["request_id"]) != pre:
                raise ValueError("missing/current-episode API pre-decision")
            expected_payload = payload("PRE_PROBE", pre["request_id"], initial=initial)
            if pre["payload"] != expected_payload:
                raise ValueError("pre-probe API sees foreign/noncausal evidence")
            used_requests.append(pre["request_id"])
            pre_event = decision_events[pre["request_id"]]
            if any(pre_event.get(k) != v for k, v in key.items()) or not sequences["begin"] < pre_event["seq"] < sequences["execution"]:
                raise ValueError("pre-decision not bound before physical execution")
            do_probe = pre["selected_action"] == "PROBE_16"
            if do_probe and pre_event["seq"] >= sequences["probe_start"]:
                raise ValueError("probe happened before its API selection")
        else:
            if pre is not None or post is not None:
                raise ValueError("baseline received API decisions")
            do_probe = method != "NO_PROBE"
        n_probe = evidence.steps if evidence else 0
        if bool(evidence) != do_probe:
            raise ValueError("API selected probe differs from actual probe execution")
        if evidence:
            if not 1 <= n_probe <= 16 or evidence.requested_steps != 16:
                raise ValueError("probe length mismatch")
            previous = initial.observation
            for row, command in zip(evidence.transitions, symmetric_program()):
                if row.before != previous or row.command != command or len(row.after) != 39 or not np.isfinite(row.after).all():
                    raise ValueError("probe observation/command discontinuity")
                previous = row.after
                rng.normal(0, .05, 3)
            stop = "SUCCESS" if handoff.success else "TERMINATED" if handoff.terminated else "TRUNCATED" if handoff.truncated else "PROGRAM_COMPLETE"
            if previous != handoff.observation or evidence.final != handoff or evidence.stop_reason != stop or (stop == "PROGRAM_COMPLETE" and n_probe != 16):
                raise ValueError("probe handoff/stop mismatch")
            start, end = by_seq[sequences["probe_start"]], by_seq[sequences["probe_end"]]
            if start["event"] != "PROBE_STARTED" or end["event"] != "PROBE_COMPLETED" or end["evidence"] != record["probe"] or not sequences["begin"] < start["seq"] < end["seq"] < sequences["execution"]:
                raise ValueError("probe event chronology mismatch")
            if start["rng_before"] != record["rng_initial"] or start["host_calls"] != 0 or end["rng_after"] != rng_hash(rng) or end["host_calls"] != n_probe:
                raise ValueError("probe reset/reseed/counter mismatch")
            prefixes.setdefault((record["seed"], record["condition_oracle"]), set()).add(canonical(record["probe"]))
            handoffs += 1
        elif handoff != initial or sequences["probe_start"] is not None or sequences["probe_end"] is not None:
            raise ValueError("unrequested probe state change")
        if record["rng_handoff"] != rng_hash(rng):
            raise ValueError("probe-to-task RNG reseed")
        if method == "LLM_AGENT":
            action = pre["selected_action"]
            chosen = {"correction": [0., 0., 0., 0.], "fit": None}
            if do_probe and evidence.stop_reason == "PROGRAM_COMPLETE":
                if post is None or api_decisions.get(post["request_id"]) != post:
                    raise ValueError("missing post-probe API choice")
                plans = candidate_plans(evidence, model)
                if post["payload"] != payload("POST_PROBE", post["request_id"], initial=initial, evidence=evidence,
                                              plans=plans, remaining_steps=500-n_probe):
                    raise ValueError("post-probe API payload/candidate mismatch")
                used_requests.append(post["request_id"])
                post_event = decision_events[post["request_id"]]
                if any(post_event.get(k) != v for k, v in key.items()) or not sequences["probe_end"] < post_event["seq"] < sequences["execution"]:
                    raise ValueError("post-probe choice after execution or foreign episode")
                action = post["selected_action"]
                if action in ACTION_METHOD:
                    chosen = plans[action]
            else:
                if post is not None:
                    raise ValueError("unexpected post-probe API call")
                if do_probe:
                    action = "TERMINAL_PROBE"
            aborted = action == "ABSTAIN"
            if aborted:
                chosen = None
        else:
            action, aborted = method, False
            chosen = baseline_plan(method, evidence, model)
        execution = {"selected_action": action, "plan": normalized(chosen), "aborted": aborted,
                     "pre_request_id": pre["request_id"] if pre else None, "post_request_id": post["request_id"] if post else None}
        selected = by_seq[sequences["execution"]]
        if record["execution"] != execution or declaration["execution"] != execution or declaration["execution_seq"] != sequences["execution"]:
            raise ValueError("executor substituted a different API action/correction")
        if selected["event"] != "EXECUTION_SELECTED" or selected["execution"] != execution or selected["handoff"] != record["handoff"] or selected["rng_handoff"] != rng_hash(rng) or selected["host_calls"] != n_probe:
            raise ValueError("persisted executor selection/handoff mismatch")
        trace = record["task_trace"]
        current = handoff
        policy = create_push_policy()
        if trace:
            task_start = by_seq[sequences["task_start"]]
            if task_start["event"] != "TASK_STARTED" or task_start["execution_seq"] != sequences["execution"] or not sequences["execution"] < task_start["seq"] < sequences["task_end"]:
                raise ValueError("task started before persisted API selection")
            if task_start["rng_before"] != rng_hash(rng) or task_start["host_calls"] != n_probe:
                raise ValueError("task start handoff mismatch")
        elif sequences["task_start"] is not None:
            raise ValueError("task start without task execution")
        for i, row in enumerate(trace, 1):
            if aborted or current.success or current.terminated or current.truncated:
                raise ValueError("task execution after abstention/termination")
            if StepObservation(**row["before"]) != current or row["host_calls"] != n_probe+i or row["rng_before"] != rng_hash(rng):
                raise ValueError("task state/RNG/counter continuity mismatch")
            base = np.asarray(policy.get_action(np.array(current.observation)), dtype=np.float32)
            if row["base_command"] != base.tolist() or row["command"] != (base+np.array(chosen["correction"], dtype=np.float64)).tolist():
                raise ValueError("physical task command does not use selected correction")
            rng.normal(0, .05, 3)
            if row["rng_after"] != rng_hash(rng):
                raise ValueError("task RNG reseed/advance mismatch")
            current = StepObservation(**row["after"])
        if n_probe+len(trace) > 500 or (not aborted and not (current.success or current.terminated or current.truncated) and n_probe+len(trace) != 500):
            raise ValueError("task budget/stop mismatch")
        expected_outcome = {**key, "success": current.success, "aborted": aborted,
                            "probe_steps": n_probe, "task_steps": len(trace), "total_steps": n_probe+len(trace),
                            "environment_resets": 1, "actuator_resets": 1, "host_calls": n_probe+len(trace),
                            "initial_hash": state_hash(initial.observation), "handoff_hash": state_hash(handoff.observation),
                            "final_hash": state_hash(current.observation)}
        if record["outcome"] != expected_outcome:
            raise ValueError("task outcome/cost reconstruction mismatch")
        task_end, end_event = by_seq[sequences["task_end"]], by_seq[sequences["end"]]
        if task_end["event"] != "TASK_COMPLETED" or task_end["final"] != normalized(asdict(current)) or task_end["task_steps"] != len(trace) or task_end["host_calls"] != n_probe+len(trace):
            raise ValueError("task completion journal mismatch")
        if not sequences["execution"] < sequences["task_end"] < sequences["end"] or end_event["event"] != "EPISODE_COMPLETED" or end_event["outcome"] != expected_outcome:
            raise ValueError("outcome occurred before decision/execution")
        previous_episode_end = sequences["end"]
        steps += len(trace)
    if used_requests != [d["request_id"] for d in api["decisions"]]:
        raise ValueError("unused, future or cross-episode API decisions")
    if any(len(v) != 1 for v in prefixes.values()) or any(len(v) != 1 for v in initials.values()):
        raise ValueError("matched initial state/probe mismatch")
    stats = summarize(records, client, c)
    expected_status = "COMPLETED_INTERFACE_PASS" if stats["gate_passed"] else "COMPLETED_INTERFACE_FAILED"
    counts = {"complete_units": 16, "episodes": 96, "physical_steps": sum(r["outcome"]["total_steps"] for r in records),
              "environment_resets": 96, "api_attempts": len(api["attempts"]), "memory_writes": 0}
    if summary["statistics"] != stats or summary["api"] != api["metrics"] or counts["physical_steps"] > 48000 or any(status.get(k) != v or summary.get(k) != v for k, v in counts.items()) or status["status"] != expected_status or summary["status"] != expected_status:
        raise ValueError("registered statistics/status/cost mismatch")
    return {**identity, **counts, "status": expected_status, "integrity": "PASSED", "statistics": stats,
            "api": api["metrics"], "replayed_api_decisions": len(api_decisions),
            "verified_task_steps": steps, "continuous_handoffs": handoffs,
            "audit_scope": "Raw API response/contract replay, selected-command replay, full visible state chains and exact RNG draws; no task-dynamics resimulation."}


def analyze(path):
    m = load(path)
    output = path.parent
    model, model_sha = load_model(m["config"])
    if model_sha != m["model_sha256"]:
        raise ValueError("qualified model binding changed")
    with_gzip = output / "episodes.jsonl.gz"
    records = []
    if with_gzip.exists():
        with gzip.open(with_gzip, "rt", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle]
    def lines(name):
        file = output / name
        return [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines()] if file.exists() else []
    def read(name):
        return json.loads((output / name).read_text(encoding="utf-8"))
    result = verify(m, records, lines("events.jsonl"), lines("decisions.jsonl"), read("status.json"),
                    read("summary.json"), read("api_audit.json"), model)
    for name, expected in m["input_sha256"].items():
        blob = subprocess.check_output(["git", "show", f"{m['source_git_commit']}:{name}"], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != expected:
            raise ValueError(f"manifest input differs from frozen Git source: {name}")
    result["matched_git_inputs"] = len(m["input_sha256"])
    result["artifact_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    return result


def report(r):
    lines = ["# 在线 API 探测与纠正闭环验证", "", f"实验状态：{r['status']}；离线审计：{r['integrity']}。", "",
             f"运行标识：{r['experiment_run_id']}", f"清单标识：{r['manifest_id']}",
             f"冻结源代码：{r['source_git_commit']}", ""]
    a = r["api"]
    lines += [f"API 尝试 {a['attempts']} 次：健康预检 {a['health_primary']} 次、决策主调用 {a['decision_primary']} 次、格式修复 {a['repairs']} 次。",
              f"硬超时 {a['timeouts']} 次，其他传输失败 {a['transport_errors']} 次，响应校验失败 {a['invalid_responses']} 次。",
              f"已知输入/输出 tokens：{a['input_tokens_known']}/{a['output_tokens_known']}；{a['unknown_usage_attempts']} 次用量未知，不计为免费调用。",
              f"延迟中位数/P90/最大值（秒）：{a['latency_p50_seconds']:.2f}/{a['latency_p90_seconds']:.2f}/{a['latency_max_seconds']:.2f}。", ""]
    if r["statistics"] is None:
        lines += ["API 预检未通过；按冻结方案停止，未创建仿真环境、执行任务种子或补跑。此结果不能证明在线闭环或任务收益。"]
    else:
        stats = r["statistics"]
        lines += [f"逻辑决策有效率：{stats['valid_logical_decisions']}/{stats['logical_decisions']}（{stats['logical_valid_rate']:.1%}）。",
                  f"完整的探测→API 纠正选择→真实执行链路：{stats['complete_correction_chains']} 次。",
                  f"主动停止 {a['intentional_abstentions']} 次；断路停止 {a['circuit_open_decisions']} 次。",
                  f"闭环验收门槛：{stats['gates']}。", "",
                  "| 方法 | 成功 / 16 | 停止 | 平均在线步数 | 平均含离线摊销步数 |",
                  "|---|---:|---:|---:|---:|"]
        names = {"NO_PROBE": "不探测", "CONT_NO_CORRECTION": "探测不纠正", "CONT_DYNAMIC": "动态 OLS",
                 "PRIOR_AFFINE": "校准仿射", "PRIOR_NEAREST": "同数据最近邻", "LLM_AGENT": "在线 LLM"}
        for method, v in stats["methods"].items():
            lines.append(f"| {names[method]} | {v['successful']} | {v['abstained']} | {v['mean_online_steps']:.2f} | {v['mean_amortized_steps']:.2f} |")
        llm = stats["methods"]["LLM_AGENT"]["successful"]
        affine = stats["methods"]["PRIOR_AFFINE"]["successful"]
        lines += ["", f"LLM 成功 {llm}/16，校准仿射基线 {affine}/16；差值 {100*(llm-affine)/16:+.2f} 个百分点，仅为描述性比较。",
                  "本轮只有四个独立任务种子簇。接口通过不等于 LLM 提升任务表现；不能作为算法创新、校准失配鲁棒性、跨任务迁移或 CCF A 发表证据。",
                  "三种可访问校准先验的方法均计入 2,304 个离线步和 144 次重置，按 16 单元摊销，每单元增加 144 步及九次重置。",
                  "停止案例保留在分母中，低步数可能来自未执行任务，不能直接解读为效率改善。",
                  "无记忆写入、策略权重更新或新条件；所有历史结果及保留种子不变。"]
    lines += ["", f"新增物理执行：{r['physical_steps']} 步、{r['environment_resets']} 次初始重置。",
              f"审计重放 {r['replayed_api_decisions']} 个 API 决策，验证 {r['continuous_handoffs']} 次探测衔接及 {r['verified_task_steps']} 个任务步。",
              "审计验证保存的响应、候选选择、底层策略命令及连续观测/随机数链，不重新仿真任务动力学。",
              "仿真在 API 等待期间暂停，网络延迟单独报告；本轮不证明物理机器人实时执行能力。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    source, target = args.manifest.resolve(), args.output.resolve()
    if target == source.parent or source.parent in target.parents:
        raise ValueError("analysis must not overwrite the immutable collection")
    result = analyze(source)
    target.mkdir(parents=True, exist_ok=False)
    (target / "audit.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    (target / "report.md").write_text(report(result), encoding="utf-8")
    print(report(result))
