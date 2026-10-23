"""Frozen I/O contract for the small live-intervention execution qualification."""

from pathlib import Path
import subprocess

from docs.paper.replay_short_probe_results_20261019 import verify_saved
from src.analysis import short_probe_study_io_v1 as source_io
from src.probe.cache_acquisition_evidence_v1 import digest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "configs/delayed_intervention/qualification_v1.json"
PROTOCOL = "docs/protocols/delayed_intervention_qualification_v1.md"
SOFTWARE = "outputs/delayed_intervention/software_v1/boundary_composition_v1/receipt.json"
COLLECTOR_SOFTWARE = "outputs/delayed_intervention/software_v1/collector_audit_v3/receipt.json"
IDENTITY = ("experiment_run_id", "manifest_id", "source_git_commit")
VARIANTS = ("CONTINUE_CURRENT", "SWITCH_SAVED", "RUN_UNCORRECTED", "STOP", "DIRECT_CURRENT")
CASES = ({"task": "push-v3", "seed": 21400}, {"task": "reach-v3", "seed": 21401},
         {"task": "door-open-v3", "seed": 21402})
REQUIRED = ("scripts/qualify_delayed_intervention_v1.py", "scripts/audit_delayed_intervention_v1.py",
            "tests/test_delayed_intervention_qualification_v1.py", PROTOCOL,
            "src/analysis/delayed_qualification_io_v1.py",
            "docs/prototypes/delayed_intervention_v1/boundary_prefix.py",
            "docs/prototypes/delayed_intervention_v1/boundary_host.py")
read, write, sha = source_io.read, source_io.write, source_io.sha


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def validate(config):
    fixed = {"protocol_id": "delayed_intervention_qualification_v1",
        "purpose": "CONTINUOUS_MIDTRAJECTORY_EXECUTION_QUALIFICATION_NOT_TASK_BENEFIT",
        "tasks_and_seeds": list(CASES), "reserved_seeds": [21403, 21599], "variants": list(VARIANTS),
        "boundary_step": 16, "logical_total_steps": 500, "noise_std": .05, "noise_namespace": 47001,
        "fault_oracle": {"matrix_xy": [[1., 0.], [0., 1.]], "bias_xy": [.12, -.08], "deadzone_xy": [0., 0.]},
        "maximum_environment_steps": 7500, "maximum_controlled_resets": 15, "maximum_simulation_frames": 420000,
        "new_api_calls": 0, "new_nominal_training": 0, "new_selector_fits": 0, "policy_updates": 0,
        "required_ready_boundaries": 15, "required_direct_comparison_tasks": 3,
        "minimum_tasks_with_three_distinct_first_commands": 1, "source_amortization_units_per_variant": 3,
        "historical_nominal_cost": {"environment_steps": 3840, "controlled_resets": 480, "all_reset_calls": 24480, "simulation_frames": 12259200},
        "historical_design_preparation": {"enumerations": 3, "candidate_rows": 432},
        "output_root": "outputs/delayed_intervention/qualification_v1"}
    if any(digest(config.get(k)) != digest(v) for k, v in fixed.items()):
        raise ValueError("registered live-qualification scope changed")
    if set(config) != set(fixed) | {"source_manifest", "source_completion", "nominal_models", "nominal_models_sha256"}:
        raise ValueError("unregistered configuration field")


def sources(config):
    prior, bindings, _ = verify_saved("MAIN")
    if (ROOT / config["source_manifest"]).resolve() != (ROOT / "outputs/short_probe_reference/development_v1" / prior["experiment_run_id"] / "manifest.json").resolve():
        raise ValueError("foreign source manifest")
    if (ROOT / config["source_completion"]).resolve() != (ROOT / config["source_manifest"]).parent / "main_pipeline_completion.json":
        raise ValueError("foreign source completion path")
    if config["nominal_models"] != prior["config"]["nominal_models"] or config["nominal_models_sha256"] != prior["config"]["nominal_models_sha256"]:
        raise ValueError("foreign nominal model")
    completion = read(ROOT / config["source_completion"])
    if (any(completion[k] != prior[k] for k in IDENTITY) or completion["status"] != "COMPLETED_FOR_REVIEW"
            or [s["stage"] for s in completion["steps"]] != ["collect", "record_audit", "analyze", "numeric_audit", "report"]
            or completion["failure"] is not None or any(s["returncode"] for s in completion["steps"])):
        raise ValueError("completed source reference study required")
    _, models, designs = source_io.load(ROOT / config["source_manifest"])
    if any(v["selected_candidate_id"] != "FOUR_002" for v in designs.values()):
        raise ValueError("registered source four-step program differs")
    for receipt_path, count in ((SOFTWARE, 12), (COLLECTOR_SOFTWARE, 11)):
        software = read(ROOT / receipt_path)
        if software["status"] != "PASSED" or software["tests_run"] != count or software["failures"] or software["errors"]:
            raise ValueError("passed composition and collector/auditor software checks required")
        for name, expected in software["source_sha256"].items():
            if sha(ROOT / name) != expected:
                raise ValueError("software-qualified source changed: " + name)
        for name, expected in software["artifact_sha256"].items():
            if sha((ROOT / receipt_path).parent / name) != expected:
                raise ValueError("software qualification artifact changed")
    return prior, models, bindings


def clean():
    if git("status", "--porcelain", "--untracked-files=no"):
        raise ValueError("clean tracked checkout required before prepare or collection")
    tracked = set(git("ls-files").splitlines())
    if any(name not in tracked or not (ROOT / name).is_file() for name in REQUIRED):
        raise ValueError("complete committed collector, auditor, protocol and tests required")
    if git("ls-files", "--others", "--exclude-standard", "src", "scripts", "tests", "configs/delayed_intervention", "docs/prototypes/delayed_intervention_v1", PROTOCOL):
        raise ValueError("all qualification source must be committed before freezing")


def load(path):
    manifest = read(path);validate(manifest["config"])
    if digest({k: v for k, v in manifest.items() if k != "manifest_id"}) != manifest["manifest_id"]:
        raise ValueError("changed manifest identity")
    if any(sha(ROOT / name) != value for name, value in manifest["input_sha256"].items()):
        raise ValueError("frozen qualification input changed")
    prior, models, _ = sources(manifest["config"])
    if manifest["prior_manifest_id"] != prior["manifest_id"]:
        raise ValueError("source experiment differs")
    if any(manifest[k] != prior[k] for k in ("library_source_sha256", "native_library_sha256", "policy_sha256")):
        raise ValueError("qualified runtime bindings differ")
    return manifest, models
