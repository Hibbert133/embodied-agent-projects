"""Matched unchanged/changed actuator qualification, with frozen prior versions."""
from src.analysis import stale_reprobe_io_v1 as prior
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY, TASKS, expected_layers = prior.IDENTITY, prior.TASKS, prior.expected_layers
VARIANTS = ("UNCHANGED_PD", "UNCHANGED_PID", "CHANGED_PD", "CHANGED_PID")
CONFIG = ROOT / "configs/integral_reprobe/qualification_v1.json"
PROTOCOL = "docs/protocols/integral_reprobe_execution_qualification_v1.md"
SOURCE = "outputs/stale_reprobe/qualification_v1/stale_reprobe_20261019T125614Z_fdb617869c37"
COMPONENT = "outputs/warm_response_reference/validation_v1/delivery_review_v1.json"
REQUIRED = ("src/analysis/integral_reprobe_io_v1.py", "src/analysis/integral_reprobe_host_v1.py",
    "src/probe/integral_reprobe_v1.py", "scripts/qualify_integral_reprobe_v1.py",
    "scripts/audit_integral_reprobe_v1.py", "tests/test_integral_reprobe_qualification_v1.py",
    "tests/test_integral_reprobe_v1.py", PROTOCOL)


def population():
    return [{"unit":3*j+i, "task":task, "seed":22800+3*j+i, "variant":variant, "planned_boundary":boundary}
        for j,boundary in enumerate((16,32,64)) for i,task in enumerate(TASKS) for variant in VARIANTS]


def expected_config():
    return {"protocol_id":"integral_reprobe_execution_qualification_v1",
        "purpose":"MATCHED_STANDARD_INTEGRAL_RELOCATION_NOT_MODEL_OR_TASK_UTILITY",
        "cases":population(), "reserved_seeds":[22809,22999], "executions":36, "paired_units":9, "integral_gain":.32, "integral_limit":.5,
        "logical_total_steps":500, "noise_std":.05, "noise_namespace":47001,
        "fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]], "bias_xy":[.12,-.08], "deadzone_xy":[0.,0.]},
        "changed_fault_oracle":{"matrix_xy":[[1.,0.],[0.,1.]], "bias_xy":[-.12,.08], "deadzone_xy":[0.,0.]},
        "maximum_environment_steps":18000, "scheduled_maximum_control_steps":3936,
        "maximum_controlled_resets":36, "maximum_simulation_frames":1008000,
        "minimum_complete_windows_per_task_per_arm":1, "witnesses_per_execution":3,
        "source_manifest":SOURCE+"/manifest.json",
        "source_manifest_id":"5ea66255714e4c3011ee21e5dbdf01b6069f3bbbb94693a33c74cd42e5390b60",
        "source_audit":SOURCE+"/audit/record_audit.json",
        "source_audit_sha256":"fb142319771a488c64df4f1712021fcdee1b08c13104ea7c69bc9584d2c98453",
        "component_review":COMPONENT,
        "component_review_sha256":"b82ca2b07bc6cc281b42cc03de968d9d427d4cf6d4b71f820476e610319b57ea",
        "historical_nominal_cost":{"environment_steps":3840,"controlled_resets":480,"all_reset_calls":24480,"simulation_frames":12259200},
        "new_api_calls":0,"new_nominal_training":0,"new_selector_fits":0,"policy_updates":0,
        "output_root":"outputs/integral_reprobe/qualification_v1"}


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
    if git("ls-files","--others","--exclude-standard","src","scripts","tests","configs/integral_reprobe",PROTOCOL):
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
    return variant.rsplit("_",1)[1]
