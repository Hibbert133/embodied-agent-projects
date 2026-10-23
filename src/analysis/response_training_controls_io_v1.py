"""TRAIN-only development allocation and fail-closed numeric-study boundaries."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import builtins
import re
import os
import sys

from src.analysis import observable_history_io_v1 as io
from src.probe.observable_history_model_v1 import HistoryTrajectory
from src.probe.response_training_controls_v1 import public_dict

ROOT = io.ROOT
SOURCE = ROOT / "outputs/observable_history_transfer/development_v1/observable_history_20261021T154956Z_d256a0cf6753"
PUBLIC_SOURCE = SOURCE / "training/public_train_bundle.json"
PUBLIC_SOURCE_SHA = "79bf2819261976b7e62faba8ad6c12d39d0552dc2acebc81949e2da8a4631e75"
CONFIG = ROOT / "configs/movement_task/response_training_controls_v1.json"
PROTOCOL = ROOT / "docs/protocols/response_training_controls_v1_zh.md"
VALIDATION = ROOT / "outputs/response_training_controls/validation_v1"
OUTPUT = ROOT / "outputs/response_training_controls/development_v1"
TRAIN_PYTHON = Path("C:/Users/Administrator/Documents/ChatGPT/robotic agent/.venv-history-training-cpu22/Scripts/python.exe")
FEATURES = ("F20", "F43")
LOSSES = ("ISO", "AXIS")
WINDOWS = (1, 16)
FIT_GROUPS = tuple(range(12))
DEV_GROUPS = tuple(range(12, 18))
REQUIRED = ("src/probe/response_training_controls_v1.py", "src/analysis/response_training_controls_io_v1.py",
    "src/analysis/response_training_controls_evaluation_v1.py",
    "scripts/train_response_training_controls_v1.py", "scripts/run_response_training_controls_v1.py",
    "scripts/audit_response_training_controls_v1.py", "scripts/report_response_training_controls_v1.py",
    "tests/test_response_training_controls_v1.py", "tests/test_response_training_controls_pipeline_v1.py",
    "docs/protocols/response_training_controls_v1_zh.md", "configs/movement_task/response_training_controls_v1.json")


def expected_config():
    return {"version": "response_training_controls_v1", "scope": "TRAIN_ONLY_DEVELOPMENT_NOT_INDEPENDENT_CONFIRMATION",
        "public_source": PUBLIC_SOURCE.relative_to(ROOT).as_posix(), "public_source_sha256": PUBLIC_SOURCE_SHA,
        "fit_groups": list(FIT_GROUPS), "dev_groups": list(DEV_GROUPS), "source_trajectories": 216,
        "fit_trajectories": 144, "dev_trajectories": 72, "features": list(FEATURES), "losses": list(LOSSES),
        "windows": list(WINDOWS), "replicates": 3, "updates": 5000, "batch": 32, "hidden_size": 32,
        "padded_input_size": 43, "scale_floor": 1e-6, "scale_floor_replacement": 1., "ridge": .001,
        "optimizer": {"name": "Adam", "lr": .001, "betas": [.9, .999], "eps": 1e-8, "weight_decay": 0., "gradient_clip": None},
        "initial_seed_base": 202610310, "sampling_seed_base": 202610340,
        "linear_models": 18, "neural_models": 144, "optimizer_updates": 720000,
        "common_history_start": 2, "candidate_selection": "NONE; report every variant and every initialization",
        "primary": "F20_ISO_W16_MINUS_F43_AXIS_W16_DEV_POST_TASK_MEAN_TRAJECTORY_RMSE",
        "bootstrap": {"replicates": 10000, "seed": 202610350, "unit": "SIX_WHOLE_DEV_GROUPS_STRATIFIED_BY_BOUNDARY"},
        "early_stopping": False, "retry": False, "training_timeout_seconds": 14400,
        "new_environment_steps": 0, "new_all_resets": 0, "new_physical_frames": 0, "new_api_calls": 0,
        "disk_free_floor_bytes": 600*1024**2}


def metadata(trajectory):
    match = re.fullmatch(r"TRAIN/(\d{2})/(push-v3|reach-v3|door-open-v3)/(NOMINAL|RANDOM)/(FEEDBACK8|BALANCED8)", trajectory.trajectory_id)
    io.require(match is not None and trajectory.split == "TRAIN" and match[2] == trajectory.task, "registered TRAIN identifier only")
    group = int(match[1]); io.require(0 <= group < 18, "registered source group")
    return {"group": group, "task": trajectory.task, "context": match[3], "source": match[4], "role": "FIT" if group in FIT_GROUPS else "DEV"}


def bundle(entries, role):
    io.require(role in ("FIT", "DEV"), "development role")
    selected = []
    seen = set()
    for source in io.PROGRAMS:
        for task in io.TASKS:
            entry = next(e for e in entries if e["source_bank"] == source and e["task"] == task)
            trajectories = [HistoryTrajectory.from_dict(t) for t in entry["trajectories"]]
            chosen = []
            for t in trajectories:
                m = metadata(t)
                io.require(m["source"] == source and t.trajectory_id not in seen, "source mapping or duplicate")
                seen.add(t.trajectory_id)
                if m["role"] == role:
                    chosen.append(public_dict(t))
            io.require(len(chosen) == (24 if role == "FIT" else 12), "complete role/source/task population")
            selected.append({"task": task, "source_bank": source, "trajectories": chosen})
    io.require(len(seen) == 216, "complete original TRAIN population")
    return {"schema": "RESPONSE_TRAINING_CONTROLS_"+role+"_V1", "entries": selected}


def read_bundle(path, role):
    data = io.read(path)
    io.require(set(data) == {"schema", "entries"} and data["schema"] == "RESPONSE_TRAINING_CONTROLS_"+role+"_V1", "strict role bundle")
    io.require(len(data["entries"]) == 6, "all six source/task entries")
    seen = set(); ids = set()
    for e in data["entries"]:
        io.require(set(e) == {"task", "source_bank", "trajectories"}, "private/statistics bundle fields rejected")
        key = (e["task"], e["source_bank"])
        io.require(key not in seen and key[0] in io.TASKS and key[1] in io.PROGRAMS, "unique registered bank")
        seen.add(key)
        io.require(len(e["trajectories"]) == (24 if role == "FIT" else 12), "complete role count")
        for raw in e["trajectories"]:
            t = HistoryTrajectory.from_dict(raw); m = metadata(t)
            io.require((m["task"], m["source"], m["role"]) == (*key, role) and t.trajectory_id not in ids and len(t.commands) >= 3, "fit/dev split or duplicate/empty history")
            ids.add(t.trajectory_id)
    return data


@contextmanager
def numeric_guard(allow_training=False):
    """No simulator, network, child process, or old CAL/TEST/model reads."""
    active = [True]
    counters = {"attempted_network_calls": 0, "forbidden_data_reads": 0, "simulator_import_attempts": 0, "child_process_attempts": 0}
    original_import = builtins.__import__
    def guarded_import(name, *args, **kwargs):
        if any(name == p or name.startswith(p+".") for p in ("metaworld", "mujoco", "gym", "gymnasium", "requests", "httpx", "openai", "zhipuai")):
            counters["simulator_import_attempts"] += 1
            raise RuntimeError("numeric study forbids simulator/network client import")
        return original_import(name, *args, **kwargs)
    forbidden = (SOURCE / "cal", SOURCE / "test", SOURCE / "evaluation", SOURCE / "calibration", SOURCE / "training/models.json")
    def audit(event, args):
        if active[0] and event.startswith("socket.") and event != "socket.gethostname":
            counters["attempted_network_calls"] += 1
            raise RuntimeError("numeric study forbids network transport")
        if active[0] and event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
            counters["child_process_attempts"] += 1
            raise RuntimeError("numeric study forbids child process")
        if active[0] and event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(os.fsdecode(args[0])).resolve()
            if any(path == p or p in path.parents for p in forbidden):
                counters["forbidden_data_reads"] += 1
                raise RuntimeError("TRAIN-only study forbids prior CAL/TEST/models")
            if allow_training and path.name in ("dev_public.json", "evaluation_metadata.json"):
                counters["forbidden_data_reads"] += 1
                raise RuntimeError("training worker cannot open development responses")
            if allow_training and (path == PUBLIC_SOURCE or SOURCE/"train" in path.parents):
                counters["forbidden_data_reads"] += 1
                raise RuntimeError("training worker reads the FIT export only")
    sys.addaudithook(audit)
    builtins.__import__ = guarded_import
    try:
        yield counters
    finally:
        active[0] = False
        builtins.__import__ = original_import


def new_manifest():
    io.require(io.read(CONFIG) == expected_config(), "frozen controls config changed")
    io.require(not io.git("diff", "--name-only") and not io.git("diff", "--cached", "--name-only"), "clean tracked freeze required")
    io.require(io.sha(PUBLIC_SOURCE) == PUBLIC_SOURCE_SHA, "public TRAIN source changed")
    validation = io.read(VALIDATION/"complete.json")
    io.require(validation["integrity"] == "PASSED", "completed source-bound validation required")
    for name, digest in validation["python_source_sha256"].items():
        io.require(io.sha(ROOT/name) == digest, "validated source changed")
    for name, digest in validation["receipt_sha256"].items():
        io.require(io.sha(VALIDATION/name) == digest, "validation receipt changed")
    for name in REQUIRED:
        io.require(io.git("ls-files", "--error-unmatch", name) == name, "implementation not committed")
    runtime = io.read(ROOT/"outputs/observable_history_transfer/runtime_v1/environment.json")
    for name, digest in runtime["file_sha256"].items():
        io.require(io.sha(Path(name)) == digest, "qualified training runtime changed")
    commit = io.git("rev-parse", "HEAD")
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = "training_controls_"+now+"_"+commit[:12]
    value = {"experiment_run_id": run_id, "source_git_commit": commit, "config": expected_config(),
        "implementation_sha256": {n: io.sha(ROOT/n) for n in sorted(set(REQUIRED) | {p.relative_to(ROOT).as_posix() for d in ("src", "scripts", "tests") for p in (ROOT/d).rglob("*.py")})}, "source_public_sha256": PUBLIC_SOURCE_SHA,
        "source_result_commit": "ab3f7a85b285b4bc8c07044a0d3b727613509c27", "diagnostic_result_commit": "5c49835",
        "validation_sha256": io.sha(VALIDATION/"complete.json"), "training_runtime_sha256": io.sha(ROOT/"outputs/observable_history_transfer/runtime_v1/environment.json"),
        "new_environment_steps": 0, "new_api_calls": 0}
    value["manifest_id"] = io.digest(value)
    folder = OUTPUT/run_id; folder.mkdir(parents=True, exist_ok=False)
    io.write(folder/"manifest.json", value)
    return folder


def load_manifest(folder):
    m = io.read(folder/"manifest.json")
    v = dict(m); identifier = v.pop("manifest_id")
    io.require(io.digest(v) == identifier and m["config"] == expected_config(), "manifest/config changed")
    for name, digest in m["implementation_sha256"].items():
        io.require(io.sha(ROOT/name) == digest, "frozen controls source changed: "+name)
    io.require(io.sha(PUBLIC_SOURCE) == PUBLIC_SOURCE_SHA, "original TRAIN bytes changed")
    return m
