"""Pinned historical ARX bank and complete known source fees; no fitting."""

import hashlib
import json
from pathlib import Path

from src.probe.movement_model_binding_v1 import BoundMovementModelV1, TASK_MODEL_SHA256, canonical

SOURCE = "outputs/forward_prediction/baselines_v1/forward_prediction_20261014T064233Z_bb812df15401"
AUDIT = "outputs/forward_prediction/analysis_v1/audit.json"
SOURCE_PINS = {
    SOURCE + "/manifest.json": "0e959783ba08e7982f037e2abbd6a6502e80f6e86fcddb83dc74aa5c44aec788",
    SOURCE + "/models.json": "b3f2d7e69316dba65e722d74d49df25c7d651043e78bf4c0f6e1d37f1e599c80",
    AUDIT: "403c394dbb6abfffe811ed6c3354e5b78557d5af4bcbf541571441e057a562c2",
}
IDENTITY = {"experiment_run_id": "forward_prediction_20261014T064233Z_bb812df15401",
            "manifest_id": "d657fa9c3d0d6582f02a0dc7f346fdf7dbd013da977e93355bbacc7477a6868f",
            "source_git_commit": "bb812df15401fdaa702659294be1e457dd309758"}


def sha(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024*1024), b""):
            result.update(block)
    return result.hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def load_bank(root):
    """Validate all archived source artifacts before returning task-bound models."""
    root = Path(root).resolve()
    for name, expected in SOURCE_PINS.items():
        require(sha(root / name) == expected, "historical ARX source changed: " + name)
    read = lambda name: json.loads((root / name).read_text(encoding="utf-8"))
    audit, manifest, bank = read(AUDIT), read(SOURCE + "/manifest.json"), read(SOURCE + "/models.json")
    for value in (audit, manifest, bank):
        require(all(value[k] == expected for k, expected in IDENTITY.items()), "source identity changed")
    require(audit["integrity"] == "PASSED" and audit["status"] == "COMPLETED_FEASIBILITY_FAILED"
            and audit["training_sources_recomputed"] is True, "preserve audited but unqualified historical source")
    require(audit["model_sha256"] == SOURCE_PINS[SOURCE + "/models.json"]
            and bank["training_artifact_sha256"] == audit["artifact_sha256"]["TRAIN.jsonl.gz"], "wrong training provenance")
    bindings = dict(SOURCE_PINS)
    base = (root / SOURCE).resolve()
    for name, expected in audit["artifact_sha256"].items():
        path = (base / name).resolve()
        require(path.is_relative_to(base), "source artifact escapes its archive")
        require(sha(path) == expected, "historical ARX artifact changed: " + name)
        bindings[path.relative_to(root).as_posix()] = expected
    require(set(bank["models"]) == set(TASK_MODEL_SHA256), "wrong source task population")
    models = {task: BoundMovementModelV1(task, canonical(bank["models"][task]["LINEAR_ARX"])) for task in TASK_MODEL_SHA256}
    require(audit["physical_steps"] == 21010 and audit["environment_resets"] == 288
            and audit["old_offline_steps"] == 2304 and audit["old_offline_resets"] == 144, "source costs changed")
    costs = {
        "direct_source_collection": {"environment_steps": 21010, "controlled_resets": 288,
                                     "all_reset_calls": None, "simulation_frames": None},
        "legacy_comparison_source": {"environment_steps": 2304, "controlled_resets": 144,
                                     "all_reset_calls": None, "simulation_frames": None},
        "known_full_source_environment_steps": 23314,
        "known_full_source_controlled_resets": 432,
        "unknown_factory_and_native_costs_are_not_zero": True,
        "legacy_comparison_cost_policy": "Disclose and conservatively charge the source study's legacy comparison dependency separately from direct collection.",
    }
    return models, {**IDENTITY, "inputs": bindings, "task_model_sha256": dict(TASK_MODEL_SHA256),
                    "historical_precision_gate_passed": False, "physical_transfer_qualified": False,
                    "costs": costs, "new_model_fits": 0, "new_environment_steps": 0, "new_api_calls": 0}
