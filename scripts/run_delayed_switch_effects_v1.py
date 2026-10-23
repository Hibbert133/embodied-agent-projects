"""One-shot matched fixed-switch collection using the unchanged qualified host."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
from time import perf_counter_ns

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import delayed_switch_effects_v1 as io
from src.analysis.capsule_record_json_v2 import JsonJournal
from src.probe.cache_acquisition_evidence_v1 import digest
from src.probe.lifecycle_ledger import LifecycleLedger
from scripts.qualify_delayed_intervention_v2 import execute_one, CollectionFailure


def prepare():
    io.clean();config = io.read(io.CONFIG);previous, _ = io.sources(config)
    parent = ROOT / config["output_root"]
    if list(parent.glob("*/manifest.json")): raise FileExistsError("fixed population already prepared")
    names = set(previous["input_sha256"]) | {config["source_manifest"], config["source_audit"], io.PROTOCOL, io.CONFIG.relative_to(ROOT).as_posix()}
    names |= set(io.git("ls-files", "src", "scripts", "tests", "docs/prototypes/delayed_intervention_v1").splitlines())
    commit = io.git("rev-parse", "HEAD")
    run_id = "delayed_switch_effects_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + commit[:12]
    manifest = {"experiment_run_id": run_id, "source_git_commit": commit, "config": config, "allocation_oracle": io.population(),
        "input_sha256": {name: io.sha(ROOT / name) for name in sorted(names)},
        **{k: previous[k] for k in ("library_source_sha256", "native_library_sha256", "policy_sha256")}}
    manifest["manifest_id"] = digest(manifest)
    folder = parent / run_id;folder.mkdir(parents=True)
    io.write(folder / "manifest.json", manifest);print((folder / "manifest.json").relative_to(ROOT), flush=True)


def collect(path):
    io.clean();manifest, models = io.load(path)
    if io.git("rev-parse", "HEAD") != manifest["source_git_commit"]: raise ValueError("frozen source commit required")
    config = manifest["config"];folder = path.parent / "collection";folder.mkdir()
    identity = {k: manifest[k] for k in io.IDENTITY}
    budget = {"completed": 0, "maximum": config["maximum_environment_steps"]}
    rows = [];key = {};saved_events = {};last = {};failure = None;started = perf_counter_ns()
    status = {**identity, "status": "RUNNING", "completed_executions": 0}
    io.write(folder / "status.json", status)
    with gzip.open(folder / "events.jsonl.gz", "xt", encoding="utf-8") as log, gzip.open(folder / "cases.jsonl.gz", "xt", encoding="utf-8") as cases, gzip.open(folder / "state_witnesses.jsonl.gz", "xt", encoding="utf-8") as private_log:
        journal = JsonJournal(log, identity);private = JsonJournal(private_log, identity)
        def emit(event, payload):
            nonlocal last
            value = journal.emit(event, {**key, **payload});last = {k: value[k] for k in ("sequence", "saved_ns")}
            if event == "AGENT_EVENT": saved_events[value["sequence"]] = deepcopy(value)
            return value
        def emit_private(event, payload): return private.emit(event, {**key, **payload})
        ledger = LifecycleLedger(emit, config["maximum_simulation_frames"])
        import metaworld
        from metaworld.sawyer_xyz_env import SawyerXYZEnv
        from gymnasium.envs.mujoco import MujocoEnv
        try:
            with ledger.instrument(SawyerXYZEnv, MujocoEnv, metaworld):
                for spec in manifest["allocation_oracle"]:
                    for method in io.METHODS:
                        key = {**{k: spec[k] for k in ("unit", "task", "seed")}, "variant": method};saved_events.clear()
                        case_config = {**config, "fault_oracle": spec["fault_oracle"]}
                        row = execute_one({**identity, **key}, case_config, models[spec["task"]], emit, ledger, budget,
                            saved_events, lambda: deepcopy(last), emit_private)
                        cases.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n");cases.flush()
                        rows.append(io.compact(row));status.update(completed_executions=len(rows), controlled_steps=budget["completed"], lifecycle=ledger.snapshot())
                        io.write(folder / "status.json", status, exclusive=False)
                        print(json.dumps({"completed_executions": len(rows), "allocated_executions": config["executions"], "controlled_steps": budget["completed"]}), flush=True)
            if len(rows) != config["executions"] or private.sequence != 3 * config["executions"]:
                raise ValueError("complete population and three witnesses per case required")
            status.update(status="COLLECTED_FOR_INDEPENDENT_AUDIT", failure=None)
        except BaseException as error:
            failure = error;status.update(status="FAILED_PARTIAL", failure={"type": type(error).__name__, "message": str(error)})
            if isinstance(error, CollectionFailure): io.write(folder / "failed_execution.json", error.record)
    status.update(rows=rows, lifecycle=ledger.snapshot(), controlled_steps=budget["completed"], wall_ns=perf_counter_ns() - started,
        private_witness_records=private.sequence, event_count=journal.sequence, collection_closed_ns=perf_counter_ns(),
        new_api_calls=0, new_nominal_training=0, new_selector_fits=0, policy_updates=0)
    io.write(folder / "summary.json", status)
    io.write(folder / "status.json", {k: v for k, v in status.items() if k != "rows"}, exclusive=False)
    io.write(folder / "completion.json", {**identity, "status": status["status"],
        "artifact_sha256": {p.name: io.sha(p) for p in folder.iterdir() if p.is_file()}})
    if failure is not None: raise failure


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "collect"));parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    if args.command == "prepare": prepare()
    elif args.manifest is None: parser.error("--manifest required")
    else: collect(args.manifest.resolve())
