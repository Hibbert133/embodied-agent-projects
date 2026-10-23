"""Frozen physical comparison of supported passive and declared-query references."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import run_chronological_cache_reference as original
from src.rollout.chronological_cache_execution import execute as legacy_execute
from src.rollout.strong_reference_execution_v1 import execute as new_execute, NEW_METHODS
from src.probe.history_query_reference_v1 import OwnedQueryHistoryV1
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.analysis.strong_chronological_reference_v1 import METHODS, population, compact_case, statistics

CONFIG = ROOT/"configs/strong_chronological_reference/development_v1.json"
PROTOCOL = "docs/protocols/strong_chronological_reference_development_v1.md"
IDENTITY = original.IDENTITY
normal, read, git, clean = original.prior.normal, original.read, original.git, original.clean


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""): h.update(block)
    return h.hexdigest()


def write(path, value, *, exclusive=False):
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(normal(value), ensure_ascii=False, indent=2, allow_nan=False)+"\n")


def validate(config):
    if (config["protocol_id"] != "strong_chronological_reference_development_v1" or tuple(config["methods"]) != METHODS or
        tuple(config["tasks"]) != ("push-v3", "reach-v3", "door-open-v3") or config["history_ivr_threshold"] != .25 or
        config["noise_std"] != .05 or config["noise_namespace"] != 47001 or config["total_steps"] != 500 or
        config["query_history_cap_per_task"] != 64 or config["bootstrap_samples"] != 10000 or config["bootstrap_seed"] != 20261020):
        raise ValueError("frozen reference scope changed")
    if any(config[k] != 0 for k in ("api_calls", "policy_weight_updates", "nominal_model_fits", "selector_fits")):
        raise ValueError("unauthorized API, training or new selector")
    for phase in ("SMOKE", "MAIN"):
        limits, specs = config[phase.lower()], population(phase)
        cases = [c for s in specs for c in s["cases"]]
        expected = (12, 1, 108, 18000, 18011, [18012, 18099], 4000000) if phase == "SMOKE" else (216, 18, 1944, 18100, 18315, [18316, 18799], 55000000)
        if (len(cases), len(specs), len(cases)*len(METHODS), min(c["seed"] for c in cases), max(c["seed"] for c in cases), limits["reserved"], limits["maximum_simulation_frames"]) != expected:
            raise ValueError("frozen physical population or frame budget changed")
        if (limits["units"] != len(cases) or limits["streams"] != len(specs) or limits["seed_start"] != min(c["seed"] for c in cases) or
            limits["seed_end"] != max(c["seed"] for c in cases) or limits["executions"] != len(cases)*len(METHODS) or
            limits["maximum_environment_steps"] != 500*limits["executions"] or limits["maximum_controlled_resets"] != limits["executions"]):
            raise ValueError("whole-study physical budget changed")


def sources(config):
    for key in ("source_manifest", "source_record_audit", "source_statistics_audit", "software_qualification_manifest", "software_qualification_summary", "source_costs"):
        if sha(ROOT/config[key]) != config[key+"_sha256"]: raise ValueError("bound source bytes changed: "+key)
    m, old, joint = original.load(ROOT/config["source_manifest"])
    for key in ("source_record_audit", "source_statistics_audit"):
        audit = read(ROOT/config[key])
        if audit["integrity"] != "PASSED" or audit["manifest_id"] != m["manifest_id"]: raise ValueError("complete audited source required")
    q = read(ROOT/config["software_qualification_manifest"])
    s = read(ROOT/config["software_qualification_summary"])
    if s["control_flow_integrity"] != "PASSED" or s["manifest_id"] != q["manifest_id"] or s["artifact_type"] != "SOFTWARE_TEST_FIXTURES_NOT_METAWORLD":
        raise ValueError("bound software qualification differs")
    if any(sha(ROOT/n) != h for n, h in q["input_sha256"].items()): raise ValueError("qualified passive implementation changed")
    return m, old, joint


def prepare():
    clean(); config = read(CONFIG); validate(config); base, _, _ = sources(config)
    parent = ROOT/config["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("one frozen run already prepared")
    names = git("ls-files", "src", "scripts", "tests").splitlines()+[CONFIG.relative_to(ROOT).as_posix(), PROTOCOL,
        "docs/research/strong_chronological_reference_design_v1.md", "outputs/strong_chronological_reference/.gitattributes",
        "AGENTS.md", ".gitattributes", "requirements.txt"]
    commit = git("rev-parse", "HEAD")
    run_id = "strong_chronological_reference_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    m = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config,
        "source_manifest_id": base["manifest_id"], "input_sha256": {n: sha(ROOT/n) for n in sorted(set(names))},
        "population_oracle": {p: population(p) for p in ("SMOKE", "MAIN")}, "library_source_sha256": base["library_source_sha256"],
        "policy_sha256": base["policy_sha256"], "versions": base["versions"]}
    m["manifest_id"] = digest(m)
    target = parent/run_id; target.mkdir(parents=True)
    write(target/"manifest.json", m, exclusive=True)
    print((target/"manifest.json").relative_to(ROOT), flush=True)


def load(path):
    m = read(path); validate(m["config"])
    if digest({k: v for k, v in m.items() if k != "manifest_id"}) != m["manifest_id"] or any(sha(ROOT/n) != h for n, h in m["input_sha256"].items()):
        raise ValueError("frozen implementation or manifest changed")
    base, old, joint = sources(m["config"])
    if (base["manifest_id"] != m["source_manifest_id"] or any(m["population_oracle"][p] != population(p) for p in ("SMOKE", "MAIN")) or
        any(m[k] != base[k] for k in ("library_source_sha256", "policy_sha256", "versions"))):
        raise ValueError("source, population, runtime or policy changed")
    return m, old, joint


def run(path, phase):
    clean(); m, old, joint = load(path)
    if git("rev-parse", "HEAD") != m["source_git_commit"]: raise ValueError("freeze commit differs")
    output = path.parent/phase.lower()
    if output.exists(): raise FileExistsError("one-shot physical phase cannot restart")
    if phase == "MAIN":
        a, s = read(path.parent/"smoke_audit/audit.json"), read(path.parent/"smoke_audit/statistics.json")
        if any(v["integrity"] != "PASSED" or v["manifest_id"] != m["manifest_id"] for v in (a, s)) or not a["required_integrity_coverage"]:
            raise ValueError("complete smoke record/statistics audits and integrity coverage required")
    output.mkdir(); limits = m["config"][phase.lower()]; identity = {k: m[k] for k in IDENTITY}
    sequence, active, rows, record = 0, None, [], None
    status = {**identity, "phase": phase, "status": "RUNNING", "executions": 0, "controlled_steps": 0, "controlled_resets": 0}
    write(output/"status.json", status)
    def emit(kind, payload):
        nonlocal sequence
        sequence += 1
        value = {**identity, "event": kind, "sequence": sequence, "saved_ns": perf_counter_ns(), **normal(payload)}
        active.write(json.dumps(value, separators=(",", ":"), allow_nan=False)+"\n"); active.flush()
        return value
    ledger = LifecycleLedger(emit, limits["maximum_simulation_frames"])
    import metaworld
    from metaworld.sawyer_xyz_env import SawyerXYZEnv
    from gymnasium.envs.mujoco.mujoco_env import MujocoEnv
    try:
        with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
            for stream in m["population_oracle"][phase]:
                states = {method: {"cache": None, "cusum": 0.} for method in METHODS}
                histories = {method: OwnedQueryHistoryV1(method) for method in METHODS}
                with gzip.open(output/f"events_{stream['stream']:02}.jsonl.gz", "xt", encoding="utf-8") as events, gzip.open(output/f"episodes_{stream['stream']:02}.jsonl.gz", "xt", encoding="utf-8") as episodes:
                    active = events
                    for case in stream["cases"]:
                        for method in METHODS:
                            record = None
                            key = {**identity, "phase": phase, "stream": stream["stream"], "episode": case["episode"], "task": case["task"], "seed": case["seed"], "method": method}
                            history = histories[method]; before_hash = history.sha256
                            queries = history.for_task(case["task"], case["episode"])
                            if method in NEW_METHODS:
                                record = new_execute(key, case["fault_oracle"], states[method], old[case["task"]], joint[case["task"]], queries, emit, ledger)
                            else:
                                record = legacy_execute(key, case["fault_oracle"], states[method], old[case["task"]], joint[case["task"]], emit, ledger)
                            history.append_record(record)
                            record["query_history_before_sha256"], record["query_history_after_sha256"] = before_hash, history.sha256
                            record["query_history_event"] = emit("QUERY_HISTORY_AFTER_OUTCOME", {**key,
                                "before_sha256": before_hash, "after_sha256": history.sha256})
                            episodes.write(json.dumps(normal(record), allow_nan=False)+"\n"); episodes.flush()
                            rows.append(compact_case(record, stream))
                            status["executions"] += 1; status["controlled_steps"] += record["outcome"]["total_steps"]; status["controlled_resets"] += 1
                            if status["controlled_steps"] > limits["maximum_environment_steps"] or status["controlled_resets"] > limits["maximum_controlled_resets"]:
                                raise ValueError("whole physical phase budget exceeded")
                        status["lifecycle"] = ledger.snapshot(); write(output/"status.json", status)
                        print(f"{phase} stream={stream['stream']} episode={case['episode']}: {status['executions']}/{limits['executions']}", flush=True)
        if status["executions"] != limits["executions"]: raise ValueError("incomplete frozen population")
        status.update(status="COMPLETED_REFERENCE", lifecycle=ledger.snapshot())
        write(output/"summary.json", {**status, "cases": rows, "statistics": statistics(rows, phase), "api_calls": 0, "policy_weight_updates": 0})
        write(output/"status.json", status)
        write(output/"completion.json", {**identity, "phase": phase, "status": "COMPLETED_REFERENCE",
            "artifact_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}}, exclusive=True)
    except BaseException as error:
        status.update(status="FAILED_PARTIAL", error_type=type(error).__name__, error=str(error), lifecycle=ledger.snapshot())
        if isinstance(error, original.prior.BranchFailure): write(output/"failed_branch.json", error.record, exclusive=True)
        elif record is not None: write(output/"failed_post_execution_record.json", record, exclusive=True)
        status["controlled_steps"] = ledger.snapshot()["by_phase"].get("CONTROL", {}).get("simulation_completed", 0)
        status["controlled_resets"] = ledger.snapshot()["by_phase"].get("CONTROLLED_RESET", {}).get("reset_completed", 0)
        write(output/"status.json", status); raise
    print(json.dumps({k: status[k] for k in ("phase", "status", "executions", "controlled_steps")}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=("prepare", "run")); parser.add_argument("--manifest", type=Path); parser.add_argument("--phase", choices=("SMOKE", "MAIN"))
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest is None or args.phase is None: parser.error("--manifest and --phase required")
    else: run(args.manifest.resolve(), args.phase)
