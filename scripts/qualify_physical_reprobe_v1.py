"""One-shot live measurement qualification; no warm estimator or task comparison."""
import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT / "docs/prototypes/delayed_intervention_v1"))
from boundary_host import prepare_live_session
from scripts.qualify_delayed_intervention_v1 import CollectionFailure
from scripts.qualify_delayed_intervention_v2 import observe_state
from src.analysis import physical_reprobe_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal, normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.physical_reprobe_host_v2 import execute_reprobe
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.operator_identification import encode_controller
from src.rollout.task_registry import create_task_environment, create_task_policy


def prepare():
    io.clean();config = io.read(io.CONFIG);previous, _ = io.sources(config)
    parent = ROOT / config["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("reprobe qualification already prepared")
    validation = ROOT / "outputs/physical_reprobe/qualification_validation_v1"
    for name in ("unittest", "compileall", "pip_check", "tracked_secret_scan", "diff_check"):
        check = io.read(validation / (name + "_receipt.json"))
        if check["returncode"] or check["output_sha256"] != io.sha(validation / (name + ".txt")):
            raise ValueError("passed frozen repository check required: " + name)
    names = set(previous["input_sha256"]) | {config["source_manifest"], config["source_audit"], io.COMPONENT,
        io.PROTOCOL, io.CONFIG.relative_to(ROOT).as_posix()}
    names |= {r["path"] for r in io.read(ROOT / io.COMPONENT)["files"]}
    names |= set(io.git("ls-files", "src", "scripts", "tests", "docs/prototypes/delayed_intervention_v1").splitlines())
    names |= {p.relative_to(ROOT).as_posix() for p in validation.iterdir() if p.is_file()}
    commit = io.git("rev-parse", "HEAD")
    run_id = "physical_reprobe_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + commit[:12]
    manifest = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config,
        "input_sha256": {name: io.sha(ROOT / name) for name in sorted(names)},
        **{k: previous[k] for k in ("library_source_sha256", "native_library_sha256", "policy_sha256")}}
    manifest["manifest_id"] = digest(manifest);folder = parent / run_id;folder.mkdir(parents=True)
    io.write(folder / "manifest.json", manifest);print((folder / "manifest.json").relative_to(ROOT), flush=True)


def approach(session, planned_boundary, prefix, lookup):
    before = session.ledger.snapshot();calls = session.ctx["calls"];queries = session.policy_queries
    session.branch = {"role": "PRE_REPROBE_APPROACH", "future": 0, "program": "CURRENT_TO_BOUNDARY"}
    ready = prefix["public"]["ready"]
    choice_id = prefix["public"]["current_choice_sequence"] if ready else None
    selected = lookup(session._map[choice_id])["public_payload"] if ready else None
    initial = session.witness()
    start = session.emit("PRE_REPROBE_START", {**session.branch, "planned_boundary": planned_boundary,
        "source_choice_global_sequence": None if choice_id is None else session._map[choice_id],
        "ledger": before, "at_calls": calls, **initial})
    if ready:
        while session.alive() and session.ctx["calls"] < planned_boundary:
            raw = session.policy_query(session.public().observation)
            saved = session._agent_emit("COMMAND", {"at_calls": session.ctx["calls"], "phase": "POLICY",
                "decision_sequence": choice_id, "before": asdict(session.public()), "raw_policy": raw.tolist(),
                "command": encode_controller(selected["controller"], raw).tolist()})
            session._agent_step(saved)
    ready = ready and session.alive() and session.ctx["calls"] == planned_boundary
    reason = "READY_FOR_REPROBE" if ready else ("PREFIX_NOT_READY" if not prefix["public"]["ready"] else "ENDED_BEFORE_BOUNDARY")
    result = {"planned_boundary": planned_boundary, "completed_steps": session.ctx["calls"],
        "new_steps": session.ctx["calls"]-calls, "policy_queries": session.policy_queries-queries,
        "ready": bool(ready), "reason": reason, "final_observation": asdict(session.public())}
    boundary = session.witness();after = session.ledger.snapshot()
    end = session.emit("PRE_REPROBE_COMPLETE", {**session.branch, "start_sequence": start["sequence"],
        "result": result, "ledger": after, **boundary})
    return normalize({"public": result, "start_sequence": start["sequence"], "end_sequence": end["sequence"],
        "initial_ledger": before, "boundary_ledger": after, "initial_witness": initial, "boundary_witness": boundary})


def execute_one(key, planned_boundary, config, model, emit, ledger, budget, saved_events, position, emit_private):
    row = {**key, "planned_boundary": planned_boundary, "fault_oracle": config["fault_oracle"], "completed": False,
        "error": None, "close_error": None, "environment_closed": False, "ledger_before": ledger.snapshot(),
        "prefix": None, "approach": None, "reacquisition": None, "physical_rows": [], "state_witnesses": [],
        "host_attempts": 0, "host_returned": 0, "policy_queries": 0, "captures": 0, "restores": 0,
        "computation_counters_complete": False}
    env = session = None
    try:
        emit("FACTORY_INTENT", {"ledger": ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"): env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {"ledger": ledger.snapshot()});reset_before = ledger.snapshot()
        with ledger.scope("CONTROLLED_RESET"): initial, _ = env.reset(seed=key["seed"])
        session = ProbeSession(env, create_task_policy(key["task"]), initial, key["task"], key["seed"],
                               config["fault_oracle"], emit, ledger, budget)
        row["initial_witness"] = session.witness()
        row["state_witnesses"].append(observe_state(session, "INITIAL", row["initial_witness"], position, emit_private))
        row["prefix"] = prepare_live_session(session, model, reset_before)
        def lookup(sequence): return deepcopy(saved_events[sequence])
        row["approach"] = approach(session, planned_boundary, row["prefix"], lookup)
        row["boundary_witness"] = row["approach"]["boundary_witness"]
        row["state_witnesses"].append(observe_state(session, "BOUNDARY", row["boundary_witness"], position, emit_private))
        row["boundary_ready"] = row["approach"]["public"]["ready"]
        if row["boundary_ready"]:
            row["reacquisition"] = execute_reprobe(session, row["prefix"]["public"]["current_choice_sequence"], lookup,
                                                  reset_before=reset_before)
        public = None if row["reacquisition"] is None else row["reacquisition"]["public"]
        row["collection_stop_reason"] = row["approach"]["public"]["reason"] if public is None else public["reason"]
        row["complete_window"] = public is not None and public["window"] is not None
        row["reposition_steps"] = 0 if public is None else public["reposition_steps"]
        row["probe_steps"] = 0 if public is None else public["probe_steps"]
        row["success"] = session.public().success;row["total_steps"] = session.ctx["calls"]
        row["end_witness"] = session.witness();row["final_observation"] = normalize(asdict(session.public()))
        row["state_witnesses"].append(observe_state(session, "FINAL", row["end_witness"], position, emit_private))
        row["completed"] = True
    except BaseException as error:
        row["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        row["ledger_before_close"] = ledger.snapshot()
        if env is not None:
            try: env.close();row["environment_closed"] = True
            except BaseException as error: row["close_error"] = {"type": type(error).__name__, "message": str(error)}
        row["ledger_after_close"] = ledger.snapshot()
        if session is not None:
            row.update(physical_rows=session.last_rows, host_attempts=session.attempts, host_returned=session.completed,
                policy_queries=session.policy_queries, captures=session.captures, restores=session.restores)
        events = [r for r in saved_events.values() if r["event"] == "AGENT_EVENT"]
        intents = [r for r in events if r["agent_event"] == "FIT_INTENT"]
        fits = [r for r in events if r["agent_event"] == "FIT_RESULT"]
        row.update(parameter_fit_attempts=len(intents), parameter_fit_results=len(fits),
            optimizer_nfev=sum(int(r["public_payload"]["fit"].get("nfev", 0)) for r in fits),
            optimizer_nfev_complete=len(intents) == len(fits))
        row["computation_counters_complete"] = row["completed"] and row["optimizer_nfev_complete"]
    if row["error"] is not None or row["close_error"] is not None or not row["completed"] or not row["environment_closed"]:
        row["completed"] = False;raise CollectionFailure(normalize(row))
    return normalize(row)


def collect(path):
    io.clean();manifest, models = io.load(path)
    if io.git("rev-parse", "HEAD") != manifest["source_git_commit"]: raise ValueError("frozen source commit required")
    config = manifest["config"];folder = path.parent / "collection";folder.mkdir()
    identity = {k: manifest[k] for k in io.IDENTITY}
    budget = {"completed": 0, "maximum": config["maximum_environment_steps"]}
    rows = [];key = {};saved_events = {};last = {};failure = None;started = perf_counter_ns()
    status = {**identity, "status": "RUNNING", "completed_executions": 0};io.write(folder / "status.json", status)
    with gzip.open(folder / "events.jsonl.gz", "xt", encoding="utf-8") as log, gzip.open(folder / "cases.jsonl.gz", "xt", encoding="utf-8") as cases, gzip.open(folder / "state_witnesses.jsonl.gz", "xt", encoding="utf-8") as private_log:
        journal = JsonJournal(log, identity);private = JsonJournal(private_log, identity)
        def emit(event, payload):
            nonlocal last
            value = journal.emit(event, {**key, **payload});last = {k:value[k] for k in ("sequence", "saved_ns")}
            if event == "AGENT_EVENT": saved_events[value["sequence"]] = deepcopy(value)
            return value
        def emit_private(event, payload): return private.emit(event, {**key, **payload})
        ledger = LifecycleLedger(emit, config["maximum_simulation_frames"])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
                for spec in config["cases"]:
                    key = {k: spec[k] for k in ("unit", "task", "seed", "variant")};saved_events.clear()
                    row = execute_one({**identity, **key}, spec["planned_boundary"], config, models[spec["task"]], emit,
                        ledger, budget, saved_events, lambda: deepcopy(last), emit_private)
                    cases.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n");cases.flush()
                    rows.append(io.compact(row));status.update(completed_executions=len(rows), controlled_steps=budget["completed"], lifecycle=ledger.snapshot())
                    io.write(folder / "status.json", status, exclusive=False)
                    print(json.dumps({"completed_executions":len(rows), "allocated_executions":config["executions"], "controlled_steps":budget["completed"]}), flush=True)
            if len(rows) != config["executions"] or private.sequence != 3*config["executions"]:
                raise ValueError("complete allocation and state witnesses required")
            status.update(status="COLLECTED_FOR_INDEPENDENT_AUDIT", failure=None)
        except BaseException as error:
            failure = error;status.update(status="FAILED_PARTIAL", failure={"type":type(error).__name__, "message":str(error)})
            if isinstance(error, CollectionFailure): io.write(folder / "failed_execution.json", error.record)
    status.update(rows=rows, lifecycle=ledger.snapshot(), controlled_steps=budget["completed"], wall_ns=perf_counter_ns()-started,
        private_witness_records=private.sequence, event_count=journal.sequence, collection_closed_ns=perf_counter_ns(),
        new_api_calls=0, new_nominal_training=0, new_selector_fits=0, policy_updates=0)
    io.write(folder / "summary.json", status);io.write(folder / "status.json", {k:v for k,v in status.items() if k != "rows"}, exclusive=False)
    io.write(folder / "completion.json", {**identity, "status":status["status"],
        "artifact_sha256":{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None: raise failure


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("command", choices=("prepare", "collect"))
    parser.add_argument("--manifest", type=Path);args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest is None: parser.error("--manifest required")
    else: collect(args.manifest.resolve())
