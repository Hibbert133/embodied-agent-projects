"""Generate an immutable manifest for the ACR retry-utility replication."""

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

from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


CONFIG_PATH = Path("configs/probemem_acr/retry_utility_replication_v1.json")
IMPLEMENTATION_PATHS = (
    Path("scripts/run_probemem_acr_retry_utility_replication.py"),
    Path("scripts/analyze_probemem_acr_retry_utility_replication.py"),
    Path("scripts/analyze_probemem_acr_failure_localization.py"),
    Path("scripts/run_probemem_v2_smoke.py"),
    Path("src/probemem/intervention_utility.py"),
    Path("src/reasoning/evidence.py"),
    Path("src/rollout/__init__.py"),
    Path("src/rollout/engine.py"),
)
INPUT_PATHS = (
    Path("configs/autoresearch/default_recovery_config.json"),
    Path("outputs/autoresearch/noise_calibration/selected.json"),
)


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("replication manifest requires a completely clean worktree")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_probemem_acr_retry_replication_seeds.py")],
            cwd=ROOT, check=True,
        )
        config = json.loads((ROOT / CONFIG_PATH).read_text(encoding="utf-8"))
        start, stop = config["seed_partitions"]["development_replication"]
        if [start, stop] != [1400, 1499]:
            raise ValueError("replication development seeds must remain 1400--1499")
        namespaces = config["random_namespaces"]
        units = [
            {
                "episode_id": index + 1,
                "environment_seed": seed,
                "condition_id_oracle": "fault_05",
                "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
                "diagnostic_probe_seed": _seed(seed, int(namespaces["registered_probe"])),
                "paired_verification_seed": _seed(seed, int(namespaces["paired_verification"])),
            }
            for index, seed in enumerate(range(start, stop + 1))
        ]
        commit = _git("rev-parse", "HEAD")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"acr_retry_replication_{timestamp}_{commit[:12]}"
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "experiment_run_id": run_id,
            "source_git_commit": commit,
            "created_at_utc": timestamp,
            "config_path": CONFIG_PATH.as_posix(),
            "config_sha256": _sha256(ROOT / CONFIG_PATH),
            "implementation_sha256": {path.as_posix(): _sha256(ROOT / path) for path in IMPLEMENTATION_PATHS},
            "input_sha256": {path.as_posix(): _sha256(ROOT / path) for path in INPUT_PATHS},
            "population_units": units,
            "reserved_seed_ranges_not_executed": {
                "validation": config["seed_partitions"]["validation_reserved"],
                "heldout": config["seed_partitions"]["heldout_reserved"],
            },
            "registered_endpoint_hash": _canonical_hash(config["registered_directional_hypotheses"]),
            "claim_scope": config["claim_scope"],
        }
        manifest["manifest_id"] = _canonical_hash(manifest)
        run_dir = ROOT / "outputs/probemem_acr/retry_replication_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest_id: {manifest['manifest_id']}")
        print(f"experiment_run_id: {run_id}")
        print(f"manifest: {run_dir / 'manifest.json'}")
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
