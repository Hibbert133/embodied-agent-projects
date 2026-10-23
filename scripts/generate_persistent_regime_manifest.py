"""Generate the immutable persistent-regime development manifest."""

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


CONFIG = Path("configs/probemem_acr/persistent_regime_development_v1.json")
IMPLEMENTATION = (
    Path("src/probemem/persistent_regime.py"), Path("scripts/generate_persistent_regime_manifest.py"),
    Path("scripts/run_persistent_regime_development.py"), Path("scripts/analyze_persistent_regime_development.py"),
    Path("scripts/run_probemem_v2_smoke.py"), Path("src/rollout/engine.py"),
)
INPUTS = (Path("configs/autoresearch/default_recovery_config.json"), Path("outputs/autoresearch/noise_calibration/selected.json"))


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_units(config: dict[str, Any]) -> list[dict[str, Any]]:
    start, end = map(int, config["seed_range"])
    ns = config["random_namespaces"]
    units = []
    episode_id = 0
    for seed in range(start, end + 1):
        for condition_index, condition in enumerate(config["conditions"]):
            episode_id += 1
            base = seed + condition_index * 100000
            units.append({
                "episode_id": episode_id, "environment_seed": seed, "condition_id_oracle": condition,
                "initial_perturbation_seed": _seed(base, int(ns["initial_perturbation"])),
                "diagnostic_probe_seed": _seed(base, int(ns["registered_probe"])),
                "paired_verification_seed": _seed(base, int(ns["paired_verification"])),
            })
    return units


def main() -> int:
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("manifest requires a clean worktree")
        config = json.loads((ROOT / CONFIG).read_text(encoding="utf-8"))
        units = build_units(config)
        if len(units) != 100:
            raise ValueError("persistent-regime manifest requires exactly 100 units")
        seeds = {int(unit["environment_seed"]) for unit in units}
        if seeds & set(range(3100, 3200)) or seeds & set(range(3950, 4000)):
            raise ValueError("manifest intersects held-out or reserved seeds")
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"acr_persistent_regime_{stamp}_{commit[:12]}"
        manifest = {
            "schema_version": 1, "experiment_run_id": run_id, "source_git_commit": commit,
            "created_at_utc": stamp, "config_path": CONFIG.as_posix(), "config_sha256": _sha(ROOT / CONFIG),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION},
            "input_sha256": {path.as_posix(): _sha(ROOT / path) for path in INPUTS},
            "population_units": units, "namespace_hash": _hash(config["random_namespaces"]),
            "rule_hash": _hash(config["frozen_mechanism_rule"]), "claim_scope": config["claim_scope"],
        }
        manifest["manifest_id"] = _hash(manifest)
        run_dir = ROOT / "outputs/probemem_acr/persistent_regime_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {run_dir / 'immutable_manifest.json'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
