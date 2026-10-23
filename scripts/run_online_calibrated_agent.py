"""One-shot live API probe/correction comparison; no policy or memory learning."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from scripts.run_evidence_persistence import git, digest, manifest_digest, check_clean, append
from scripts.run_probemem_acr_utility_stability import _write_json
from scripts.run_calibrated_tasks import load_model, plan as baseline_plan
from scripts.run_continuous_probe import LiveHost, state_hash, normalized
from scripts.build_autoresearch_benchmark import get_conditions
from src.probe.continuous import collect_continuous, symmetric_program
from src.probe.online_calibrated_agent import OnlineClient, payload
from src.perturbations import BiasNoisePerturbation
from src.rollout import create_push_environment, create_push_policy

METHODS = ("NO_PROBE", "CONT_NO_CORRECTION", "CONT_DYNAMIC", "PRIOR_AFFINE", "PRIOR_NEAREST", "LLM_AGENT")
CONFIG = ROOT / "configs/online_calibrated_agent/development_v1.json"
PROTOCOL = ROOT / "docs/protocols/online_calibrated_agent_development_v1.md"
API_CONFIG = {"model": "glm-5.2", "temperature": 0., "max_tokens": 512, "hard_deadline_seconds": 210,
              "maximum_health_calls": 1, "maximum_decision_primary_calls": 32, "maximum_repairs": 7,
              "maximum_total_calls": 40, "maximum_repairs_per_decision": 1,
              "maximum_consecutive_failures": 2, "transport_retries": 0}
ACTION_METHOD = {"RUN_AFFINE": "PRIOR_AFFINE", "RUN_NEAREST": "PRIOR_NEAREST", "RUN_DYNAMIC": "CONT_DYNAMIC"}
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")


def validate(c):
    if (c["protocol_id"], c["seed_start"], c["num_seeds"], c["reserved_seeds"], tuple(c["methods"]),
        c["conditions"], c["noise_std"], c["noise_namespace"], c["total_steps"], c["probe_steps"],
        c["post_probe_reserve"], c["offline_steps"], c["offline_resets"], c["maximum_physical_steps"],
        c["memory_writes"], c["api"], c["gate"]) != (
            "online_calibrated_agent_development_v1", 9400, 4, [9404, 9599], METHODS,
            ["fault_01", "fault_02", "fault_03", "fault_04"], .05, 3457, 500, 16, 484, 2304, 144, 48000,
            0, API_CONFIG, {"minimum_logical_valid_rate": .9, "minimum_complete_correction_chains": 1,
                            "maximum_integrity_violations": 0}):
        raise ValueError("frozen online-calibrated protocol configuration mismatch")


def load(path):
    m = json.loads(path.read_text(encoding="utf-8"))
    validate(m["config"])
    if manifest_digest(m) != m["manifest_id"]:
        raise ValueError("manifest hash mismatch")
    for name, expected in m["input_sha256"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"frozen input changed: {name}")
    return m


def prepare():
    check_clean()
    c = json.loads(CONFIG.read_text(encoding="utf-8"))
    validate(c)
    _, model_sha = load_model(c)
    root = ROOT / c["output_root"]
    if list(root.glob("*/manifest.json")):
        raise FileExistsError("this one-shot protocol is already frozen")
    source = git("rev-parse", "HEAD")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    names = git("ls-files", "src", "scripts", "tests").splitlines() + [
        CONFIG.relative_to(ROOT).as_posix(), PROTOCOL.relative_to(ROOT).as_posix(), "requirements.txt",
        c["model_path"], c["calibration_manifest"]]
    m = {"experiment_run_id": f"online_calibrated_agent_{stamp}_{source[:12]}",
         "source_git_commit": source, "created_at_utc": stamp, "config": c,
         "model_sha256": model_sha, "input_sha256": {p: digest(ROOT / p) for p in names},
         "python": platform.python_version(),
         "versions": {p: importlib.metadata.version(p) for p in ("anthropic", "metaworld", "mujoco", "numpy")}}
    m["manifest_id"] = manifest_digest(m)
    output = root / m["experiment_run_id"]
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "manifest.json", m)
    print(output / "manifest.json")


class Journal:
    def __init__(self, output, identity):
        self.output, self.identity = output, identity
        self.seq = 0

    def event(self, kind, row):
        self.seq += 1
        event = {**self.identity, **row, "seq": self.seq, "event": kind}
        append(self.output / "events.jsonl", event)
        return self.seq


def candidate_plans(evidence, model):
    return {action: baseline_plan(method, evidence, model) for action, method in ACTION_METHOD.items()}


def execute_episode(host, method, model, client, journal, key):
    initial = host.current
    initial_rng = host.rng_hash()
    begin_seq = journal.event("EPISODE_STARTED", {**key, "initial": asdict(initial), "rng_initial": initial_rng})
    evidence = None
    pre = post = None
    probe_start_seq = probe_end_seq = None
    action = "RUN_UNCORRECTED"
    chosen = {"correction": [0., 0., 0., 0.], "fit": None}
    aborted = False
    if method == "LLM_AGENT":
        pre = client.decide(payload("PRE_PROBE", client.next_request_id, initial=initial))
        action = pre["selected_action"]
        aborted = action == "ABSTAIN"
        do_probe = action == "PROBE_16"
    else:
        do_probe = method != "NO_PROBE"
    if do_probe:
        probe_start_seq = journal.event("PROBE_STARTED", {**key, "request_id": pre["request_id"] if pre else None,
                                                        "host_calls": host.calls, "rng_before": host.rng_hash()})
        evidence = collect_continuous(host.step, initial, symmetric_program(), remaining_budget=500, task_reserve=484)
        probe_end_seq = journal.event("PROBE_COMPLETED", {**key, "evidence": evidence.to_dict(),
                                                        "host_calls": host.calls, "rng_after": host.rng_hash()})
        if method == "LLM_AGENT" and evidence.stop_reason == "PROGRAM_COMPLETE":
            plans = candidate_plans(evidence, model)
            post = client.decide(payload("POST_PROBE", client.next_request_id, initial=initial,
                                        evidence=evidence, plans=plans, remaining_steps=500-evidence.steps))
            action = post["selected_action"]
            aborted = action == "ABSTAIN"
            if action in ACTION_METHOD:
                chosen = plans[action]
            elif action != "RUN_UNCORRECTED":
                chosen = None
        elif method == "LLM_AGENT":
            action = "TERMINAL_PROBE"
    if method != "LLM_AGENT":
        chosen = baseline_plan(method, evidence, model)
        action = method
    if aborted:
        chosen = None
    handoff = host.current
    n_probe = evidence.steps if evidence else 0
    execution = {"selected_action": action, "plan": chosen, "aborted": aborted,
                 "pre_request_id": pre["request_id"] if pre else None,
                 "post_request_id": post["request_id"] if post else None}
    execution_seq = journal.event("EXECUTION_SELECTED", {**key, "execution": normalized(execution),
                                                       "host_calls": host.calls, "handoff": asdict(handoff),
                                                       "rng_handoff": host.rng_hash()})
    declaration = {**key, "execution_seq": execution_seq, "execution": normalized(execution)}
    append(journal.output / "decisions.jsonl", declaration)
    trace = []
    task_start_seq = None
    if not aborted and not (handoff.success or handoff.terminated or handoff.truncated):
        task_start_seq = journal.event("TASK_STARTED", {**key, "execution_seq": execution_seq,
                                                       "host_calls": host.calls, "rng_before": host.rng_hash()})
        policy = create_push_policy()
        while not (host.current.success or host.current.terminated or host.current.truncated) and n_probe+len(trace) < 500:
            before = host.current
            before_rng = host.rng_hash()
            base_command = np.asarray(policy.get_action(np.array(before.observation)), dtype=np.float32)
            command = base_command + np.array(chosen["correction"], dtype=np.float64)
            after = host.step(command)
            trace.append({"before": asdict(before), "after": asdict(after), "rng_before": before_rng,
                          "rng_after": host.rng_hash(), "host_calls": host.calls,
                          "base_command": base_command.tolist(), "command": command.tolist()})
    task_end_seq = journal.event("TASK_COMPLETED", {**key, "task_steps": len(trace),
                                                  "host_calls": host.calls, "final": asdict(host.current)})
    outcome = {**key, "success": host.current.success, "aborted": aborted,
               "probe_steps": n_probe, "task_steps": len(trace), "total_steps": n_probe+len(trace),
               "environment_resets": host.resets, "actuator_resets": 1, "host_calls": host.calls,
               "initial_hash": state_hash(initial.observation), "handoff_hash": state_hash(handoff.observation),
               "final_hash": state_hash(host.current.observation)}
    end_seq = journal.event("EPISODE_COMPLETED", {**key, "outcome": outcome})
    return {**key, "initial": asdict(initial), "rng_initial": initial_rng,
            "probe": evidence.to_dict() if evidence else None, "handoff": asdict(handoff),
            "rng_handoff": (trace[0]["rng_before"] if trace else host.rng_hash()),
            "pre_decision": pre, "post_decision": post, "execution": normalized(execution),
            "task_trace": trace, "outcome": outcome,
            "sequences": {"begin": begin_seq, "probe_start": probe_start_seq, "probe_end": probe_end_seq,
                          "execution": execution_seq, "task_start": task_start_seq, "task_end": task_end_seq, "end": end_seq}}


def summarize(records, client, c):
    expected = [(s, k, m) for s in range(9400, 9404) for k in c["conditions"] for m in METHODS]
    if [(r["seed"], r["condition_oracle"], r["method"]) for r in records] != expected:
        raise ValueError("incomplete or duplicate 96-episode population")
    metrics = {}
    for method in METHODS:
        rs = [r["outcome"] for r in records if r["method"] == method]
        charged = method in ("PRIOR_AFFINE", "PRIOR_NEAREST", "LLM_AGENT")
        mean = statistics.fmean(r["total_steps"] for r in rs)
        metrics[method] = {"successful": sum(r["success"] for r in rs), "units": 16,
                           "abstained": sum(r["aborted"] for r in rs), "mean_online_steps": mean,
                           "probe_steps": sum(r["probe_steps"] for r in rs),
                           "offline_steps": 2304 if charged else 0, "offline_resets": 144 if charged else 0,
                           "mean_amortized_steps": mean+(144 if charged else 0),
                           "mean_amortized_resets": 10. if charged else 1.}
    logical = [d for d in client.decisions if d["stage"] != "HEALTH"]
    llm = [r for r in records if r["method"] == "LLM_AGENT"]
    chains = sum(r["pre_decision"]["valid"] and r["pre_decision"]["selected_action"] == "PROBE_16" and
                 r["post_decision"] is not None and r["post_decision"]["valid"] and
                 r["execution"]["selected_action"] in ACTION_METHOD and
                 any(r["execution"]["plan"]["correction"]) and r["outcome"]["task_steps"] > 0 for r in llm)
    valid_rate = sum(d["valid"] for d in logical)/len(logical)
    per_seed = {base: [sum(int(next(r["outcome"]["success"] for r in records if r["seed"] == seed and r["condition_oracle"] == k and r["method"] == "LLM_AGENT")) -
                               int(next(r["outcome"]["success"] for r in records if r["seed"] == seed and r["condition_oracle"] == k and r["method"] == base))
                           for k in c["conditions"])/4 for seed in range(9400, 9404)] for base in METHODS[:-1]}
    gates = {"logical_valid_rate": valid_rate >= .9, "complete_correction_chain": chains >= 1,
             "call_budget": len(client.attempts) <= 40, "integrity": True}
    return {"methods": metrics, "logical_decisions": len(logical), "valid_logical_decisions": sum(d["valid"] for d in logical),
            "logical_valid_rate": valid_rate, "complete_correction_chains": chains,
            "pre_probe_valid": sum(d["valid"] for d in logical if d["stage"] == "PRE_PROBE"),
            "post_probe_valid": sum(d["valid"] for d in logical if d["stage"] == "POST_PROBE"),
            "llm_minus_baseline_per_seed": per_seed, "independent_seed_clusters": 4,
            "gates": gates, "gate_passed": all(gates.values()), "integrity_violations": 0}


def api_metrics(client):
    rows = client.attempts
    latencies = sorted(r["latency_ms"]/1000. for r in rows)
    return {"attempts": len(rows), "health_primary": client.health_calls, "decision_primary": client.primary_calls,
            "repairs": client.repairs, "timeouts": sum(r["status"] == "TIMEOUT" for r in rows),
            "transport_errors": sum(r["status"] == "TRANSPORT_ERROR" for r in rows),
            "invalid_responses": sum(r["status"] == "INVALID_RESPONSE" for r in rows),
            "input_tokens_known": sum(r["usage"].get("input_tokens", 0) for r in rows),
            "output_tokens_known": sum(r["usage"].get("output_tokens", 0) for r in rows),
            "unknown_usage_attempts": sum(not {"input_tokens", "output_tokens"} <= set(r["usage"]) for r in rows),
            "latency_p50_seconds": statistics.median(latencies) if latencies else None,
            "latency_p90_seconds": float(np.quantile(latencies, .9)) if latencies else None,
            "latency_max_seconds": max(latencies) if latencies else None,
            "intentional_abstentions": sum(d["valid"] and d["selected_action"] == "ABSTAIN" and d["stage"] != "HEALTH" for d in client.decisions),
            "circuit_open_decisions": sum(d["failure"] == "CIRCUIT_OPEN" for d in client.decisions)}


def run(path, *, client_factory=OnlineClient):
    check_clean()
    m = load(path)
    c = m["config"]
    if git("rev-parse", "HEAD") != m["source_git_commit"]:
        raise ValueError("source commit changed before one-shot execution")
    model, model_sha = load_model(c)
    if model_sha != m["model_sha256"]:
        raise ValueError("qualified calibration model changed")
    output = path.parent
    if (output / "status.json").exists():
        raise FileExistsError("one-shot API experiment cannot be restarted")
    identity = {k: m[k] for k in IDENTITY}
    journal = Journal(output, identity)
    status = {**identity, "status": "PREFLIGHT_RUNNING", "complete_units": 0, "episodes": 0,
              "physical_steps": 0, "environment_resets": 0, "api_attempts": 0, "memory_writes": 0}
    _write_json(output / "status.json", status)
    _write_json(output / "runtime_api.json", {**identity, "model": c["api"]["model"],
                "endpoint_sha256": hashlib.sha256(__import__("os").environ.get("ANTHROPIC_BASE_URL", "").encode()).hexdigest()})
    context = dict(identity)
    def emit(kind, row):
        journal.event(kind, {**context, "api": row})
        if kind == "API_REQUEST_STARTED":
            print(f"API start {row['stage']} {row['request_id']} attempt {row['attempt']}", flush=True)
        elif kind == "API_ATTEMPT_COMPLETED":
            status["api_attempts"] = len(client.attempts)
            _write_json(output / "status.json", status)
            print(f"API end {row['status']} {row['latency_ms']/1000.:.1f}s", flush=True)
    client = client_factory(c["api"], emit=emit)
    records = []
    def save():
        _write_json(output / "api_audit.json", {**identity, "metrics": api_metrics(client),
                                              "attempts": client.attempts, "decisions": client.decisions})
        _write_json(output / "status.json", status)
    try:
        health = client.decide(payload("HEALTH", client.next_request_id))
        if not health["valid"]:
            status["status"] = "FAILED_API_PREFLIGHT"
            save()
            _write_json(output / "summary.json", {**status, "statistics": None, "api": api_metrics(client)})
            print("FAILED_API_PREFLIGHT: zero simulator episodes; preserving failure without retry.", flush=True)
            return
        status["status"] = "RUNNING"
        save()
        conditions = {x.condition_id: x for x in get_conditions(0)}
        with gzip.open(output / "episodes.jsonl.gz", "wt", encoding="utf-8") as handle:
            for seed in range(9400, 9404):
                for index, condition in enumerate(c["conditions"]):
                    initial_hashes, probe_transcripts = set(), set()
                    for method in METHODS:
                        key = {**identity, "episode_index": len(records)+1, "seed": seed,
                               "condition_oracle": condition, "method": method, "model_sha256": model_sha}
                        context.clear()
                        context.update(key)
                        noise_seed = int(np.random.SeedSequence([seed, index, c["noise_namespace"]]).generate_state(1)[0])
                        env = create_push_environment(seed)
                        try:
                            host = LiveHost(env, BiasNoisePerturbation(conditions[condition].parameters["bias"], .05), seed, noise_seed)
                            record = execute_episode(host, method, model, client, journal, key)
                            initial_hashes.add(record["outcome"]["initial_hash"])
                            if record["probe"]:
                                probe_transcripts.add(json.dumps(record["probe"], sort_keys=True))
                            handle.write(json.dumps(record)+"\n")
                            handle.flush()
                            records.append(record)
                            status["episodes"] += 1
                            status["physical_steps"] += record["outcome"]["total_steps"]
                            status["environment_resets"] += record["outcome"]["environment_resets"]
                            save()
                        finally:
                            env.close()
                    if len(initial_hashes) != 1 or len(probe_transcripts) != 1:
                        raise ValueError("matched initial/probe trajectories differ")
                    status["complete_units"] += 1
                    save()
                    last = records[-1]
                    print(f"Completed {seed}/{condition}: {status['complete_units']}/16; LLM={last['execution']['selected_action']} success={last['outcome']['success']}", flush=True)
        if status["physical_steps"] > 48000:
            raise ValueError("physical collection budget exceeded")
        stats = summarize(records, client, c)
        status["status"] = "COMPLETED_INTERFACE_PASS" if stats["gate_passed"] else "COMPLETED_INTERFACE_FAILED"
        save()
        _write_json(output / "summary.json", {**status, "statistics": stats, "api": api_metrics(client)})
        print(json.dumps({"status": status["status"], "api_attempts": len(client.attempts), "gates": stats["gates"]}), flush=True)
    except BaseException as exc:
        status.update(status="INCOMPLETE", error_type=type(exc).__name__, error=str(exc)[:1000])
        save()
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    prepare() if args.prepare else run(args.manifest.resolve())
