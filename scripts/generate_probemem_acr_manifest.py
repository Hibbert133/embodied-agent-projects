"""Generate an immutable manifest for deterministic ProbeMem-ACR development."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_PATHS = (
    Path("src/probemem/action_memory.py"),
    Path("src/probemem/action_evidence.py"),
    Path("src/probemem/action_prediction.py"),
    Path("src/probemem/resonance.py"),
    Path("src/probemem/intervention_memory_gate.py"),
    Path("src/probemem/intervention_selector.py"),
    Path("scripts/run_probemem_acr_development.py"),
    Path("scripts/analyze_probemem_acr.py"),
)


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT, check=True, capture_output=True, text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def _derived_seed(seed: int, namespace: int) -> int:
    from scripts.run_probemem_v2_smoke import _seed

    return _seed(seed, namespace)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path,
        default=ROOT / "configs/probemem_acr/development_v1.json",
    )
    parser.add_argument(
        "--output-root", type=Path,
        default=ROOT / "outputs/probemem_acr/runs",
    )
    args = parser.parse_args()
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("ACR manifest generation requires a completely clean worktree")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_probemem_acr_seed_registry.py")],
            cwd=ROOT, check=True,
        )
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        start, stop = (int(item) for item in config["seed_range"])
        if (start, stop) != (1100, 1199) or stop - start + 1 != 100:
            raise ValueError("ACR development must contain exactly seeds 1100--1199")
        cycle = tuple(config["condition_cycle"])
        if cycle != tuple(f"fault_{index:02d}" for index in range(1, 6)):
            raise ValueError("ACR development condition cycle differs from registration")
        namespaces = config["random_seed_namespaces"]
        units = []
        for seed in range(start, stop + 1):
            condition = cycle[(seed - start) % len(cycle)]
            units.append({
                "episode_id": seed - start + 1,
                "environment_seed": seed,
                "condition_id_oracle": condition,
                "initial_perturbation_seed": _derived_seed(seed, int(namespaces["initial_rollout"])),
                "diagnostic_probe_seed": _derived_seed(seed, int(namespaces["diagnostic_probe"])),
                "paired_verification_seed": _derived_seed(seed, int(namespaces["shared_paired_verification"])),
            })
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        commit = _git("rev-parse", "HEAD")
        input_paths = (
            config["recovery_policy_config"],
            config["noise_selection"],
            config["v2_coverage_baseline"]["snapshot"],
            "configs/probemem_acr/seed_registry_v1.json",
            "configs/probemem_acr/v2_provenance_lock.json",
        )
        content = {
            "manifest_schema_version": 1,
            "protocol": config["protocol"],
            "stage": config["stage"],
            "source_git_commit": commit,
            "config_path": config_path.relative_to(ROOT).as_posix(),
            "config_sha256": _sha256(config_path),
            "implementation_sha256": {
                path.as_posix(): _sha256(ROOT / path) for path in IMPLEMENTATION_PATHS
            },
            "input_sha256": {path: _sha256(ROOT / path) for path in input_paths},
            "feature_order": list(__import__(
                "src.probemem.intervention_utility", fromlist=["INTERVENTION_APPLICABILITY_FEATURES"]
            ).INTERVENTION_APPLICABILITY_FEATURES),
            "population_units": units,
            "candidate_execution_order": config["candidates"],
            "budget": config["budget"],
            "estimator": config["estimator"],
            "bootstrap": config["bootstrap"],
            "execution_timestamp_utc": timestamp,
            "dependencies": {
                "python": platform.python_version(),
                "metaworld": _version("metaworld"),
                "mujoco": _version("mujoco"),
                "numpy": _version("numpy"),
            },
        }
        manifest_id = _canonical(content)
        compact = timestamp.replace("+00:00", "Z").replace("-", "").replace(":", "")
        manifest = {
            **content,
            "manifest_id": manifest_id,
            "experiment_run_id": f"probemem_acr_{compact}_{commit[:12]}",
        }
        run_dir = args.output_root.resolve() / manifest["experiment_run_id"]
        run_dir.mkdir(parents=True, exist_ok=False)
        path = run_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest_id: {manifest_id}")
        print(f"experiment_run_id: {manifest['experiment_run_id']}")
        print(f"manifest: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
