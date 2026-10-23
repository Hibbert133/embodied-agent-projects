"""Generate an immutable manifest for ProbeMem paired utility development."""

from __future__ import annotations

import argparse
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
    Path("src/probemem/intervention_utility.py"),
    Path("src/probemem/intervention_selector.py"),
    Path("src/probemem/intervention_memory.py"),
    Path("src/probemem/intervention_memory_gate.py"),
    Path("src/evaluation/intervention_utility.py"),
    Path("scripts/run_probemem_paired_utility.py"),
    Path("scripts/run_probemem_v2_smoke.py"),
)


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def _canonical(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT
        / "configs/probemem_v2/paired_intervention_utility_development_v1.json",
    )
    parser.add_argument(
        "--output-root", type=Path, default=ROOT / "outputs/probemem_v2/runs"
    )
    args = parser.parse_args()
    try:
        if _git("status", "--porcelain", "--untracked-files=no"):
            raise RuntimeError("manifest generation requires a clean tracked worktree")
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        seed_start, seed_stop = (int(item) for item in config["seed_range"])
        heldout_start, heldout_stop = (int(item) for item in config["heldout_seed_range"])
        if set(range(seed_start, seed_stop + 1)) & set(
            range(heldout_start, heldout_stop + 1)
        ):
            raise ValueError("development and held-out seeds overlap")
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        commit = _git("rev-parse", "HEAD")
        input_paths = {
            config["recovery_policy_config"]: _sha256(
                ROOT / config["recovery_policy_config"]
            ),
            config["noise_selection"]: _sha256(ROOT / config["noise_selection"]),
        }
        if "verified_memory_snapshot" in config:
            input_paths[config["verified_memory_snapshot"]] = _sha256(
                ROOT / config["verified_memory_snapshot"]
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
            "input_sha256": input_paths,
            "seed_range": config["seed_range"],
            "condition_cycle": config["condition_cycle"],
            "candidates": config["candidates"],
            "budget": config["budget"],
            "stopping_rule": config.get("stopping_rule"),
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
            "experiment_run_id": f"probemem_paired_utility_{compact}_{commit[:12]}",
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
