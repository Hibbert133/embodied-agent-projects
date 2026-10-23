"""Frozen nominal TRAIN and independent identification allocation; evaluator only."""
import numpy as np
from src.analysis import local_reprobe_io_v1 as prior
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY, TASKS, expected_layers = prior.IDENTITY, prior.TASKS, prior.expected_layers
VARIANTS = ("TRAIN", "UNCHANGED", "CHANGED")
STAGES = ("train", "qualify")
CONFIG = ROOT / "configs/selected_response/qualification_v1.json"
PROTOCOL = "docs/protocols/selected_response_identification_v1.md"
SOURCE = "outputs/local_reprobe/qualification_v1/local_reprobe_20261019T140639Z_7bf2aa94b5ab"
COMPONENT = "outputs/selected_response_reference/validation_v1/delivery_review_v1.json"
NOMINAL = {"matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [0., 0.], "deadzone_xy": [0., 0.]}
INITIAL = {**NOMINAL, "bias_xy": [.12, -.08]}
REQUIRED = ("src/analysis/selected_response_io_v1.py", "scripts/collect_selected_response_v1.py",
    "scripts/audit_selected_response_v1.py", "scripts/evaluate_selected_response_v1.py",
    "scripts/audit_selected_response_analysis_v1.py",
    "tests/test_selected_response_pipeline_v1.py", PROTOCOL)


def population(stage):
    if stage == "train":
        return [{"unit": i, "task": TASKS[i%3], "seed": 23200+i, "variant": "TRAIN",
                 "planned_boundary": (16,32,64)[(i//3)%3]} for i in range(1152)]
    if stage == "qualify":
        return [{"unit": i, "task": TASKS[i%3], "seed": 24500+i, "variant": condition,
                 "planned_boundary": (16,32,64)[(i//3)%3]} for i in range(144) for condition in VARIANTS[1:]]
    raise ValueError("registered collection stage required")


def expected_config():
    return {"protocol_id": "selected_response_identification_v1", "train_cases": population("train"),
        "qualify_cases": population("qualify"), "reserved_seeds": [[24352,24499],[24644,24999]],
        "nominal_command_namespace": 88001, "qualification_operator_namespace": 88002,
        "noise_namespace": 47001, "noise_std": .05, "episode_budget": 500,
        "candidate": "SELECTED_POSE_HISTORY", "bootstrap_replicates": 10000, "bootstrap_seed": 20261020,
        "invalid_matrix_error": 8., "invalid_bias_error": 1., "bias_score_scale": .4,
        "minimum_complete_fraction_each_task_condition": .5, "minimum_valid_fraction_complete": .9,
        "source_manifest": SOURCE+"/manifest.json", "source_manifest_id": "c796817f1058edf54901c0ff00d9b771847c16325bfa9998c51470baa1d3b123",
        "source_audit": SOURCE+"/audit/record_audit.json", "source_audit_sha256": "0f914e3851e075dd0a424fdf1b082d8074b34c3ba680d42e04f59b113023b170",
        "component_review": COMPONENT, "component_review_sha256": "7edffffdbfc7d5209896f441f0b4cdbbc68b7293cfbe120bc7021c58ad409cc6",
        "historical_nominal_cost": {"environment_steps":3840,"controlled_resets":480,"all_reset_calls":24480,"simulation_frames":12259200},
        "new_api_calls": 0, "policy_updates": 0, "output_root": "outputs/selected_response/qualification_v1"}


def limits(config, stage):
    cases = config[stage+"_cases"];tight = sum(r["planned_boundary"]+72 for r in cases)
    return {"executions": len(cases), "maximum_environment_steps": 500*len(cases),
        "scheduled_maximum_control_steps": tight, "maximum_simulation_frames": 25500*len(cases)+5*tight,
        "maximum_controlled_resets": len(cases)}


def program(seed):
    rng = np.random.default_rng(np.random.SeedSequence([seed,88001]))
    return np.c_[rng.uniform(-.8,.8,(8,2)),np.zeros((8,2))].astype(np.float32).tolist()


def initial(variant):
    if variant not in VARIANTS:raise ValueError("unknown allocation")
    return NOMINAL if variant == "TRAIN" else INITIAL


def destination(spec):
    if spec["variant"] in ("TRAIN","UNCHANGED"):return initial(spec["variant"])
    if spec["variant"] != "CHANGED":raise ValueError("unknown allocation")
    rng = np.random.default_rng(np.random.SeedSequence([88002,spec["unit"]//9]))
    return {"matrix_xy":[[float(rng.uniform(.75,1.25)),float(rng.uniform(-.2,.2))],
                         [float(rng.uniform(-.2,.2)),float(rng.uniform(.75,1.25))]],
            "bias_xy":rng.uniform(-.2,.2,2).tolist(),"deadzone_xy":[0.,0.]}


def validate(config):
    if digest(config) != digest(expected_config()):raise ValueError("registered selected-response allocation changed")


def sources(config):
    validate(config);previous,models = prior.load(ROOT/config["source_manifest"])
    if previous["manifest_id"] != config["source_manifest_id"] or sha(ROOT/config["source_audit"]) != config["source_audit_sha256"]:
        raise ValueError("frozen local execution source differs")
    audit = read(ROOT/config["source_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "QUALIFIED":raise ValueError("audited execution qualification required")
    for name,value in audit["collection_artifact_sha256"].items():
        if sha((ROOT/config["source_manifest"]).parent/"collection"/name) != value:raise ValueError("source records changed")
    if sha(ROOT/COMPONENT) != config["component_review_sha256"]:raise ValueError("selected response component changed")
    review = read(ROOT/COMPONENT)
    if review["status"] != "PASSED_SOFTWARE_REFERENCE_ONLY" or review["tests_passed"] != 1311:raise ValueError("software component required")
    for row in review["files"]:
        if sha(ROOT/row["path"]) != row["sha256"]:raise ValueError("frozen component changed: "+row["path"])
    return previous,models


def clean():
    if git("status","--porcelain","--untracked-files=no"):raise ValueError("clean committed source required")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked for name in REQUIRED):raise ValueError("complete committed scientific pipeline required")
    if git("ls-files","--others","--exclude-standard","src","scripts","tests","configs/selected_response",PROTOCOL):
        raise ValueError("uncommitted scientific source")


def load(path):
    manifest = read(path);validate(manifest["config"])
    if digest({k:v for k,v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:raise ValueError("manifest changed")
    for name,value in manifest["input_sha256"].items():
        if sha(ROOT/name) != value:raise ValueError("frozen input changed: "+name)
    previous,models = sources(manifest["config"])
    for key in ("library_source_sha256","native_library_sha256","policy_sha256"):
        if manifest[key] != previous[key]:raise ValueError("runtime binding changed")
    return manifest,models


COMPACT = prior.COMPACT
def compact(row):return {k:row[k] for k in COMPACT}


def bank(path, *, require_audit=True):
    from src.probe.selected_response_reference_v1 import METHODS, validate_model
    folder = path.parent;manifest = read(path)
    done = read(folder/"models_completion.json");saved = read(folder/"models.json")
    started = read(folder/"model_fit_started.json");audit = read(folder/"train_audit/record_audit.json")
    for record in (done,saved,started,audit):
        if any(record[k] != manifest[k] for k in IDENTITY):raise ValueError("model TRAIN identity differs")
    if done["models_sha256"] != sha(folder/"models.json") or done["status"] != saved["status"] or saved["status"] != "READY_FOR_INDEPENDENT_QUALIFICATION":
        raise ValueError("successfully frozen selected-response bank required")
    audit_sha = sha(folder/"train_audit/record_audit.json")
    if (audit["integrity"] != "PASSED" or audit["stage"] != "train" or
            started["train_audit_sha256"] != audit_sha or saved["train_audit_sha256"] != audit_sha or
            saved["train_collection_sha256"] != audit["collection_artifact_sha256"] or
            saved["training_costs"] != audit["costs"] or saved["training_attempts"] != len(manifest["config"]["train_cases"])):
        raise ValueError("audited TRAIN binding differs")
    for name,value in saved["train_collection_sha256"].items():
        if sha(folder/"train"/name) != value:raise ValueError("frozen TRAIN artifact changed")
    if not read(folder/"train/summary.json")["collection_closed_ns"] < started["started_ns"] == saved["started_ns"] <= saved["fit_completed_ns"] < done["models_closed_ns"]:
        raise ValueError("model freeze ordering differs")
    if saved["physical_response_qualified"] is not False or saved["task_utility_demonstrated"] is not False:
        raise ValueError("training cannot qualify a physical model")
    expected = [(task,method) for task in TASKS for method in METHODS]
    if [(r["task"],r["method"]) for r in saved["fits"]] != expected or set(saved["models"]) != set(TASKS):
        raise ValueError("nine registered model fits required")
    last = started["started_ns"]
    for fit in saved["fits"]:
        if not fit["valid"] or fit["error"] is not None or not last <= fit["started_ns"] <= fit["completed_ns"] <= saved["fit_completed_ns"]:
            raise ValueError("invalid or unordered model fit")
        last = fit["completed_ns"]
        if fit["training_windows"] != saved["complete_windows"][fit["task"]]:raise ValueError("fit sample count differs")
    for task in TASKS:
        count = sum(r["task"] == task and r["complete_window"] for r in audit["rows"])
        if count != saved["complete_windows"][task] or set(saved["models"][task]) != set(METHODS):
            raise ValueError("all same-task complete TRAIN windows required")
        for method in METHODS:
            model = saved["models"][task][method];validate_model(model)
            if model["task"] != task or model["method"] != method or model["training_trajectories"] != count:
                raise ValueError("model allocation changed")
    if require_audit:
        checked = read(folder/"model_audit/record_audit.json")
        if (checked["integrity"] != "PASSED" or checked["models_sha256"] != done["models_sha256"] or
                checked["train_audit_sha256"] != audit_sha or any(checked[k] != manifest[k] for k in IDENTITY) or
                checked["audit_completed_ns"] <= done["models_closed_ns"]):
            raise ValueError("independent nominal model audit required before qualification")
        done = {**done,"model_audit_sha256":sha(folder/"model_audit/record_audit.json"),"model_audit_completed_ns":checked["audit_completed_ns"]}
    return saved,done
