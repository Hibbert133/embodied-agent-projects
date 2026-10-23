"""Independent streaming replay of frame decisions, inputs and costs; no simulation."""
import argparse
from dataclasses import asdict
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_frame_evidence import (load, load_priors, identity, noise_seed, choose,
                                      summarize, CONTEXTS, METHODS)
from scripts.run_continuous_probe import state_hash, normalized
from scripts.run_response_calibration import restore
from src.probe.continuous import StepObservation
from src.probe.frame_identification import program, canonical_hash, transcript_hash, encode_command
from src.rollout import create_push_policy


def rng_hash(rng):
    return hashlib.sha256(json.dumps(rng.bit_generator.state, sort_keys=True).encode()).hexdigest()


def verify_event_order(events):
    if [e["event_index"] for e in events] != list(range(1,len(events)+1)):
        raise ValueError("chronology event index mismatch")
    for event in events:
        if type(event["perf_counter_ns"]) is not int or event["perf_counter_ns"] <= 0 or datetime.fromisoformat(event["utc"]).tzinfo is None:
            raise ValueError("invalid chronology timestamp")
    if any(first["perf_counter_ns"] >= second["perf_counter_ns"] for first,second in zip(events,events[1:])):
        raise ValueError("decision/execution timestamp order mismatch")
    # Wall clocks can step under synchronization; only the monotonic QPC orders execution.
    return sum(datetime.fromisoformat(a["utc"]) > datetime.fromisoformat(b["utc"]) for a,b in zip(events,events[1:]))


def verify_episode(m, record, declaration, events, arx, legacy, policy):
    key_names = (*identity(m), "episode_index", "seed", "context_oracle", "method", "arx_model_sha256", "legacy_model_sha256")
    key = {k:record[k] for k in key_names}
    if any(key[k] != v for k,v in identity(m).items()) or key["arx_model_sha256"] != m["arx_model_sha256"] or \
            key["legacy_model_sha256"] != m["legacy_model_sha256"]:
        raise ValueError("episode provenance/model mismatch")
    if any(any(value.get(k) != v for k,v in key.items()) for value in [declaration, record["outcome"], *events]):
        raise ValueError("record/declaration/event association mismatch")
    if declaration != record["declaration"]:
        raise ValueError("saved declaration was changed")
    evidence = restore(declaration["evidence"]) if declaration["evidence"] is not None else None
    if evidence is not None and normalized(asdict(evidence)) != declaration["evidence"]:
        raise ValueError("visible evidence schema mismatch")
    initial = StepObservation(**declaration["initial"])
    if len(initial.observation) != 39 or initial.success or initial.terminated or initial.truncated:
        raise ValueError("invalid initial observation")
    method, context, seed = key["method"], key["context_oracle"], key["seed"]
    if method not in METHODS or context not in CONTEXTS:
        raise ValueError("unknown registered population")
    expected_program = program(method)
    n_probe = evidence.steps if evidence else 0
    if (method=="NO_PROBE" and evidence is not None) or (method!="NO_PROBE" and evidence is None):
        raise ValueError("no-probe evidence mismatch")
    if evidence and (not 1 <= n_probe <= len(expected_program) or evidence.requested_steps != len(expected_program)):
        raise ValueError("probe step/reserve mismatch")
    choice = normalized(choose(method, evidence, arx, legacy))
    if choice != declaration["choice"] or canonical_hash(choice) != declaration["choice_hash"]:
        raise ValueError("visible-only decision replay mismatch")
    trace = record["steps"]
    if len(trace) < n_probe or len(trace) > 500:
        raise ValueError("episode budget mismatch")
    rng = np.random.default_rng(noise_seed(seed))
    initial_rng = rng_hash(rng)
    previous, handoff, handoff_rng = initial, initial if n_probe==0 else None, initial_rng if n_probe==0 else None
    # Independent implementation of the evaluator injection; do not reuse FrameFault.
    rotation = np.eye(2, dtype=np.float32) if context == "FRAME0" else np.array([[0,-1],[1,0]], dtype=np.float32)
    bias = np.array([-.1,.1], dtype=np.float32) if context == "FRAME0" else np.array([.1,-.1], dtype=np.float32)
    for index, row in enumerate(trace, 1):
        before, after = StepObservation(**row["before"]), StepObservation(**row["after"])
        if before != previous or row["host_calls"] != index or len(after.observation) != 39:
            raise ValueError("observation/counter handoff discontinuity")
        if before.success or before.terminated or before.truncated:
            raise ValueError("step after terminal state")
        command = np.asarray(row["command"], dtype=np.float32)
        if command.shape != (4,) or not np.isfinite(command).all() or np.any(np.abs(command) > 1):
            raise ValueError("bounded input violation")
        if index <= n_probe:
            transition = evidence.transitions[index-1]
            if tuple(row["command"]) != expected_program[index-1] or transition.command != tuple(row["command"]) or \
                    transition.before != before.observation or transition.after != after.observation:
                raise ValueError("probe evidence/command mismatch")
            if "raw_policy" in row or "choice_hash" in row:
                raise ValueError("future task choice attached to probe")
        else:
            if choice["stop"]:
                raise ValueError("task executed after stop")
            raw = np.asarray(policy.get_action(np.array(before.observation)), dtype=np.float32)
            if row.get("raw_policy") != raw.tolist() or row.get("choice_hash") != declaration["choice_hash"] or \
                    not np.array_equal(command, encode_command(choice["controller"], raw)):
                raise ValueError("task did not execute the saved fixed-policy controller")
        if row["rng_before"] != rng_hash(rng):
            raise ValueError("actuator RNG reseed/discontinuity")
        acted = command.copy()
        acted[:2] = rotation @ command[:2] + bias
        acted[:3] += rng.normal(0, .05, 3).astype(np.float32)
        acted = np.clip(acted, -1, 1)
        if row["executed_action_oracle"] != acted.tolist() or row["rng_after"] != rng_hash(rng):
            raise ValueError("frame/noise/clipping replay mismatch")
        previous = after
        if index == n_probe:
            handoff, handoff_rng = after, rng_hash(rng)
    if (evidence and handoff != evidence.final) or declaration["host_calls"] != n_probe or declaration["rng_handoff"] != handoff_rng:
        raise ValueError("probe/task handoff mismatch")
    stop = "SUCCESS" if handoff.success else "TERMINATED" if handoff.terminated else "TRUNCATED" if handoff.truncated else "PROGRAM_COMPLETE"
    if evidence and (evidence.stop_reason != stop or (stop == "PROGRAM_COMPLETE" and n_probe != len(expected_program))):
        raise ValueError("registered probe stopping mismatch")
    ended = previous.success or previous.terminated or previous.truncated
    if (choice["stop"] and len(trace) != n_probe) or (not ended and not choice["stop"] and len(trace) != 500):
        raise ValueError("task budget/stop mismatch")
    controller_id = choice["controller"]["id"] if choice["controller"] else None
    correct = controller_id == ("FRAME_A" if context == "FRAME0" else "FRAME_B") if method.startswith("MODEL_") else None
    outcome = {**key, "success":previous.success, "stopped":choice["stop"], "controller_id":controller_id,
        "correct_frame_choice_oracle":correct, "probe_steps":n_probe, "task_steps":len(trace)-n_probe,
        "total_steps":len(trace), "environment_resets":1, "actuator_resets":1,
        "prefix4_hash":transcript_hash(evidence,4) if evidence else None, "probe_hash":transcript_hash(evidence) if evidence else None,
        "initial_hash":state_hash(initial.observation), "handoff_hash":state_hash(handoff.observation),
        "final_hash":state_hash(previous.observation)}
    if outcome != record["outcome"]:
        raise ValueError("outcome/cost reconstruction mismatch")
    expected_events = [
        ("INITIAL", {"host_calls":0, "observation_hash":state_hash(initial.observation), "rng_hash":initial_rng}),
        ("PROBE_FINISHED", {"host_calls":n_probe, "observation_hash":state_hash(handoff.observation), "rng_hash":handoff_rng}),
        ("CHOICE_SAVED", {"host_calls":n_probe, "choice_hash":declaration["choice_hash"]}),
        ("TASK_SKIPPED" if choice["stop"] else "TASK_STARTED", {"host_calls":n_probe,
            "observation_hash":state_hash(handoff.observation), "rng_hash":handoff_rng, "choice_hash":declaration["choice_hash"]}),
        ("FINISHED", {"host_calls":len(trace), "outcome_hash":canonical_hash(outcome)})]
    if len(events) != 5:
        raise ValueError("chronology event count mismatch")
    for event, (kind, values) in zip(events, expected_events):
        if event["kind"] != kind or any(event.get(k) != v for k,v in values.items()):
            raise ValueError("decision/execution chronology mismatch")
    return outcome


def analyze(path):
    m = load(path); root = path.parent
    arx, legacy, legacy_sha = load_priors(m["config"])
    if normalized(arx.to_dict()) != m["nominal_arx"] or canonical_hash(arx.to_dict()) != m["arx_model_sha256"] or legacy_sha != m["legacy_model_sha256"]:
        raise ValueError("training-only model reconstruction mismatch")
    saved_model = json.loads((root/"nominal_arx.json").read_text())
    if saved_model != {**identity(m), "model":m["nominal_arx"], "arx_model_sha256":m["arx_model_sha256"]}:
        raise ValueError("model artifact mismatch")
    declarations = [json.loads(line) for line in (root/"decisions.jsonl").read_text().splitlines()]
    events = [json.loads(line) for line in (root/"events.jsonl").read_text().splitlines()]
    if len(declarations) != 176 or len(events) != 880 or [e["event_index"] for e in events] != list(range(1,881)):
        raise ValueError("complete decision/event population mismatch")
    wall_backsteps = verify_event_order(events)
    expected = [(s,k,method) for s in range(9800,9808) for k in CONTEXTS for method in METHODS]
    outcomes = []; initial_hashes = {}
    with gzip.open(root/"episodes.jsonl.gz", "rt", encoding="utf-8") as handle:
        for index, line in enumerate(handle,1):
            record = json.loads(line)
            if index > 176 or record["episode_index"] != index or \
                    (record["seed"], record["context_oracle"], record["method"]) != expected[index-1]:
                raise ValueError("registered execution population/order mismatch")
            outcome = verify_episode(m, record, declarations[index-1], events[5*(index-1):5*index], arx, legacy, create_push_policy())
            outcomes.append(outcome)
            initial_hashes.setdefault(outcome["seed"],set()).add(outcome["initial_hash"])
    if len(outcomes) != 176 or any(len(v)!=1 for v in initial_hashes.values()):
        raise ValueError("paired initial state/population mismatch")
    # Eight-step reverse and repeat are different programs, so group explicitly.
    for seed in range(9800,9808):
        for context in CONTEXTS:
            reverse = [r["probe_hash"] for r in outcomes if r["seed"]==seed and r["context_oracle"]==context and r["method"].endswith("REVERSE8")]
            full = [r["probe_hash"] for r in outcomes if r["seed"]==seed and r["context_oracle"]==context and len(program(r["method"]))==16]
            prefix = [r["probe_hash"] for r in outcomes if r["seed"]==seed and r["context_oracle"]==context and r["method"].endswith("PREFIX4")]
            if len(set(reverse))!=1 or len(set(full))!=1 or len(set(prefix))!=1:
                raise ValueError("matched probe controls mismatch")
    status = json.loads((root/"status.json").read_text()); summary = json.loads((root/"summary.json").read_text())
    statistics = summarize(outcomes,m["config"])
    if statistics != summary["statistics"]:
        raise ValueError("registered statistics mismatch")
    counts = {"status":"COMPLETED_PREREQUISITE_PASS" if statistics["gate_passed"] else "COMPLETED_PREREQUISITE_FAILED",
        "complete_units":16, "episodes":176, "physical_steps":sum(r["total_steps"] for r in outcomes),
        "environment_resets":176, "events":880, "api_calls":0, "memory_writes":0}
    if counts["physical_steps"] > 88000 or any(any(value.get(k)!=v for k,v in {**identity(m),**counts}.items()) for value in (status,summary)):
        raise ValueError("completion/cost accounting mismatch")
    return {**identity(m), **counts, "integrity":"PASSED", "arx_model_sha256":m["arx_model_sha256"],
        "legacy_model_sha256":legacy_sha, "statistics":statistics, "replayed_decisions":176,
        "continuous_handoffs":160, "verified_task_steps":sum(r["task_steps"] for r in outcomes),
        "wall_clock_backsteps":wall_backsteps,
        "verified_probe_steps":sum(r["probe_steps"] for r in outcomes), "offline_steps":2304, "offline_resets":144,
        "violations":{"leakage":0,"budget":0,"handoff":0,"choice_substitution":0,"chronology":0},
        "source_input_hashes_checked":len(m["input_sha256"]),
        "artifact_sha256":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()},
        "audit_scope":"Training-only reconstruction, visible decision replay, complete observation/RNG chains, fixed-policy commands and evaluator frame/noise/clipping inputs. Task dynamics are not resimulated."}


def report(result):
    stats = result["statistics"]
    lines = ["# 坐标框架歧义独立审计", "", f'状态 `{result["status"]}`；完整性 `{result["integrity"]}`。', "",
        f'结构见证：{stats["disjoint_action_seeds"]}/8；上下文盲/知上下文评估上界：{stats["context_blind_evaluator_upper"]}/{stats["context_informed_evaluator_upper"]}（分母 16）。', "",
        "| 方法 | 成功/16 | FRAME0/8 | FRAME90/8 | 平均在线步 | 平均含离线摊销步 | 正确旋转/16 |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, row in stats["methods"].items():
        lines.append(f'| {name} | {row["successful"]} | {row["per_context_successful"]["FRAME0"]} | {row["per_context_successful"]["FRAME90"]} | {row["mean_online_steps"]:.2f} | {row["mean_amortized_steps"]:.2f} | {row["correct_frame_choices_oracle"]} |')
    lines += ["", f'结构门 `{stats["structural_gates"]}`。', f'标准基线门 `{stats["standard_baseline_gates"]}`。', "",
        f'物理收集 {result["physical_steps"]} 步/176 次初始重置；已有离线资源 2,304 步/144 次重置；API 0 次。', "",
        "所有先验访问方法均按 16 单元加 144 步/9 次重置；旧资格不认证新的 ARX/旋转模型。", "",
        result["audit_scope"], "", "构造例中的标准基线结果不是新算法、真实故障频率或 CCF A 发表证据。", ""]
    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest",type=Path,required=True); p.add_argument("--output",type=Path,required=True)
    a = p.parse_args(); path, output = a.manifest.resolve(), a.output.resolve()
    if output == path.parent or path.parent in output.parents:
        raise ValueError("audit output must be outside immutable collection")
    result = analyze(path); output.mkdir(parents=True,exist_ok=False)
    (output/"audit.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (output/"report.md").write_text(report(result),encoding="utf-8"); print(report(result))
