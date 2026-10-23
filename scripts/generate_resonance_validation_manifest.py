"""Generate the immutable one-shot ProbeMem-ACR validation manifest."""

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

from scripts.check_probemem_acr_resonance_validation_seeds import validation_seeds  # noqa: E402
from scripts.run_probemem_v2_smoke import _seed  # noqa: E402


CONFIG_PATH = Path("configs/probemem_acr/resonance_validation_v1.json")
IMPLEMENTATION_PATHS = (
    Path("scripts/check_probemem_acr_resonance_validation_seeds.py"),
    Path("scripts/generate_resonance_validation_manifest.py"),
    Path("scripts/run_resonance_validation.py"),
    Path("scripts/analyze_resonance_validation.py"),
    Path("scripts/render_resonance_validation_figures.py"),
    Path("scripts/run_probemem_acr_utility_stability.py"),
    Path("scripts/run_probemem_v2_smoke.py"),
    Path("src/probemem/resonance_policy.py"),
    Path("src/reasoning/evidence.py"),
    Path("src/reasoning/structured_evidence.py"),
    Path("src/rollout/engine.py"),
)
INPUT_PATHS = (
    Path("configs/autoresearch/default_recovery_config.json"),
    Path("outputs/autoresearch/noise_calibration/selected.json"),
    Path("docs/protocols/seed_registry.json"),
)


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_population_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    namespaces = config["random_namespaces"]
    return [
        {
            "episode_id": index,
            "environment_seed": seed,
            "condition_id_oracle": config["registered_condition"],
            "initial_perturbation_seed": _seed(seed, int(namespaces["initial_perturbation"])),
            "diagnostic_probe_seed": _seed(seed, int(namespaces["registered_probe"])),
            "first_verification_seed": _seed(seed, int(namespaces["first_verification"])),
            "paired_second_verification_seed": _seed(seed, int(namespaces["paired_second_verification"])),
        }
        for index, seed in enumerate(validation_seeds(config), start=1)
    ]


def main() -> int:
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("validation manifest requires a clean worktree")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_probemem_acr_resonance_validation_seeds.py")],
            cwd=ROOT, check=True,
        )
        config = json.loads((ROOT / CONFIG_PATH).read_text(encoding="utf-8"))
        units = build_population_units(config)
        if len(units) != int(config["population"]["expected_initial_units"]):
            raise ValueError("manifest population differs from frozen size")
        heldout = set(range(3100, 3200))
        if any(int(unit["environment_seed"]) in heldout for unit in units):
            raise ValueError("manifest attempts to execute held-out seed")
        commit = _git("rev-parse", "HEAD")
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"acr_resonance_validation_{timestamp}_{commit[:12]}"
        manifest: dict[str, Any] = {
            "schema_version": 1,
            "experiment_run_id": run_id,
            "source_git_commit": commit,
            "created_at_utc": timestamp,
            "config_path": CONFIG_PATH.as_posix(),
            "config_sha256": _sha(ROOT / CONFIG_PATH),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION_PATHS},
            "input_sha256": {path.as_posix(): _sha(ROOT / path) for path in INPUT_PATHS},
            "population_units": units,
            "heldout_seed_range_not_executed": config["heldout_reserved_not_executed"],
            "namespace_hash": _hash(config["random_namespaces"]),
            "frozen_rule_hash": _hash(config["frozen_status_rule"]),
            "promotion_gate_hash": _hash(config["promotion_gate"]),
            "development_manifest_id": "747da99f8929aa9c17159c4af220ee5afdfab4ca93866d673bf778debd5ca839",
            "claim_scope": config["claim_scope"],
        }
        manifest["manifest_id"] = _hash(manifest)
        run_dir = ROOT / "outputs/probemem_acr/resonance_validation_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest_id: {manifest['manifest_id']}")
        print(f"experiment_run_id: {run_id}")
        print(f"manifest: {run_dir / 'immutable_manifest.json'}")
        return 0
    except (KeyError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError, subprocess.CalledProcessError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
