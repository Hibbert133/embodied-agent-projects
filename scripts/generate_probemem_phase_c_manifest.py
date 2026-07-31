"""Generate an immutable manifest for the Phase-C episodic comparison."""

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
    Path("src/probemem/models.py"),
    Path("src/probemem/online_policy.py"),
    Path("src/probemem/episodic_memory.py"),
    Path("scripts/run_probemem_phase_c_comparison.py"),
    Path("scripts/run_probemem_v2_smoke.py"),
)


def _git(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


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
        default=ROOT / "configs/probemem_v2/verified_episode_development_v2.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs/probemem_v2/runs",
    )
    args = parser.parse_args()
    try:
        if _git("status", "--porcelain", "--untracked-files=no"):
            raise RuntimeError("manifest generation requires a clean tracked worktree")
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        commit = _git("rev-parse", "HEAD")
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
            "source_phase_b_manifest_id": config["source_phase_b_manifest_id"],
            "seed_range": config["seed_range"],
            "methods": config["methods"],
            "retrieval": config["retrieval"],
            "api_budget": config["api_budget"],
            "budget": config["budget"],
            "execution_timestamp_utc": timestamp,
            "dependencies": {
                "python": platform.python_version(),
                "metaworld": _version("metaworld"),
                "mujoco": _version("mujoco"),
                "numpy": _version("numpy"),
                "anthropic": _version("anthropic"),
            },
        }
        manifest_id = _canonical(content)
        compact = timestamp.replace("+00:00", "Z").replace("-", "").replace(":", "")
        manifest = {
            **content,
            "manifest_id": manifest_id,
            "experiment_run_id": f"probemem_phase_c_{compact}_{commit[:12]}",
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
