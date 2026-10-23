"""One-shot prospective acquisition benchmark with isolated chronological caches."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import random
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.build_autoresearch_benchmark import get_conditions
from scripts.run_evidence_persistence import check_clean, git, digest, manifest_digest, append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_probemem_additional_ablation import _execute
from src.autoresearch import RecoveryPolicyConfig
from src.perturbations import BiasNoisePerturbation
from src.probe.directional import run_symmetric_probes, estimate_planar_bias
from src.probemem.evidence_refresh import METHODS, Measurement, decide, accepted_update
from src.rollout import create_push_environment
from src.task_metrics import extract_push_positions

CONFIG = ROOT / "configs/evidence_refresh/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/evidence_refresh_prefix_development_v1.md"
CACHED_METHODS = {"STALE", "PERIODIC_4", "CHANGE_THRESHOLD", "DECISION_STABILITY"}


def validate_config(c):
    if (c["seed_start"], c["streams"], c["episodes_per_stream"]) != (8200, 8, 12):
        raise ValueError("frozen stream population mismatch")
    if tuple(c["methods"]) != METHODS or c["noise_std"] != .05 or c["api_calls"] != 0:
        raise ValueError("frozen methods/noise/scope mismatch")
    if (c["max_probe_repetitions"], c["steps_per_repetition"], c["verification_steps"], c["path_max_steps"]) != (4, 16, 500, 564):
        raise ValueError("frozen budget mismatch")


def units(c):
    validate_config(c)
    return [{"stream": s, "episode": e, "seed": c["seed_start"] + s * c["episodes_per_stream"] + e,
             "schedule_oracle": "stationary" if s < 4 else "abrupt",
             "context_id_oracle": c["condition_ids"][(s % 4 + (0 if s < 4 else e // 3)) % 4]}
            for s in range(c["streams"]) for e in range(c["episodes_per_stream"])]


def summarize(rows, c):
    expected = {(u["stream"], u["episode"], m) for u in units(c) for m in METHODS}
    indexed = {}
    for row in rows:
        key = (row["stream"], row["episode"], row["method"])
        if key not in expected or key in indexed or type(row["success"]) is not bool:
            raise ValueError("invalid or duplicate outcome")
        indexed[key] = row
    if set(indexed) != expected:
        raise ValueError("incomplete stream population")
    methods = {}
    for method in METHODS:
        selected = [r for r in rows if r["method"] == method]
        methods[method] = {"episodes": len(selected), "successful": sum(r["success"] for r in selected),
            "success_rate": statistics.fmean(r["success"] for r in selected),
            "mean_probe_steps": statistics.fmean(r["probe_steps"] for r in selected),
            "mean_path_steps": statistics.fmean(r["probe_steps"] + r["steps"] for r in selected),
            "prefix_counts": {str(k): sum(r["probe_steps"] == k * 16 for r in selected) for k in range(5)},
            "stationary_successful": sum(r["success"] for r in selected if r["stream"] < 4),
            "abrupt_successful": sum(r["success"] for r in selected if r["stream"] >= 4)}
    contrasts = {}
    for method in METHODS:
        if method == "DECISION_STABILITY":
            continue
        clusters = [statistics.fmean(int(indexed[s, e, "DECISION_STABILITY"]["success"])
                                     - int(indexed[s, e, method]["success"])
                                     for e in range(c["episodes_per_stream"])) for s in range(c["streams"])]
        rng = random.Random(c["bootstrap_seed"])
        draws = sorted(statistics.fmean(rng.choices(clusters, k=len(clusters)))
                       for _ in range(c["bootstrap_samples"]))
        contrasts[method] = {"difference": statistics.fmean(clusters), "per_stream": clusters,
            "cluster_bootstrap_95": [draws[int(.025 * (len(draws) - 1))], draws[int(.975 * (len(draws) - 1))]]}
    candidate, reference = methods["DECISION_STABILITY"], methods["FIXED_64"]
    dominated = [m for m, r in methods.items() if m != "DECISION_STABILITY"
                 and r["successful"] >= candidate["successful"] and r["mean_probe_steps"] <= candidate["mean_probe_steps"]
                 and (r["successful"] > candidate["successful"] or r["mean_probe_steps"] < candidate["mean_probe_steps"])]
    saving = 1 - candidate["mean_probe_steps"] / reference["mean_probe_steps"]
    gates = {"success_tolerance": contrasts["FIXED_64"]["cluster_bootstrap_95"][0] > -.05,
             "probe_saving": saving >= .25, "not_pareto_dominated": not dominated}
    return {"methods": methods, "candidate_minus_baseline": contrasts, "probe_saving_vs_fixed64": saving,
            "dominating_baselines": dominated, "performance_gates": gates,
            "performance_gate_passed": all(gates.values()), "independent_streams": c["streams"]}


def prepare():
    check_clean()
    c = json.loads(CONFIG.read_text())
    validate_config(c)
    root = ROOT / c["output_root"]
    if list(root.glob("*/manifest.json")):
        raise FileExistsError("protocol already frozen; do not replace run")
    paths = git("ls-files", "src", "scripts").splitlines() + [CONFIG.relative_to(ROOT).as_posix(),
        PROTOCOL.relative_to(ROOT).as_posix(), c["recovery_config"], "requirements.txt"]
    commit = git("rev-parse", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {"experiment_run_id": f"evidence_refresh_{stamp}_{commit[:12]}", "source_git_commit": commit,
        "created_at_utc": stamp, "config": c, "units": units(c), "python": platform.python_version(),
        "versions": {p: importlib.metadata.version(p) for p in ("metaworld", "mujoco", "numpy")},
        "input_sha256": {p: digest(ROOT / p) for p in paths}}
    manifest["manifest_id"] = manifest_digest(manifest)
    output = root / manifest["experiment_run_id"]
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "manifest.json", manifest)
    print(output / "manifest.json")


class MixedFault:
    def __init__(self, bias, c):
        self.bias, self.config = bias, c

    def build(self):
        return BiasNoisePerturbation(self.bias, self.config["noise_std"], self.config["noise_mask"])


def run(path):
    manifest = json.loads(path.read_text())
    check_clean()
    if manifest_digest(manifest) != manifest["manifest_id"] or git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise ValueError("manifest/source mismatch")
    for p, sha in manifest["input_sha256"].items():
        if digest(ROOT / p) != sha:
            raise ValueError(f"frozen input changed: {p}")
    c = manifest["config"]
    validate_config(c)
    if manifest["units"] != units(c):
        raise ValueError("frozen stream schedule mismatch")
    output = path.parent
    status_path = output / "status.json"
    if status_path.exists():
        raise FileExistsError("one-shot execution cannot restart")
    provenance = {k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    state = {**provenance, "status": "RUNNING", "complete_episodes": 0, "physical_probe_steps": 0,
             "physical_task_steps": 0, "physical_task_rollouts": 0, "api_calls": 0, "cache_writes": 0}
    _write_json(status_path, state)
    recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / c["recovery_config"]).read_text()))
    conditions = {f.condition_id: f for f in get_conditions(0)}
    caches, sequence, outcomes = {}, 0, []
    try:
        for unit in manifest["units"]:
            stream, episode, seed = unit["stream"], unit["episode"], unit["seed"]
            if episode == 0:
                caches = {m: None for m in METHODS}
            fault = MixedFault(conditions[unit["context_id_oracle"]].parameters["bias"], c)
            env = create_push_environment(seed)
            try:
                observation, _ = env.reset(seed=seed)
            finally:
                env.close()
            initial_hash = hashlib.sha256(json.dumps(observation.tolist(), separators=(",", ":")).encode()).hexdigest()
            grip, obj, goal = extract_push_positions(observation)
            measurements, raw = [], []
            for repeat in range(4):
                probe_seed = int(np.random.SeedSequence([seed, 0xE21, repeat]).generate_state(1)[0])
                probe_env = create_push_environment(seed)
                try:
                    group = run_symmetric_probes(lambda: create_push_environment(seed), seed=seed,
                        perturbation_factory=fault.build, magnitude=.2, steps=4,
                        perturbation_seed=probe_seed, shared_env=probe_env)
                finally:
                    probe_env.close()
                if sum(r.steps for r in group) != 16 or any(not np.allclose(r.start_gripper_position, grip, rtol=0, atol=1e-12) for r in group):
                    raise ValueError("probe budget/reset mismatch")
                inference = estimate_planar_bias(group).to_dict()
                measurement = Measurement.from_mapping({k: inference[k] for k in
                    ("estimated_drift_per_step", "axis_response_gain", "residual")})
                measurements.append(measurement)
                raw.append({"repeat": repeat, "transitions": [r.to_dict() for r in group], "inference": inference})
                state["physical_probe_steps"] += 16
            sequence += 1
            append(output / "evaluator_probes.jsonl", {**provenance, **unit, "sequence": sequence,
                "repetitions": raw, "initial_state_hash": initial_hash, "evaluator_only_suffix": True})
            selected, decision_sequences = {}, {}
            for method in METHODS:
                consumed = []

                def read_next():
                    index = len(consumed)
                    if index >= 4:
                        raise ValueError("prefix exhausted")
                    consumed.append(measurements[index])
                    return measurements[index]

                sequence += 1
                d = decide(method, read_next, cache=caches[method], recovery=recovery, stream=stream,
                           episode=episode, decision_sequence=sequence)
                if len(consumed) != d.repetitions:
                    raise ValueError("charged/read prefix mismatch")
                selected[method], decision_sequences[method] = d, sequence
                append(output / "decisions.jsonl", {**provenance, "stream": stream, "episode": episode,
                    "seed": seed, "sequence": sequence, "decision": asdict(d),
                    "consumed_measurements": [asdict(x) for x in consumed],
                    "cache_before": asdict(caches[method]) if caches[method] else None})
            branches = {}
            verification_seed = int(np.random.SeedSequence([seed, 0xE22]).generate_state(1)[0])
            for method in METHODS:
                d = selected[method]
                signature = d.plan.execution_signature()
                reused = signature in branches
                if not reused:
                    result = _execute(seed=seed, fault=fault, plan=d.plan, perturbation_seed=verification_seed,
                        max_steps=500, initial_distance=float(np.linalg.norm(obj - goal)), expected_initial_hash=initial_hash)
                    state["physical_task_rollouts"] += int(result["steps"] > 0)
                    state["physical_task_steps"] += result["steps"]
                    branches[signature] = result
                result = branches[signature]
                if result["steps"] + 16 * d.repetitions > 564:
                    raise ValueError("logical path budget exceeded")
                sequence += 1
                branch_id = hashlib.sha256(json.dumps([seed, signature]).encode()).hexdigest()[:20]
                row = {**provenance, **unit, "sequence": sequence, "decision_sequence": decision_sequences[method],
                       "method": method, "probe_steps": 16 * d.repetitions, "branch_id": branch_id,
                       "reused_branch": reused, "plan_executable": d.plan.requires_fresh_verification, **result}
                outcomes.append(row)
                append(output / "outcomes.jsonl", row)
                if method in CACHED_METHODS:
                    updated = accepted_update(d, caches[method], stream=stream, episode=episode,
                                              outcome_sequence=sequence, status=result["verification_status"])
                    if updated is not caches[method]:
                        state["cache_writes"] += 1
                        append(output / "cache_writes.jsonl", {**provenance, "cache": asdict(updated),
                                                              "fresh_status": result["verification_status"]})
                    caches[method] = updated
            state["complete_episodes"] += 1
            _write_json(status_path, state)
            print(f"completed stream {stream} episode {episode}: {state['complete_episodes']}/96", flush=True)
        if state["physical_task_steps"] + state["physical_probe_steps"] > c["maximum_physical_steps"]:
            raise ValueError("physical budget exceeded")
        summary = summarize(outcomes, c)
        state["status"] = "COMPLETED_FEASIBILITY_PASS" if summary["performance_gate_passed"] else "COMPLETED_FEASIBILITY_FAILED"
        _write_json(output / "summary.json", {**state, **summary})
        _write_json(status_path, state)
        print(json.dumps({"status": state["status"], "gates": summary["performance_gates"],
                          "dominating_baselines": summary["dominating_baselines"]}))
    except BaseException as exc:
        state.update(status="INCOMPLETE", error_type=type(exc).__name__, error=str(exc))
        _write_json(status_path, state)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    prepare() if args.prepare else run(args.manifest.resolve())
