"""One controlled-reset nominal calibration then frozen prefix identification."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import run_acquisition_value as prior
from scripts.run_action_response import load_bank, operators as base_operators, write_json
from scripts.run_forward_prediction import check_clean, git, digest, manifest_digest, policy_hashes
from src.probe.cold_start_response import TASKS, MODELS
from src.analysis.cold_start_evidence import visible_prefix, fit_training, estimates, statistics
from src.probe.continuous import StepObservation, symmetric_program
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment

CONFIG = ROOT / "configs/cold_start_evidence/qualification_v1.json"
PROTOCOL = ROOT / "docs/protocols/cold_start_evidence_qualification_v1.md"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
normal = prior.normal


def validate(c):
    fixed = {"protocol_id": "cold_start_evidence_qualification_v1", "tasks": list(TASKS), "training_trajectories_per_task": 128,
             "training_seed_start": 14000, "training_reserved_seeds": [14384, 14599], "qualification_seed_start": 13800,
             "qualification_reserved_seeds": [13848, 13999], "operator_generation_seeds": [50001, 50002],
             "qualification_streams": 16, "qualification_replicates": 2, "steps_per_trajectory": 8, "training_command_bound": .9,
             "noise_std": .05, "command_namespace": 54001, "noise_namespace": 54002, "maximum_controlled_steps": 3840,
             "maximum_controlled_resets": 480, "maximum_do_simulation_frames": 13000000, "models": list(MODELS),
             "ridge": 1e-6, "covariance_diagonal_shrinkage": .05, "covariance_floor": 1e-12, "bootstrap_samples": 10000,
             "bootstrap_seed": 20261016, "qualification_minimum_valid_fraction": .95, "forward_offline_steps": 21010,
             "forward_offline_resets": 288, "api_calls": 0, "task_policy_executions": 0, "memory_writes": 0}
    if set(c) != set(fixed) | {"forward_model_path", "forward_model_sha256", "forward_audit_path", "output_root"} or any(c[k] != v for k, v in fixed.items()) or c["forward_model_sha256"] != "b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80":
        raise ValueError("frozen cold-start qualification changed")


def operators(c):
    result = []
    for nonce in c["operator_generation_seeds"]:
        for row in base_operators({"operator_generation_seed": nonce}): result.append({**row, "stream": len(result)})
    return result


def population(c, split):
    if split == "TRAIN":
        return [{"split": split, "case_id": f"train_{i:03d}_{t}", "task": task, "seed": 14000+3*i+t,
                 "stream": -1, "replicate": 0} for i in range(128) for t, task in enumerate(TASKS)]
    return [{"split": split, "case_id": f"qual_{s:02d}_{t}_{f}", "task": task, "seed": 13800+3*s+t,
             "stream": s, "replicate": f} for s in range(16) for t, task in enumerate(TASKS) for f in range(2)]


def program(key):
    if key["split"] == "QUALIFY": return np.asarray(symmetric_program(.4, steps_per_direction=2), np.float32)
    rng = np.random.default_rng(np.random.SeedSequence([key["seed"], TASKS.index(key["task"]), 54001]))
    return np.c_[rng.uniform(-.9, .9, (8, 2)), np.zeros((8, 2))].astype(np.float32)


def noise(key):
    rng = np.random.default_rng(np.random.SeedSequence([key["seed"], TASKS.index(key["task"]), 54002,
                                                       0 if key["split"] == "TRAIN" else 1, key["replicate"]+1]))
    return rng.normal(0, .05, (8, 3)).astype("<f4")


def prepare():
    check_clean(); c = json.loads(CONFIG.read_text(encoding="utf-8")); validate(c); load_bank(c)
    parent = ROOT / c["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("qualification already prepared")
    names = git("ls-files", "src", "scripts", "tests").splitlines()+[CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(),
        "docs/research/cold_start_evidence_question_v1.md", "AGENTS.md", ".gitattributes", "requirements.txt", c["forward_model_path"], c["forward_audit_path"]]
    commit = git("rev-parse", "HEAD"); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    m = {"experiment_run_id": f"cold_start_evidence_{stamp}_{commit[:12]}", "source_git_commit": commit, "config": c,
         "input_sha256": {name: digest(ROOT/name) for name in names}, "policy_sha256": policy_hashes(TASKS),
         "operators_oracle": operators(c), "library_source_sha256": prior.library_sources(),
         "versions": {name: importlib.metadata.version(name) for name in ("metaworld", "mujoco", "gymnasium", "numpy", "scipy")}}
    m["manifest_id"] = manifest_digest(m); output = parent / m["experiment_run_id"]; output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", m); print(output / "manifest.json")


def load(path):
    m = json.loads(path.read_text(encoding="utf-8")); validate(m["config"])
    if manifest_digest(m) != m["manifest_id"] or any(digest(ROOT/name) != h for name, h in m["input_sha256"].items()): raise ValueError("frozen inputs changed")
    if operators(m["config"]) != m["operators_oracle"] or prior.library_sources() != m["library_source_sha256"] or policy_hashes(TASKS) != m["policy_sha256"]: raise ValueError("frozen operator/library changed")
    if any(importlib.metadata.version(k) != v for k, v in m["versions"].items()): raise ValueError("runtime changed")
    load_bank(m["config"]); return m


def collect(key, operator, emit, ledger):
    commands = program(key); disturbances = noise(key); env = None; trace = []; current = None; initial = None; witness = None
    before_ledger = ledger.snapshot(); past = hashlib.sha256()
    declaration = emit("PROGRAM_SAVED", {**key, "commands": commands.tolist(), "noise_commitment_oracle": hashlib.sha256(disturbances.tobytes()).hexdigest(), "ledger": before_ledger})
    try:
        emit("FACTORY_INTENT", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"): env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {**key, "ledger": ledger.snapshot()})
        with ledger.scope("CONTROLLED_RESET"): observation, _ = env.reset(seed=key["seed"])
        current = StepObservation(tuple(observation), False, False, False)
        initial = asdict(current); witness = prior.physics_witness(env)
        emit("CONTROLLED_INITIAL", {**key, "initial": initial, "physics_witness_oracle": witness, "ledger": ledger.snapshot()})
        for t, sent in enumerate(commands):
            if current.success or current.terminated or current.truncated: break
            intent = emit("STEP_INTENT", {**key, "step": t+1, "program_sequence": declaration["sequence"], "command": sent.tolist(),
                "before": asdict(current), "noise_before_hash": past.copy().hexdigest(), "ledger_before": ledger.snapshot()})
            acted = sent.copy(); acted[:2] = np.asarray(operator["matrix_xy"], np.float32) @ acted[:2]+np.asarray(operator["bias_xy"], np.float32)
            acted[:3] += disturbances[t]; acted = np.clip(acted, -1, 1)
            started = perf_counter_ns(); time_before = float(env.unwrapped.data.time)
            with ledger.scope("CONTROL"): observation, _, terminated, truncated, info = env.step(acted)
            finished = perf_counter_ns(); time_after = float(env.unwrapped.data.time)
            previous = current; current = StepObservation(tuple(observation), bool(terminated), bool(truncated), bool(info.get("success", False)))
            past.update(disturbances[t].tobytes())
            row = {"step": t+1, "intent_sequence": intent["sequence"], "program_sequence": declaration["sequence"],
                   "command": sent.tolist(), "before": asdict(previous), "after": asdict(current), "noise_before_hash": intent["noise_before_hash"],
                   "noise_after_hash": past.copy().hexdigest(), "executed_action_oracle": acted.tolist(), "intent_saved_ns": intent["saved_ns"],
                   "execution_started_ns": started, "completed_ns": finished, "simulation_time_before_oracle": time_before,
                   "simulation_time_after_oracle": time_after, "ledger_before": intent["ledger_before"], "ledger_after": ledger.snapshot()}
            trace.append(row); emit("STEP_COMPLETE", {**key, **row})
        reset_count = ledger.snapshot()["by_phase"]["CONTROLLED_RESET"]["reset_completed"]-before_ledger["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        if reset_count != 1: raise ValueError("one controlled reset per prefix required")
        return {**key, "initial": initial, "initial_physics_witness_oracle": witness, "program": normal(declaration), "trace": normal(trace),
                "ledger_before": before_ledger, "ledger_after": ledger.snapshot(), "total_steps": len(trace), "environment_resets": 1,
                "completed_eight": len(trace) == 8, "task_success_during_probe": current.success}
    except BaseException as error:
        partial = {**key, "initial": initial, "trace": normal(trace), "program": normal(declaration),
                   "ledger_before": before_ledger, "ledger_after": ledger.snapshot(), "error": type(error).__name__+": "+str(error)}
        failure = RuntimeError("prefix collection failed; partial record attached")
        failure.partial_record = partial
        raise failure from error
    finally:
        if env is not None: env.close()


def run(path):
    check_clean(); m = load(path); c = m["config"]; base = path.parent
    if git("rev-parse", "HEAD") != m["source_git_commit"] or (base / "status.json").exists(): raise ValueError("one-shot source/restart guard")
    old, _, _ = load_bank(c); identity = {k: m[k] for k in IDENTITY}; sequence = 0; active = None
    status = {**identity, "status": "RUNNING", "training_episodes": 0, "qualification_episodes": 0,
              "controlled_steps": 0, "controlled_resets": 0, "api_calls": 0, "task_policy_executions": 0, "memory_writes": 0}
    write_json(base / "status.json", status)
    def emit(kind, payload):
        nonlocal sequence
        sequence += 1; value = {**identity, "event": kind, "sequence": sequence, "saved_ns": perf_counter_ns(), **normal(payload)}
        active.write(json.dumps(value, separators=(",", ":"), allow_nan=False)+"\n"); active.flush(); return value
    ledger = LifecycleLedger(emit, c["maximum_do_simulation_frames"]); training = []; qualification = []
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
    try:
        with gzip.open(base / "events.jsonl.gz", "wt", encoding="utf-8") as events, ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
            active = events
            for split in ("TRAIN", "QUALIFY"):
                if split == "QUALIFY":
                    models = fit_training(training); write_json(base / "models.json", {**identity, **models})
                    model_hash = digest(base / "models.json")
                    emit("MODELS_FROZEN", {"models_sha256": model_hash, "training_case_ids": models["training_cases"], "ledger": ledger.snapshot()})
                with gzip.open(base / (split+".jsonl.gz"), "wt", encoding="utf-8") as handle:
                    for number, spec in enumerate(population(c, split), 1):
                        key = {**identity, **spec}
                        operator = {"matrix_xy": np.eye(2).tolist(), "bias_xy": [0., 0.]} if split == "TRAIN" else next(o for o in m["operators_oracle"][spec["stream"]]["states_oracle"] if o["id"] == "A")
                        record = collect(key, operator, emit, ledger)
                        if split == "TRAIN": training.append(record)
                        else:
                            record["models_sha256"] = model_hash; record["estimates"] = estimates(models, old, visible_prefix(record))
                            saved = emit("ESTIMATES_SAVED", {**key, "models_sha256": model_hash, "estimates": record["estimates"], "ledger": ledger.snapshot()})
                            record["estimates_sequence"] = saved["sequence"]; record["operator_oracle"] = operator; qualification.append(record)
                        handle.write(json.dumps(normal(record), separators=(",", ":"), allow_nan=False)+"\n"); handle.flush()
                        status["training_episodes" if split == "TRAIN" else "qualification_episodes"] += 1
                        status["controlled_steps"] += record["total_steps"]; status["controlled_resets"] += 1
                        if status["controlled_steps"] > 3840 or status["controlled_resets"] > 480: raise ValueError("qualification resource cap exceeded")
                        status["lifecycle"] = ledger.snapshot(); write_json(base / "status.json", status)
                        if number % 12 == 0: print(f"{split} {number}/{384 if split=='TRAIN' else 96}", flush=True)
            stats = statistics(qualification, c); status.update(status="COMPLETED_COMPONENT_PASSED" if stats["qualification"]["passed"] else "COMPLETED_COMPONENT_FAILED", lifecycle=ledger.snapshot())
            write_json(base / "summary.json", {**status, "statistics": stats, "models_sha256": model_hash})
    except BaseException as error:
        status.update(status="INCOMPLETE_ERROR", error=type(error).__name__+": "+str(error), lifecycle=ledger.snapshot())
        if hasattr(error, "partial_record"): write_json(base / "failed_prefix.json", error.partial_record)
        control = ledger.snapshot()["by_phase"].get("CONTROL", {})
        status["controlled_steps"] = control.get("simulation_completed", 0)
        status["controlled_resets"] = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        write_json(base / "status.json", status); raise
    write_json(base / "status.json", status); print(json.dumps(status), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(); p.add_argument("command", choices=("prepare", "run")); p.add_argument("--manifest", type=Path)
    args = p.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest: run(args.manifest.resolve())
    else: p.error("run requires --manifest")
