"""Separate freeze for inspectable state-witness execution qualification."""
from pathlib import Path

from src.analysis import delayed_qualification_io_v1 as old
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = old.ROOT
CONFIG = ROOT / "configs/delayed_intervention/qualification_v2.json"
PROTOCOL = "docs/protocols/delayed_intervention_qualification_v2.md"
WITNESS_SOFTWARE = "outputs/continuous_state_witness/software_v1/inspectable_graph_v1/receipt.json"
PIPELINE_SOFTWARE = "outputs/continuous_state_witness/software_v1/qualification_v2_pipeline_v2/receipt.json"
PRIOR = "outputs/delayed_intervention/qualification_v1/delayed_intervention_20261019T081007Z_72cd966d73d9"
IDENTITY, VARIANTS = old.IDENTITY, old.VARIANTS
read, write, sha, git = old.read, old.write, old.sha, old.git
CASES = [{"task": "push-v3", "seed": 21600}, {"task": "reach-v3", "seed": 21601}, {"task": "door-open-v3", "seed": 21602}]
COMPONENT_RUNTIME = {
    ".venv/Lib/site-packages/gymnasium/core.py": "245745bf21d7b6f6f6d187260c17fd3c19988806ce12fc9c606b2bbe813d37a8",
    ".venv/Lib/site-packages/gymnasium/wrappers/common.py": "2a2cd78973296d5871af0ae1334f4c567cacef380bc69b4a759fcc29cbcff51a",
    ".venv/Lib/site-packages/metaworld/wrappers.py": "43d9e436dfb4826c11f8afcfe2ba5642f67212996dfe48dd869b352094f5d89c",
    ".venv/Lib/site-packages/metaworld/__init__.py": "8613586a1f5236a8c10079809d6ea94a2c2e597fcdb1fbd6241468419dba22d7"}
REQUIRED = ("scripts/qualify_delayed_intervention_v2.py", "scripts/audit_delayed_intervention_v2.py",
    "src/analysis/delayed_qualification_io_v2.py", "src/analysis/continuous_state_witness_v1.py",
    "tests/test_delayed_intervention_qualification_v2.py", "tests/test_continuous_state_witness_v1.py", PROTOCOL)


def expected_layers(task):
    base = {"push-v3": "metaworld.envs.sawyer_push_v3.SawyerPushEnvV3",
            "reach-v3": "metaworld.envs.sawyer_reach_v3.SawyerReachEnvV3",
            "door-open-v3": "metaworld.envs.sawyer_door_v3.SawyerDoorEnvV3"}[task]
    return ["gymnasium.wrappers.common.OrderEnforcing", "gymnasium.wrappers.common.PassiveEnvChecker",
        "metaworld.wrappers.CheckpointWrapper", "metaworld.wrappers.RandomTaskSelectWrapper",
        "gymnasium.wrappers.common.RecordEpisodeStatistics", "metaworld.wrappers.AutoTerminateOnSuccessWrapper",
        "gymnasium.wrappers.common.TimeLimit", base]


def validate(config):
    original = read(ROOT / "configs/delayed_intervention/qualification_v1.json")
    old.validate(original)
    expected = {**original, "protocol_id": "delayed_intervention_qualification_v2",
        "purpose": "CONTINUOUS_EXECUTION_WITH_INSPECTABLE_TIMING_PROJECTION_NOT_TASK_BENEFIT",
        "tasks_and_seeds": CASES, "reserved_seeds": [21603, 21799], "output_root": "outputs/delayed_intervention/qualification_v2",
        "prior_qualification_manifest": PRIOR + "/manifest.json",
        "prior_qualification_manifest_id": "764fa8ef1c65e0bef7d40b085641c0d5cf6c4318aa6fcd3a4278a545d6c4f8ab",
        "prior_record_audit": PRIOR + "/audit/record_audit.json",
        "prior_record_audit_sha256": "9f55468b17f6414d936d2348603c79da934c1234c72413c49b5566ca4ee5f6b0",
        "witness_schema": "continuous_state_witness_v1", "witnesses_per_execution": 3,
        "historical_qualification_v1_cost": {"environment_steps": 1377, "controlled_resets": 15, "all_reset_calls": 765, "simulation_frames": 389385}}
    if digest(config) != digest(expected): raise ValueError("registered v2 qualification differs")


def sources(config):
    if any(sha(ROOT / name) != expected for name, expected in COMPONENT_RUNTIME.items()):
        raise ValueError("reviewed wrapper/factory runtime changed")
    previous, models = old.load(ROOT / config["prior_qualification_manifest"])
    if previous["manifest_id"] != config["prior_qualification_manifest_id"]: raise ValueError("foreign qualification source")
    if sha(ROOT / config["prior_record_audit"]) != config["prior_record_audit_sha256"]: raise ValueError("prior result changed")
    audit = read(ROOT / config["prior_record_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "NOT_QUALIFIED": raise ValueError("preserve previous nonqualification")
    for name, expected in audit["collection_artifact_sha256"].items():
        if sha((ROOT / config["prior_qualification_manifest"]).parent / "collection" / name) != expected:
            raise ValueError("prior raw qualification artifact changed")
    for receipt_path, count in ((WITNESS_SOFTWARE, 13), (PIPELINE_SOFTWARE, 8)):
        receipt = read(ROOT / receipt_path)
        if receipt["status"] != "PASSED" or receipt["tests_run"] != count or receipt["failures"] or receipt["errors"]: raise ValueError("passed v2 software checks required")
        for name, expected in receipt["source_sha256"].items():
            if sha(ROOT / name) != expected: raise ValueError("qualified software changed: " + name)
        for name, expected in receipt["artifact_sha256"].items():
            if sha((ROOT / receipt_path).parent / name) != expected: raise ValueError("qualified artifact changed")
    return previous, models


def clean():
    if git("status", "--porcelain", "--untracked-files=no"): raise ValueError("clean committed implementation required")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked for name in REQUIRED): raise ValueError("complete committed v2 collector/auditor/tests required")
    if git("ls-files", "--others", "--exclude-standard", "src", "scripts", "tests", "configs/delayed_intervention", PROTOCOL):
        raise ValueError("uncommitted v2 implementation")


def load(path):
    manifest = read(path);validate(manifest["config"])
    if digest({k: v for k, v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("manifest identity differs")
    if any(sha(ROOT / name) != expected for name, expected in manifest["input_sha256"].items()): raise ValueError("frozen v2 input changed")
    previous, models = sources(manifest["config"])
    if previous["manifest_id"] != manifest["prior_manifest_id"]: raise ValueError("previous population differs")
    for key in ("library_source_sha256", "native_library_sha256", "policy_sha256"):
        if manifest[key] != previous[key]: raise ValueError("frozen qualified runtime differs")
    return manifest, models
