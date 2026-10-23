"""One-shot early-probe continuation target and disclosed Gaussian references."""
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
from scripts.run_action_response import load_bank, operators, write_json
from scripts.run_forward_prediction import check_clean, git, digest, manifest_digest, policy_hashes, state_hash
from src.operator_perturbations_v1 import AffineNoisePerturbation
from src.probe.continuous import StepObservation, ContinuousTransition, symmetric_program
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator, affine_controller, identity_controller, encode_controller
from src.probe.gaussian_response_reference import GaussianReference, PRIMITIVES, bounded_command
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment, create_task_policy

CONFIG = ROOT / "configs/early_evidence/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/early_evidence_development_v1.md"
TASKS = ("push-v3", "reach-v3", "door-open-v3")
METHODS = ("POINT8", "POINT16_CYCLE", "POINT16_WIDE", "GAUSS8", "GAUSS16_CYCLE", "IVR_GLOBAL16", "IVR_TASK16", "NO_PROBE")
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
normal = prior.normal
physics_witness = prior.physics_witness


def validate(c):
    fixed = {"protocol_id": "early_evidence_development_v1", "seed_start": 11500, "streams": 8,
             "tasks": list(TASKS), "replicates": 4, "reserved_seeds": [11524, 11799], "methods": list(METHODS),
             "noise_std": .05, "noise_namespace": 44003, "operator_generation_seed": 44001, "total_steps": 500,
             "maximum_controlled_steps": 384000, "maximum_controlled_resets": 768, "maximum_do_simulation_frames": 24000000,
             "primary_target": "POINT16_CYCLE", "primary_reference": "POINT8", "minimum_non_tie_contexts": 12,
             "maximum_sign_reversal_fraction": .25, "minimum_leave_one_out_agreement": .75, "minimum_leave_one_out_coverage": .75,
             "forward_offline_steps": 21010, "forward_offline_resets": 288,
             "task_measure_program": "POLICY_ONLY", "task_measure_grid": .25, "api_calls": 0, "memory_writes": 0}
    if any(c.get(k) != v for k, v in fixed.items()) or c["forward_model_sha256"] != "b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80":
        raise ValueError("registered early evidence protocol differs")


def task_seed(stream, task):
    return 11500 + stream * 3 + TASKS.index(task)


def noise_seed(seed, task, replicate):
    return int(np.random.SeedSequence([seed, TASKS.index(task), 44003, replicate + 1]).generate_state(1)[0])


def task_measures(source):
    counts = {task: Counter() for task in TASKS}
    included = Counter()
    with gzip.open(source / "TRAIN.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if row["stage"] != "TRAIN":
                raise ValueError("nontraining data in task measure")
            if row["program"] != "POLICY_ONLY":
                continue
            included[row["task"]] += 1
            for step in row["trace"]:
                raw = np.asarray(step["raw_policy"][:2], float)
                if not np.isfinite(raw).all():
                    raise ValueError("invalid nominal policy command")
                key = tuple(np.round(np.clip(raw, -1, 1) / .25) * .25)
                counts[row["task"]][key] += 1
    if any(included[t] != 16 or not counts[t] for t in TASKS):
        raise ValueError("complete nominal policy training measure required")
    return {task: {"commands": [list(q) for q in sorted(values)], "weights": [values[q] / sum(values.values()) for q in sorted(values)],
                   "training_policy_episodes": included[task], "training_policy_steps": sum(values.values()),
                   "source": "FROZEN_NOMINAL_TRAIN_POLICY_ONLY_RAW_COMMANDS"} for task, values in counts.items()}


def query_measure(method, task, measures):
    if method == "IVR_TASK16":
        measure = measures[task]
        return measure["commands"], measure["weights"]
    if method != "IVR_GLOBAL16":
        raise ValueError("unknown query measure")
    return [[x, y] for x in (-1., 0., 1.) for y in (-1., 0., 1.)], [1 / 9] * 9


def prepare():
    check_clean(); c = json.loads(CONFIG.read_text(encoding="utf-8")); validate(c)
    _, source, _ = load_bank(c)
    profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8"))
    if profile["confidence_qualified"] or profile["probability_guarantee"]:
        raise ValueError("original unqualified empirical scale required")
    parent = ROOT / c["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("early evidence protocol already prepared")
    names = git("ls-files", "src", "scripts", "tests").splitlines()
    names += [CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(), "requirements.txt",
              c["forward_model_path"], c["forward_audit_path"], c["nominal_profile_path"], (source / "TRAIN.jsonl.gz").relative_to(ROOT).as_posix()]
    commit = git("rev-parse", "HEAD"); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m = {"experiment_run_id": f"early_evidence_{stamp}_{commit[:12]}", "source_git_commit": commit, "config": c,
         "input_sha256": {name: digest(ROOT / name) for name in names}, "policy_sha256": policy_hashes(TASKS),
         "operators_oracle": operators(c), "task_measures": task_measures(source), "library_source_sha256": prior.library_sources(),
         "versions": {name: importlib.metadata.version(name) for name in ("metaworld", "mujoco", "gymnasium", "numpy", "scipy")}}
    m["manifest_id"] = manifest_digest(m)
    output = parent / m["experiment_run_id"]; output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", m); print(output / "manifest.json")


def load(path):
    m = json.loads(path.read_text(encoding="utf-8")); validate(m["config"])
    if manifest_digest(m) != m["manifest_id"] or any(digest(ROOT / n) != h for n, h in m["input_sha256"].items()):
        raise ValueError("frozen early evidence source changed")
    _, source, _ = load_bank(m["config"])
    if task_measures(source) != m["task_measures"] or operators(m["config"]) != m["operators_oracle"] or policy_hashes(TASKS) != m["policy_sha256"] or prior.library_sources() != m["library_source_sha256"]:
        raise ValueError("bound prior, task measure, operator or library changed")
    if any(importlib.metadata.version(k) != v for k, v in m["versions"].items()):
        raise ValueError("pinned library version changed")
    return m


def command(saved, raw):
    return bounded_command(saved, raw) if saved.get("kind") == "LOCAL_GAUSSIAN_BOX" else encode_controller(saved, raw)


class BranchFailure(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(record["error"])


def execute(key, operator, model, sigma, measures, emit, ledger):
    method = key["method"]
    if method not in METHODS:
        raise ValueError("unregistered early evidence method")
    record = {**key, "initial": None, "initial_rng_hash": None, "initial_physics_witness_oracle": None,
              "eight_physics_witness_oracle": None, "trace": [], "decisions": [], "ledger_before": ledger.snapshot()}
    env = None; calls = 0; attempts = 0; current = None; samples = []; last = None
    try:
        emit("FACTORY_INTENT", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"):
            env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("CONTROLLED_RESET"):
            observation, _ = env.reset(seed=key["seed"])
        fault = AffineNoisePerturbation(operator["matrix_xy"], operator["bias_xy"], .05)
        fault.reset(noise_seed(key["seed"], key["task"], key["replicate"]))
        def rng_hash():
            import hashlib
            return hashlib.sha256(json.dumps(fault._rng.bit_generator.state, sort_keys=True).encode()).hexdigest()
        current = StepObservation(tuple(observation), False, False, False)
        history = ForwardHistory(current.observation); policy = create_task_policy(key["task"])
        record.update(initial=asdict(current), initial_rng_hash=rng_hash(), initial_physics_witness_oracle=physics_witness(env))
        emit("CONTROLLED_INITIAL", {**key, "initial": record["initial"], "rng_hash": record["initial_rng_hash"],
                                   "physics_witness_oracle": record["initial_physics_witness_oracle"], "ledger": ledger.snapshot()})
        def ended():
            return current.success or current.terminated or current.truncated
        def choose(action, controller=None, **values):
            nonlocal last
            last = emit("DECISION", {**key, "at_host_calls": calls, "observation_sha256": state_hash(current.observation),
                                     "rng_hash": rng_hash(), "action": action, "controller": normal(controller), **values})
            record["decisions"].append(last); last = normal(last)
        def step(sent, phase, raw=None):
            nonlocal current, calls, attempts
            if ended() or calls >= 500:
                raise ValueError("ended or exhausted branch stepped")
            before = current; sent = np.asarray(sent, np.float32); query = history.request(sent)
            intent = normal(emit("STEP_INTENT", {**key, "at_host_calls": calls, "decision_sequence": last["sequence"],
                         "phase": phase, "command": sent.tolist(), "raw_policy": raw, "before": asdict(before),
                         "rng_before": rng_hash(), "forward_query": normal(asdict(query)) if query else None, "ledger_before": ledger.snapshot()}))
            started = perf_counter_ns(); acted = np.clip(fault.apply(np.asarray(intent["command"], np.float32)), -1, 1)
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
                   "rng_before": intent["rng_before"], "rng_after": rng_hash(), "target_xy": list(target), "executed_action_oracle": acted.tolist(),
                   "intent_saved_ns": intent["saved_ns"], "execution_started_ns": started, "completed_ns": finished,
                   "simulation_time_before_oracle": time_before, "simulation_time_after_oracle": time_after,
                   "ledger_before": intent["ledger_before"], "ledger_after": ledger.snapshot()}
            record["trace"].append(row); emit("STEP_COMPLETE", {**key, **row})
            if calls == 8:
                record["eight_physics_witness_oracle"] = physics_witness(env)
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
        def gaussian():
            try:
                reference, fit = GaussianReference.from_visible(model, tuple(samples), sigma)
            except ValueError as exc:
                choose("STOP_NO_GAUSSIAN_POINT", reason=str(exc), fit=infer_operator(model, tuple(samples))); return None
            choose("BUILD_GAUSSIAN", reference.controller(), fit=fit)
            return reference
        if method == "NO_PROBE":
            choose("RUN_UNCORRECTED", identity_controller())
        elif method == "POINT16_WIDE":
            fixed(16)
            if not ended(): point()
        else:
            fixed(8)
            if not ended():
                if method in ("POINT16_CYCLE", "GAUSS16_CYCLE"):
                    fixed(8)
                if not ended():
                    if method.startswith("IVR_"):
                        for _ in range(2):
                            reference = gaussian()
                            if reference is None or ended(): break
                            queries, weights = query_measure(method, key["task"], measures)
                            selection = reference.choose(queries, weights, 500 - calls, calls)
                            choose("REQUEST_IVR_PROBE", validation=selection)
                            program(PRIMITIVES[last["validation"]["action"]], "IVR_PROBE")
                            if ended(): break
                        if not ended() and last["action"] != "STOP_NO_GAUSSIAN_POINT": gaussian()
                    elif method.startswith("GAUSS"):
                        gaussian()
                    else:
                        point()
        while not ended() and calls < 500 and last["controller"] is not None:
            raw = np.asarray(policy.get_action(np.asarray(current.observation)), np.float32)
            step(command(last["controller"], raw), "POLICY", raw.tolist())
        phases = Counter(r["phase"] for r in record["trace"])
        reset_count = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0) - record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        if reset_count != 1: raise ValueError("one controlled reset required")
        record.update(ledger_after=ledger.snapshot(), outcome={"success": current.success, "stopped": last["controller"] is None and not ended(),
                      "total_steps": calls, "environment_resets": reset_count, "fixed_probe_steps": phases["FIXED_PROBE"], "ivr_probe_steps": phases["IVR_PROBE"],
                      "policy_steps": phases["POLICY"], "point_fit_failures": sum(d.get("fit") is not None and not d["fit"]["valid"] for d in record["decisions"]),
                      "deadline_loss": calls if current.success else 500})
    except BaseException as exc:
        record.update(error_type=type(exc).__name__, error=str(exc), completed_steps=calls, unresolved_controlled_step_attempts=attempts - calls,
                      ledger_after=ledger.snapshot(), partial_current=asdict(current) if current is not None else None)
        raise BranchFailure(record) from exc
    finally:
        if env is not None: env.close()
    return record


def pairing(target, reference):
    if target["method"] != "POINT16_CYCLE" or reference["method"] != "POINT8":
        raise ValueError("registered early continuation pair required")
    if any(target[k] != reference[k] for k in ("stream", "task", "replicate", "seed", "operator_id_oracle", "initial", "initial_rng_hash", "initial_physics_witness_oracle")):
        raise ValueError("foreign early continuation state")
    a, b = target["trace"][:8], reference["trace"][:8]
    if len(a) != len(b) or any({k: x[k] for k in prior.PREFIX_FIELDS} != {k: y[k] for k in prior.PREFIX_FIELDS} for x, y in zip(a, b)):
        raise ValueError("initial eight-step observations/actions/RNG differ")
    if len(a) < 8: return "ENDED_BEFORE_EIGHT"
    if target["eight_physics_witness_oracle"] != reference["eight_physics_witness_oracle"]:
        raise ValueError("post-eight integration witness differs")
    if any(a[-1]["after"][k] for k in ("success", "terminated", "truncated")): return "ENDED_AT_EIGHT"
    return "MATCHED_CONTINUATION"


def run(path):
    check_clean(); m = load(path); c = m["config"]; output = path.parent
    if git("rev-parse", "HEAD") != m["source_git_commit"]: raise ValueError("frozen commit differs")
    if (output / "status.json").exists(): raise FileExistsError("one-shot collection cannot restart")
    models, _, _ = load_bank(c); profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8"))
    identity = {k: m[k] for k in IDENTITY}; sequence = 0; active = None; rows = []; pairs = []
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
            for stream in range(8):
                with gzip.open(output / f"events_{stream:02}.jsonl.gz", "wt", encoding="utf-8") as events, gzip.open(output / f"episodes_{stream:02}.jsonl.gz", "wt", encoding="utf-8") as episodes:
                    active = events
                    operator = next(v for v in m["operators_oracle"][stream]["states_oracle"] if v["id"] == "A")
                    for task in TASKS:
                        for replicate in range(4):
                            branches = {}
                            for method in METHODS:
                                key = {**identity, "stream": stream, "task": task, "replicate": replicate, "seed": task_seed(stream, task), "method": method, "operator_id_oracle": "A"}
                                record = execute(key, operator, models[task], profile["rms_m"][task], m["task_measures"], emit, ledger)
                                episodes.write(json.dumps(record, allow_nan=False) + "\n"); episodes.flush(); branches[method] = record
                                rows.append({**key, **record["outcome"]}); status["episodes"] += 1
                                status["controlled_steps"] += record["outcome"]["total_steps"]; status["controlled_resets"] += 1
                                if status["controlled_steps"] > c["maximum_controlled_steps"] or status["controlled_resets"] > c["maximum_controlled_resets"]:
                                    raise ValueError("whole-study control budget exceeded")
                            pairs.append({"stream": stream, "task": task, "replicate": replicate, "reason": pairing(branches["POINT16_CYCLE"], branches["POINT8"])})
                            status["lifecycle"] = ledger.snapshot(); write_json(output / "status.json", status)
                            print(f"Collected stream={stream} task={task} replicate={replicate}: {status['episodes']}/768", flush=True)
        from scripts.analyze_early_evidence import statistics
        summary = statistics(m, rows, pairs)
        status.update(status="COMPLETED_TARGET_REPEAT_PASS" if summary["repeat_gate"]["passed"] else "COMPLETED_TARGET_REPEAT_FAILED", lifecycle=ledger.snapshot())
        write_json(output / "summary.json", {**status, "statistics": summary, "pairs": pairs, "cases": rows})
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
