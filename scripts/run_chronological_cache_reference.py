"""Frozen smoke-then-main chronological reference collection, with owned caches."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from scripts import run_cold_start_task_bridge as prior
from src.rollout.chronological_cache_execution import execute
from src.rollout.chronological_faults import population
from src.probe.chronological_cache_reference import METHODS
from src.probe.cold_cache_prediction import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.analysis.chronological_cache_reference import statistics

CONFIG = ROOT/"configs/chronological_cache_reference/development_v1.json"
PROTOCOL = ROOT/"docs/protocols/chronological_cache_reference_development_v1.md"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")


def read(path): return json.loads(path.read_text(encoding="utf-8"))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args): return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write(path, value, *, exclusive=False):
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as handle:
        json.dump(prior.normal(value), handle, ensure_ascii=False, indent=2, allow_nan=False); handle.write("\n")


def clean():
    if git("status", "--porcelain", "--untracked-files=no"): raise ValueError("commit clean implementation first")


def sources(config):
    for key in ("source_bridge_manifest", "source_bridge_audit"):
        if sha(ROOT/config[key]) != config[key+"_sha256"]: raise ValueError("bound source bytes changed")
    m = prior.load(ROOT/config["source_bridge_manifest"])
    if read(ROOT/config["source_bridge_audit"])["integrity"] != "PASSED": raise ValueError("audited source required")
    old, _, _ = prior.load_bank(m["config"]); response, _, _ = prior.load_response(m["config"])
    return m, old, response["joint"]


def validate(config):
    if config["protocol_id"] != "chronological_cache_reference_development_v1" or tuple(config["tasks"]) != ("push-v3", "reach-v3", "door-open-v3") or config["bootstrap_samples"] != 10000 or config["bootstrap_seed"] != 20261019:
        raise ValueError("frozen scope or inference plan changed")
    if tuple(config["methods"]) != METHODS or config["noise_std"] != .05 or config["noise_namespace"] != 47001 or config["total_steps"] != 500 or config["minimum_policy_reserve"] != 32:
        raise ValueError("frozen execution rules changed")
    if config["api_calls"] != 0 or config["policy_weight_updates"] != 0 or config["nominal_model_fits"] != 0:
        raise ValueError("unauthorized additional training/API")
    for phase in ("SMOKE", "MAIN"):
        entries = population(phase); limits = config[phase.lower()]
        units = sum(len(row["cases"]) for row in entries)
        seeds = [c["seed"] for row in entries for c in row["cases"]]
        if units != limits["units"] or len(entries) != limits["streams"] or units*len(METHODS) != limits["executions"] or set(seeds) != set(range(limits["seed_start"], limits["seed_end"]+1)) or len(set(seeds)) != units:
            raise ValueError("fixed population changed")
        if limits["maximum_environment_steps"] != units*len(METHODS)*500 or limits["maximum_controlled_resets"] != units*len(METHODS):
            raise ValueError("whole study budget changed")
        expected_frames, expected_reserved = (4000000, [16006, 16999]) if phase == "SMOKE" else (140000000, [17432, 17999])
        if limits["maximum_simulation_frames"] != expected_frames or limits["reserved"] != expected_reserved:
            raise ValueError("simulation cap or reserved range changed")


def prepare():
    clean(); config = read(CONFIG); validate(config); source, _, _ = sources(config)
    parent = ROOT/config["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("one frozen run already exists")
    names = git("ls-files", "src", "scripts", "tests").splitlines()+[CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(),
        "docs/research/chronological_cache_reference_question_v1.md", "outputs/chronological_cache_reference/.gitattributes", "AGENTS.md", ".gitattributes", "requirements.txt"]
    commit = git("rev-parse", "HEAD"); run_id = "chronological_cache_reference_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    m = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config,
         "input_sha256": {n: sha(ROOT/n) for n in sorted(set(names))}, "source_bridge_manifest_id": source["manifest_id"],
         "population_oracle": {phase: population(phase) for phase in ("SMOKE", "MAIN")},
         "library_source_sha256": source["library_source_sha256"], "policy_sha256": source["policy_sha256"],
         "versions": source["versions"], "api_calls": 0}
    m["manifest_id"] = digest(m); target = parent/run_id; target.mkdir(parents=True)
    write(target/"manifest.json", m, exclusive=True); print((target/"manifest.json").relative_to(ROOT))


def load(path):
    m = read(path); validate(m["config"])
    if digest({k: v for k, v in m.items() if k != "manifest_id"}) != m["manifest_id"]: raise ValueError("manifest changed")
    if any(sha(ROOT/n) != h for n, h in m["input_sha256"].items()): raise ValueError("frozen source input changed")
    source, old, joint = sources(m["config"])
    if source["manifest_id"] != m["source_bridge_manifest_id"] or any(population(p) != m["population_oracle"][p] for p in ("SMOKE", "MAIN")):
        raise ValueError("source or population mismatch")
    if prior.prior.library_sources() != m["library_source_sha256"] or prior.policy_hashes(configured_tasks(m)) != m["policy_sha256"] or any(importlib.metadata.version(k) != v for k, v in m["versions"].items()):
        raise ValueError("runtime or policy changed")
    return m, old, joint


def configured_tasks(manifest): return tuple(manifest["config"]["tasks"])


def compact_case(record, stream):
    before, after = record["state_before"]["cache"], record["state_after"]["cache"]
    decisions = {d["sequence"]: d for d in record["decisions"]}
    stale = False
    if before is not None:
        origin = stream["cases"][before["source_episode"]]["fault_oracle"]
        current = stream["cases"][record["episode"]]["fault_oracle"]
        stale = origin != current
    return {**{k: record[k] for k in (*IDENTITY, "phase", "stream", "episode", "task", "method", "seed")},
            "family_oracle": stream["family_oracle"], "schedule_oracle": stream["schedule_oracle"], **record["outcome"],
            "cache_writes": int(after is not None and after["source_episode"] == record["episode"]),
            "cache_clears": int(before is not None and after is None),
            "reuse_cases": int(any(d["action"] == "RUN_CACHED" for d in record["decisions"])),
            "requested_refit": int(any(d["action"] in ("PROBE8", "PROBE16", "REFRESH8", "PASSIVE8") for d in record["decisions"])),
            "stale_cached_policy_steps_oracle": sum(stale and decisions[r["decision_sequence"]]["action"] in ("RUN_CACHED", "PASSIVE8") for r in record["trace"]),
            "same_mapping_refresh_cases_oracle": int(before is not None and not stale and any(d["action"] == "REFRESH8" for d in record["decisions"]))}


def run(path, phase):
    clean(); m, old, joint = load(path)
    if git("rev-parse", "HEAD") != m["source_git_commit"]: raise ValueError("frozen commit differs")
    output = path.parent/phase.lower()
    if output.exists(): raise FileExistsError("one-shot phase cannot restart")
    if phase == "MAIN":
        audit = read(path.parent/"smoke_audit/audit.json")
        if audit["integrity"] != "PASSED" or audit["manifest_id"] != m["manifest_id"] or not audit["required_chain_coverage"]:
            raise ValueError("complete smoke audit required before main")
        numeric = read(path.parent/"smoke_audit/statistics.json")
        if numeric["integrity"] != "PASSED" or numeric["manifest_id"] != m["manifest_id"]:
            raise ValueError("independent smoke statistics required before main")
    output.mkdir(); limits = m["config"][phase.lower()]; identity = {k: m[k] for k in IDENTITY}
    sequence = 0; active = None; rows = []; status = {**identity, "phase": phase, "status": "RUNNING", "executions": 0, "controlled_steps": 0, "controlled_resets": 0}
    write(output/"status.json", status)
    def emit(kind, payload):
        nonlocal sequence
        sequence += 1; value = {**identity, "event": kind, "sequence": sequence, "saved_ns": perf_counter_ns(), **prior.normal(payload)}
        active.write(json.dumps(value, separators=(",", ":"), allow_nan=False)+"\n"); active.flush(); return value
    ledger = LifecycleLedger(emit, limits["maximum_simulation_frames"])
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
    try:
        with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
            for stream in m["population_oracle"][phase]:
                states = {method: {"cache": None, "cusum": 0.} for method in METHODS}
                with gzip.open(output/f"events_{stream['stream']:02}.jsonl.gz", "xt", encoding="utf-8") as events, gzip.open(output/f"episodes_{stream['stream']:02}.jsonl.gz", "xt", encoding="utf-8") as episodes:
                    active = events
                    for case in stream["cases"]:
                        for method in METHODS:
                            key = {**identity, "phase": phase, "stream": stream["stream"], "episode": case["episode"], "task": case["task"], "seed": case["seed"], "method": method}
                            record = execute(key, case["fault_oracle"], states[method], old[case["task"]], joint[case["task"]], emit, ledger)
                            episodes.write(json.dumps(prior.normal(record), allow_nan=False)+"\n"); episodes.flush()
                            rows.append(compact_case(record, stream)); status["executions"] += 1
                            status["controlled_steps"] += record["outcome"]["total_steps"]; status["controlled_resets"] += 1
                            if status["controlled_steps"] > limits["maximum_environment_steps"] or status["controlled_resets"] > limits["maximum_controlled_resets"]:
                                raise ValueError("whole-phase budget exceeded")
                        status["lifecycle"] = ledger.snapshot(); write(output/"status.json", status)
                        print(f"{phase} stream={stream['stream']} episode={case['episode']}: {status['executions']}/{limits['executions']}", flush=True)
        if status["executions"] != limits["executions"]: raise ValueError("incomplete frozen population")
        status.update(status="COMPLETED_REFERENCE", lifecycle=ledger.snapshot())
        write(output/"summary.json", {**status, "statistics": statistics(rows, phase), "cases": rows, "api_calls": 0, "policy_weight_updates": 0})
        write(output/"status.json", status)
        write(output/"completion.json", {**identity, "phase": phase, "status": "COMPLETED_REFERENCE",
              "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}}, exclusive=True)
    except BaseException as error:
        status.update(status="FAILED_PARTIAL", error_type=type(error).__name__, error=str(error), lifecycle=ledger.snapshot())
        if isinstance(error, prior.BranchFailure): write(output/"failed_branch.json", error.record, exclusive=True)
        status["controlled_steps"] = ledger.snapshot()["by_phase"].get("CONTROL", {}).get("simulation_completed", 0)
        status["controlled_resets"] = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        write(output/"status.json", status); raise
    print(json.dumps({"status": status["status"], "executions": status["executions"], "controlled_steps": status["controlled_steps"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "run")); parser.add_argument("--manifest", type=Path); parser.add_argument("--phase", choices=("SMOKE", "MAIN"))
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest is None or args.phase is None: parser.error("--manifest and --phase required")
    else: run(args.manifest.resolve(), args.phase)
