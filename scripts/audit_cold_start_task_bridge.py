"""Recorded-action, immutable-noise, program and lifecycle replay; no robot resimulation."""
import argparse
from collections import Counter, deque
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_cold_start_task_bridge as run
from scripts.audit_acquisition_value_v3 import JournalAudit, compiled_clock_units
from src.analysis.cold_start_task_bridge import statistics as bridge_statistics
from src.probe.cold_start_response import ColdPrefix, infer_operator as infer_joint
from src.probe.cold_start_task_bridge import source_hash
from src.probe.continuous import ContinuousTransition, symmetric_program
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator, affine_controller, identity_controller
from src.probe.gaussian_response_reference import GaussianReference


def equal(a, b):
    if run.normal(a) != run.normal(b): raise ValueError("saved observation/decision differs")


def statistics(manifest, rows, pairs, repetitions):
    return bridge_statistics(rows, pairs, repetitions)


def verify_record(record, model, response, sigma, operator, events, env_dt):
    fields = (*run.IDENTITY, "stream", "task", "replicate", "seed", "method", "operator_id_oracle")
    def event():
        value = events.popleft()
        if any(value[k] != record[k] for k in fields): raise ValueError("foreign branch event")
        return value
    start, factory, initial = event(), event(), event()
    if start["event"] != "FACTORY_INTENT" or factory["event"] != "FACTORY_COMPLETE" or initial["event"] != "CONTROLLED_INITIAL": raise ValueError("initialization order differs")
    equal(start["ledger"], record["ledger_before"]); equal(initial["initial"], record["initial"]); equal(initial["physics_witness_oracle"], record["initial_physics_witness_oracle"])
    method = record["method"]; trace = record["trace"]; decisions = {d["sequence"]: d for d in record["decisions"]}
    if method not in run.METHODS or len(trace) > 500 or [r["host_calls"] for r in trace] != list(range(1, len(trace) + 1)): raise ValueError("registered method/timeline differs")
    if len(decisions) != len(record["decisions"]): raise ValueError("duplicate decision")
    prefix_seed = int(np.random.SeedSequence([record["seed"], run.TASKS.index(record["task"]), 46003]).generate_state(1)[0])
    future_seed = int(np.random.SeedSequence([record["seed"], run.TASKS.index(record["task"]), 46005, record["replicate"]+1]).generate_state(1)[0])
    prefix = np.random.default_rng(prefix_seed).normal(0,.05,(8,3)).astype("<f4")
    future = np.random.default_rng(future_seed).normal(0,.05,(492,3)).astype("<f4")
    noise = np.concatenate((prefix,future)); past = hashlib.sha256()
    commitment = {"prefix_sha256": hashlib.sha256(prefix.tobytes()).hexdigest(), "future_sha256": hashlib.sha256(future.tobytes()).hexdigest(),
                  "full_sha256": hashlib.sha256(noise.tobytes()).hexdigest(), "prefix_steps": 8, "future_steps": 492, "dtype": "little-endian-float32"}
    equal(commitment, record["noise_commitment_oracle"]); equal(commitment, start["noise_commitment_oracle"])
    def noise_hash(): return past.copy().hexdigest()
    if record["initial_noise_hash"] != noise_hash() or initial["noise_hash"] != noise_hash(): raise ValueError("initial consumed-noise history differs")
    current = record["initial"]; history = ForwardHistory(current["observation"]); samples = []; calls = 0; selected = None; last_sequence = None
    program = (); position = 0; fixed_batches = 0; reference = None; built_at = None; seen_decisions = set(); previous_clock = None
    policy = run.create_task_policy(record["task"])
    while events:
        item = event(); kind = item["event"]
        if kind == "DECISION":
            if any(current[k] for k in ("success", "terminated", "truncated")): raise ValueError("decision after task ended")
            if item["sequence"] not in decisions or item["sequence"] in seen_decisions: raise ValueError("unrecorded/duplicate choice")
            equal(item, decisions[item["sequence"]]); seen_decisions.add(item["sequence"])
            if item["at_host_calls"] != calls or item["observation_sha256"] != run.state_hash(current["observation"]) or item["noise_hash"] != noise_hash(): raise ValueError("future evidence at choice")
            action = item["action"]; expected = None
            if item["model_bundle_sha256"] != source_hash(method): raise ValueError("declared estimator source differs")
            if position != len(program): raise ValueError("decision before selected measurement completed")
            if action == "RUN_UNCORRECTED":
                if method != "NO_PROBE" or calls or seen_decisions != {item["sequence"]}: raise ValueError("uncorrected method changed")
                expected = identity_controller()
            elif action == "RUN_IDENTITY_CONTINUATION":
                if method != "IDENTITY_AFTER8" or calls != 8 or item["source_decision_sequence"] != last_sequence:
                    raise ValueError("identity continuation outside registered prefix")
                expected = identity_controller()
            elif action == "REQUEST_FIXED_PROBE":
                batches = (8, 8) if method == "OLD_POINT16_CYCLE" else (8,)
                if method == "NO_PROBE" or fixed_batches >= len(batches) or calls != sum(batches[:fixed_batches]) or item["probe_steps"] != batches[fixed_batches] or calls+item["probe_steps"]+32 > 500:
                    raise ValueError("fixed measurement budget differs")
                program = symmetric_program(.4, steps_per_direction=2); position = 0; fixed_batches += 1
            elif action in ("RUN_POINT", "STOP_POINT_FIT"):
                boundary = 16 if method == "OLD_POINT16_CYCLE" else 8 if method in ("JOINT8", "JOINT_DROP2_8", "SAME_DATA_POINT8", "OLD_POINT8") else None
                if calls != boundary or built_at == calls: raise ValueError("unregistered point boundary")
                if method in ("JOINT8", "JOINT_DROP2_8"):
                    visible = trace[:calls]
                    prefix = ColdPrefix(record["task"], record["initial"]["observation"], [r["command"] for r in visible], [r["after"]["observation"] for r in visible], True)
                    fit = infer_joint(response["joint"][record["task"]], prefix, method == "JOINT_DROP2_8")
                else:
                    fit = infer_operator(response["same_data_arx"][record["task"]] if method == "SAME_DATA_POINT8" else model, tuple(samples))
                equal(fit, item["fit"])
                if action == "RUN_POINT" and fit["valid"]: expected = affine_controller(fit["matrix_xy"], fit["bias_xy"])
                elif action != "STOP_POINT_FIT" or fit["valid"]: raise ValueError("point validity substituted")
                built_at = calls
            elif action in ("BUILD_GAUSSIAN", "STOP_NO_GAUSSIAN_POINT"):
                boundary = 8 if method == "OLD_G8" else None
                if calls != boundary or built_at == calls: raise ValueError("unregistered Gaussian boundary")
                try:
                    reference, fit = GaussianReference.from_visible(model, tuple(samples), sigma)
                except ValueError as exc:
                    if action != "STOP_NO_GAUSSIAN_POINT" or item["reason"] != str(exc): raise ValueError("Gaussian failure replaced")
                    equal(item["fit"], infer_operator(model, tuple(samples)))
                else:
                    if action != "BUILD_GAUSSIAN": raise ValueError("valid Gaussian construction stopped")
                    equal(fit, item["fit"]); expected = reference.controller()
                built_at = calls
            else: raise ValueError("unexpected or budget-stop action")
            equal(expected, item["controller"]); selected = item["controller"]; last_sequence = item["sequence"]
        elif kind == "STEP_INTENT":
            if calls >= len(trace) or last_sequence is None or item["decision_sequence"] != last_sequence or any(current[k] for k in ("success", "terminated", "truncated")): raise ValueError("unselected or ended branch stepped")
            row = trace[calls]; phase = row["phase"]
            for name in ("command", "before", "noise_before_hash", "phase", "raw_policy", "decision_sequence", "ledger_before"): equal(item[name], row[name])
            if row["before"] != current or item["at_host_calls"] != calls or row["noise_before_hash"] != noise_hash() or row["intent_sequence"] != item["sequence"]: raise ValueError("step chronology/consumed-noise history differs")
            if not (last_sequence < item["sequence"] and decisions[last_sequence]["saved_ns"] <= item["saved_ns"] == row["intent_saved_ns"] < row["execution_started_ns"] <= row["completed_ns"]): raise ValueError("choice or intent did not precede execution")
            if phase == "FIXED_PROBE":
                if position >= len(program) or row["raw_policy"] is not None: raise ValueError("extra or changed fixed measurement")
                if np.asarray(program[position], np.float32).tolist() != row["command"]: raise ValueError("saved fixed program not executed")
                position += 1
            elif phase == "POLICY":
                if selected is None or position != len(program): raise ValueError("policy before saved controller or probe completion")
                ready = (method == "NO_PROBE" or
                         method in ("JOINT8", "JOINT_DROP2_8", "SAME_DATA_POINT8", "OLD_POINT8", "OLD_G8") and built_at == 8 or
                         method == "OLD_POINT16_CYCLE" and built_at == 16 or
                         method == "IDENTITY_AFTER8" and decisions[last_sequence]["action"] == "RUN_IDENTITY_CONTINUATION")
                if not ready: raise ValueError("policy before registered continuation")
                raw = np.asarray(policy.get_action(np.asarray(current["observation"])), np.float32)
                if raw.tolist() != row["raw_policy"] or run.command(selected, raw).tolist() != row["command"]: raise ValueError("saved controller not consumed")
            else: raise ValueError("unknown physical phase")
            query = history.request(row["command"]); equal(asdict(query) if query else None, item["forward_query"])
            actual = np.asarray(row["command"], np.float32).copy()
            actual[:2] = np.asarray(operator["matrix_xy"], np.float32) @ actual[:2] + np.asarray(operator["bias_xy"], np.float32)
            actual[:3] += noise[calls]; past.update(noise[calls].tobytes()); actual = np.clip(actual, -1, 1)
            if actual.tolist() != row["executed_action_oracle"] or noise_hash() != row["noise_after_hash"]: raise ValueError("injection or continuous noise differs")
            target = history.observe(ContinuousTransition(tuple(row["command"]), current["observation"], row["after"]["observation"])); calls += 1
            if query is not None: samples.append(OperatorSample(calls, query, target))
            equal(list(target), row["target_xy"]); current = row["after"]
            if not np.isclose(row["simulation_time_after_oracle"] - row["simulation_time_before_oracle"], env_dt, atol=1e-10, rtol=1e-10) or previous_clock is not None and row["simulation_time_before_oracle"] != previous_clock: raise ValueError("clock or reset discontinuity")
            previous_clock = row["simulation_time_after_oracle"]
            complete = event()
            if complete["event"] != "STEP_COMPLETE": raise ValueError("missing completed execution")
            for name, value in row.items(): equal(value, complete[name])
        else: raise ValueError("unexpected business event")
    if calls != len(trace) or seen_decisions != set(decisions): raise ValueError("incomplete decision/trace replay")
    ended = any(current[k] for k in ("success", "terminated", "truncated"))
    if selected is not None and calls < 500 and not ended: raise ValueError("policy branch truncated early")
    phase = Counter(r["phase"] for r in trace)
    expected = {"success": current["success"], "stopped": selected is None and not ended, "total_steps": calls, "environment_resets": 1,
                "fixed_probe_steps": phase["FIXED_PROBE"], "policy_measure_steps": phase["PASSIVE_POLICY"], "policy_steps": phase["POLICY"]+phase["PASSIVE_POLICY"], "noise_rows_consumed": calls,
                "point_fit_failures": sum(d.get("fit") is not None and not d["fit"]["valid"] for d in decisions.values()), "deadline_loss": calls if current["success"] else 500}
    if record["outcome"] != expected or record["ledger_after"] != (trace[-1]["ledger_after"] if trace else initial["ledger"]): raise ValueError("branch outcome or cost substituted")
    if phase["FIXED_PROBE"] > 16: raise ValueError("probe cap exceeded")
    before,after=record["ledger_before"]["by_phase"],record["ledger_after"]["by_phase"]
    if after["CONTROLLED_RESET"]["reset_completed"]-before.get("CONTROLLED_RESET",{}).get("reset_completed",0) != 1:
        raise ValueError("per-execution initial reset count differs")
    if after.get("CONTROL",{}).get("simulation_completed",0)-before.get("CONTROL",{}).get("simulation_completed",0) != calls:
        raise ValueError("per-execution physical step count differs")


def read_lines(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle: yield json.loads(line)


def verify_lifecycle(ledger,steps):
    counts=ledger["counts"];control=ledger["by_phase"]["CONTROL"];reset=ledger["by_phase"]["CONTROLLED_RESET"]
    if any(counts.get(k,0) for k in ("reset_errors","simulation_errors","uncertain_simulation_frames","frame_budget_rejections")):
        raise ValueError("unresolved lifecycle error")
    if control.get("reset_attempts",0) or control.get("simulation_frames_completed") != 5*steps:
        raise ValueError("reset or extra simulation during live control")
    if control["simulation_completed"] != steps or reset["reset_completed"] != 2688 or counts["simulation_frames_completed"] > 80000000 or steps > 1344000 or counts["simulation_frames_completed"] != 500*counts["reset_completed"]+5*steps:
        raise ValueError("complete step/reset/frame arithmetic differs")


def analyze(path):
    m = run.load(path); output = path.parent; c = m["config"]; identity = {k: m[k] for k in run.IDENTITY}
    for name, expected in m["input_sha256"].items():
        content = __import__("subprocess").check_output(["git", "show", m["source_git_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(content).hexdigest() != expected: raise ValueError("frozen Git bytes differ")
    clocks = compiled_clock_units(m); models, _, _ = run.load_bank(c); response, _, _ = run.load_response(c)
    profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8")); journal = JournalAudit(identity); rows = []; pairs = []; repetitions = []
    for stream in range(56):
        events = iter(read_lines(output / f"events_{stream:02}.jsonl.gz")); branches = {}
        expected_order=iter((task,future,method) for task in run.TASKS for future in range(2) for method in run.METHODS)
        operator = next(v for v in m["operators_oracle"][stream]["states_oracle"] if v["id"] == "A")
        for record in read_lines(output / f"episodes_{stream:02}.jsonl.gz"):
            if (record["task"],record["replicate"],record["method"]) != next(expected_order,None): raise ValueError("registered execution order differs")
            if any(record[k] != v for k, v in identity.items()) or record["stream"] != stream or record["seed"] != run.task_seed(stream, record["task"]) or record["operator_id_oracle"] != "A": raise ValueError("foreign raw episode")
            business = deque(); needed = 3 + len(record["decisions"]) + 2 * len(record["trace"])
            while len(business) < needed:
                item = journal.accept(next(events))
                if item is not None: business.append(item)
            verify_record(record, models[record["task"]], response, profile["rms_m"][record["task"]], operator, business, clocks[record["task"]]["env_step_seconds"])
            if business or journal.ledger != record["ledger_after"]: raise ValueError("episode journal did not terminate")
            rows.append({**{k: record[k] for k in (*run.IDENTITY, "stream", "task", "replicate", "seed", "method", "operator_id_oracle")}, **record["outcome"]})
            key = (record["task"], record["replicate"])
            branches[(record["task"],record["method"],record["replicate"])] = record
        if next(events, None) is not None: raise ValueError("unexpected trailing events")
        if next(expected_order,None) is not None: raise ValueError("missing registered execution")
        journal.boundary()
        for task in run.TASKS:
            for replicate in range(2):
                for method in run.PORTFOLIO:
                    pairs.append({"stream": stream,"task": task,"replicate": replicate,"method": method,"reference":"JOINT8","boundary":8,
                                  "reason": run.prefix_match(branches[(task,method,replicate)],branches[(task,"JOINT8",replicate)])})
            for method in run.METHODS:
                for replicate in range(1,2):
                    repetitions.append({"stream": stream,"task": task,"method": method,"replicate": replicate,
                                        "reason": run.prefix_match(branches[(task,method,replicate)],branches[(task,method,0)])})
        print(f"Audited stream {stream + 1}/56: {len(rows)}/2688", flush=True)
    stats = statistics(m, rows, pairs, repetitions); steps = sum(r["total_steps"] for r in rows)
    verify_lifecycle(journal.ledger,steps)
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8")); status = json.loads((output / "status.json").read_text(encoding="utf-8"))
    expected_status = "COMPLETED_COMPONENT_PASSED" if stats["component_gate"]["passed"] else "COMPLETED_COMPONENT_FAILED"
    expected = {**identity, "status": expected_status, "episodes": 2688, "controlled_steps": steps, "controlled_resets": 2688, "api_calls": 0, "memory_writes": 0, "policy_weight_updates": 0, "lifecycle": journal.ledger}
    if status != expected or any(summary[k] != v for k, v in expected.items()) or summary["cases"] != rows or summary["pairs"] != pairs or summary["prefix_repetitions"] != repetitions or summary["statistics"] != stats:
        raise ValueError("terminal population, statistics or ledger differs")
    return {**identity, "integrity": "PASSED", "status": expected_status, "episodes": 2688, "controlled_steps": steps, "controlled_resets": 2688,
            "statistics": stats, "lifecycle": journal.ledger, "events_checked": journal.sequence, "clock_units": clocks,
            "frozen_git_inputs_checked": len(m["input_sha256"]), "api_calls": 0, "memory_writes": 0, "policy_weight_updates": 0,
            "artifact_sha256": {p.name: run.digest(p) for p in output.iterdir() if p.is_file()},
            "scope": "Recorded joint/drop-two/new-ARX/old-point/Gaussian choices and lifecycle replay; noise independently reconstructed. Working optimizer/command math, prefix checks and statistics reused. No robot resimulation, new selector or physical/probability qualification; statistics also need separate independent audit."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--manifest", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); output = args.output.resolve()
    if output.exists() or args.manifest.resolve().parent in output.parents: raise FileExistsError("new external audit directory required")
    result = analyze(args.manifest.resolve()); output.mkdir(parents=True, exist_ok=False); run.write_json(output / "audit.json", result)
    print(json.dumps({k: result[k] for k in ("integrity", "status", "episodes", "controlled_steps", "controlled_resets")}))
