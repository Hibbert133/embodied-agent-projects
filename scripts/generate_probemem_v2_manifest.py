"""Generate an immutable development manifest for a ProbeMem v2 run."""

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
    Path("src/probemem/tools.py"),
    Path("src/probemem/runtime.py"),
    Path("src/probemem/online_policy.py"),
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
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_id(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def build_manifest(config_path: Path, timestamp: str) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
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
        "seed_partitions": config["seed_partitions"],
        "condition_cycle": config["smoke"]["condition_cycle"],
        "budget": config["budget"],
        "registered_probe": config["registered_probe"],
        "random_seed_namespaces": config["random_seed_namespaces"],
        "memory_mode": config["memory"]["phase_b_mode"],
        "model": config["model"],
        "execution_timestamp_utc": timestamp,
        "dependencies": {
            "python": platform.python_version(),
            "metaworld": _version("metaworld"),
            "mujoco": _version("mujoco"),
            "gymnasium": _version("gymnasium"),
            "numpy": _version("numpy"),
            "anthropic": _version("anthropic"),
        },
    }
    manifest_id = _canonical_id(content)
    compact = timestamp.replace("+00:00", "Z").replace("-", "").replace(":", "")
    return {
        **content,
        "manifest_id": manifest_id,
        "experiment_run_id": f"probemem_v2_smoke_{compact}_{commit[:12]}",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/probemem_v2/development_smoke_v2.json",
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
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest = build_manifest(config_path, timestamp)
        run_dir = args.output_root.resolve() / manifest["experiment_run_id"]
        run_dir.mkdir(parents=True, exist_ok=False)
        path = run_dir / "manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest_id: {manifest['manifest_id']}")
        print(f"experiment_run_id: {manifest['experiment_run_id']}")
        print(f"manifest: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
