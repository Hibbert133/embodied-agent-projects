"""Generate an immutable manifest for one Calibrated Verifier v2 stage."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_probemem_v2_smoke import _seed  # noqa: E402

IMPLEMENTATION = (
    "scripts/generate_calibrated_verifier_manifest.py",
    "scripts/probemem_calibrated_runner.py",
    "scripts/run_calibrated_verifier_calibration.py",
    "scripts/run_calibrated_verifier_development.py",
    "scripts/analyze_calibrated_verifier.py",
    "scripts/render_calibrated_verifier_figures.py",
    "src/probemem_verifier/weighted_posterior.py",
    "src/probemem_verifier/posterior_comparison.py",
    "src/probemem_verifier/applicability.py",
    "src/probemem_verifier/calibrated_override_guard.py",
    "src/probemem_verifier/calibrated_policy.py",
    "src/probemem_verifier/admission.py",
    "src/probemem_verifier/candidate_verifier.py",
    "src/probemem_verifier/override_guard.py",
    "src/probemem_verifier/online_policy.py",
    "src/probemem/regime_memory.py",
)


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, stop = map(int, config["seed_range"])
    cycle = tuple(config.get("regime_cycle", ("A_bias_low_noise", "B_zero_mean_noise", "C_bias_dominant_mixed", "D_noise_dominant_mixed")))
    namespaces = config["random_namespaces"]
    units = []
    for index, seed in enumerate(range(start, stop + 1)):
        units.append({
            "unit_id": index + 1, "environment_seed": seed,
            "regime_id_oracle": cycle[index % len(cycle)],
            "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
            "diagnostic_probe_seed": _seed(seed, int(namespaces["registered_probe"])),
            "paired_verification_seed": _seed(seed, int(namespaces["paired_verification"])),
        })
    expected = 100 if config["stage"] == "calibration" else 200
    if len(units) != expected:
        raise ValueError("calibrated verifier manifest population capacity changed")
    return units


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("manifest generation requires a clean worktree")
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        stage = config["stage"]
        expected_status = "CALIBRATION_FROZEN_BEFORE_EXECUTION" if stage == "calibration" else "DEVELOPMENT_FROZEN_BEFORE_EXECUTION"
        if config["status"] != expected_status:
            raise RuntimeError("calibrated verifier stage is not executable")
        if stage == "prospective_development" and (not config.get("calibration_binding") or not config.get("frozen_thresholds")):
            raise RuntimeError("development lacks frozen calibration binding")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_calibrated_verifier_{stage}_{stamp}_{commit[:12]}"
        inputs = [config["seed_registry"], "docs/protocols/probemem_calibrated_verifier_v2.md"]
        if config.get("memory"):
            inputs.extend((config["memory"]["bootstrap_records"], config["recovery_policy_config"]))
        else:
            calibration_config = json.loads((ROOT / "configs/probemem_verifier/calibrated_v2_calibration.json").read_text(encoding="utf-8"))
            inputs.extend((calibration_config["memory"]["bootstrap_records"], calibration_config["recovery_policy_config"]))
        manifest = {
            "schema_version": 2, "experiment_run_id": run_id, "stage": stage,
            "created_at_utc": stamp, "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha(config_path),
            "implementation_sha256": {path: _sha(ROOT / path) for path in IMPLEMENTATION},
            "input_sha256": {path: _sha(ROOT / path) for path in inputs},
            "population_units": build_units(_expanded_config(config)),
        }
        manifest["manifest_id"] = _hash(manifest)
        output = ROOT / "outputs/probemem_calibrated_verifier" / ("calibration" if stage == "calibration" else "development") / "runs" / run_id
        output.mkdir(parents=True, exist_ok=False)
        path = output / "immutable_manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


def _expanded_config(config: dict[str, Any]) -> dict[str, Any]:
    if config["stage"] == "calibration":
        return config
    base = json.loads((ROOT / "configs/probemem_verifier/calibrated_v2_calibration.json").read_text(encoding="utf-8"))
    return {**base, **config, "random_namespaces": config["random_namespaces"]}


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
