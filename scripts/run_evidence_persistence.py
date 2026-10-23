"""Freeze and run a one-shot, evaluator-only crossed-context causal experiment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_autoresearch_benchmark import get_conditions
from scripts.run_frozen_heldout_allocation import _build_probe_context
from scripts.run_probemem_additional_ablation import _execute, _plan, COMP, RETRY
from scripts.run_probemem_acr_utility_stability import _write_json
from src.autoresearch import RecoveryPolicyConfig
from src.probemem.evidence_persistence import CONDITIONS, METHODS, summarize_crossed
from src.reasoning.evidence import validate_no_oracle_evidence
from src.rollout import create_push_environment
from src.task_metrics import extract_push_positions
import numpy as np

CONFIG = ROOT / "configs/evidence_persistence/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/evidence_persistence_crossed_development_v1.md"


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(value):
    body = {k: v for k, v in value.items() if k != "manifest_id"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_clean():
    if git("diff", "--name-only") or git("diff", "--cached", "--name-only"):
        raise RuntimeError("tracked implementation must be clean and committed")
    untracked = git("ls-files", "--others", "--exclude-standard", "src", "scripts", "configs", "tests")
    if untracked:
        raise RuntimeError("untracked implementation is not allowed")


def validate_config(config):
    if (config["seed_start"], config["num_seeds"]) != (8000, 16):
        raise ValueError("frozen task population changed")
    if tuple(config["conditions"]) != CONDITIONS or tuple(config["methods"]) != METHODS:
        raise ValueError("frozen methods/contexts changed")
    if (config["probe_max_steps"], config["verification_max_steps"], config["case_max_steps"]) != (64, 500, 564):
        raise ValueError("frozen budget changed")
    if config["api_calls"] or config["memory_writes"] or not config["all_states_included"]:
        raise ValueError("evaluator-only scope changed")


def prepare():
    check_clean()
    config = json.loads(CONFIG.read_text())
    validate_config(config)
    output_root = ROOT / config["output_root"]
    if list(output_root.glob("*/manifest.json")):
        raise FileExistsError("this protocol already has a frozen run; do not replace it")
    paths = git("ls-files", "src", "scripts").splitlines()
    paths += [CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(),
              config["recovery_config"], "requirements.txt"]
    commit = git("rev-parse", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {"experiment_run_id": f"evidence_persistence_{stamp}_{commit[:12]}",
                "source_git_commit": commit, "created_at_utc": stamp, "config": config,
                "input_sha256": {p: digest(ROOT / p) for p in paths},
                "python": platform.python_version(),
                "versions": {p: importlib.metadata.version(p) for p in ("metaworld", "mujoco", "numpy")}}
    manifest["manifest_id"] = manifest_digest(manifest)
    target = output_root / manifest["experiment_run_id"]
    target.mkdir(parents=True, exist_ok=False)
    _write_json(target / "manifest.json", manifest)
    print(target / "manifest.json")


def append(path, value):
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value) + "\n")
        handle.flush()


def run(path):
    manifest = json.loads(path.read_text())
    if manifest_digest(manifest) != manifest["manifest_id"]:
        raise ValueError("manifest hash mismatch")
    check_clean()
    if git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise ValueError("source commit mismatch")
    for name, sha in manifest["input_sha256"].items():
        if digest(ROOT / name) != sha:
            raise ValueError(f"source hash mismatch: {name}")
    config = manifest["config"]
    validate_config(config)
    target = path.parent
    status_path = target / "status.json"
    if status_path.exists():
        raise FileExistsError("one-shot run cannot restart or overwrite status")
    provenance = {k: manifest[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    state = {**provenance, "status": "RUNNING", "complete_seeds": [], "physical_task_rollouts": 0,
             "physical_task_steps": 0, "probe_steps": 0, "api_calls": 0, "memory_writes": 0}
    _write_json(status_path, state)
    faults = {f.condition_id: f for f in get_conditions(0.0) if f.condition_id in CONDITIONS}
    recovery = RecoveryPolicyConfig.from_mapping(json.loads((ROOT / config["recovery_config"]).read_text()))
    seeds = list(range(config["seed_start"], config["seed_start"] + config["num_seeds"]))
    outcomes = []
    sequence = 0
    try:
        for seed in seeds:
            env = create_push_environment(seed)
            try:
                observation, _ = env.reset(seed=seed)
            finally:
                env.close()
            observation_hash = hashlib.sha256(json.dumps(observation.tolist(), separators=(",", ":")).encode()).hexdigest()
            grip, obj, goal = extract_push_positions(observation)
            initial_distance = float(np.linalg.norm(obj - goal))
            plans = {}
            decisions = {}
            for source in CONDITIONS:
                probe = _build_probe_context(fault=faults[source], seed=seed, perturbation_seed_base=seed + 100000)
                validate_no_oracle_evidence(probe)
                if probe["probe_environment_steps"] != config["probe_max_steps"]:
                    raise ValueError("registered probe length mismatch")
                # The probe API records gripper state; full task-reset hashes are checked by _execute.
                for repetition in probe["repetitions"]:
                    for transition in repetition["transitions"]:
                        if not np.allclose(transition["start_gripper_position"], grip, rtol=0, atol=1e-12):
                            raise ValueError("probe reset mismatch")
                state["probe_steps"] += probe["probe_environment_steps"]
                evidence_id = f"probe_{seed}_{CONDITIONS.index(source)}"
                plan = _plan(plan_id=evidence_id, evidence_id=evidence_id, skill=COMP,
                             passive_context={}, probe_context=probe, probe_requested=True, recovery=recovery)
                sequence += 1
                decisions[source] = sequence
                plans[source] = plan
                append(target / "decisions.jsonl", {**provenance, "sequence": sequence,
                    "seed": seed, "source_context_oracle": source, "agent_evidence": probe,
                    "plan": plan.to_dict()})
            control = _plan(plan_id=f"control_{seed}", evidence_id=f"reset_{seed}", skill=RETRY,
                            passive_context={}, probe_context=None, probe_requested=False, recovery=recovery)
            sequence += 1
            control_sequence = sequence
            append(target / "decisions.jsonl", {**provenance, "sequence": sequence, "seed": seed,
                                               "method": "UNCORRECTED", "plan": control.to_dict()})
            cache = {}
            for source in CONDITIONS:
                for target_context in CONDITIONS:
                    for method in METHODS:
                        plan = control if method == "UNCORRECTED" else plans[source]
                        key = (target_context, "control" if method == "UNCORRECTED" else source)
                        reused = key in cache
                        if not reused:
                            result = _execute(seed=seed, fault=faults[target_context], plan=plan,
                                perturbation_seed=seed + 200000, max_steps=config["verification_max_steps"],
                                initial_distance=initial_distance, expected_initial_hash=observation_hash)
                            state["physical_task_rollouts"] += int(result["steps"] > 0)
                            state["physical_task_steps"] += result["steps"]
                            cache[key] = result
                        result = cache[key]
                        probe_steps = config["probe_max_steps"] if method == "PROBE_COMPENSATION" else 0
                        if probe_steps + result["steps"] > config["case_max_steps"]:
                            raise ValueError("logical path budget exceeded")
                        sequence += 1
                        row = {**provenance, "sequence": sequence,
                            "decision_sequence": control_sequence if method == "UNCORRECTED" else decisions[source],
                            "seed": seed, "source_context_oracle": source, "target_context_oracle": target_context,
                            "method": method, "branch_id": f"{seed}_{key[0]}_{key[1]}", "reused": reused,
                            "logical_probe_steps": probe_steps, "plan_executable": plan.requires_fresh_verification,
                            **result}
                        append(target / "outcomes.jsonl", row)
                        outcomes.append(row)
            state["complete_seeds"].append(seed)
            _write_json(status_path, state)
            print(f"completed task seed {seed}: {len(state['complete_seeds'])}/{len(seeds)}", flush=True)
        summary = summarize_crossed(outcomes, seeds, samples=config["bootstrap_samples"],
                                    bootstrap_seed=config["bootstrap_seed"])
        if state["physical_task_rollouts"] > 320 or state["physical_task_steps"] + state["probe_steps"] > 164096:
            raise ValueError("physical collection budget exceeded")
        means = summary["means"]
        gate = (means["interaction"] >= config["minimum_interaction"]
                and means["aligned_benefit"] >= config["minimum_aligned_benefit"]
                and summary["interaction_cluster_bootstrap_95"][0] > 0)
        state["status"] = "COMPLETED_FEASIBILITY_PASS" if gate else "COMPLETED_FEASIBILITY_FAILED"
        _write_json(target / "summary.json", {**state, **summary,
            "nonexecuted_logical_rows": sum(not r["plan_executable"] for r in outcomes),
            "claim": "evaluator-only context-persistence feasibility, not online recovery or a novel algorithm"})
        _write_json(status_path, state)
        print(json.dumps({"status": state["status"], **means}, indent=2))
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
