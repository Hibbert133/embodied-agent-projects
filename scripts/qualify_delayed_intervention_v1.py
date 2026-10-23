"""One-shot real-task qualification of a saved mid-trajectory intervention.

Preparation is blocked until the separate auditor and qualification tests exist
and all implementation sources have been committed. No API is called.
"""

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
sys.path.insert(0, str(ROOT))
PROTOTYPE = ROOT / "docs/prototypes/delayed_intervention_v1"
sys.path.insert(0, str(PROTOTYPE))
from boundary_host import prepare_live_session, direct_continue
from session_adapter import execute_live_session
from src.analysis import delayed_qualification_io_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal, normalize
from src.analysis.paired_probe_host_v1 import ProbeSession
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from src.rollout.task_registry import create_task_environment, create_task_policy


class CollectionFailure(RuntimeError):
    def __init__(self, record):
        super().__init__("qualification execution failed; preserve one-shot partial records")
        self.record = record


def prepare():
    io.clean();config = io.read(io.CONFIG);io.validate(config)
    prior, _, bindings = io.sources(config)
    parent = ROOT / config["output_root"]
    if list(parent.glob("*/manifest.json")):
        raise FileExistsError("qualification already prepared; no same-population rerun")
    names = set(prior["input_sha256"]) | {p.relative_to(ROOT).as_posix() for p in bindings}
    names |= set(io.git("ls-files", "src", "scripts", "tests", "docs/prototypes/delayed_intervention_v1").splitlines())
    names |= {io.CONFIG.relative_to(ROOT).as_posix(), io.PROTOCOL, io.SOFTWARE, io.COLLECTOR_SOFTWARE,
              "outputs/delayed_intervention/.gitattributes", config["source_completion"]}
    for receipt_path in (io.SOFTWARE, io.COLLECTOR_SOFTWARE):
        source_receipt = io.read(ROOT / receipt_path)
        names |= {((ROOT / receipt_path).parent / p).relative_to(ROOT).as_posix() for p in source_receipt["artifact_sha256"]}
    commit = io.git("rev-parse", "HEAD")
    run_id = "delayed_intervention_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + commit[:12]
    manifest = {"experiment_run_id": run_id, "source_git_commit": commit, "prior_manifest_id": prior["manifest_id"],
        "config": config, "input_sha256": {name: io.sha(ROOT / name) for name in sorted(names)},
        **{k: prior[k] for k in ("library_source_sha256", "native_library_sha256", "policy_sha256")}}
    manifest["manifest_id"] = digest(manifest)
    folder = parent / run_id;folder.mkdir(parents=True)
    io.write(folder / "manifest.json", manifest)
    print((folder / "manifest.json").relative_to(ROOT), flush=True)


def execute_one(key, config, model, emit, ledger, budget, saved_events):
    row = {**key, "fault_oracle": config["fault_oracle"], "completed": False,
        "error": None, "close_error": None, "environment_closed": False,
        "ledger_before": ledger.snapshot(), "prefix": None, "intervention": None,
        "physical_rows": [], "host_attempts": 0, "host_returned": 0, "policy_queries": 0,
        "captures": 0, "restores": 0, "computation_counters_complete": False}
    env = session = None
    try:
        emit("FACTORY_INTENT", {"ledger": ledger.snapshot()})
        with ledger.scope("FACTORY_SETUP"):
            env = create_task_environment(key["task"], key["seed"])
        emit("FACTORY_COMPLETE", {"ledger": ledger.snapshot()})
        before_reset = ledger.snapshot()
        with ledger.scope("CONTROLLED_RESET"):
            initial, _ = env.reset(seed=key["seed"])
        session = ProbeSession(env, create_task_policy(key["task"]), initial, key["task"], key["seed"],
                               config["fault_oracle"], emit, ledger, budget)
        row["initial_witness"] = session.witness()
        row["prefix"] = prepare_live_session(session, model, before_reset)
        public = row["prefix"]["public"]
        def lookup(sequence):
            return deepcopy(saved_events[sequence])
        if public["ready"]:
            if key["variant"] == "DIRECT_CURRENT":
                row["intervention"] = direct_continue(session, public["current_choice_sequence"], lookup)
            else:
                row["intervention"] = execute_live_session(session, key["variant"],
                    current_choice_sequence=public["current_choice_sequence"],
                    saved_choice_sequence=public["saved_choice_sequence"], lookup=lookup, reset_before=before_reset)
        row["success"] = session.public().success
        row["total_steps"] = session.ctx["calls"]
        row["deadline_loss"] = row["total_steps"] if row["success"] else 500
        row["boundary_ready"] = public["ready"]
        row["stopped"] = (public["ready"] and key["variant"] == "STOP") or public["reason"] in ("INVALID_FOUR", "INVALID_EIGHT")
        row["end_witness"] = session.witness()
        row["final_observation"] = normalize(asdict(session.public()))
        row["completed"] = True
    except BaseException as error:
        row["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        row["ledger_before_close"] = ledger.snapshot()
        if env is not None:
            try:
                env.close();row["environment_closed"] = True
            except BaseException as error:
                row["close_error"] = {"type": type(error).__name__, "message": str(error)}
        row["ledger_after_close"] = ledger.snapshot()
        if session is not None:
            row.update(physical_rows=session.last_rows, host_attempts=session.attempts, host_returned=session.completed,
                policy_queries=session.policy_queries, captures=session.captures, restores=session.restores)
        public_events = [r for r in saved_events.values() if r["event"] == "AGENT_EVENT"]
        intents = [r for r in public_events if r["agent_event"] == "FIT_INTENT"]
        fits = [r for r in public_events if r["agent_event"] == "FIT_RESULT"]
        row.update(parameter_fit_attempts=len(intents), parameter_fit_results=len(fits),
            optimizer_nfev=sum(int(r["public_payload"]["fit"].get("nfev", 0)) for r in fits),
            optimizer_nfev_complete=len(intents) == len(fits))
        row["computation_counters_complete"] = row["completed"] and row["optimizer_nfev_complete"]
    if row["error"] is not None or row["close_error"] is not None or not row["completed"] or not row["environment_closed"]:
        row["completed"] = False
        raise CollectionFailure(normalize(row))
    return normalize(row)


def collect(path):
    io.clean();manifest, models = io.load(path)
    if io.git("rev-parse", "HEAD") != manifest["source_git_commit"]:
        raise ValueError("collect only the frozen source commit")
    config = manifest["config"];folder = path.parent / "collection";folder.mkdir()
    identity = {k: manifest[k] for k in io.IDENTITY}
    budget = {"completed": 0, "maximum": config["maximum_environment_steps"]}
    records = [];key = {};saved_events = {};started = perf_counter_ns();failure = None
    status = {**identity, "status": "RUNNING", "completed_executions": 0}
    io.write(folder / "status.json", status)
    with gzip.open(folder / "events.jsonl.gz", "xt", encoding="utf-8") as log, gzip.open(
            folder / "cases.jsonl.gz", "xt", encoding="utf-8") as cases:
        journal = JsonJournal(log, identity)
        def emit(event, payload):
            value = journal.emit(event, {**key, **payload})
            if event == "AGENT_EVENT": saved_events[value["sequence"]] = deepcopy(value)
            return value
        ledger = LifecycleLedger(emit, config["maximum_simulation_frames"])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
                for unit, spec in enumerate(config["tasks_and_seeds"]):
                    for variant in config["variants"]:
                        key = {"unit": unit, **spec, "variant": variant};saved_events.clear()
                        row = execute_one({**identity, **key}, config, models[spec["task"]], emit, ledger, budget, saved_events)
                        cases.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n");cases.flush()
                        records.append({k: row[k] for k in ("unit", "task", "seed", "variant", "completed", "success", "stopped",
                            "total_steps", "deadline_loss", "boundary_ready", "host_attempts", "host_returned", "policy_queries",
                            "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev", "optimizer_nfev_complete")})
                        status.update(completed_executions=len(records), controlled_steps=budget["completed"], lifecycle=ledger.snapshot())
                        io.write(folder / "status.json", status, exclusive=False)
                        print(json.dumps({"completed_executions": len(records), "allocated_executions": 15, "controlled_steps": budget["completed"]}), flush=True)
            if len(records) != 15:
                raise ValueError("incomplete allocated population")
            status.update(status="COLLECTED_FOR_INDEPENDENT_AUDIT", failure=None)
        except BaseException as error:
            failure = error;status.update(status="FAILED_PARTIAL", failure={"type": type(error).__name__, "message": str(error)})
            if isinstance(error, CollectionFailure): io.write(folder / "failed_execution.json", error.record)
    status.update(rows=records, lifecycle=ledger.snapshot(), controlled_steps=budget["completed"], wall_ns=perf_counter_ns()-started,
                  new_api_calls=0, new_nominal_training=0, new_selector_fits=0, policy_updates=0)
    io.write(folder / "summary.json", status)
    io.write(folder / "status.json", {k: v for k, v in status.items() if k != "rows"}, exclusive=False)
    io.write(folder / "completion.json", {**identity, "status": status["status"],
             "artifact_sha256": {p.name: io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None: raise failure


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "collect"))
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest is None: parser.error("--manifest required")
    else: collect(args.manifest.resolve())
