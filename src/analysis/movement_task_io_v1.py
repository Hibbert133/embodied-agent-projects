"""Versioned movement/task study; missing audits or checks block preparation."""
from src.analysis import local_reprobe_io_v1 as prior
from src.analysis.movement_model_source_v1 import load_bank
from src.analysis.movement_task_design_v1 import (
    TASKS, METHODS, CONDITIONS, VARIANTS, GROUPS, CONTRASTS, INITIAL, PLANNING_PINS,
    destination, method, planning, population,
)
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY, expected_layers = prior.IDENTITY, prior.expected_layers
CONFIG = ROOT / "configs/movement_task/development_v1.json"
PLANNING = ROOT / "configs/movement_task/planning_v1.json"
PROTOCOL = "docs/protocols/movement_task_development_v1.md"
SOURCE = "outputs/local_reprobe/qualification_v1/local_reprobe_20261019T140639Z_7bf2aa94b5ab"
COMPONENT = "outputs/movement_task/software_validation_v1/delivery_review.json"
COMPONENT_SHA256 = "ed449f326202b5dcf6d4239f7f4df9d3c1a3e800d0cc9cfc8820639373c5e5c3"
REQUIRED = ("src/analysis/movement_task_design_v1.py", "src/analysis/movement_task_io_v1.py",
    "scripts/collect_movement_task_v1.py", "scripts/audit_movement_task_v1.py",
    "scripts/evaluate_movement_task_v1.py", "scripts/audit_movement_task_statistics_v1.py",
    "src/analysis/movement_task_numerical_v1.py", "src/analysis/movement_task_statistics_v1.py",
    "tests/test_movement_task_pipeline_v1.py", "tests/test_movement_task_statistics_v1.py",
    "tests/test_movement_task_design_v1.py", "tests/test_movement_task_numerical_v1.py", PROTOCOL)


def expected_config():
    return {"protocol_id": "movement_task_development_v1", "purpose": "FIXED_MOVEMENT_AND_INFORMATION_TASK_CONTROLS_NOT_NOVEL_SELECTOR",
        "cases": population(), "reserved_seeds": [25162,25399], "executions": 1296, "paired_units": 162,
        "independent_groups": GROUPS, "boundary_strata_groups": [18,18,18], "methods": list(METHODS),
        "contrasts": [list(v) for v in CONTRASTS], "primary": list(CONTRASTS[0]),
        "episode_budget": 500, "movement_limit": 64, "task_reserve": 100, "noise_std": .05, "noise_namespace": 47001,
        "operator_namespace": 88003, "fault_oracle": INITIAL,
        "maximum_environment_steps": 648000, "maximum_controlled_resets": 1296, "maximum_simulation_frames": 36288000,
        "witnesses_per_execution": 4, "bootstrap_replicates": 10000, "bootstrap_seed": 20261023,
        "historical_planning": PLANNING.relative_to(ROOT).as_posix(),
        "source_manifest": SOURCE+"/manifest.json", "source_manifest_id": "c796817f1058edf54901c0ff00d9b771847c16325bfa9998c51470baa1d3b123",
        "source_audit": SOURCE+"/audit/record_audit.json", "source_audit_sha256": "0f914e3851e075dd0a424fdf1b082d8074b34c3ba680d42e04f59b113023b170",
        "component_review": COMPONENT, "component_review_sha256": COMPONENT_SHA256,
        "historical_c8_cost": {"environment_steps": 3840, "controlled_resets": 480, "all_reset_calls": 24480, "simulation_frames": 12259200},
        "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0,
        "output_root": "outputs/movement_task/development_v1"}


def validate(config):
    if digest(config) != digest(expected_config()):raise ValueError("prospective movement-task allocation changed")


def sources(config):
    validate(config)
    if digest(read(PLANNING)) != digest(planning(ROOT)):raise ValueError("sample-size planning differs from historical records")
    previous, models = prior.load(ROOT/config["source_manifest"])
    if previous["manifest_id"] != config["source_manifest_id"] or sha(ROOT/config["source_audit"]) != config["source_audit_sha256"]:
        raise ValueError("source execution qualification changed")
    audit = read(ROOT/config["source_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "QUALIFIED":raise ValueError("audited local movement execution required")
    for name, expected in audit["collection_artifact_sha256"].items():
        if sha((ROOT/config["source_manifest"]).parent/"collection"/name) != expected:raise ValueError("source collection changed")
    if sha(ROOT/COMPONENT) != COMPONENT_SHA256:raise ValueError("movement software review changed")
    review = read(ROOT/COMPONENT)
    if review["status"] != "PASSED_SOFTWARE_EXECUTION_AND_RECORD_CONTRACT_ONLY":raise ValueError("movement contract software required")
    # Bind code contracts, not a subsequently maintained publication progress page.
    for name, expected in review["staged_file_sha256"].items():
        if name.startswith(("src/", "tests/")) and sha(ROOT/name) != expected:raise ValueError("frozen movement contract changed: "+name)
    references, receipt = load_bank(ROOT)
    return previous, models, references, receipt


def clean():
    if git("status", "--porcelain", "--untracked-files=no"):raise ValueError("clean committed scientific source required")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked for name in (*REQUIRED, CONFIG.relative_to(ROOT).as_posix(), PLANNING.relative_to(ROOT).as_posix())):
        raise ValueError("complete committed collector, independent audits, statistics and protocol required")
    if git("ls-files", "--others", "--exclude-standard", "src", "scripts", "tests", "configs/movement_task", PROTOCOL):
        raise ValueError("uncommitted movement-task source")


def load(path):
    manifest = read(path);validate(manifest["config"])
    if digest({k:v for k,v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:raise ValueError("manifest changed")
    for name, expected in manifest["input_sha256"].items():
        if sha(ROOT/name) != expected:raise ValueError("frozen input changed: "+name)
    previous, models, references, receipt = sources(manifest["config"])
    if digest(receipt) != digest(manifest["arx_source_receipt"]):raise ValueError("ARX source or costs differ")
    for key in ("library_source_sha256", "native_library_sha256", "policy_sha256"):
        if manifest[key] != previous[key]:raise ValueError("frozen runtime changed")
    return manifest, models, references


COMPACT = ("unit", "task", "seed", "variant", "planned_boundary", "completed", "success", "total_steps", "deadline_loss",
    "boundary_ready", "stopped", "action", "reposition_steps", "task_steps", "policy_queries", "parameter_fit_attempts",
    "parameter_fit_results", "optimizer_nfev", "movement_fit_attempts", "movement_fit_results", "movement_optimizer_nfev")
def compact(row):return {k:row[k] for k in COMPACT}
