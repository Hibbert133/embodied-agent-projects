"""Fixed-size nominal collection followed by a separately frozen identification bank."""
import argparse
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import numpy as np
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT));sys.path.insert(0, str(ROOT / "docs/prototypes/delayed_intervention_v1"))
from boundary_host import prepare_live_session
from scripts.qualify_delayed_intervention_v1 import CollectionFailure
from scripts.qualify_delayed_intervention_v2 import observe_state
from src.analysis import selected_response_io_v1 as io
from src.analysis.stale_reprobe_context_v1 import install_context
from src.analysis.capsule_record_json_v2 import JsonJournal, normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.analysis.local_reprobe_host_v1 import execute_reprobe
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.probe.operator_identification import encode_controller
from src.rollout.task_registry import create_task_environment, create_task_policy


from scripts.qualify_local_reprobe_v1 import approach
from src.analysis.selected_nominal_host_v1 import execute_nominal
from src.probe.selected_nominal_acquisition_v1 import NominalProgram
from src.probe.selected_response_reference_v1 import METHODS, NominalSelectedTrajectory, fit_response


def execute_one(key, planned_boundary, config, model, emit, ledger, budget, saved_events, position, emit_private, bank_hash):
    row = {**key, "planned_boundary": planned_boundary, "fault_oracle": io.initial(key["variant"]), "completed": False,
        "error": None, "close_error": None, "environment_closed": False, "ledger_before": ledger.snapshot(),
        "prefix": None, "approach": None, "reacquisition": None, "physical_rows": [], "state_witnesses": [],
        "scheduled_fault_oracle": io.destination(key), "fault_transition": None, "context_applied": False,
        "host_attempts": 0, "host_returned": 0, "policy_queries": 0, "captures": 0, "restores": 0,
        "computation_counters_complete": False}
    assigned = io.program(key["seed"]) if key["variant"] == "TRAIN" else None
    env = session = None
    try:
        assignment = emit("COLLECTION_ASSIGNMENT", {"nominal_program": assigned, "model_bank_sha256": bank_hash})
        row["assignment_sequence"] = assignment["sequence"]
        row["model_bank_sha256"] = bank_hash
        emit("FACTORY_INTENT", {"ledger": ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"): env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {"ledger": ledger.snapshot()});reset_before = ledger.snapshot()
        with ledger.scope("CONTROLLED_RESET"): initial, _ = env.reset(seed=key["seed"])
        session = ProbeSession(env, create_task_policy(key["task"]), initial, key["task"], key["seed"],
                               io.initial(key["variant"]), emit, ledger, budget)
        row["initial_witness"] = session.witness()
        row["state_witnesses"].append(observe_state(session, "INITIAL", row["initial_witness"], position, emit_private))
        row["prefix"] = prepare_live_session(session, model, reset_before)
        def lookup(sequence): return deepcopy(saved_events[sequence])
        row["approach"] = approach(session, planned_boundary, row["prefix"], lookup)
        row["boundary_witness"] = row["approach"]["boundary_witness"]
        row["state_witnesses"].append(observe_state(session, "BOUNDARY", row["boundary_witness"], position, emit_private))
        row["boundary_ready"] = row["approach"]["public"]["ready"]
        if row["boundary_ready"]:
            if key["variant"] == "TRAIN":
                row["reacquisition"] = execute_nominal(session, row["prefix"]["public"]["current_choice_sequence"], lookup,
                    reset_before=reset_before, program=NominalProgram(assigned))
            else:
                row["fault_transition"] = install_context(session, io.initial(key["variant"]), row["scheduled_fault_oracle"], planned_boundary=planned_boundary)
                row["context_applied"] = True
                row["reacquisition"] = execute_reprobe(session, row["prefix"]["public"]["current_choice_sequence"], lookup,
                    reset_before=reset_before, method="LOCAL_PID")
        public = None if row["reacquisition"] is None else row["reacquisition"]["public"]
        row["collection_stop_reason"] = row["approach"]["public"]["reason"] if public is None else public["reason"]
        row["complete_window"] = public is not None and public["nominal_trajectory" if key["variant"] == "TRAIN" else "window"] is not None
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


def prepare():
    io.clean();config = io.read(io.CONFIG);previous,_ = io.sources(config)
    parent = ROOT/config["output_root"]
    if list(parent.glob("*/manifest.json")):raise FileExistsError("selected-response study already prepared")
    validation = ROOT/"outputs/selected_response/validation_v1"
    for name in ("unittest","compileall","pip_check","tracked_secret_scan","diff_check"):
        receipt = io.read(validation/(name+"_receipt.json"))
        if receipt["returncode"] or io.sha(validation/(name+".txt")) != receipt["output_sha256"]:
            raise ValueError("passed frozen check required: "+name)
    names = set(previous["input_sha256"]) | {config["source_manifest"],config["source_audit"],io.COMPONENT,
        io.PROTOCOL,io.CONFIG.relative_to(ROOT).as_posix()}
    names |= {r["path"] for r in io.read(ROOT/io.COMPONENT)["files"]}
    names |= set(io.git("ls-files","src","scripts","tests","docs/prototypes/delayed_intervention_v1").splitlines())
    names |= {p.relative_to(ROOT).as_posix() for p in validation.iterdir() if p.is_file()}
    commit = io.git("rev-parse","HEAD")
    run = "selected_response_"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"_"+commit[:12]
    manifest = {"experiment_run_id":run,"source_git_commit":commit,"config":config,
        "input_sha256":{name:io.sha(ROOT/name) for name in sorted(names)},
        **{k:previous[k] for k in ("library_source_sha256","native_library_sha256","policy_sha256")}}
    manifest["manifest_id"] = digest(manifest);folder = parent/run;folder.mkdir(parents=True)
    io.write(folder/"manifest.json",manifest);print((folder/"manifest.json").relative_to(ROOT),flush=True)


def collect(path, stage):
    if stage not in io.STAGES:raise ValueError("registered collection stage required")
    io.clean();manifest,models = io.load(path)
    if io.git("rev-parse","HEAD") != manifest["source_git_commit"]:raise ValueError("frozen source commit required")
    bank_hash = None;bank_closed = None;model_audit_hash = None
    if stage == "qualify":
        bank,done = io.bank(path)
        for k in io.IDENTITY:
            if bank[k] != manifest[k] or done[k] != manifest[k]:raise ValueError("frozen model bank identity differs")
        bank_hash = done["models_sha256"];bank_closed = done["model_audit_completed_ns"];model_audit_hash = done["model_audit_sha256"]
    config = manifest["config"];caps = io.limits(config,stage);folder = path.parent/stage;folder.mkdir()
    identity = {k:manifest[k] for k in io.IDENTITY}
    budget = {"completed":0,"maximum":caps["maximum_environment_steps"]}
    rows = [];key = {};saved_events = {};last = {};failure = None;started = perf_counter_ns()
    if bank_closed is not None and started <= bank_closed:raise ValueError("qualification precedes frozen models")
    status = {**identity,"stage":stage,"status":"RUNNING","completed_executions":0,
        "model_bank_sha256":bank_hash,"model_audit_sha256":model_audit_hash,"collection_started_ns":started}
    io.write(folder/"status.json",status)
    with gzip.open(folder/"events.jsonl.gz","xt",encoding="utf-8") as log, gzip.open(folder/"cases.jsonl.gz","xt",encoding="utf-8") as cases, gzip.open(folder/"state_witnesses.jsonl.gz","xt",encoding="utf-8") as private_log:
        journal = JsonJournal(log,identity);private = JsonJournal(private_log,identity)
        def emit(event,payload):
            nonlocal last
            value = journal.emit(event,{**key,**payload});last = {k:value[k] for k in ("sequence","saved_ns")}
            if event == "AGENT_EVENT":saved_events[value["sequence"]] = deepcopy(value)
            return value
        def emit_private(event,payload):return private.emit(event,{**key,**payload})
        ledger = LifecycleLedger(emit,caps["maximum_simulation_frames"])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv,MujocoEnv,metaworld):
                for spec in config[stage+"_cases"]:
                    key = {k:spec[k] for k in ("unit","task","seed","variant")};saved_events.clear()
                    row = execute_one({**identity,**key},spec["planned_boundary"],config,models[spec["task"]],emit,
                        ledger,budget,saved_events,lambda:deepcopy(last),emit_private,bank_hash)
                    cases.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+"\n");cases.flush()
                    rows.append(io.compact(row));status.update(completed_executions=len(rows),controlled_steps=budget["completed"],lifecycle=ledger.snapshot())
                    io.write(folder/"status.json",status,exclusive=False)
                    print(json.dumps({"stage":stage,"completed_executions":len(rows),"allocated_executions":caps["executions"],"controlled_steps":budget["completed"]}),flush=True)
            if len(rows) != caps["executions"] or private.sequence != 3*caps["executions"]:raise ValueError("complete allocation and state witnesses required")
            status.update(status="COLLECTED_FOR_INDEPENDENT_AUDIT",failure=None)
        except BaseException as error:
            failure = error;status.update(status="FAILED_PARTIAL",failure={"type":type(error).__name__,"message":str(error)})
            if isinstance(error,CollectionFailure):io.write(folder/"failed_execution.json",error.record)
    status.update(rows=rows,lifecycle=ledger.snapshot(),controlled_steps=budget["completed"],wall_ns=perf_counter_ns()-started,
        private_witness_records=private.sequence,event_count=journal.sequence,collection_closed_ns=perf_counter_ns(),new_api_calls=0,policy_updates=0)
    io.write(folder/"summary.json",status);io.write(folder/"status.json",{k:v for k,v in status.items() if k != "rows"},exclusive=False)
    io.write(folder/"completion.json",{**identity,"stage":stage,"status":status["status"],
        "artifact_sha256":{p.name:io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None:raise failure


def fit_models(path):
    io.clean();manifest,_ = io.load(path);folder = path.parent
    if io.git("rev-parse","HEAD") != manifest["source_git_commit"]:raise ValueError("frozen source commit required")
    if (folder/"models.json").exists() or (folder/"model_fit_started.json").exists():raise FileExistsError("model fitting already attempted")
    audited = io.read(folder/"train_audit/record_audit.json")
    if audited["integrity"] != "PASSED" or audited["stage"] != "train":raise ValueError("independently audited nominal collection required")
    for name,value in audited["collection_artifact_sha256"].items():
        if io.sha(folder/"train"/name) != value:raise ValueError("nominal collection changed")
    identity = {k:manifest[k] for k in io.IDENTITY};started = perf_counter_ns()
    for k in io.IDENTITY:
        if audited[k] != identity[k]:raise ValueError("training audit identity differs")
    io.write(folder/"model_fit_started.json",{**identity,"started_ns":started,"train_audit_sha256":io.sha(folder/"train_audit/record_audit.json")})
    samples = {task:[] for task in io.TASKS};attempts = 0
    with gzip.open(folder/"train/cases.jsonl.gz","rt",encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line);attempts += 1
            if row["complete_window"]:
                samples[row["task"]].append(NominalSelectedTrajectory.from_mapping(row["reacquisition"]["public"]["nominal_trajectory"]))
    models = {task:{} for task in io.TASKS};fits = []
    for task in io.TASKS:
        for method in METHODS:
            begin = perf_counter_ns();result = {"task":task,"method":method,"training_windows":len(samples[task]),"started_ns":begin}
            try:
                models[task][method] = fit_response(samples[task],task,method=method);result.update(valid=True,error=None)
            except (ValueError,ArithmeticError,np.linalg.LinAlgError) as error:result.update(valid=False,error={"type":type(error).__name__,"message":str(error)})
            result.update(completed_ns=perf_counter_ns());fits.append(result)
    ready = all(r["valid"] for r in fits)
    bank = {**identity,"status":"READY_FOR_INDEPENDENT_QUALIFICATION" if ready else "FAILED_TRAIN_SUPPORT",
        "training_attempts":attempts,"complete_windows":{k:len(v) for k,v in samples.items()},"models":models,"fits":fits,
        "train_audit_sha256":io.sha(folder/"train_audit/record_audit.json"),"train_collection_sha256":audited["collection_artifact_sha256"],
        "training_costs":audited["costs"],"started_ns":started,"fit_completed_ns":perf_counter_ns(),
        "physical_response_qualified":False,"task_utility_demonstrated":False}
    io.write(folder/"models.json",bank)
    io.write(folder/"models_completion.json",{**identity,"status":bank["status"],"models_sha256":io.sha(folder/"models.json"),"models_closed_ns":perf_counter_ns()})
    print(json.dumps({"status":bank["status"],"complete_windows":bank["complete_windows"]}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument("command",choices=("prepare","train","fit","qualify"));parser.add_argument("--manifest",type=Path)
    args = parser.parse_args()
    if args.command == "prepare":prepare()
    elif args.manifest is None:parser.error("--manifest required")
    elif args.command == "fit":fit_models(args.manifest.resolve())
    else:collect(args.manifest.resolve(),args.command)
