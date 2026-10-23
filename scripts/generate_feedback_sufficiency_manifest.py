"""Generate an immutable manifest for the feedback-sufficiency audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_probemem_acr_feedback_sufficiency_seeds import development_seeds  # noqa: E402
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


CONFIG_PATH = Path("configs/probemem_acr/verification_feedback_sufficiency_development_v1.json")
IMPLEMENTATION_PATHS = (
    Path("scripts/check_probemem_acr_feedback_sufficiency_seeds.py"),
    Path("scripts/generate_feedback_sufficiency_manifest.py"),
    Path("scripts/run_feedback_sufficiency_audit.py"),
    Path("scripts/analyze_feedback_sufficiency_audit.py"),
    Path("scripts/run_probemem_acr_utility_stability.py"),
    Path("scripts/run_probemem_v2_smoke.py"),
    Path("src/reasoning/structured_evidence.py"),
    Path("src/rollout/engine.py"),
)
INPUT_PATHS = (
    Path("configs/autoresearch/default_recovery_config.json"),
    Path("outputs/autoresearch/noise_calibration/selected.json"),
    Path("docs/protocols/seed_registry.json"),
)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_population_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    ns = config["random_namespaces"]
    count = int(config["first_retry_realizations"])
    units = []
    for episode_id, seed in enumerate(development_seeds(config), start=1):
        units.append({
            "episode_id": episode_id,
            "environment_seed": seed,
            "condition_id_oracle": config["registered_condition"],
            "initial_perturbation_seed": _seed(seed, int(ns["initial_perturbation"])),
            "diagnostic_probe_seed": _seed(seed, int(ns["registered_probe"])),
            "first_verification_seeds": [_seed(seed, int(ns["first_verification_start"]) + i) for i in range(count)],
            "paired_second_verification_seeds": [_seed(seed, int(ns["paired_second_verification_start"]) + i) for i in range(count)],
        })
    return units


def main() -> int:
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("manifest requires a clean worktree")
        subprocess.run([sys.executable, str(ROOT / "scripts/check_probemem_acr_feedback_sufficiency_seeds.py")], cwd=ROOT, check=True)
        config = json.loads((ROOT / CONFIG_PATH).read_text(encoding="utf-8"))
        units = build_population_units(config)
        if len(units) != int(config["stopping_rule"]["maximum_initial_units"]):
            raise ValueError("manifest population differs from frozen maximum")
        forbidden = set(range(3100, 3200)) | set(range(3500, 3600))
        if {int(row["environment_seed"]) for row in units} & forbidden:
            raise ValueError("manifest contains reserved seed")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"acr_feedback_sufficiency_{stamp}_{commit[:12]}"
        manifest: dict[str, Any] = {
            "schema_version": 1, "experiment_run_id": run_id,
            "source_git_commit": commit, "created_at_utc": stamp,
            "config_path": CONFIG_PATH.as_posix(), "config_sha256": _sha(ROOT / CONFIG_PATH),
            "implementation_sha256": {p.as_posix(): _sha(ROOT / p) for p in IMPLEMENTATION_PATHS},
            "input_sha256": {p.as_posix(): _sha(ROOT / p) for p in INPUT_PATHS},
            "population_units": units,
            "namespace_hash": _hash(config["random_namespaces"]),
            "analysis_hash": _hash(config["analysis"]),
            "completion_gate_hash": _hash(config["completion_gate"]),
            "claim_scope": config["claim_scope"],
        }
        manifest["manifest_id"] = _hash(manifest)
        run_dir = ROOT / "outputs/probemem_acr/feedback_sufficiency_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest_id: {manifest['manifest_id']}")
        print(f"experiment_run_id: {run_id}")
        print(f"manifest: {run_dir / 'immutable_manifest.json'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
