"""Generate an immutable, content-addressed held-out experiment manifest."""

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
MANIFEST_SCHEMA_VERSION = 1
IMPLEMENTATION_PATHS = {
    "matching": Path("scripts/build_bias_noise_ambiguity_benchmark.py"),
    "probe": Path("src/probe/directional.py"),
    "structured_evidence": Path("src/reasoning/structured_evidence.py"),
    "budgeted_policy": Path("src/uncertainty/budgeted_policy.py"),
}


def _git(*arguments: str) -> str:
    command = [
        "git",
        "-c",
        f"safe.directory={ROOT.as_posix()}",
        *arguments,
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_manifest_id(content: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        content,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def installed_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def build_manifest(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    source_commit: str,
    timestamp_utc: str,
    implementation_hashes: Mapping[str, str],
    dependency_versions: Mapping[str, str],
) -> dict[str, Any]:
    """Build canonical content before adding its self-derived identifiers."""

    allocation = config["allocation"]
    probe = config["registered_probe"]
    matching = config["matching"]
    content = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "protocol_id": config["protocol_id"],
        "protocol_version": config["protocol_version"],
        "source_git_commit": source_commit,
        "source_worktree_clean": True,
        "config_path": config_path.resolve().relative_to(ROOT).as_posix(),
        "config_sha256": sha256_file(config_path),
        "execution_timestamp_utc": timestamp_utc,
        "seed_range": {
            "start": config["seed_start"],
            "stop_inclusive": config["seed_start"] + config["num_seeds"] - 1,
            "count": config["num_seeds"],
        },
        "allocation": {
            "score": allocation["score"],
            "threshold": allocation["threshold"],
            "minimum_phase_samples": allocation["minimum_phase_samples"],
        },
        "condition_mapping_version": config["condition_mapping_version"],
        "condition_ids": [item["condition_id"] for item in config["conditions"]],
        "matching_rule_version": matching["version"],
        "probe_implementation_version": probe["probe_id"],
        "probe_max_environment_steps": probe["max_environment_steps"],
        "evidence_feature_schema_version": config["evidence_feature_schema"],
        "implementation_git_blob_hashes": dict(implementation_hashes),
        "dependencies": dict(dependency_versions),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    }
    manifest_id = canonical_manifest_id(content)
    timestamp_compact = timestamp_utc.replace("+00:00", "Z")
    timestamp_compact = timestamp_compact.replace("-", "").replace(":", "")
    return {
        **content,
        "manifest_id": manifest_id,
        "experiment_run_id": f"heldout_{timestamp_compact}_{manifest_id[:12]}",
    }


def write_manifest(manifest: Mapping[str, Any], output_root: Path) -> Path:
    run_directory = output_root / str(manifest["experiment_run_id"])
    if run_directory.exists():
        raise FileExistsError(f"held-out run directory already exists: {run_directory}")
    run_directory.mkdir(parents=True, exist_ok=False)
    path = run_directory / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/autoresearch/heldout_allocation_v1.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs/heldout_allocation/runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("immutable manifest requires a clean worktree")
        source_commit = _git("rev-parse", "HEAD")
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        implementation_hashes = {
            name: _git("hash-object", path.as_posix())
            for name, path in IMPLEMENTATION_PATHS.items()
        }
        dependencies = {
            "python": platform.python_version(),
            "metaworld": installed_version("metaworld"),
            "mujoco": installed_version("mujoco"),
            "gymnasium": installed_version("gymnasium"),
            "numpy": installed_version("numpy"),
        }
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest = build_manifest(
            config,
            config_path=config_path,
            source_commit=source_commit,
            timestamp_utc=timestamp,
            implementation_hashes=implementation_hashes,
            dependency_versions=dependencies,
        )
        path = write_manifest(manifest, args.output_root.resolve())
        print(f"manifest_id: {manifest['manifest_id']}")
        print(f"experiment_run_id: {manifest['experiment_run_id']}")
        print(f"manifest: {path}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
