"""Matched unchanged/changed actuator qualification, with frozen prior versions."""
from src.analysis import integral_reprobe_io_v1 as prior
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY, TASKS, expected_layers = prior.IDENTITY, prior.TASKS, prior.expected_layers
METHODS = ("FIXED_PD", "FIXED_PID", "LOCAL_PD", "LOCAL_PID")
VARIANTS = tuple(c+"_"+m for c in ("UNCHANGED", "CHANGED") for m in METHODS)
CONFIG = ROOT / "configs/local_reprobe/qualification_v1.json"
PROTOCOL = "docs/protocols/local_reprobe_execution_qualification_v1.md"
SOURCE = "outputs/integral_reprobe/qualification_v1/integral_reprobe_20261019T132410Z_8014d27d424a"
COMPONENT = "outputs/warm_response_reference/validation_v1/delivery_review_v1.json"
REQUIRED = ("src/analysis/local_reprobe_io_v1.py", "src/analysis/local_reprobe_host_v1.py",
    "src/probe/local_reprobe_v1.py", "scripts/qualify_local_reprobe_v1.py",
    "scripts/audit_local_reprobe_v1.py", "tests/test_local_reprobe_qualification_v1.py",
    "tests/test_local_reprobe_v1.py", PROTOCOL)


def population():
    return [{"unit":3*j+i, "task":task, "seed":23000+3*j+i, "variant":variant, "planned_boundary":boundary}
        for j,boundary in enumerate((16,32,64)) for i,task in enumerate(TASKS) for variant in VARIANTS]


def expected_config():
    return {"protocol_id":"local_reprobe_execution_qualification_v1",
        "purpose":"MATCHED_LOCAL_TARGET_ACQUISITION_NOT_CALIBRATED_INFORMATION_OR_TASK_UTILITY",
        "cases":population(), "reserved_seeds":[23009,23199], "executions":72, "paired_units":9, "integral_gain":.32, "integral_limit":.5,
        "local_target":{"x_range":[-.45,.45],"y_range":[.45,.95],"z_range":[.25,.45],"object_height_margin":.12},
        "candidate_method":"LOCAL_PID",
        "logical_total_steps":500, "noise_std":.05, "noise_namespace":47001,
        "fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]], "bias_xy":[.12,-.08], "deadzone_xy":[0.,0.]},
        "changed_fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]], "bias_xy":[-.12,.08], "deadzone_xy":[0.,0.]},
        "maximum_environment_steps":36000, "scheduled_maximum_control_steps":7872,
        "maximum_controlled_resets":72, "maximum_simulation_frames":2016000,
        "minimum_complete_windows_per_task_per_arm":1, "witnesses_per_execution":3,
        "source_manifest":SOURCE+"/manifest.json",
        "source_manifest_id":"2406a8e68db6e603bd85443b0587354cf9f3f4d78a787b3de096a0323e3c405e",
        "source_audit":SOURCE+"/audit/record_audit.json",
        "source_audit_sha256":"a6fef649bacd0677644e43e91b80c82ae68f05bfa4bffaa7b246272899c777cc",
        "component_review":COMPONENT,
        "component_review_sha256":"b82ca2b07bc6cc281b42cc03de968d9d427d4cf6d4b71f820476e610319b57ea",
        "historical_nominal_cost":{"environment_steps":3840,"controlled_resets":480,"all_reset_calls":24480,"simulation_frames":12259200},
        "new_api_calls":0,"new_nominal_training":0,"new_selector_fits":0,"policy_updates":0,
        "output_root":"outputs/local_reprobe/qualification_v1"}


def destination(config, variant):
    if variant not in VARIANTS: raise ValueError("unknown private allocation")
    return config["fault_oracle" if variant.startswith("UNCHANGED_") else "changed_fault_oracle"]


def validate(config):
    if digest(config) != digest(expected_config()): raise ValueError("registered stale-reprobe allocation changed")


def sources(config):
    validate(config);previous,models = prior.load(ROOT/config["source_manifest"])
    if previous["manifest_id"] != config["source_manifest_id"]: raise ValueError("wrong physical qualification source")
    if sha(ROOT/config["source_audit"]) != config["source_audit_sha256"]: raise ValueError("source audit changed")
    audit = read(ROOT/config["source_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "NOT_QUALIFIED": raise ValueError("record-audited negative stale-correction source required")
    for name,value in audit["collection_artifact_sha256"].items():
        if sha((ROOT/config["source_manifest"]).parent/"collection"/name) != value: raise ValueError("source records changed")
    if sha(ROOT/COMPONENT) != config["component_review_sha256"]: raise ValueError("software reference changed")
    review = read(ROOT/COMPONENT)
    if review["status"] != "PASSED_SOFTWARE_REFERENCE_ONLY" or review["tests_passed"] != 1199: raise ValueError("software source required")
    for row in review["files"]:
        if sha(ROOT/row["path"]) != row["sha256"]: raise ValueError("frozen reference changed: "+row["path"])
    return previous,models


def clean():
    if git("status","--porcelain","--untracked-files=no"): raise ValueError("clean committed source required")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked for name in REQUIRED): raise ValueError("complete committed protocol and implementation required")
    if git("ls-files","--others","--exclude-standard","src","scripts","tests","configs/local_reprobe",PROTOCOL):
        raise ValueError("uncommitted stale-reprobe source")


def load(path):
    manifest = read(path);validate(manifest["config"])
    if digest({k:v for k,v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]: raise ValueError("manifest changed")
    for name,value in manifest["input_sha256"].items():
        if sha(ROOT/name) != value: raise ValueError("frozen input changed: "+name)
    previous,models = sources(manifest["config"])
    for key in ("library_source_sha256","native_library_sha256","policy_sha256"):
        if manifest[key] != previous[key]: raise ValueError("runtime binding changed")
    return manifest,models


COMPACT = prior.COMPACT
def compact(row): return {k:row[k] for k in COMPACT}


def method(variant):
    if variant not in VARIANTS: raise ValueError("unknown method allocation")
    return variant.split("_",1)[1]
