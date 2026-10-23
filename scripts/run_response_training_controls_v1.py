"""One frozen TRAIN-only numeric development run; never creates a simulator."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import subprocess
import sys
from time import perf_counter_ns
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.analysis import response_training_controls_io_v1 as allocation
from src.analysis import response_training_controls_evaluation_v1 as evaluation
from src.analysis import observable_history_io_v1 as io
from src.analysis.history_response_failure_v1 import phase_labels
from src.probe import response_training_controls_v1 as core
from src.probe.observable_history_model_v1 import HistoryTrajectory, targets


def prepare(folder):
    allocation.load_manifest(folder)
    with allocation.numeric_guard() as counters:
        source = io.read(allocation.PUBLIC_SOURCE)
        io.require(set(source) == {"schema", "entries"} and source["schema"] == "PUBLIC_TRAIN_BUNDLE_V1", "strict original public export")
        for role in ("FIT", "DEV"):
            io.write(folder/(role.lower()+"_public.json"), allocation.bundle(source["entries"], role))
        public = {t["trajectory_id"]: HistoryTrajectory.from_dict(t) for e in source["entries"] for t in e["trajectories"]}
        source_completion = io.read(allocation.SOURCE/"train/completion.json")
        cases = allocation.SOURCE/"train/cases.jsonl.gz"
        io.require(io.sha(cases) == source_completion["artifact_sha256"]["cases.jsonl.gz"] and io.read(allocation.SOURCE/"train/audit.json")["integrity"] == "PASSED", "audited original TRAIN records")
        metadata = {}; registry = []; total_steps = 0
        for case in io.rows(cases):
            t = public[case["case_id"]]; m = allocation.metadata(t)
            observed = HistoryTrajectory.from_dict({"trajectory_id": case["case_id"], "task": case["task"], "split": "TRAIN", "initial": case["initial"]["observation"],
                "commands": [r["command"] for r in case["physical_rows"]], "observations": [r["after"]["observation"] for r in case["physical_rows"]]})
            io.require(core.public_dict(t) == core.public_dict(observed), "public export/source trajectory mismatch")
            labels = phase_labels(case).tolist()
            meta = {"case_id": case["case_id"], "group": m["group"], "task": m["task"], "context": m["context"], "program": m["source"], "role": m["role"], "labels": labels}
            io.require(len(labels) == len(targets(t)) and case["case_id"] not in metadata, "target/phase chronology")
            metadata[case["case_id"]] = meta
            registry.append({k: meta[k] for k in ("case_id", "group", "task", "context", "program", "role")} | {"success": case["success"], "stop_reason": case["stop_reason"], "source_steps": len(t.commands),
                "stage_response_counts": {s: int(evaluation.stage_mask(labels, s).sum()) for s in evaluation.STAGES}})
            total_steps += len(t.commands)
        io.require(len(registry) == 216 and total_steps == 20195 and len(public) == 216, "complete original TRAIN")
        io.write(folder/"evaluation_metadata.json", metadata); io.write(folder/"case_registry.json", registry)
        io.write(folder/"prepared.json", {"integrity": "PASSED", "fit_public_sha256": io.sha(folder/"fit_public.json"), "dev_public_sha256": io.sha(folder/"dev_public.json"),
            "metadata_sha256": io.sha(folder/"evaluation_metadata.json"), "registry_sha256": io.sha(folder/"case_registry.json"), "source_train_cases_sha256": io.sha(cases),
            "source_trajectories": 216, "fit_trajectories": 144, "dev_trajectories": 72, "source_control_steps": total_steps, "guard": counters,
            "new_environment_steps": 0, "new_api_calls": 0})


def child(folder, mode, timeout):
    log = folder/(mode+"_process.txt"); started = perf_counter_ns()
    command = [str(allocation.TRAIN_PYTHON), str(ROOT/"scripts/train_response_training_controls_v1.py"), mode, str(folder)]
    process = None; timed_out = False
    with log.open("xb") as handle:
        process = subprocess.Popen(command, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        io.write(folder/(mode+"_started.json"), {"pid": process.pid, "command": command, "timeout_seconds": timeout, "started_ns": started})
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; process.kill(); code = process.wait()
    result = {"returncode": code, "timed_out": timed_out, "wall_ns": perf_counter_ns()-started, "log_sha256": io.sha(log), "retry": False,
        "scientific_optimizer_steps_on_hard_timeout": "See committed checkpoints; unfinished block count is unknown and must not be filled with zero." if timed_out else None,
        "new_environment_steps": 0, "new_api_calls": 0}
    io.write(folder/(mode+"_process.json"), result)
    io.require(code == 0 and not timed_out, "preserve failed/timed-out numeric child; do not retry")


def evaluate(folder):
    allocation.load_manifest(folder)
    lock = io.read(folder/"model_lock.json")
    io.require(lock["models_index_sha256"] == io.sha(folder/"training/models.json") and io.read(folder/"training_audit.json")["integrity"] == "PASSED", "training audit and model lock precede DEV evaluation")
    with allocation.numeric_guard() as counters:
        index = io.read(folder/"training/models.json")["models"]
        metadata = io.read(folder/"evaluation_metadata.json")
        trajectories = [HistoryTrajectory.from_dict(t) for role in ("FIT", "DEV") for e in allocation.read_bundle(folder/(role.lower()+"_public.json"), role)["entries"] for t in e["trajectories"]]
        output = folder/"evaluation"; output.mkdir(exist_ok=False)
        rows = []; prediction_count = 0; started = perf_counter_ns()
        with gzip.open(output/"step_predictions.jsonl.gz", "xt", encoding="utf-8") as stream:
            for key, entry in index.items():
                path = folder/"training"/entry["file"]; io.require(io.sha(path) == entry["sha256"], "frozen model file changed")
                model = io.read(path)
                for t in trajectories:
                    if t.task != entry["task"]:
                        continue
                    predicted, target = core.predict(model, t), targets(t)
                    rows.extend(evaluation.trajectory_rows(metadata[t.trajectory_id], entry, key, predicted, target))
                    for j, (a, b) in enumerate(zip(predicted, target)):
                        stream.write(json.dumps({"case_id": t.trajectory_id, "model_key": key, "step": j+2, "prediction": a.tolist(), "target": b.tolist()}, separators=(",", ":"))+"\n")
                        prediction_count += 1
        io.write(output/"trajectory_metrics.json", rows)
        io.write(output/"statistics.json", evaluation.summarize(rows))
        io.write(output/"completion.json", {"status": "COMPLETE_FOR_INDEPENDENT_AUDIT", "models": len(index), "trajectories": len(trajectories), "predictions": prediction_count,
            "trajectory_stage_cells": len(rows), "guard": counters, "wall_ns": perf_counter_ns()-started, "models_index_sha256": io.sha(folder/"training/models.json"),
            "artifact_sha256": {p.name: io.sha(p) for p in output.iterdir()}, "new_environment_steps": 0, "new_api_calls": 0, "new_model_fits": 0})


def run():
    io.require(shutil.disk_usage(ROOT).free >= allocation.expected_config()["disk_free_floor_bytes"], "disk floor before run")
    folder = allocation.new_manifest(); started = perf_counter_ns(); failure = None
    try:
        prepare(folder)
        child(folder, "train", 14400)
        from scripts.audit_response_training_controls_v1 import audit_training, audit_evaluation
        audit_training(folder)
        io.write(folder/"model_lock.json", {"models_index_sha256": io.sha(folder/"training/models.json"), "training_audit_sha256": io.sha(folder/"training_audit.json"), "locked_ns": perf_counter_ns()})
        child(folder, "forward", 7200)
        evaluate(folder); audit_evaluation(folder)
    except BaseException as error:
        failure = {"type": type(error).__name__, "message": str(error)}
    io.write(folder/"pipeline_completion.json", {"status": "COMPLETE" if failure is None else "FAILED_NO_RETRY", "failure": failure, "wall_ns": perf_counter_ns()-started,
        "scientific_fit_limit": 162, "optimizer_update_limit": 720000, "independent_qualification": "NOT_ATTEMPTED", "new_environment_steps": 0,
        "new_all_resets": 0, "new_physical_frames": 0, "new_api_calls": 0})
    print(folder, flush=True)
    io.require(failure is None, "preserved numeric development failure")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("run", "prepare", "evaluate")); parser.add_argument("--folder", type=Path)
    args = parser.parse_args()
    if args.mode == "run":
        run()
    else:
        io.require(args.folder is not None, "explicit new run folder")
        {"prepare": prepare, "evaluate": evaluate}[args.mode](args.folder.resolve())
