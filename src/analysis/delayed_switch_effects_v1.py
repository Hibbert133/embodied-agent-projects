"""Evaluator-only allocation, frozen sources and fixed-switch effect statistics.

No policy learner. Single realized outcomes do not identify individual expected
effects, and selecting the best observed branch is not a deployable policy.
"""
from pathlib import Path
import numpy as np

from src.analysis import delayed_qualification_io_v2 as prior
from src.probe.cache_acquisition_evidence_v1 import digest
from src.rollout.chronological_faults import states

ROOT = prior.ROOT
read, write, sha, git = prior.read, prior.write, prior.sha, prior.git
IDENTITY = prior.IDENTITY
CONFIG = ROOT / "configs/delayed_switch_effects/development_v1.json"
PROTOCOL = "docs/protocols/delayed_switch_effects_development_v1.md"
SOURCE = "outputs/delayed_intervention/qualification_v2/delayed_intervention_v2_20261019T090014Z_1ba6b7b81e55"
METHODS = ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED")
TASKS = ("push-v3", "reach-v3", "door-open-v3")
FAMILIES = ("BIAS", "COLUMN_Y", "DEADZONE")
REQUIRED = ("src/analysis/delayed_switch_effects_v1.py", "scripts/run_delayed_switch_effects_v1.py",
    "scripts/audit_delayed_switch_effects_v1.py", "tests/test_delayed_switch_effects_v1.py", PROTOCOL)


def expected_config():
    return {"protocol_id": "delayed_switch_effects_development_v1", "purpose": "ACTUAL_FIXED_BOUNDARY_EFFECTS_NOT_LEARNED_POLICY",
        "methods": list(METHODS), "tasks": list(TASKS), "families": list(FAMILIES), "replicates_per_family": 12,
        "endpoints_per_generator": 2, "generator_seed_start": 71001, "task_seed_start": 21800, "task_seed_end": 22015,
        "reserved_task_seeds": [22016, 22399], "independent_generator_groups": 36, "units": 216, "executions": 648,
        "boundary_step": 16, "logical_total_steps": 500, "noise_std": .05, "noise_namespace": 47001,
        "maximum_environment_steps": 324000, "maximum_controlled_resets": 648, "maximum_simulation_frames": 18144000,
        "bootstrap_samples": 10000, "bootstrap_seed": 20261023, "source_manifest": SOURCE + "/manifest.json",
        "source_manifest_id": "ae549ee2e9cfdcac76a8f565db1f04321c22f6ebaac93d18694eec783aee6b6a",
        "source_audit": SOURCE + "/audit/record_audit.json",
        "source_audit_sha256": "b5d30f1e8976cef0d88d5429948990128cc52fd7a684ffacd81606749603a78f",
        "historical_nominal_cost": {"environment_steps": 3840, "controlled_resets": 480, "all_reset_calls": 24480, "simulation_frames": 12259200},
        "historical_design_preparation": {"enumerations": 3, "candidate_rows": 432},
        "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0,
        "output_root": "outputs/delayed_switch_effects/development_v1"}


def validate(config):
    if digest(config) != digest(expected_config()):
        raise ValueError("registered allocation, comparison or budget differs")


def population():
    result = []
    for replicate in range(12):
        for family in FAMILIES:
            group = replicate * 3 + FAMILIES.index(family)
            endpoints = states(71001 + group, family)
            for endpoint, fault in enumerate(endpoints):
                for task in TASKS:
                    unit = len(result)
                    result.append({"unit": unit, "task": task, "seed": 21800 + unit, "group": group,
                        "family_oracle": family, "endpoint_oracle": endpoint, "generator_seed_oracle": 71001 + group,
                        "fault_oracle": fault})
    return result


def sources(config):
    validate(config)
    manifest, models = prior.load(ROOT / config["source_manifest"])
    if manifest["manifest_id"] != config["source_manifest_id"] or sha(ROOT / config["source_audit"]) != config["source_audit_sha256"]:
        raise ValueError("qualified source identity differs")
    audit = read(ROOT / config["source_audit"])
    if audit["integrity"] != "PASSED" or audit["qualification"] != "QUALIFIED":
        raise ValueError("completed live execution qualification required")
    for key in IDENTITY:
        if audit[key] != manifest[key]: raise ValueError("source audit identity differs")
    for name, expected in audit["collection_artifact_sha256"].items():
        if sha((ROOT / config["source_manifest"]).parent / "collection" / name) != expected:
            raise ValueError("qualified source raw artifact changed")
    return manifest, models


def clean():
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("clean committed research source required")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked for name in (*REQUIRED, CONFIG.relative_to(ROOT).as_posix())):
        raise ValueError("complete committed study required")
    if git("ls-files", "--others", "--exclude-standard", "src", "scripts", "tests", "configs/delayed_switch_effects", PROTOCOL):
        raise ValueError("uncommitted study implementation")


def load(path):
    manifest = read(path)
    if digest({k: v for k, v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("manifest changed")
    validate(manifest["config"])
    if digest(manifest["allocation_oracle"]) != digest(population()):
        raise ValueError("frozen allocation differs")
    for name, expected in manifest["input_sha256"].items():
        if sha(ROOT / name) != expected: raise ValueError("frozen study input changed: " + name)
    previous, models = sources(manifest["config"])
    for key in ("library_source_sha256", "native_library_sha256", "policy_sha256"):
        if manifest[key] != previous[key]: raise ValueError("qualified runtime changed")
    return manifest, models


def compact(row):
    keys = ("unit", "task", "seed", "variant", "completed", "success", "stopped", "total_steps", "deadline_loss",
        "boundary_ready", "host_attempts", "host_returned", "policy_queries", "parameter_fit_attempts", "parameter_fit_results", "optimizer_nfev")
    return {k: row[k] for k in keys}


def statistics(rows):
    specs = population()
    expected = [(s["unit"], s["task"], s["seed"], method) for s in specs for method in METHODS]
    if [(r["unit"], r["task"], r["seed"], r["variant"]) for r in rows] != expected:
        raise ValueError("complete ordered three-branch population required")
    for row in rows:
        for key in ("completed", "success", "stopped", "boundary_ready"):
            if type(row[key]) is not bool: raise ValueError("ordinary outcome booleans required")
        if not row["completed"] or type(row["total_steps"]) is not int or not 0 <= row["total_steps"] <= 500:
            raise ValueError("complete bounded episode required")
        if type(row["deadline_loss"]) is not int or row["deadline_loss"] != (row["total_steps"] if row["success"] else 500):
            raise ValueError("failure penalty differs")
    losses = np.array([r["deadline_loss"] for r in rows], dtype=float).reshape(216, 3)
    group_means = losses.reshape(36, 6, 3).mean(axis=1)
    rng = np.random.default_rng(20261023)
    draws = np.zeros((10000, 3))
    for fi in range(3):
        ids = np.arange(fi, 36, 3)
        sampled = rng.choice(ids, size=(10000, 12), replace=True)
        draws += group_means[sampled].sum(axis=1)
    draws /= 36
    methods = []
    for index, method in enumerate(METHODS):
        chosen = [r for r in rows if r["variant"] == method]
        methods.append({"variant": method, "executions": len(chosen), "successes": sum(r["success"] for r in chosen),
            "failures": sum(not r["success"] for r in chosen), "stops": sum(r["stopped"] for r in chosen),
            "unavailable_boundaries": sum(not r["boundary_ready"] for r in chosen),
            "mean_deadline_loss": float(losses[:, index].mean()), "actual_control_steps": sum(r["total_steps"] for r in chosen)})
    contrasts = []
    for index in (1, 2):
        delta = losses[:, index] - losses[:, 0]
        contrasts.append({"left": METHODS[index], "right": METHODS[0], "primary": index == 1,
            "multiplicity": "PRIMARY" if index == 1 else "UNADJUSTED_SECONDARY",
            "mean_loss_difference": float(delta.mean()), "ci95": np.quantile(draws[:, index] - draws[:, 0], [.025, .975]).tolist(),
            "realized_better_units": int((delta < 0).sum()), "realized_worse_units": int((delta > 0).sum()),
            "realized_tied_units": int((delta == 0).sum())})
    paired = [{**{k: spec[k] for k in ("unit", "task", "seed", "group", "family_oracle", "endpoint_oracle")},
        "losses": dict(zip(METHODS, map(int, losses[i]))), "switch_minus_continue": int(losses[i, 1] - losses[i, 0]),
        "uncorrected_minus_continue": int(losses[i, 2] - losses[i, 0])} for i, spec in enumerate(specs)]
    return {"units": 216, "executions": 648, "independent_generator_groups": 36, "methods": methods, "contrasts": contrasts,
        "paired_rows": paired, "failures": [r for r in rows if not r["success"]],
        "bootstrap_samples": 10000, "bootstrap_seed": 20261023, "interval_scope": "FAMILY_STRATIFIED_WHOLE_GENERATOR_GROUP",
        "learned_policy_evaluation": False, "algorithm_promotion_claim": False, "individual_expected_effect_identified": False}
