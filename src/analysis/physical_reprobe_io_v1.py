"""Frozen I/O and allocation for continuous physical-reprobe execution qualification."""
from pathlib import Path
from src.analysis import delayed_qualification_io_v2 as prior
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY = prior.IDENTITY
CONFIG = ROOT / "configs/physical_reprobe/qualification_v1.json"
PROTOCOL = "docs/protocols/physical_reprobe_execution_qualification_v1.md"
SOURCE = "outputs/delayed_intervention/qualification_v2/delayed_intervention_v2_20261019T090014Z_1ba6b7b81e55"
COMPONENT = "outputs/physical_reprobe/validation_v1/delivery_review_v1.json"
TASKS = ("push-v3", "reach-v3", "door-open-v3")
VARIANTS = ("PHYSICAL_REPROBE",)
REQUIRED = ("src/analysis/physical_reprobe_io_v1.py", "src/probe/physical_reprobe_v1.py",
    "src/analysis/physical_reprobe_host_v2.py", "scripts/qualify_physical_reprobe_v1.py",
    "scripts/audit_physical_reprobe_v1.py", "tests/test_physical_reprobe_qualification_v1.py", PROTOCOL)
expected_layers = prior.expected_layers


def population():
    return [{"unit": 3*j+i, "task": task, "seed": 22400+3*j+i,
             "variant": "PHYSICAL_REPROBE", "planned_boundary": boundary}
            for j, boundary in enumerate((16, 32, 64)) for i, task in enumerate(TASKS)]


def expected_config():
    return {"protocol_id": "physical_reprobe_execution_qualification_v1",
        "purpose": "CONTINUOUS_MEASUREMENT_EXECUTION_NOT_IDENTIFICATION_OR_TASK_BENEFIT",
        "cases": population(), "reserved_seeds": [22409, 22599], "executions": 9,
        "logical_total_steps": 500, "noise_std": .05, "noise_namespace": 47001,
        "fault_oracle": {"matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]},
        "maximum_environment_steps": 4500, "scheduled_maximum_control_steps": 984,
        "maximum_controlled_resets": 9, "maximum_simulation_frames": 252000,
        "minimum_complete_windows_per_task": 1, "witnesses_per_execution": 3,
        "source_manifest": SOURCE + "/manifest.json",
        "source_manifest_id": "ae549ee2e9cfdcac76a8f565db1f04321c22f6ebaac93d18694eec783aee6b6a",
        "source_audit": SOURCE + "/audit/record_audit.json",
        "source_audit_sha256": "b5d30f1e8976cef0d88d5429948990128cc52fd7a684ffacd81606749603a78f",
        "component_review": COMPONENT,
        "component_review_sha256": "4ce929687e477d13c65386b0f94c324d8f7fae8e5696812541ac75a23008cf03",
        "historical_nominal_cost": {"environment_steps": 3840, "controlled_resets": 480,
            "all_reset_calls": 24480, "simulation_frames": 12259200},
        "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0,
        "output_root": "outputs/physical_reprobe/qualification_v1"}


def validate(config):
    if digest(config) != digest(expected_config()): raise ValueError("registered physical-reprobe scope changed")


def sources(config):
    validate(config)
    previous, models = prior.load(ROOT / config["source_manifest"])
    if previous["manifest_id"] != config["source_manifest_id"]: raise ValueError("wrong continuous source")
    if sha(ROOT / config["source_audit"]) != config["source_audit_sha256"]: raise ValueError("prior audit changed")
    audit = read(ROOT / config["source_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "QUALIFIED": raise ValueError("qualified source required")
    for name, value in audit["collection_artifact_sha256"].items():
        if sha((ROOT / config["source_manifest"]).parent / "collection" / name) != value: raise ValueError("old source artifact changed")
    if sha(ROOT / COMPONENT) != config["component_review_sha256"]: raise ValueError("component review changed")
    review = read(ROOT / COMPONENT)
    if review["status"] != "PASSED_SOFTWARE_COMPONENT_ONLY" or review["tests_passed"] != 1176:
        raise ValueError("passed physical-reprobe software source required")
    for row in review["files"]:
        if sha(ROOT / row["path"]) != row["sha256"]: raise ValueError("physical-reprobe source changed: " + row["path"])
    return previous, models


def clean():
    if git("status", "--porcelain", "--untracked-files=no"): raise ValueError("clean committed source required")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked for name in REQUIRED): raise ValueError("complete committed collector/auditor/protocol/tests required")
    if git("ls-files", "--others", "--exclude-standard", "src", "scripts", "tests", "configs/physical_reprobe", PROTOCOL):
        raise ValueError("uncommitted qualification source")


def load(path):
    manifest = read(path);validate(manifest["config"])
    if digest({k:v for k,v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]: raise ValueError("manifest changed")
    for name, value in manifest["input_sha256"].items():
        if sha(ROOT / name) != value: raise ValueError("frozen input changed: " + name)
    previous, models = sources(manifest["config"])
    for key in ("library_source_sha256", "native_library_sha256", "policy_sha256"):
        if manifest[key] != previous[key]: raise ValueError("qualified runtime binding differs")
    return manifest, models


COMPACT = ("unit", "task", "seed", "variant", "planned_boundary", "completed", "boundary_ready",
    "collection_stop_reason", "complete_window", "success", "total_steps", "reposition_steps", "probe_steps",
    "host_attempts", "host_returned", "policy_queries", "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev")


def compact(row): return {k: row[k] for k in COMPACT}
