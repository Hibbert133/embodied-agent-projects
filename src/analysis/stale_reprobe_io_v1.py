"""Matched unchanged/changed actuator qualification, with frozen prior versions."""
from src.analysis import physical_reprobe_io_v1 as prior
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY, TASKS, expected_layers = prior.IDENTITY, prior.TASKS, prior.expected_layers
VARIANTS = ("UNCHANGED", "CHANGED")
CONFIG = ROOT / "configs/stale_reprobe/qualification_v1.json"
PROTOCOL = "docs/protocols/stale_reprobe_execution_qualification_v1.md"
SOURCE = "outputs/physical_reprobe/qualification_v1/physical_reprobe_20261019T120619Z_e6ffa2f4deae"
COMPONENT = "outputs/warm_response_reference/validation_v1/delivery_review_v1.json"
REQUIRED = ("src/analysis/stale_reprobe_io_v1.py", "src/analysis/stale_reprobe_context_v1.py",
    "scripts/qualify_stale_reprobe_v1.py", "scripts/audit_stale_reprobe_v1.py",
    "tests/test_stale_reprobe_qualification_v1.py", PROTOCOL)


def population():
    return [{"unit":3*j+i, "task":task, "seed":22600+3*j+i, "variant":variant, "planned_boundary":boundary}
        for j,boundary in enumerate((16,32,64)) for i,task in enumerate(TASKS) for variant in VARIANTS]


def expected_config():
    return {"protocol_id":"stale_reprobe_execution_qualification_v1",
        "purpose":"MATCHED_REACQUISITION_AFTER_STALE_CORRECTION_NOT_MODEL_OR_TASK_UTILITY",
        "cases":population(), "reserved_seeds":[22609,22799], "executions":18, "paired_units":9,
        "logical_total_steps":500, "noise_std":.05, "noise_namespace":47001,
        "fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]], "bias_xy":[.12,-.08], "deadzone_xy":[0.,0.]},
        "changed_fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]], "bias_xy":[-.12,.08], "deadzone_xy":[0.,0.]},
        "maximum_environment_steps":9000, "scheduled_maximum_control_steps":1968,
        "maximum_controlled_resets":18, "maximum_simulation_frames":504000,
        "minimum_complete_windows_per_task_per_arm":1, "witnesses_per_execution":3,
        "source_manifest":SOURCE+"/manifest.json",
        "source_manifest_id":"612f593437f5e8f6ecd00a0d1d14e009daba92b661297d89ac642ed9c3ddbf61",
        "source_audit":SOURCE+"/audit/record_audit.json",
        "source_audit_sha256":"53c359cb43c8c14154d22780b72bb6ec8b51f451390175707bc45c022ea8f417",
        "component_review":COMPONENT,
        "component_review_sha256":"b82ca2b07bc6cc281b42cc03de968d9d427d4cf6d4b71f820476e610319b57ea",
        "historical_nominal_cost":{"environment_steps":3840,"controlled_resets":480,"all_reset_calls":24480,"simulation_frames":12259200},
        "new_api_calls":0,"new_nominal_training":0,"new_selector_fits":0,"policy_updates":0,
        "output_root":"outputs/stale_reprobe/qualification_v1"}


def destination(config, variant):
    if variant not in VARIANTS: raise ValueError("unknown private allocation")
    return config["fault_oracle" if variant == "UNCHANGED" else "changed_fault_oracle"]


def validate(config):
    if digest(config) != digest(expected_config()): raise ValueError("registered stale-reprobe allocation changed")


def sources(config):
    validate(config);previous,models = prior.load(ROOT/config["source_manifest"])
    if previous["manifest_id"] != config["source_manifest_id"]: raise ValueError("wrong physical qualification source")
    if sha(ROOT/config["source_audit"]) != config["source_audit_sha256"]: raise ValueError("source audit changed")
    audit = read(ROOT/config["source_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "QUALIFIED": raise ValueError("qualified static source required")
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
    if git("ls-files","--others","--exclude-standard","src","scripts","tests","configs/stale_reprobe",PROTOCOL):
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


COMPACT = prior.COMPACT + ("context_applied",)
def compact(row): return {k:row[k] for k in COMPACT}
