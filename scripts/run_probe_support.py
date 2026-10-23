"""Freeze, collect once, and audit the evaluator-only probe-support witness."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git, digest, manifest_digest, check_clean, append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_probemem_additional_ablation import _execute
from src.probemem.probe_support import CONTEXTS, CORRECTIONS, ProbeNullPerturbation, candidate_plan, summarize_support
from src.probe.directional import run_symmetric_probes, PROBE_DIRECTIONS
from src.rollout import create_push_environment
from src.task_metrics import extract_push_positions

CONFIG = ROOT / "configs/probe_support/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/probe_support_identifiability_development_v1.md"


def validate(c):
    if (c["seed_start"], c["num_seeds"], c["contexts"], c["corrections"], c["probe_amplitudes"],
        c["probe_steps_per_direction"], c["verification_steps"], c["maximum_physical_steps"],
        c["noise_std"], c["api_calls"], c["memory_writes"]) != (
        8500, 16, CONTEXTS, CORRECTIONS, [.2, .8], 4, 500, 73536, 0., 0, 0):
        raise ValueError("frozen configuration mismatch")


def prepare():
    check_clean()
    c = json.loads(CONFIG.read_text())
    validate(c)
    root = ROOT / c["output_root"]
    if list(root.glob("*/manifest.json")):
        raise FileExistsError("protocol already frozen")
    paths = git("ls-files", "src", "scripts").splitlines() + [CONFIG.relative_to(ROOT).as_posix(),
        PROTOCOL.relative_to(ROOT).as_posix(), "requirements.txt"]
    commit = git("rev-parse", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = {"experiment_run_id": f"probe_support_{stamp}_{commit[:12]}", "source_git_commit": commit,
        "config": c, "input_sha256": {p: digest(ROOT / p) for p in paths},
        "versions": {p: importlib.metadata.version(p) for p in ("metaworld", "mujoco", "numpy")}}
    manifest["manifest_id"] = manifest_digest(manifest)
    output = root / manifest["experiment_run_id"]
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "manifest.json", manifest)
    print(output / "manifest.json")


def load_manifest(path):
    m = json.loads(path.read_text())
    validate(m["config"])
    if manifest_digest(m) != m["manifest_id"]:
        raise ValueError("manifest hash mismatch")
    for p, sha in m["input_sha256"].items():
        if digest(ROOT / p) != sha:
            raise ValueError(f"changed frozen input: {p}")
    return m


def run(path):
    check_clean()
    m = load_manifest(path)
    if git("rev-parse", "HEAD") != m["source_git_commit"]:
        raise ValueError("source commit mismatch")
    c, output = m["config"], path.parent
    identity = {k: m[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    if (output / "status.json").exists():
        raise FileExistsError("one-shot collection cannot restart")
    status = {**identity, "status": "RUNNING", "complete_seeds": 0, "probe_steps": 0,
              "task_steps": 0, "task_rollouts": 0, "api_calls": 0, "memory_writes": 0}
    _write_json(output / "status.json", status)
    plans = {name: candidate_plan(name) for name in CORRECTIONS}
    _write_json(output / "plans.json", {**identity, "plans": {name: asdict(p) for name, p in plans.items()}})
    probes, outcomes, sequence = [], [], 0
    seeds = list(range(c["seed_start"], c["seed_start"] + c["num_seeds"]))
    try:
        for seed in seeds:
            env = create_push_environment(seed)
            try:
                observation, _ = env.reset(seed=seed)
            finally:
                env.close()
            initial_hash = hashlib.sha256(json.dumps(observation.tolist(), separators=(",", ":")).encode()).hexdigest()
            grip, obj, goal = extract_push_positions(observation)
            for context, coefficient in CONTEXTS.items():
                for amplitude in c["probe_amplitudes"]:
                    env = create_push_environment(seed)
                    try:
                        group = run_symmetric_probes(lambda: create_push_environment(seed), seed=seed,
                            perturbation_factory=ProbeNullPerturbation(coefficient).build,
                            magnitude=amplitude, steps=4, shared_env=env)
                    finally:
                        env.close()
                    if len(group) != 4 or sum(r.steps for r in group) != 16 or any(
                            not np.allclose(r.start_gripper_position, grip, rtol=0, atol=1e-12) for r in group):
                        raise ValueError("probe budget/reset mismatch")
                    sequence += 1
                    row = {**identity, "sequence": sequence, "seed": seed, "context_oracle": context,
                        "amplitude": amplitude, "initial_state_hash": initial_hash,
                        "transitions": [r.to_dict() for r in group]}
                    append(output / "probes.jsonl", row)
                    probes.append(row)
                    status["probe_steps"] += 16
            for context, coefficient in CONTEXTS.items():
                for name, plan in plans.items():
                    result = _execute(seed=seed, fault=ProbeNullPerturbation(coefficient), plan=plan,
                        perturbation_seed=seed, max_steps=500, initial_distance=float(np.linalg.norm(obj-goal)),
                        expected_initial_hash=initial_hash)
                    sequence += 1
                    row = {**identity, "sequence": sequence, "seed": seed, "context_oracle": context,
                           "candidate": name, **result}
                    append(output / "outcomes.jsonl", row)
                    outcomes.append(row)
                    status["task_steps"] += result["steps"]
                    status["task_rollouts"] += 1
            status["complete_seeds"] += 1
            _write_json(output / "status.json", status)
            print(f"Completed seed {seed}: {status['complete_seeds']}/16", flush=True)
        if status["probe_steps"] + status["task_steps"] > c["maximum_physical_steps"]:
            raise ValueError("physical budget exceeded")
        summary = summarize_support(probes, outcomes, seeds)
        status["status"] = "COMPLETED_WITNESS_PASS" if summary["gate_passed"] else "COMPLETED_WITNESS_FAILED"
        _write_json(output / "summary.json", {**status, "statistics": summary})
        _write_json(output / "status.json", status)
        print(json.dumps({"status": status["status"], "gates": summary["gates"]}))
    except BaseException as exc:
        status.update(status="INCOMPLETE", error_type=type(exc).__name__, error=str(exc))
        _write_json(output / "status.json", status)
        raise


def audit(path):
    m = load_manifest(path)
    output = path.parent
    identity = {k: m[k] for k in ("experiment_run_id", "manifest_id", "source_git_commit")}
    status = json.loads((output / "status.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    plans = json.loads((output / "plans.json").read_text())
    expected_plans = json.loads(json.dumps({**identity, "plans": {n: asdict(candidate_plan(n)) for n in CORRECTIONS}}))
    if plans != expected_plans:
        raise ValueError("predeclared plans changed")
    probes, outcomes = [[json.loads(x) for x in (output / name).read_text().splitlines()]
                        for name in ("probes.jsonl", "outcomes.jsonl")]
    events = probes + outcomes
    if any(any(r[k] != v for k, v in identity.items()) for r in events + [status, summary]):
        raise ValueError("provenance mismatch")
    if sorted(r["sequence"] for r in events) != list(range(1, len(events) + 1)):
        raise ValueError("event sequence mismatch")
    seeds = list(range(8500, 8516))
    rebuilt = summarize_support(probes, outcomes, seeds)
    if rebuilt != summary["statistics"]:
        raise ValueError("statistics fail reproduction")
    previous = 0
    for seed in seeds:
        ps, ys = [r for r in probes if r["seed"] == seed], [r for r in outcomes if r["seed"] == seed]
        if not previous < min(r["sequence"] for r in ps) <= max(r["sequence"] for r in ps) < min(r["sequence"] for r in ys):
            raise ValueError("chronology mismatch")
        previous = max(r["sequence"] for r in ys)
        if len({r["initial_state_hash"] for r in ps+ys}) != 1:
            raise ValueError("initial state mismatch")
        starts = set()
        for p in ps:
            if len(p["transitions"]) != 4:
                raise ValueError("probe count mismatch")
            for t, (name, vector) in zip(p["transitions"], PROBE_DIRECTIONS):
                if t["direction"] != name or t["steps"] != 4 or t["seed"] != seed or not np.array_equal(
                        t["commanded_action"], vector * np.float32(p["amplitude"])):
                    raise ValueError("probe protocol mismatch")
                starts.add(tuple(t["start_gripper_position"]))
                if not np.allclose(np.array(t["end_gripper_position"])-t["start_gripper_position"],
                                   t["gripper_displacement"], rtol=0, atol=1e-12):
                    raise ValueError("probe displacement mismatch")
        if len(starts) != 1:
            raise ValueError("probe reset mismatch")
        for y in ys:
            if type(y["steps"]) is not int or not 1 <= y["steps"] <= 500 or y["success"] != (y["verification_status"] == "ACCEPTED"):
                raise ValueError("task budget/status mismatch")
    expected_status = "COMPLETED_WITNESS_PASS" if rebuilt["gate_passed"] else "COMPLETED_WITNESS_FAILED"
    if any(status.get(k) != v or summary.get(k) != v for k, v in {
            "status": expected_status, "complete_seeds": 16, "probe_steps": 1536,
            "task_steps": sum(r["steps"] for r in outcomes), "task_rollouts": 144,
            "api_calls": 0, "memory_writes": 0}.items()):
        raise ValueError("physical accounting/completion mismatch")
    if status["probe_steps"] + status["task_steps"] > 73536:
        raise ValueError("total budget exceeded")
    return {**identity, "status": expected_status, "integrity": "PASSED", "statistics": rebuilt,
            "physical_steps": status["probe_steps"] + status["task_steps"],
            "artifact_sha256": {p.name: digest(p) for p in output.iterdir() if p.is_file()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--prepare", action="store_true")
    group.add_argument("--manifest", type=Path)
    group.add_argument("--audit", type=Path)
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()
    if args.prepare:
        prepare()
    elif args.manifest:
        run(args.manifest.resolve())
    else:
        result = audit(args.audit.resolve())
        if args.audit_output is None or args.audit_output.exists() or args.audit.resolve().parent in args.audit_output.resolve().parents:
            raise ValueError("provide a new audit file outside immutable collection")
        args.audit_output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(args.audit_output, result)
        print(json.dumps({"status": result["status"], "integrity": result["integrity"],
                          "gates": result["statistics"]["gates"], "witnesses": result["statistics"]["witness_count"]}))
