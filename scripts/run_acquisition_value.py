"""One-shot real post-prefix branches with immutable cold-source controllers."""
import argparse
from collections import Counter
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import inspect
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git, digest, manifest_digest, check_clean
from scripts.run_action_response import load_bank, operators, agent_validation, saved_cache, cached, write_json
from scripts.run_continuous_probe import state_hash
from scripts.run_nominal_observer import policy_hashes
from src.probe.acquisition_value import PROGRAMS, METHODS, MID_METHODS, PRIOR_CACHE_METHODS, deadline_loss, repeat_consistency
from src.probe.action_response_validity import CachedPoint, PRIMITIVES
from src.probe.continuous import StepObservation, ContinuousTransition, symmetric_program
from src.probe.forward_prediction import ForwardHistory
from src.probe.operator_identification import OperatorSample, infer_operator, identity_controller, encode_controller
from src.probe.lifecycle_ledger import LifecycleLedger
from src.operator_perturbations_v1 import AffineNoisePerturbation
from src.rollout.task_registry import create_task_environment, create_task_policy

CONFIG = ROOT / "configs/acquisition_value/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/postprefix_probe_value_development_v1.md"
TASKS = ("push-v3", "reach-v3", "door-open-v3")
SCENARIOS = ("UNCHANGED", "CHANGED")
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
PREFIX_FIELDS = ("command", "raw_policy", "before", "after", "rng_before", "rng_after")


def normal(value):
    return json.loads(json.dumps(value, allow_nan=False))


def validate(c):
    expected = {"protocol_id": "postprefix_probe_value_development_v1", "seed_start": 11200, "streams": 8,
                "tasks": list(TASKS), "scenarios": list(SCENARIOS), "replicates": 4, "reserved_seeds": [11248, 11499],
                "methods": list(METHODS), "total_steps": 500, "prefix_steps": 6, "calibration_steps": 16,
                "noise_std": .05, "noise_namespace": 43003, "operator_generation_seed": 43001,
                "maximum_controlled_steps": 1152384, "maximum_controlled_resets": 2328, "maximum_do_simulation_frames": 66000000,
                "forward_offline_steps": 21010, "forward_offline_resets": 288,
                "primary_target": "MID16_WIDE", "primary_reference": "CACHE_CONTINUE", "minimum_non_tie_contexts": 24,
                "maximum_sign_reversal_fraction": .25, "minimum_leave_one_out_agreement": .75, "minimum_leave_one_out_coverage": .75,
                "api_calls": 0, "memory_writes": 0, "models_or_thresholds_fitted_from_new_outcomes": 0}
    if any(c.get(k) != v for k, v in expected.items()):
        raise ValueError("registered acquisition-value protocol differs")
    if c["forward_model_sha256"] != "b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80":
        raise ValueError("frozen forward bank differs")


def task_seed(stream, task, cold=False):
    return 11200 + stream * 6 + TASKS.index(task) * 2 + (0 if cold else 1)


def noise_seed(seed, task, replicate):
    return int(np.random.SeedSequence([seed, TASKS.index(task), 43003, replicate + 1]).generate_state(1)[0])


def library_sources():
    import metaworld
    from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
    package = Path(metaworld.__file__).parent
    paths = {"metaworld/__init__.py": package / "__init__.py", "metaworld/sawyer_xyz_env.py": package / "sawyer_xyz_env.py",
             "metaworld/wrappers.py": package / "wrappers.py", "gymnasium/mujoco_env.py": Path(inspect.getfile(MujocoEnv))}
    for name in ("sawyer_push_v3.py", "sawyer_reach_v3.py", "sawyer_door_v3.py"):
        paths["metaworld/envs/" + name] = package / "envs" / name
    for path in sorted(package.rglob("*")):
        if path.is_file() and path.suffix.lower() in (".py", ".xml", ".stl", ".obj", ".mtl", ".png", ".jpg", ".jpeg"):
            paths["metaworld/" + path.relative_to(package).as_posix()] = path
    return {name: digest(path) for name, path in paths.items()}


def prepare():
    check_clean()
    c = json.loads(CONFIG.read_text(encoding="utf-8")); validate(c)
    _, source, _ = load_bank(c)
    profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8"))
    if profile["confidence_qualified"] or profile["probability_guarantee"]:
        raise ValueError("unqualified original reference scale required")
    parent = ROOT / c["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("protocol already prepared")
    commit = git("rev-parse", "HEAD"); stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names = git("ls-files", "src", "scripts", "tests").splitlines() + [CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(),
             "requirements.txt", c["forward_model_path"], c["forward_audit_path"], c["nominal_profile_path"],
             (source / "CALIBRATION.jsonl.gz").relative_to(ROOT).as_posix(), (source / "predictions.jsonl").relative_to(ROOT).as_posix()]
    m = {"experiment_run_id": f"acquisition_value_{stamp}_{commit[:12]}", "source_git_commit": commit, "config": c,
         "input_sha256": {name: digest(ROOT / name) for name in names}, "policy_sha256": policy_hashes(TASKS),
         "operators_oracle": operators(c), "library_source_sha256": library_sources(),
         "versions": {p: importlib.metadata.version(p) for p in ("metaworld", "mujoco", "gymnasium", "numpy", "scipy")}}
    m["manifest_id"] = manifest_digest(m)
    output = parent / m["experiment_run_id"]; output.mkdir(parents=True, exist_ok=False)
    write_json(output / "manifest.json", m); print(output / "manifest.json")


def load(path):
    m = json.loads(path.read_text(encoding="utf-8")); validate(m["config"])
    if manifest_digest(m) != m["manifest_id"] or any(digest(ROOT / n) != h for n, h in m["input_sha256"].items()):
        raise ValueError("frozen acquisition source changed")
    if operators(m["config"]) != m["operators_oracle"] or policy_hashes(TASKS) != m["policy_sha256"] or library_sources() != m["library_source_sha256"]:
        raise ValueError("frozen bank, policy or initialization library changed")
    if any(importlib.metadata.version(p) != v for p, v in m["versions"].items()):
        raise ValueError("pinned runtime version changed")
    return m


def physics_witness(env):
    """Declared integration/model/task fields, not a full clone qualification."""
    import mujoco
    e = env.unwrapped
    spec = mujoco.mjtState.mjSTATE_INTEGRATION
    state = np.empty(mujoco.mj_stateSize(e.model, spec))
    mujoco.mj_getState(e.model, e.data, state, spec)
    fields = ("curr_path_length", "_prev_obs", "_target_pos", "_last_rand_vec", "obj_init_pos", "init_tcp")
    task = {}
    for field in fields:
        value = getattr(e, field)
        task[field] = value.tolist() if isinstance(value, np.ndarray) else value
    return normal({"state_spec": int(spec), "integration": state.tolist(), "body_pos": e.model.body_pos.tolist(),
                   "site_pos": e.model.site_pos.tolist(), "task_fields": task,
                   "complete_hidden_state_qualification": False})


class BranchFailure(RuntimeError):
    def __init__(self, record):
        self.record = record
        super().__init__(record["error"])


def execute(key, operator, previous, model, sigma, emit, ledger):
    method = key["method"]; calibration = method == "CALIBRATE_OLD16"
    if not calibration and method not in PROGRAMS:
        raise ValueError("unregistered actual branch")
    record = {**key, "source_cache": saved_cache(previous), "trace": [], "decisions": [], "initial": None,
              "initial_rng_hash": None, "initial_physics_witness_oracle": None, "prefix_physics_witness_oracle": None,
              "post_fixed_probe_physics_witness_oracle": None,
              "ledger_before": ledger.snapshot()}
    if not calibration and method in PRIOR_CACHE_METHODS and previous is None:
        d = emit("DECISION", {**key, "at_host_calls": 0, "action": "STOP_NO_SOURCE_CACHE", "controller": None, "ledger": ledger.snapshot()})
        record["decisions"].append(d)
        record.update(ledger_after=ledger.snapshot(), new_cache=None,
                      outcome={"success": False, "stopped": True, "total_steps": 0, "environment_resets": 0,
                               "prefix_steps": 0, "micro_steps": 0, "fixed_probe_steps": 0, "policy_steps": 0,
                               "point_fit_failures": 0, "deadline_loss": 500, "source_cache_unavailable": True})
        return record
    env = None; current = None; calls = 0; step_attempts = 0; samples = []; new_cache = None
    controller = previous.controller if previous is not None else identity_controller()
    last = None; micro = 0
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
            return hashlib.sha256(json.dumps(fault._rng.bit_generator.state, sort_keys=True).encode()).hexdigest()
        current = StepObservation(tuple(observation), False, False, False)
        history = ForwardHistory(current.observation); policy = create_task_policy(key["task"])
        record.update(initial=asdict(current), initial_rng_hash=rng_hash(), initial_physics_witness_oracle=physics_witness(env))
        reset_delta = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0) - record["ledger_before"]["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        if reset_delta != 1:
            raise ValueError("exactly one measured control reset required")
        emit("CONTROLLED_INITIAL", {**key, "initial": record["initial"], "rng_hash": record["initial_rng_hash"],
                                   "physics_witness_oracle": record["initial_physics_witness_oracle"], "ledger": ledger.snapshot()})
        def ended():
            return current.success or current.terminated or current.truncated
        def choose(action, **values):
            nonlocal last
            last = emit("DECISION", {**key, "at_host_calls": calls, "observation_sha256": state_hash(current.observation),
                                      "rng_hash": rng_hash(), "action": action, "controller": normal(controller), **values})
            record["decisions"].append(last)
            last = normal(last)
        def step(command, phase, raw=None):
            nonlocal current, calls, step_attempts
            if ended() or calls >= 500:
                raise ValueError("ended or exhausted branch stepped")
            before = current; sent = np.asarray(command, dtype=np.float32)
            query = history.request(sent)
            intent = emit("STEP_INTENT", {**key, "at_host_calls": calls, "decision_sequence": last["sequence"], "phase": phase,
                        "command": sent.tolist(), "raw_policy": raw, "before": asdict(before), "rng_before": rng_hash(),
                        "forward_query": normal(asdict(query)) if query is not None else None, "ledger_before": ledger.snapshot()})
            intent = normal(intent)
            started = perf_counter_ns()
            acted = np.clip(fault.apply(np.asarray(intent["command"], dtype=np.float32)), -1, 1)
            simulation_before = float(env.unwrapped.data.time)
            step_attempts += 1
            with ledger.scope("CONTROL"):
                observation, _, terminated, truncated, info = env.step(acted)
            simulation_after = float(env.unwrapped.data.time)
            finished = perf_counter_ns(); calls += 1
            current = StepObservation(tuple(observation), bool(terminated), bool(truncated), bool(info.get("success", False)))
            expected_elapsed = float(env.unwrapped.model.opt.timestep) * int(env.unwrapped.frame_skip)
            if not np.isclose(simulation_after-simulation_before, expected_elapsed, atol=1e-10, rtol=1e-10):
                raise ValueError("simulation clock discontinuity or automatic reset")
            control_before = intent["ledger_before"]["by_phase"].get("CONTROL", {})
            control_after = ledger.snapshot()["by_phase"].get("CONTROL", {})
            if control_after.get("reset_attempts", 0) != control_before.get("reset_attempts", 0):
                raise ValueError("reset during a continuous control step")
            if control_after.get("simulation_frames_completed", 0)-control_before.get("simulation_frames_completed", 0) != 5:
                raise ValueError("registered five-frame control request differs")
            target = history.observe(ContinuousTransition(tuple(intent["command"]), before.observation, current.observation))
            if query is not None:
                samples.append(OperatorSample(calls, query, target))
            row = {"host_calls": calls, "intent_sequence": intent["sequence"], "decision_sequence": last["sequence"], "phase": phase,
                   "command": intent["command"], "raw_policy": raw, "before": asdict(before), "after": asdict(current),
                   "rng_before": intent["rng_before"], "rng_after": rng_hash(), "target_xy": list(target),
                   "executed_action_oracle": acted.tolist(), "intent_saved_ns": intent["saved_ns"],
                   "simulation_time_before_oracle": simulation_before, "simulation_time_after_oracle": simulation_after,
                   "execution_started_ns": started, "completed_ns": finished, "ledger_before": intent["ledger_before"], "ledger_after": ledger.snapshot()}
            record["trace"].append(row)
            emit("STEP_COMPLETE", {**key, **row})
            if calls == 6:
                record["prefix_physics_witness_oracle"] = physics_witness(env)
        def program(commands, phase):
            for command in commands:
                if ended() or calls >= 500:
                    break
                step(command, phase)
        def policy_step(phase="POLICY"):
            raw = np.asarray(policy.get_action(np.asarray(current.observation)), dtype=np.float32)
            step(encode_controller(last["controller"], raw), phase, raw.tolist())
        def fresh(length, magnitude, keep_old=False):
            nonlocal controller, new_cache
            if ended():
                return
            if calls + length + 32 > 500:
                controller = None; choose("STOP_BUDGET"); return
            start = calls
            choose("REQUEST_FIXED_PROBE", probe_steps=length, magnitude=magnitude)
            program(symmetric_program(magnitude, steps_per_direction=length // 4), "FIXED_PROBE")
            record["post_fixed_probe_physics_witness_oracle"] = physics_witness(env)
            if ended():
                return
            if keep_old:
                if previous is None:raise ValueError("keep branch needs its original cache")
                choose("KEEP_MEASURED_OLD_POINT");return
            fit = infer_operator(model, tuple(s for s in samples if s.step > start))
            if fit["valid"]:
                new_cache = CachedPoint(fit["matrix_xy"], fit["bias_xy"])
                controller = new_cache.controller; choose("RUN_NEW_POINT", fit=fit)
            else:
                controller = None; choose("STOP_POINT_FIT", fit=fit)
        if calibration:
            fresh(16, .2)
        else:
            spec = PROGRAMS[method]
            if spec.uncorrected:
                controller = identity_controller(); choose("RUN_UNCORRECTED")
            elif spec.prefix_steps:
                choose("REQUEST_PREFIX", prefix_steps=6)
                for _ in range(6):
                    if ended(): break
                    policy_step("PREFIX_POLICY")
                if not ended() and spec.guard:
                    while not ended():
                        decision = agent_validation(spec.guard, model, previous, tuple(samples), sigma, micro, 500 - calls)
                        if decision["action"].startswith("STOP"):
                            controller = None
                        choose(decision["action"], validation=decision, micro_steps=micro)
                        action = decision["action"]
                        if action == "REUSE_CACHE" or action.startswith("STOP"):
                            break
                        if action in ("REFRESH_FIXED16", "REFRESH_NUMERICAL_DESIGN"):
                            fresh(16, .2); break
                        start = calls; program(PRIMITIVES[decision["program_id"]], "MICRO_PROBE"); micro += calls - start
                elif not ended():
                    fresh(spec.probe_steps, spec.magnitude, spec.keep_old)
            elif spec.probe_steps:
                fresh(spec.probe_steps, spec.magnitude)
            else:
                choose("RUN_OLD_POINT")
            while not ended() and calls < 500 and last["controller"] is not None:
                policy_step()
        phase = Counter(r["phase"] for r in record["trace"])
        stopped = last["controller"] is None
        record.update(new_cache=saved_cache(new_cache), ledger_after=ledger.snapshot(),
                      outcome={"success": current.success, "stopped": stopped, "total_steps": calls, "environment_resets": 1,
                               "prefix_steps": phase["PREFIX_POLICY"], "micro_steps": phase["MICRO_PROBE"],
                               "fixed_probe_steps": phase["FIXED_PROBE"], "policy_steps": phase["POLICY"],
                               "point_fit_failures": sum(d.get("fit") is not None and not d["fit"]["valid"] for d in record["decisions"]),
                               "deadline_loss": deadline_loss(current.success, stopped, calls), "source_cache_unavailable": False})
        return record
    except BaseException as exc:
        record.update(error_type=type(exc).__name__, error=str(exc), completed_steps=calls,
                      attempted_controlled_steps=step_attempts, unresolved_controlled_step_attempts=step_attempts-calls,
                      last_observation=asdict(current) if current is not None else None,
                      ledger_after=ledger.snapshot(), unconfirmed_attempt=True)
        raise BranchFailure(record) from exc
    finally:
        if env is not None:
            env.close()


def pairing_reason(target, reference):
    if any(target[k]!=reference[k] for k in ("stream","task","scenario","replicate","seed","operator_id_oracle")):
        raise ValueError("foreign physical pair")
    if target["source_cache"] is None or reference["source_cache"] is None:
        return "NO_SOURCE_CACHE"
    if target["source_cache"] != reference["source_cache"] or target["initial"] != reference["initial"] or target["initial_rng_hash"] != reference["initial_rng_hash"]:
        raise ValueError("source or initialization matching violated")
    if target["initial_physics_witness_oracle"] != reference["initial_physics_witness_oracle"]:
        raise ValueError("declared initial integration witness differs")
    a, b = target["trace"][:6], reference["trace"][:6]
    if len(a) != 6 or len(b) != 6:
        return "ENDED_BEFORE_SIX"
    if any({k: x[k] for k in PREFIX_FIELDS} != {k: y[k] for k in PREFIX_FIELDS} for x, y in zip(a, b)):
        raise ValueError("real six-step physical prefix differs")
    if target["prefix_physics_witness_oracle"] != reference["prefix_physics_witness_oracle"]:
        raise ValueError("declared post-prefix integration witness differs")
    if any(a[5]["after"][k] for k in ("success", "terminated", "truncated")):
        return "ENDED_AT_SIX"
    return "MATCHED"


def update_pair(target, keep, reference):
    method=target["method"]
    if method not in ("MID8_WIDE","MID16_WIDE") or keep["method"]!=method+"_KEEP":
        raise ValueError("unregistered update contrast")
    if reference["method"]!="CACHE_CONTINUE":raise ValueError("unregistered motion reference")
    why=pairing_reason(target,keep)
    if pairing_reason(keep,reference)!=why:raise ValueError("unmatched motion reference")
    length=PROGRAMS[method].probe_steps;end=6+length
    if why=="MATCHED":
        a,b=target["trace"][:end],keep["trace"][:end]
        if any({k:x[k] for k in PREFIX_FIELDS}!={k:y[k] for k in PREFIX_FIELDS} for x,y in zip(a,b)):
            raise ValueError("probe motion/RNG differs before update")
        if len(a)!=end or len(b)!=end:
            if len(a)!=len(b):raise ValueError("probe completion differs")
            why="ENDED_DURING_PROBE"
        elif target["post_fixed_probe_physics_witness_oracle"]!=keep["post_fixed_probe_physics_witness_oracle"]:
            raise ValueError("declared post-probe state differs")
        elif any(a[-1]["after"][k] for k in ("success","terminated","truncated")):
            why="ENDED_AT_PROBE"
        else:why="MATCHED_UPDATE"
    c,b,a=target["outcome"],keep["outcome"],reference["outcome"]
    return {**{k:target[k] for k in ("stream","task","scenario","replicate","seed")},"method":method,"probe_steps":length,"reason":why,
            "updated_success":c["success"],"kept_success":b["success"],"reference_success":a["success"],
            "updated_stop":c["stopped"],"kept_stop":b["stopped"],
            "updated_steps":c["total_steps"],"kept_steps":b["total_steps"],"reference_steps":a["total_steps"],
            "updated_deadline_loss":c["deadline_loss"],"kept_deadline_loss":b["deadline_loss"],"reference_deadline_loss":a["deadline_loss"],
            "update_loss_difference":c["deadline_loss"]-b["deadline_loss"],
            "probe_motion_loss_difference":b["deadline_loss"]-a["deadline_loss"],
            "total_loss_difference":c["deadline_loss"]-a["deadline_loss"],
            "pure_information_value_claim":False}


def run(path):
    check_clean(); m = load(path)
    if git("rev-parse", "HEAD") != m["source_git_commit"]:
        raise ValueError("frozen commit differs")
    output = path.parent; c = m["config"]
    if (output / "status.json").exists():
        raise FileExistsError("one-shot collection cannot restart")
    models, _, _ = load_bank(c)
    profile = json.loads((ROOT / c["nominal_profile_path"]).read_text(encoding="utf-8"))
    identity = {k: m[k] for k in IDENTITY}
    status = {**identity, "status": "RUNNING", "episodes": 0, "cold_sources": 0, "controlled_steps": 0,
              "controlled_resets": 0, "api_calls": 0, "memory_writes": 0}
    write_json(output / "status.json", status)
    sequence = 0; active = None; rows = []; sources = []; pairings = []; update_pairs=[]
    def emit(kind, payload):
        nonlocal sequence
        sequence += 1
        event = {**identity, "event": kind, "sequence": sequence, "saved_ns": perf_counter_ns(), **normal(payload)}
        active.write(json.dumps(event, separators=(",", ":"), allow_nan=False) + "\n"); active.flush()
        return event
    ledger = LifecycleLedger(emit, c["maximum_do_simulation_frames"])
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
    try:
        with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld), ExitStack() as stack:
            cold_file = stack.enter_context(gzip.open(output / "cold_sources.jsonl.gz", "wt", encoding="utf-8"))
            for stream in range(8):
                with gzip.open(output / f"events_{stream:02}.jsonl.gz", "wt", encoding="utf-8") as events, \
                     gzip.open(output / f"episodes_{stream:02}.jsonl.gz", "wt", encoding="utf-8") as cases:
                    active = events
                    bank = {p["id"]: p for p in m["operators_oracle"][stream]["states_oracle"]}
                    for task in TASKS:
                        key = {**identity, "stream": stream, "task": task, "scenario": "SOURCE_A", "replicate": -1,
                               "seed": task_seed(stream, task, True), "method": "CALIBRATE_OLD16", "operator_id_oracle": "A"}
                        source = execute(key, bank["A"], None, models[task], profile["rms_m"][task], emit, ledger)
                        cold_file.write(json.dumps(source, allow_nan=False) + "\n"); cold_file.flush()
                        sources.append({**key, **source["outcome"]}); previous = cached(source["new_cache"])
                        status["cold_sources"] += 1; status["controlled_steps"] += source["outcome"]["total_steps"]
                        status["controlled_resets"] += source["outcome"]["environment_resets"]
                        for scenario in SCENARIOS:
                            label = "A" if scenario == "UNCHANGED" else "B"
                            for replicate in range(4):
                                branches = {}
                                for method in METHODS:
                                    key = {**identity, "stream": stream, "task": task, "scenario": scenario, "replicate": replicate,
                                           "seed": task_seed(stream, task), "method": method, "operator_id_oracle": label}
                                    record = execute(key, bank[label], previous if method in PRIOR_CACHE_METHODS else None, models[task], profile["rms_m"][task], emit, ledger)
                                    cases.write(json.dumps(record, allow_nan=False) + "\n"); cases.flush(); branches[method] = record
                                    rows.append({**key, **record["outcome"]}); status["episodes"] += 1
                                    status["controlled_steps"] += record["outcome"]["total_steps"]
                                    status["controlled_resets"] += record["outcome"]["environment_resets"]
                                    if status["controlled_steps"] > c["maximum_controlled_steps"] or status["controlled_resets"] > c["maximum_controlled_resets"]:
                                        raise ValueError("whole-study control cap exceeded")
                                for method in MID_METHODS:
                                    pairings.append({**{k: key[k] for k in ("stream", "task", "scenario", "replicate", "seed")},
                                                     "method": method, "reason": pairing_reason(branches[method], branches["CACHE_CONTINUE"])})
                                for method in ("MID8_WIDE","MID16_WIDE"):
                                    update_pairs.append(update_pair(branches[method],branches[method+"_KEEP"],branches["CACHE_CONTINUE"]))
                                status["lifecycle"] = ledger.snapshot(); write_json(output / "status.json", status)
                                print(f"Collected stream={stream} task={task} scenario={scenario} replicate={replicate}: {status['episodes']}/2304", flush=True)
        from scripts.analyze_acquisition_value import statistics
        summary = statistics(m, rows, sources, pairings,update_pairs)
        status.update(status="COMPLETED_TARGET_REPEAT_PASS" if summary["repeat_gate"]["passed"] else "COMPLETED_TARGET_REPEAT_FAILED", lifecycle=ledger.snapshot())
        write_json(output / "summary.json", {**status, "statistics": summary, "pairings": pairings,"update_pairs":update_pairs, "cold_sources": sources, "cases": rows})
    except BaseException as exc:
        status.update(status="FAILED_PARTIAL", error_type=type(exc).__name__, error=str(exc), lifecycle=ledger.snapshot())
        if isinstance(exc, BranchFailure):
            status["controlled_steps"] += exc.record["completed_steps"]
            status["controlled_resets"] = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
            status["unresolved_controlled_step_attempts"] = exc.record["unresolved_controlled_step_attempts"]
            write_json(output / "failed_branch.json", exc.record)
        write_json(output / "status.json", status)
        raise
    write_json(output / "status.json", status)
    print(json.dumps({k: status[k] for k in ("status", "episodes", "cold_sources", "controlled_steps", "controlled_resets")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "run"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest: run(args.manifest.resolve())
    else: parser.error("run requires --manifest")
