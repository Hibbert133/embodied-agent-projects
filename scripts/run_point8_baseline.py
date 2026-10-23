"""Fresh eight-step point controls; no learning or API."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import importlib.metadata
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_acquisition_value as prior
from scripts.run_action_response import load_bank, operators as base_operators, write_json
from scripts.run_forward_prediction import check_clean, git, digest, manifest_digest, policy_hashes, state_hash
from src.probe.conditional_noise import ConditionalNoiseTape, apply_affine_tape
from src.probe.continuous import StepObservation, ContinuousTransition, symmetric_program
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator, affine_controller, identity_controller, encode_controller
from src.probe.gaussian_response_reference import GaussianReference, bounded_command
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment, create_task_policy

CONFIG = ROOT / "configs/point8_baseline/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/point8_baseline_development_v1.md"
TASKS = ("push-v3", "reach-v3", "door-open-v3")
METHODS = ('DIRECT_POINT8', 'KEEP_POINT8_AFTER16', 'POINT16_CYCLE', 'DIRECT_G8', 'UPDATE_G16', 'NO_PROBE', 'IDENTITY_AFTER8')
PORTFOLIO = ('DIRECT_POINT8', 'KEEP_POINT8_AFTER16', 'POINT16_CYCLE', 'DIRECT_G8', 'UPDATE_G16', 'IDENTITY_AFTER8')
MATCHED_PAIRS = (("DIRECT_POINT8", "DIRECT_G8", 8), ("KEEP_POINT8_AFTER16", "POINT16_CYCLE", 16), ("UPDATE_G16", "POINT16_CYCLE", 16))
PREFIX_FIELDS = ("command", "raw_policy", "before", "after", "noise_before_hash", "noise_after_hash",
                 "executed_action_oracle", "phase", "simulation_time_before_oracle", "simulation_time_after_oracle")
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
normal = prior.normal
physics_witness = prior.physics_witness


def validate(c):
    fixed = {"protocol_id": "point8_baseline_development_v1", "seed_start": 13400, "streams": 16,
             "tasks": list(TASKS), "replicates": 2, "reserved_seeds": [13448, 13799], "methods": list(METHODS),
             "portfolio": list(PORTFOLIO), "noise_std": .05, "prefix_noise_namespace": 46003, "future_noise_namespace": 46005,
             "operator_generation_seeds": [49001, 49002], "total_steps": 500, "maximum_controlled_steps": 336000,
             "maximum_controlled_resets": 672, "maximum_do_simulation_frames": 20000000,
             "bootstrap_samples": 10000, "bootstrap_seed": 20261015,
             "forward_offline_steps": 21010, "forward_offline_resets": 288, "api_calls": 0, "memory_writes": 0}
    allowed = set(fixed) | {"forward_model_path", "forward_model_sha256", "forward_audit_path", "nominal_profile_path", "output_root"}
    if set(c) != allowed or any(c.get(k) != v for k, v in fixed.items()) or c["forward_model_sha256"] != "b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80":
        raise ValueError("registered eight-step point protocol differs")


def operators(c):
    result = []
    for nonce in c["operator_generation_seeds"]:
        for row in base_operators({**c, "operator_generation_seed": nonce}):
            result.append({**row, "stream": len(result)})
    return result


def task_seed(stream, task):
    return 13400 + stream * 3 + TASKS.index(task)


def prepare():
    check_clean(); c = json.loads(CONFIG.read_text(encoding="utf-8")); validate(c)
    _, source, _ = load_bank(c)
    profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8"))
    if profile["confidence_qualified"] or profile["probability_guarantee"]:
        raise ValueError("original unqualified empirical scale required")
    parent = ROOT / c["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("point8 baseline protocol already prepared")
    names = git("ls-files", "src", "scripts", "tests").splitlines()
    names += [CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(), "requirements.txt",
              c["forward_model_path"], c["forward_audit_path"], c["nominal_profile_path"], "docs/research/point8_baseline_question_v1.md", "AGENTS.md", ".gitattributes"]
    commit = git("rev-parse", "HEAD"); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m = {"experiment_run_id": f"point8_baseline_{stamp}_{commit[:12]}", "source_git_commit": commit, "config": c,
         "input_sha256": {name: digest(ROOT / name) for name in names}, "policy_sha256": policy_hashes(TASKS),
         "operators_oracle": operators(c), "library_source_sha256": prior.library_sources(),
         "versions": {name: importlib.metadata.version(name) for name in ("metaworld", "mujoco", "gymnasium", "numpy", "scipy")}}
    m["manifest_id"] = manifest_digest(m)
    output = parent / m["experiment_run_id"]; output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", m); print(output / "manifest.json")


def load(path):
    m = json.loads(path.read_text(encoding="utf-8")); validate(m["config"])
    if manifest_digest(m) != m["manifest_id"] or any(digest(ROOT / n) != h for n, h in m["input_sha256"].items()):
        raise ValueError("frozen point8 baseline source changed")
    _, source, _ = load_bank(m["config"])
    if operators(m["config"]) != m["operators_oracle"] or policy_hashes(TASKS) != m["policy_sha256"] or prior.library_sources() != m["library_source_sha256"]:
        raise ValueError("bound prior, operator or library changed")
    if any(importlib.metadata.version(k) != v for k, v in m["versions"].items()):
        raise ValueError("pinned library version changed")
    return m


def command(saved, raw):
    return bounded_command(saved, raw) if saved.get("kind") == "LOCAL_GAUSSIAN_BOX" else encode_controller(saved, raw)


class BranchFailure(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(record["error"])


def execute(key, operator, model, sigma, emit, ledger):
    method = key["method"]
    if method not in METHODS:
        raise ValueError("unregistered early evidence method")
    record = {**key, "initial": None, "initial_noise_hash": None, "initial_physics_witness_oracle": None,
              "eight_physics_witness_oracle": None, "sixteen_physics_witness_oracle": None, "trace": [], "decisions": [], "ledger_before": ledger.snapshot()}
    tape = ConditionalNoiseTape(key["seed"], TASKS.index(key["task"]), key["replicate"])
    record["noise_commitment_oracle"] = normal(tape.commitment_oracle)
    env = None; calls = 0; attempts = 0; current = None; samples = []; last = None
    try:
        emit("FACTORY_INTENT", {**key, "ledger": ledger.snapshot(), "noise_commitment_oracle": record["noise_commitment_oracle"]})
        with ledger.scope("FACTORY_SETUP"):
            env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("CONTROLLED_RESET"):
            observation, _ = env.reset(seed=key["seed"])
        noise_hash = tape.past_hash
        current = StepObservation(tuple(observation), False, False, False)
        history = ForwardHistory(current.observation); policy = create_task_policy(key["task"])
        record.update(initial=asdict(current), initial_noise_hash=noise_hash(), initial_physics_witness_oracle=physics_witness(env))
        emit("CONTROLLED_INITIAL", {**key, "initial": record["initial"], "noise_hash": record["initial_noise_hash"],
                                   "physics_witness_oracle": record["initial_physics_witness_oracle"], "ledger": ledger.snapshot()})
        def ended():
            return current.success or current.terminated or current.truncated
        def choose(action, controller=None, **values):
            nonlocal last
            last = emit("DECISION", {**key, "at_host_calls": calls, "observation_sha256": state_hash(current.observation),
                                     "noise_hash": noise_hash(), "action": action, "controller": normal(controller), **values})
            record["decisions"].append(last); last = normal(last)
        def step(sent, phase, raw=None):
            nonlocal current, calls, attempts
            if ended() or calls >= 500:
                raise ValueError("ended or exhausted branch stepped")
            before = current; sent = np.asarray(sent, np.float32); query = history.request(sent)
            intent = normal(emit("STEP_INTENT", {**key, "at_host_calls": calls, "decision_sequence": last["sequence"],
                         "phase": phase, "command": sent.tolist(), "raw_policy": raw, "before": asdict(before),
                         "noise_before_hash": noise_hash(), "forward_query": normal(asdict(query)) if query else None, "ledger_before": ledger.snapshot()}))
            started = perf_counter_ns(); acted = apply_affine_tape(intent["command"], operator["matrix_xy"], operator["bias_xy"], tape)
            time_before = float(env.unwrapped.data.time); attempts += 1
            with ledger.scope("CONTROL"):
                observation, _, terminated, truncated, info = env.step(acted)
            time_after = float(env.unwrapped.data.time); finished = perf_counter_ns(); calls += 1
            current = StepObservation(tuple(observation), bool(terminated), bool(truncated), bool(info.get("success", False)))
            elapsed = float(env.unwrapped.model.opt.timestep) * int(env.unwrapped.frame_skip)
            if not np.isclose(time_after - time_before, elapsed, atol=1e-10, rtol=1e-10):
                raise ValueError("simulation clock discontinuity")
            b = intent["ledger_before"]["by_phase"].get("CONTROL", {}); a = ledger.snapshot()["by_phase"].get("CONTROL", {})
            if a.get("reset_attempts", 0) != b.get("reset_attempts", 0) or a.get("simulation_frames_completed", 0) - b.get("simulation_frames_completed", 0) != 5:
                raise ValueError("continuous five-frame step contract differs")
            target = history.observe(ContinuousTransition(tuple(intent["command"]), before.observation, current.observation))
            if query is not None:
                samples.append(OperatorSample(calls, query, target))
            row = {"host_calls": calls, "intent_sequence": intent["sequence"], "decision_sequence": last["sequence"], "phase": phase,
                   "command": intent["command"], "raw_policy": raw, "before": asdict(before), "after": asdict(current),
                   "noise_before_hash": intent["noise_before_hash"], "noise_after_hash": noise_hash(), "target_xy": list(target), "executed_action_oracle": acted.tolist(),
                   "intent_saved_ns": intent["saved_ns"], "execution_started_ns": started, "completed_ns": finished,
                   "simulation_time_before_oracle": time_before, "simulation_time_after_oracle": time_after,
                   "ledger_before": intent["ledger_before"], "ledger_after": ledger.snapshot()}
            record["trace"].append(row); emit("STEP_COMPLETE", {**key, **row})
            if calls == 8:
                record["eight_physics_witness_oracle"] = physics_witness(env)
            if calls == 16:
                record["sixteen_physics_witness_oracle"] = physics_witness(env)
        def program(commands, phase):
            for sent in commands:
                if ended(): break
                step(sent, phase)
        def fixed(length):
            if calls + length + 32 > 500:
                choose("STOP_BUDGET"); return
            choose("REQUEST_FIXED_PROBE", probe_steps=length)
            program(symmetric_program(.4, steps_per_direction=length // 4), "FIXED_PROBE")
        def point():
            fit = infer_operator(model, tuple(samples))
            if fit["valid"]:
                choose("RUN_POINT", affine_controller(fit["matrix_xy"], fit["bias_xy"]), fit=fit)
            else:
                choose("STOP_POINT_FIT", fit=fit)
            return fit["valid"]
        def gaussian():
            try:
                reference, fit = GaussianReference.from_visible(model, tuple(samples), sigma)
            except ValueError as exc:
                choose("STOP_NO_GAUSSIAN_POINT", reason=str(exc), fit=infer_operator(model, tuple(samples))); return None
            choose("BUILD_GAUSSIAN", reference.controller(), fit=fit)
            return reference
        if method == "NO_PROBE":
            choose("RUN_UNCORRECTED", identity_controller())
        else:
            fixed(8)
            if not ended():
                if method == "IDENTITY_AFTER8":
                    choose("RUN_IDENTITY_CONTINUATION", identity_controller(), source_decision_sequence=last["sequence"])
                elif method == "DIRECT_POINT8":
                    point()
                elif method == "KEEP_POINT8_AFTER16":
                    if point():
                        saved, source_sequence = normal(last["controller"]), last["sequence"]
                        fixed(8)
                        if not ended(): choose("RUN_KEEP_POINT", saved, source_decision_sequence=source_sequence)
                elif method in ("POINT16_CYCLE", "UPDATE_G16"):
                    fixed(8)
                    if not ended():
                        if method == "POINT16_CYCLE": point()
                        else: gaussian()
                elif method == "DIRECT_G8":
                    gaussian()
                else:
                    raise ValueError("unregistered eight-step continuation")
        while not ended() and calls < 500 and last["controller"] is not None:
            raw = np.asarray(policy.get_action(np.asarray(current.observation)), np.float32)
            step(command(last["controller"], raw), "POLICY", raw.tolist())
        phases = Counter(r["phase"] for r in record["trace"])
        if tape.cursor != calls: raise ValueError("noise consumed outside registered physical steps")
        reset_count = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0) - record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        if reset_count != 1: raise ValueError("one controlled reset required")
        record.update(ledger_after=ledger.snapshot(), outcome={"success": current.success, "stopped": last["controller"] is None and not ended(),
                      "total_steps": calls, "environment_resets": reset_count, "fixed_probe_steps": phases["FIXED_PROBE"], "policy_measure_steps": phases["PASSIVE_POLICY"],
                      "policy_steps": phases["POLICY"] + phases["PASSIVE_POLICY"], "noise_rows_consumed": tape.cursor, "point_fit_failures": sum(d.get("fit") is not None and not d["fit"]["valid"] for d in record["decisions"]),
                      "deadline_loss": calls if current.success else 500})
    except BaseException as exc:
        record.update(error_type=type(exc).__name__, error=str(exc), completed_steps=calls, noise_rows_consumed=tape.cursor, unresolved_controlled_step_attempts=attempts - calls,
                      ledger_after=ledger.snapshot(), partial_current=asdict(current) if current is not None else None)
        raise BranchFailure(record) from exc
    finally:
        if env is not None: env.close()
    return record


def prefix_match(target, reference, boundary=8):
    if boundary not in (8,16): raise ValueError("registered prefix boundary required")
    if boundary == 16 and (target["method"],reference["method"],16) not in MATCHED_PAIRS: raise ValueError("unregistered late matched pair")
    if boundary == 8 and target["method"] != reference["method"] and not {target["method"], reference["method"]}.issubset(PORTFOLIO):
        raise ValueError("not a same-prefix continuation pair")
    if any(target[k] != reference[k] for k in ("stream", "task", "seed", "operator_id_oracle", "initial", "initial_noise_hash", "initial_physics_witness_oracle")):
        raise ValueError("foreign paired prefix")
    if boundary == 16 and target["replicate"] != reference["replicate"]:
        raise ValueError("late-prefix comparison must use the same future")
    if target["noise_commitment_oracle"]["prefix_sha256"] != reference["noise_commitment_oracle"]["prefix_sha256"]:
        raise ValueError("different initial noise tape")
    a, b = target["trace"][:boundary], reference["trace"][:boundary]
    shared = min(len(a), len(b))
    if any({k: x[k] for k in PREFIX_FIELDS} != {k: y[k] for k in PREFIX_FIELDS} for x, y in zip(a[:shared], b[:shared])):
        raise ValueError("visible prefix or consumed noise differs")
    if shared < boundary:
        if shared >= 8 and target["eight_physics_witness_oracle"] != reference["eight_physics_witness_oracle"]:
            raise ValueError("incomplete late comparison has different eight-step witness")
        return f"ENDED_BEFORE_{boundary}_SHARED_{shared}"
    witness = "eight_physics_witness_oracle" if boundary == 8 else "sixteen_physics_witness_oracle"
    if target[witness] != reference[witness]:
        raise ValueError("declared post-eight witness differs")
    if any(a[-1]["after"][k] for k in ("success", "terminated", "truncated")): return f"ENDED_AT_{boundary}"
    return f"MATCHED_ACTIVE_PREFIX_{boundary}"


def run(path):
    check_clean(); m = load(path); c = m["config"]; output = path.parent
    if git("rev-parse", "HEAD") != m["source_git_commit"]: raise ValueError("frozen commit differs")
    if (output / "status.json").exists(): raise FileExistsError("one-shot collection cannot restart")
    models, _, _ = load_bank(c); profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8"))
    identity = {k: m[k] for k in IDENTITY}; sequence = 0; active = None; rows = []; pairs = []; repetitions = []
    status = {**identity, "status": "RUNNING", "episodes": 0, "controlled_steps": 0, "controlled_resets": 0, "api_calls": 0, "memory_writes": 0}
    write_json(output / "status.json", status)
    def emit(kind, payload):
        nonlocal sequence
        sequence += 1
        event = {**identity, "event": kind, "sequence": sequence, "saved_ns": perf_counter_ns(), **normal(payload)}
        active.write(json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n"); active.flush(); return event
    ledger = LifecycleLedger(emit, c["maximum_do_simulation_frames"])
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
    try:
        with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
            for stream in range(16):
                with gzip.open(output / f"events_{stream:02}.jsonl.gz", "wt", encoding="utf-8") as events, gzip.open(output / f"episodes_{stream:02}.jsonl.gz", "wt", encoding="utf-8") as episodes:
                    active = events
                    operator = next(v for v in m["operators_oracle"][stream]["states_oracle"] if v["id"] == "A")
                    for task in TASKS:
                        repeated = {}
                        for replicate in range(2):
                            branches = {}
                            for method in METHODS:
                                key = {**identity, "stream": stream, "task": task, "replicate": replicate, "seed": task_seed(stream, task), "method": method, "operator_id_oracle": "A"}
                                record = execute(key, operator, models[task], profile["rms_m"][task], emit, ledger)
                                episodes.write(json.dumps(record, allow_nan=False) + "\n"); episodes.flush(); branches[method] = record; repeated[(method, replicate)] = record
                                rows.append({**key, **record["outcome"]}); status["episodes"] += 1
                                status["controlled_steps"] += record["outcome"]["total_steps"]; status["controlled_resets"] += 1
                                if status["controlled_steps"] > c["maximum_controlled_steps"] or status["controlled_resets"] > c["maximum_controlled_resets"]:
                                    raise ValueError("whole-study control budget exceeded")
                            for method in PORTFOLIO:
                                pairs.append({"stream": stream, "task": task, "replicate": replicate, "method": method, "reference": "DIRECT_G8", "boundary": 8,
                                              "reason": prefix_match(branches[method], branches["DIRECT_G8"])})
                            for method,reference,boundary in MATCHED_PAIRS:
                                if boundary == 8: continue
                                pairs.append({"stream": stream, "task": task, "replicate": replicate, "method": method, "reference": reference, "boundary": boundary,
                                              "reason": prefix_match(branches[method],branches[reference],boundary)})
                            status["lifecycle"] = ledger.snapshot(); write_json(output / "status.json", status)
                            print(f"Collected stream={stream} task={task} future={replicate}: {status['episodes']}/672", flush=True)
                        for method in METHODS:
                            for replicate in range(1, 2):
                                repetitions.append({"stream": stream, "task": task, "method": method, "replicate": replicate,
                                                    "reason": prefix_match(repeated[(method, replicate)], repeated[(method, 0)])})
        from scripts.analyze_point8_baseline import statistics
        summary = statistics(m, rows, pairs, repetitions)
        status.update(status="COMPLETED_POINT8_BASELINE", lifecycle=ledger.snapshot())
        write_json(output / "summary.json", {**status, "statistics": summary, "pairs": pairs, "prefix_repetitions": repetitions, "cases": rows})
    except BaseException as exc:
        status.update(status="FAILED_PARTIAL", error_type=type(exc).__name__, error=str(exc), lifecycle=ledger.snapshot())
        if isinstance(exc, BranchFailure):
            status["controlled_steps"] += exc.record["completed_steps"]
            status["controlled_resets"] = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
            status["unresolved_controlled_step_attempts"] = exc.record["unresolved_controlled_step_attempts"]
            write_json(output / "failed_branch.json", exc.record)
        write_json(output / "status.json", status); raise
    write_json(output / "status.json", status)
    print(json.dumps({k: status[k] for k in ("status", "episodes", "controlled_steps", "controlled_resets")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("command", choices=("prepare", "run")); parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest: run(args.manifest.resolve())
    else: parser.error("run requires --manifest")
