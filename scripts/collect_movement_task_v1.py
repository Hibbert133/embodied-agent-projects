"""One-shot four-method continuous task collection after a private boundary change."""
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
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT/"docs/prototypes/delayed_intervention_v1"))
from boundary_host import prepare_live_session
from scripts.qualify_delayed_intervention_v1 import CollectionFailure
from scripts.qualify_delayed_intervention_v2 import observe_state
from scripts.qualify_local_reprobe_v1 import approach
from src.analysis import movement_task_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal, normalize
from src.analysis.movement_task_host_v1 import MovementHostFailure, execute_movement_task
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.stale_reprobe_context_v1 import install_context
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment, create_task_policy


def prepare():
    io.clean();config = io.read(io.CONFIG);previous, _, _, arx = io.sources(config)
    parent = ROOT/config["output_root"]
    if list(parent.glob("*/manifest.json")):raise FileExistsError("movement-task allocation already prepared")
    validation = ROOT/"outputs/movement_task/pipeline_validation_v1"
    for name in ("unittest", "compileall", "pip_check", "tracked_secret_scan", "diff_check"):
        check = io.read(validation/(name+"_receipt.json"))
        if check["returncode"] or check["output_sha256"] != io.sha(validation/(name+".txt")):
            raise ValueError("passed frozen repository check required: "+name)
        code = io.read(validation/check["code_inputs_file"])
        if io.sha(validation/check["code_inputs_file"]) != check["code_inputs_sha256"] or any(io.sha(ROOT/n) != h for n,h in code.items()):
            raise ValueError("repository checks do not match current sources")
    names = set(previous["input_sha256"]) | {config["source_manifest"], config["source_audit"], io.COMPONENT,
        io.CONFIG.relative_to(ROOT).as_posix(), io.PLANNING.relative_to(ROOT).as_posix(), io.PROTOCOL}
    names |= set(arx["inputs"]) | set(io.PLANNING_PINS)
    names |= set(io.git("ls-files", "src", "scripts", "tests", "docs/prototypes/delayed_intervention_v1").splitlines())
    names |= {p.relative_to(ROOT).as_posix() for p in validation.iterdir() if p.is_file()}
    commit = io.git("rev-parse", "HEAD")
    run_id = "movement_task_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    manifest = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config, "arx_source_receipt": arx,
        "input_sha256": {n:io.sha(ROOT/n) for n in sorted(names)},
        **{k:previous[k] for k in ("library_source_sha256", "native_library_sha256", "policy_sha256")}}
    manifest["manifest_id"] = digest(manifest);folder = parent/run_id;folder.mkdir(parents=True)
    io.write(folder/"manifest.json", manifest);print((folder/"manifest.json").relative_to(ROOT), flush=True)


def execute_one(key, planned_boundary, config, model, reference, emit, ledger, budget, saved_events, position, emit_private):
    row = {**key, "planned_boundary": planned_boundary, "fault_oracle": config["fault_oracle"],
        "scheduled_fault_oracle": io.destination(key), "fault_transition": None, "context_applied": False,
        "completed": False, "error": None, "close_error": None, "environment_closed": False,
        "ledger_before": ledger.snapshot(), "prefix": None, "approach": None, "movement": None, "movement_failure": None,
        "physical_rows": [], "state_witnesses": [], "host_attempts": 0, "host_returned": 0, "policy_queries": 0,
        "captures": 0, "restores": 0, "computation_counters_complete": False}
    env = session = None

    def event(kind, payload):
        saved = emit(kind, payload)
        if kind == "AGENT_EVENT" and payload["agent_event"] == "MOVEMENT_TASK_DECISION":
            witness = session.witness()
            emit("MOVEMENT_TASK_CHECKPOINT", {**session.branch, "at_calls": session.ctx["calls"],
                "decision_global_sequence": saved["sequence"], "ledger": session.ledger.snapshot(), **witness})
            row["state_witnesses"].append(observe_state(session, "POST_MOVEMENT", witness, position, emit_private))
        return saved

    try:
        event("FACTORY_INTENT", {"ledger": ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"):env = create_task_environment(key["task"], key["seed"])
        event("FACTORY_COMPLETE", {"ledger": ledger.snapshot()});reset_before = ledger.snapshot()
        with ledger.scope("CONTROLLED_RESET"):initial, _ = env.reset(seed=key["seed"])
        session = ProbeSession(env, create_task_policy(key["task"]), initial, key["task"], key["seed"],
                               config["fault_oracle"], event, ledger, budget)
        row["initial_witness"] = session.witness()
        row["state_witnesses"].append(observe_state(session, "INITIAL", row["initial_witness"], position, emit_private))
        row["prefix"] = prepare_live_session(session, model, reset_before)
        def lookup(sequence):return deepcopy(saved_events[sequence])
        row["approach"] = approach(session, planned_boundary, row["prefix"], lookup)
        row["boundary_witness"] = row["approach"]["boundary_witness"]
        row["state_witnesses"].append(observe_state(session, "BOUNDARY", row["boundary_witness"], position, emit_private))
        row["boundary_ready"] = row["approach"]["public"]["ready"]
        if row["boundary_ready"]:
            row["fault_transition"] = install_context(session, config["fault_oracle"], row["scheduled_fault_oracle"], planned_boundary=planned_boundary)
            row["context_applied"] = True
            row["movement"] = execute_movement_task(session, row["prefix"]["public"]["current_choice_sequence"], lookup,
                reset_before=reset_before, method=io.method(key["variant"]), reference=reference)
        else:
            row["state_witnesses"].append(observe_state(session, "POST_MOVEMENT", session.witness(), position, emit_private))
        public = None if row["movement"] is None else row["movement"]["public"]["outcome"]
        row["action"] = "NO_LIVE_BOUNDARY" if public is None else public["action"]
        row["reposition_steps"] = 0 if public is None else public["reposition_steps"]
        row["task_steps"] = 0 if public is None else public["task_steps"]
        row["success"] = session.public().success;row["total_steps"] = session.ctx["calls"]
        row["deadline_loss"] = row["total_steps"] if row["success"] else 500
        row["stopped"] = row["prefix"]["public"]["reason"] in ("INVALID_FOUR", "INVALID_EIGHT")
        row["end_witness"] = session.witness();row["final_observation"] = normalize(asdict(session.public()))
        row["state_witnesses"].append(observe_state(session, "FINAL", row["end_witness"], position, emit_private))
        if [p["label"] for p in row["state_witnesses"]] != ["INITIAL", "BOUNDARY", "POST_MOVEMENT", "FINAL"]:
            raise ValueError("four actual chronological state witnesses required")
        row["completed"] = True
    except BaseException as error:
        row["error"] = {"type": type(error).__name__, "message": str(error)}
        if isinstance(error, MovementHostFailure):row["movement_failure"] = error.record
    finally:
        row["ledger_before_close"] = ledger.snapshot()
        if env is not None:
            try:env.close();row["environment_closed"] = True
            except BaseException as error:row["close_error"] = {"type": type(error).__name__, "message": str(error)}
        row["ledger_after_close"] = ledger.snapshot()
        if session is not None:
            row.update(physical_rows=session.last_rows, host_attempts=session.attempts, host_returned=session.completed,
                policy_queries=session.policy_queries, captures=session.captures, restores=session.restores)
        events = [r for r in saved_events.values() if r["event"] == "AGENT_EVENT"]
        cold_intents = [r for r in events if r["agent_event"] == "FIT_INTENT"]
        cold_results = [r for r in events if r["agent_event"] == "FIT_RESULT"]
        move_intents = [r for r in events if r["agent_event"] == "MOVEMENT_FIT_INTENT"]
        move_results = [r for r in events if r["agent_event"] == "MOVEMENT_FIT_RESULT"]
        cold_nfev = sum(int(r["public_payload"]["fit"].get("nfev", 0)) for r in cold_results)
        move_nfev = sum(int(r["public_payload"]["estimate"]["optimizer_nfev"]) for r in move_results)
        row.update(parameter_fit_attempts=len(cold_intents)+len(move_intents), parameter_fit_results=len(cold_results)+len(move_results),
            optimizer_nfev=cold_nfev+move_nfev, movement_fit_attempts=len(move_intents), movement_fit_results=len(move_results),
            movement_optimizer_nfev=move_nfev, optimizer_nfev_complete=len(cold_intents) == len(cold_results) and len(move_intents) == len(move_results))
        row["computation_counters_complete"] = row["completed"] and row["optimizer_nfev_complete"]
    if row["error"] is not None or row["close_error"] is not None or not row["completed"] or not row["environment_closed"]:
        row["completed"] = False;raise CollectionFailure(normalize(row))
    return normalize(row)


def collect(path):
    io.clean();manifest, models, references = io.load(path)
    if io.git("rev-parse", "HEAD") != manifest["source_git_commit"]:raise ValueError("frozen source commit required")
    config = manifest["config"];folder = path.parent/"collection";folder.mkdir()
    identity = {k:manifest[k] for k in io.IDENTITY};budget = {"completed": 0, "maximum": config["maximum_environment_steps"]}
    rows = [];key = {};saved_events = {};last = {};failure = None;started = perf_counter_ns()
    status = {**identity, "status": "RUNNING", "completed_executions": 0};io.write(folder/"status.json", status)
    with gzip.open(folder/"events.jsonl.gz", "xt", encoding="utf-8") as log, gzip.open(folder/"cases.jsonl.gz", "xt", encoding="utf-8") as cases, gzip.open(folder/"state_witnesses.jsonl.gz", "xt", encoding="utf-8") as private_log:
        journal = JsonJournal(log, identity);private = JsonJournal(private_log, identity)
        def emit(event, payload):
            nonlocal last
            value = journal.emit(event, {**key, **payload});last = {k:value[k] for k in ("sequence", "saved_ns")}
            if event == "AGENT_EVENT":saved_events[value["sequence"]] = deepcopy(value)
            return value
        def emit_private(event, payload):return private.emit(event, {**key, **payload})
        ledger = LifecycleLedger(emit, config["maximum_simulation_frames"])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
                for spec in config["cases"]:
                    key = {k:spec[k] for k in ("unit", "task", "seed", "variant")};saved_events.clear()
                    reference = references[spec["task"]] if io.method(spec["variant"]) == "MOVE_ARX_KEEP" else None
                    row = execute_one({**identity, **key}, spec["planned_boundary"], config, models[spec["task"]], reference,
                        emit, ledger, budget, saved_events, lambda: deepcopy(last), emit_private)
                    cases.write(json.dumps(row, ensure_ascii=False, allow_nan=False)+"\n");cases.flush()
                    rows.append(io.compact(row));status.update(completed_executions=len(rows), controlled_steps=budget["completed"], lifecycle=ledger.snapshot())
                    io.write(folder/"status.json", status, exclusive=False)
                    print(json.dumps({"completed_executions": len(rows), "allocated_executions": config["executions"], "controlled_steps": budget["completed"]}), flush=True)
            if len(rows) != config["executions"] or private.sequence != 4*config["executions"]:raise ValueError("incomplete allocation or state witnesses")
            status.update(status="COLLECTED_FOR_INDEPENDENT_AUDIT", failure=None)
        except BaseException as error:
            failure = error;status.update(status="FAILED_PARTIAL", failure={"type": type(error).__name__, "message": str(error)})
            if isinstance(error, CollectionFailure):io.write(folder/"failed_execution.json", error.record)
    status.update(rows=rows, lifecycle=ledger.snapshot(), controlled_steps=budget["completed"], wall_ns=perf_counter_ns()-started,
        private_witness_records=private.sequence, event_count=journal.sequence, collection_closed_ns=perf_counter_ns(),
        new_api_calls=0, new_nominal_training=0, new_selector_fits=0, policy_updates=0)
    io.write(folder/"summary.json", status);io.write(folder/"status.json", {k:v for k,v in status.items() if k != "rows"}, exclusive=False)
    io.write(folder/"completion.json", {**identity, "status": status["status"], "artifact_sha256": {p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None:raise failure


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("command", choices=("prepare", "collect"))
    parser.add_argument("--manifest", type=Path);args = parser.parse_args()
    if args.command == "prepare":prepare()
    elif args.manifest is None:parser.error("--manifest required")
    else:collect(args.manifest.resolve())
