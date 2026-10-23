"""Freeze and run the one-shot finite-frame action-relevance diagnostic."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import importlib.metadata
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git, digest, manifest_digest, check_clean, append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_continuous_probe import LiveHost, state_hash, normalized
from scripts.run_response_calibration import audit as calibration_audit, restore
from scripts.run_calibrated_tasks import plan as legacy_plan
from src.probe.continuous import ContinuousEvidence, collect_continuous
from src.probe.response_calibration import ResponseModel, known_offset_program
from src.probe.frame_identification import (METHODS, NominalARX, program, canonical_hash,
    transcript_hash, fit_nominal_arx, select_frame, registered_controller, encode_command)
from src.rollout import create_push_environment, create_push_policy

CONFIG = ROOT / "configs/frame_evidence/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/frame_evidence_development_v1.md"
CONTEXTS = ("FRAME0", "FRAME90")
PRIOR_METHODS = ("MODEL_REPEAT8", "MODEL_REVERSE8", "MODEL_SYM16", "LEGACY_AFFINE16", "LEGACY_NEAREST16")


def validate(c):
    fixed = (c["protocol_id"], c["seed_start"], c["num_seeds"], c["reserved_seeds"],
        tuple(c["contexts"]), tuple(c["methods"]), c["noise_std"], c["total_steps"],
        c["maximum_physical_steps"], c["offline_steps"], c["offline_resets"],
        c["minimum_disjoint_action_seeds"], c["minimum_correct_controller_successes"],
        c["minimum_identification_successes"], c["minimum_reverse_task_successes"],
        c["minimum_reverse_gain_count"], c["maximum_reverse_deficit_to_sym16"],
        c["bootstrap_samples"], c["bootstrap_seed"], c["api_calls"], c["memory_writes"])
    if fixed != ("frame_evidence_development_v1", 9800, 8, [9808, 9999], CONTEXTS,
                 METHODS, .05, 500, 88000, 2304, 144, 6, 14, 14, 14, 4, 1, 10000,
                 2026101401, 0, 0):
        raise ValueError("frozen frame-evidence configuration mismatch")


def load_priors(c):
    path = ROOT / c["calibration_manifest"]
    qualified = calibration_audit(path)
    if qualified["status"] != "COMPLETED_QUALIFICATION_PASS":
        raise ValueError("legacy nominal calibration is not qualified")
    model_path = ROOT / c["legacy_model_path"]
    if digest(model_path) != qualified["model_sha256"]:
        raise ValueError("legacy model changed")
    rows = [json.loads(line) for line in (path.parent / "training.jsonl").read_text().splitlines()]
    training = []
    for row in rows:
        evidence = restore(row["evidence"])
        if row["phase"] != "training" or not 8900 <= row["seed"] <= 8907 or \
                tuple(t.command for t in evidence.transitions) != known_offset_program(row["known_command_offset"]):
            raise ValueError("nominal ARX training boundary mismatch")
        training.append(evidence)
    arx = fit_nominal_arx(training)
    if arx.training_trials != 72 or arx.samples != 1080:
        raise ValueError("nominal ARX training population mismatch")
    legacy = ResponseModel(**json.loads(model_path.read_text())["model"])
    return arx, legacy, qualified["model_sha256"]


def prepare():
    check_clean()
    c = json.loads(CONFIG.read_text()); validate(c)
    arx, _, legacy_sha = load_priors(c)
    root = ROOT / c["output_root"]
    if list(root.glob("*/manifest.json")):
        raise FileExistsError("frame protocol already frozen")
    commit = git("rev-parse", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    calibration_root = Path(c["calibration_manifest"]).parent
    names = git("ls-files", "src", "scripts", "tests").splitlines() + [
        CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(), "requirements.txt",
        c["legacy_model_path"], c["calibration_manifest"],
        (calibration_root / "training.jsonl").as_posix(),
        (calibration_root / "qualification.jsonl").as_posix(),
        (calibration_root / "status.json").as_posix(), (calibration_root / "summary.json").as_posix()]
    m = {"experiment_run_id": f"frame_evidence_{stamp}_{commit[:12]}", "source_git_commit": commit,
         "config": c, "nominal_arx": arx.to_dict(), "arx_model_sha256": canonical_hash(arx.to_dict()),
         "legacy_model_sha256": legacy_sha, "input_sha256": {n: digest(ROOT/n) for n in names},
         "versions": {p: importlib.metadata.version(p) for p in ("metaworld", "mujoco", "numpy")}}
    m["manifest_id"] = manifest_digest(m)
    output = root / m["experiment_run_id"]; output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "manifest.json", m)
    _write_json(output / "nominal_arx.json", {**identity(m), "model": m["nominal_arx"],
                                             "arx_model_sha256": m["arx_model_sha256"]})
    print(output / "manifest.json")


def identity(m):
    return {k: m[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}


def load(path):
    m = json.loads(path.read_text()); validate(m["config"])
    if manifest_digest(m) != m["manifest_id"] or canonical_hash(m["nominal_arx"]) != m["arx_model_sha256"]:
        raise ValueError("manifest/model hash mismatch")
    for p, sha in m["input_sha256"].items():
        if digest(ROOT/p) != sha:
            raise ValueError(f"frozen input changed: {p}")
    return m


def noise_seed(seed):
    # Coupled evaluator worlds. Neither context nor method changes the stream.
    return int(np.random.SeedSequence([seed, 0xF81]).generate_state(1)[0])


class FrameFault:
    """Evaluator-only frame/bias/noise injection, never passed to selection."""
    def __init__(self, context):
        if context not in CONTEXTS:
            raise ValueError("unknown evaluator context")
        self.rotation = np.eye(2, dtype=np.float32) if context == "FRAME0" else np.array([[0,-1],[1,0]], dtype=np.float32)
        self.bias = np.array([-.1,.1], dtype=np.float32) if context == "FRAME0" else np.array([.1,-.1], dtype=np.float32)
        self._rng = None
        self.last_executed = None

    def reset(self, seed):
        self._rng = np.random.default_rng(seed)

    def apply(self, command):
        command = np.asarray(command, dtype=np.float32)
        if self._rng is None:
            raise RuntimeError("actuator must be initialized")
        if command.shape != (4,) or not np.isfinite(command).all() or np.any(np.abs(command) > 1):
            raise ValueError("all methods must send bounded finite commands")
        result = command.copy()
        result[:2] = self.rotation @ command[:2] + self.bias
        result[:3] += self._rng.normal(0, .05, 3).astype(np.float32)
        self.last_executed = np.clip(result, -1, 1)
        return result


class LoggedHost(LiveHost):
    def __init__(self, *args):
        super().__init__(*args)
        self.trace = []

    def step(self, command):
        before, before_rng = self.current, self.rng_hash()
        after = super().step(command)
        self.trace.append({"before": asdict(before), "after": asdict(after),
            "command": np.asarray(command, dtype=np.float32).tolist(),
            "executed_action_oracle": self.fault.last_executed.tolist(),
            "rng_before": before_rng, "rng_after": self.rng_hash(), "host_calls": self.calls})
        return after


def choose(method, evidence, arx, legacy):
    """No evaluator context/seed/fault/RNG/outcome parameter is accepted."""
    if method == "NO_PROBE" and evidence is None:
        return {"controller":registered_controller("UNCORRECTED"), "inference":None, "stop":False}
    if method not in METHODS or type(evidence) is not ContinuousEvidence or method == "NO_PROBE":
        raise ValueError("invalid frame method/evidence")
    expected = program(method)
    if type(evidence.requested_steps) is not int or evidence.requested_steps != len(expected) or \
            not 1 <= evidence.steps <= len(expected) or evidence.stop_reason == "PROGRAM_COMPLETE" and evidence.steps != len(expected):
        raise ValueError("registered probe size mismatch")
    if tuple(t.command for t in evidence.transitions) != program(method)[:evidence.steps]:
        raise ValueError("unregistered probe program")
    if evidence.stop_reason != "PROGRAM_COMPLETE":
        return {"controller": None, "inference": {"valid": False, "reason": "TERMINAL_PROBE"}, "stop": True}
    if method.startswith("MODEL_"):
        inference = select_frame(arx, evidence)
        controller = registered_controller(inference["controller_id"])
    elif method.startswith("LEGACY_"):
        old_method = "PRIOR_AFFINE" if method == "LEGACY_AFFINE16" else "PRIOR_NEAREST"
        old = legacy_plan(old_method, evidence, legacy)
        controller = {"id": old_method.replace("PRIOR", "LEGACY"), "matrix_xy": np.eye(2).tolist(), "offset": old["correction"]}
        inference = old["fit"]
    else:
        name = "FRAME_A" if method.startswith("FIXED_A") else "FRAME_B" if method.startswith("FIXED_B") else "UNCORRECTED"
        controller, inference = registered_controller(name), None
    return {"controller": controller, "inference": inference, "stop": False}


def summarize(rows, c):
    seeds = list(range(c["seed_start"], c["seed_start"]+c["num_seeds"]))
    expected = [(s, k, method) for s in seeds for k in CONTEXTS for method in METHODS]
    if [(r["seed"], r["context_oracle"], r["method"]) for r in rows] != expected:
        raise ValueError("incomplete/duplicate frame population")
    indexed = {(r["seed"], r["context_oracle"], r["method"]): r for r in rows}
    metrics = {}
    for method in METHODS:
        selected = [r for r in rows if r["method"] == method]
        mean = float(np.mean([r["total_steps"] for r in selected])); prior = method in PRIOR_METHODS
        metrics[method] = {"successful": sum(r["success"] for r in selected),
            "per_context_successful": {k: sum(r["success"] for r in selected if r["context_oracle"]==k) for k in CONTEXTS},
            "mean_online_steps": mean, "mean_probe_steps": float(np.mean([r["probe_steps"] for r in selected])),
            "offline_steps": 2304 if prior else 0, "offline_resets": 144 if prior else 0,
            "mean_amortized_steps": mean + (144 if prior else 0), "mean_amortized_resets": 10 if prior else 1,
            "stopped": sum(r["stopped"] for r in selected),
            "correct_frame_choices_oracle": sum(r["correct_frame_choice_oracle"] is True for r in selected) if method.startswith("MODEL_") else None}
    common, repeat_equal, reverse_distinct, disjoint, informed, blind = 0, 0, 0, 0, 0, 0
    witnesses = []
    fixed = ("FIXED_A_PREFIX4", "FIXED_B_PREFIX4", "UNCORRECTED_PREFIX4")
    for seed in seeds:
        same = len({indexed[seed,k,method]["prefix4_hash"] for k in CONTEXTS for method in METHODS if method!="NO_PROBE"}) == 1
        common += same
        repeated = indexed[seed,"FRAME0","MODEL_REPEAT8"]["probe_hash"] == indexed[seed,"FRAME90","MODEL_REPEAT8"]["probe_hash"]
        separated = indexed[seed,"FRAME0","MODEL_REVERSE8"]["probe_hash"] != indexed[seed,"FRAME90","MODEL_REVERSE8"]["probe_hash"]
        repeat_equal += repeated; reverse_distinct += separated
        successful_sets = [[method for method in fixed if indexed[seed,k,method]["success"]] for k in CONTEXTS]
        witness = all(successful_sets) and not (set(successful_sets[0]) & set(successful_sets[1]))
        disjoint += witness
        seed_blind = max(sum(indexed[seed,k,method]["success"] for k in CONTEXTS) for method in fixed)
        seed_informed = sum(bool(v) for v in successful_sets)
        blind += seed_blind; informed += seed_informed
        witnesses.append({"seed": seed, "common_prefix_equal": same, "repeat_equal": repeated,
            "reverse_distinct": separated, "successful_sets": successful_sets, "disjoint": witness,
            "context_blind_evaluator_upper": seed_blind, "context_informed_evaluator_upper": seed_informed})
    correct_fixed = sum(indexed[s,"FRAME0","FIXED_A_PREFIX4"]["success"] +
                        indexed[s,"FRAME90","FIXED_B_PREFIX4"]["success"] for s in seeds)
    structural = {"common_prefix_all": common == 8, "repeated_probe_all": repeat_equal == 8,
        "reverse_separates_all": reverse_distinct == 8, "disjoint_actions": disjoint >= c["minimum_disjoint_action_seeds"],
        "correct_fixed_controller": correct_fixed >= c["minimum_correct_controller_successes"]}
    reverse = metrics["MODEL_REVERSE8"]
    baseline_counts = [metrics[name]["successful"] for name in ("MODEL_REPEAT8", "FIXED_A_REVERSE8", "FIXED_B_REVERSE8")]
    baseline = {"identification": reverse["correct_frame_choices_oracle"] >= c["minimum_identification_successes"],
        "task_count": reverse["successful"] >= c["minimum_reverse_task_successes"],
        "choice_gain": reverse["successful"] - max(baseline_counts) >= c["minimum_reverse_gain_count"],
        "legacy_affine": reverse["successful"] >= metrics["LEGACY_AFFINE16"]["successful"],
        "legacy_nearest": reverse["successful"] >= metrics["LEGACY_NEAREST16"]["successful"],
        "no_probe": reverse["successful"] >= metrics["NO_PROBE"]["successful"],
        "cheap_vs_full": reverse["successful"] >= metrics["MODEL_SYM16"]["successful"] - c["maximum_reverse_deficit_to_sym16"]}
    contrasts = {}
    rng = np.random.default_rng(c["bootstrap_seed"])
    resample = rng.integers(0, 8, size=(c["bootstrap_samples"], 8))
    for method in METHODS:
        if method == "MODEL_REVERSE8":
            continue
        delta = np.array([np.mean([int(indexed[s,k,"MODEL_REVERSE8"]["success"])-int(indexed[s,k,method]["success"]) for k in CONTEXTS]) for s in seeds])
        draws = np.mean(delta[resample], axis=1)
        contrasts[method] = {"difference": float(np.mean(delta)), "per_seed": delta.tolist(),
            "cluster_bootstrap_95": np.quantile(draws, [.025,.975], method="linear").tolist()}
    failures = [{k:r[k] for k in ("seed", "context_oracle", "method", "controller_id", "probe_steps", "task_steps", "stopped")}
                for r in rows if not r["success"]]
    return {"methods": metrics, "witnesses": witnesses, "disjoint_action_seeds": int(disjoint),
        "context_blind_evaluator_upper": int(blind), "context_informed_evaluator_upper": int(informed),
        "correct_fixed_controller_successes": int(correct_fixed), "structural_gates": structural,
        "structural_pass": all(structural.values()), "standard_baseline_gates": baseline,
        "standard_baseline_pass": all(baseline.values()), "gate_passed": all(structural.values()) and all(baseline.values()),
        "reverse_minus_baseline": contrasts, "independent_seed_clusters": 8, "failures": failures}


def run(path):
    check_clean(); m = load(path); c = m["config"]
    if git("rev-parse", "HEAD") != m["source_git_commit"]:
        raise ValueError("source commit mismatch")
    arx, legacy, legacy_sha = load_priors(c)
    if canonical_hash(arx.to_dict()) != m["arx_model_sha256"] or legacy_sha != m["legacy_model_sha256"]:
        raise ValueError("frozen nominal model changed")
    output = path.parent
    if (output / "status.json").exists():
        raise FileExistsError("one-shot frame run cannot restart")
    status = {**identity(m), "status":"RUNNING", "complete_units":0, "episodes":0, "physical_steps":0,
              "environment_resets":0, "events":0, "api_calls":0, "memory_writes":0}
    _write_json(output / "status.json", status)
    outcomes = []
    def event(key, kind, **values):
        status["events"] += 1
        append(output / "events.jsonl", {**key, "event_index": status["events"], "kind": kind,
            "perf_counter_ns": time.perf_counter_ns(), "utc": datetime.now(timezone.utc).isoformat(), **values})
    try:
        with gzip.open(output / "episodes.jsonl.gz", "wt", encoding="utf-8") as handle:
            for seed in range(c["seed_start"], c["seed_start"]+c["num_seeds"]):
                for context in CONTEXTS:
                    for method in METHODS:
                        key = {**identity(m), "episode_index": status["episodes"]+1, "seed":seed,
                            "context_oracle":context, "method":method, "arx_model_sha256":m["arx_model_sha256"],
                            "legacy_model_sha256":m["legacy_model_sha256"]}
                        env = create_push_environment(seed); host = None
                        try:
                            host = LoggedHost(env, FrameFault(context), seed, noise_seed(seed)); initial = host.current
                            event(key, "INITIAL", host_calls=0, observation_hash=state_hash(initial.observation), rng_hash=host.rng_hash())
                            commands = program(method)
                            evidence = collect_continuous(host.step, initial, commands, remaining_budget=500, task_reserve=500-len(commands)) if commands else None
                            handoff, n_probe = host.current, evidence.steps if evidence else 0
                            event(key, "PROBE_FINISHED", host_calls=host.calls, observation_hash=state_hash(handoff.observation), rng_hash=host.rng_hash())
                            choice = normalized(choose(method, evidence, arx, legacy))
                            declaration = {**key, "initial":asdict(initial), "evidence":evidence.to_dict() if evidence else None, "choice":choice,
                                "host_calls":host.calls, "rng_handoff":host.rng_hash(), "choice_hash":canonical_hash(choice)}
                            append(output / "decisions.jsonl", declaration)
                            event(key, "CHOICE_SAVED", host_calls=host.calls, choice_hash=declaration["choice_hash"])
                            # Execution reloads the persisted selection. No evaluator-based substitution.
                            saved = json.loads((output / "decisions.jsonl").read_text().splitlines()[-1])
                            if saved["episode_index"] != key["episode_index"] or saved["choice_hash"] != canonical_hash(saved["choice"]):
                                raise ValueError("persisted choice association changed")
                            choice = saved["choice"]
                            event(key, "TASK_SKIPPED" if choice["stop"] else "TASK_STARTED", host_calls=host.calls,
                                  observation_hash=state_hash(host.current.observation), rng_hash=host.rng_hash(), choice_hash=saved["choice_hash"])
                            policy = create_push_policy()
                            while not choice["stop"] and not (host.current.success or host.current.terminated or host.current.truncated) and host.calls < 500:
                                raw = np.asarray(policy.get_action(np.array(host.current.observation)), dtype=np.float32)
                                command = encode_command(choice["controller"], raw)
                                host.step(command)
                                host.trace[-1].update(raw_policy=raw.tolist(), choice_hash=saved["choice_hash"])
                            controller_id = choice["controller"]["id"] if choice["controller"] else None
                            correct = controller_id == ("FRAME_A" if context=="FRAME0" else "FRAME_B") if method.startswith("MODEL_") else None
                            outcome = {**key, "success":host.current.success, "stopped":choice["stop"], "controller_id":controller_id,
                                "correct_frame_choice_oracle":correct, "probe_steps":n_probe, "task_steps":host.calls-n_probe,
                                "total_steps":host.calls, "environment_resets":host.resets, "actuator_resets":1,
                                "prefix4_hash":transcript_hash(evidence, 4) if evidence else None, "probe_hash":transcript_hash(evidence) if evidence else None,
                                "initial_hash":state_hash(initial.observation), "handoff_hash":state_hash(handoff.observation),
                                "final_hash":state_hash(host.current.observation)}
                            event(key, "FINISHED", host_calls=host.calls, outcome_hash=canonical_hash(outcome))
                            record = {**key, "declaration":saved, "steps":host.trace, "outcome":outcome}
                            handle.write(json.dumps(record, allow_nan=False)+"\n"); handle.flush()
                            outcomes.append(outcome); status["episodes"] += 1
                            status["physical_steps"] += host.calls; status["environment_resets"] += host.resets
                        except BaseException as exc:
                            partial = {**key, "error_type":type(exc).__name__, "error":str(exc),
                                "partial_steps":host.trace if host else [], "partial_host_calls":host.calls if host else 0,
                                "partial_environment_resets":host.resets if host else 0}
                            append(output / "failed_episode.jsonl", partial)
                            status["partial_physical_steps"] = partial["partial_host_calls"]
                            status["partial_environment_resets"] = partial["partial_environment_resets"]
                            raise
                        finally:
                            env.close()
                    status["complete_units"] += 1; _write_json(output / "status.json", status)
                    print(f"Completed {seed}/{context}: {status['complete_units']}/16", flush=True)
        if status["physical_steps"] > c["maximum_physical_steps"]:
            raise ValueError("physical task budget exceeded")
        statistics = summarize(outcomes, c)
        status["status"] = "COMPLETED_PREREQUISITE_PASS" if statistics["gate_passed"] else "COMPLETED_PREREQUISITE_FAILED"
        _write_json(output / "summary.json", {**status, "statistics":statistics}); _write_json(output / "status.json", status)
        print(json.dumps({"status":status["status"], "structural_gates":statistics["structural_gates"],
                          "standard_baseline_gates":statistics["standard_baseline_gates"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE", error_type=type(exc).__name__, error=str(exc))
        _write_json(output / "status.json", status)
        raise


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__); group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true"); group.add_argument("--manifest", type=Path)
    a = p.parse_args()
    prepare() if a.prepare else run(a.manifest.resolve())
