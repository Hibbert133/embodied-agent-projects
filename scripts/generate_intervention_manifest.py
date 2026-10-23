"""Generate an immutable manifest for frozen P1 fresh verification."""

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
IMPLEMENTATIONS = {
    "runner": Path("scripts/run_frozen_heldout_intervention.py"),
    "planner": Path("src/planner/evidence_grounded.py"),
    "rollout": Path("src/rollout/engine.py"),
    "recovery_policy": Path("src/autoresearch.py"),
    "metrics": Path("src/evaluation/allocation_metrics.py"),
}


def _git(*arguments: str) -> str:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def canonical_id(content: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "NOT_INSTALLED"


def build_manifest(
    config: Mapping[str, Any],
    *,
    config_path: Path,
    source_commit: str,
    timestamp: str,
    implementation_hashes: Mapping[str, str],
    source_artifact_hashes: Mapping[str, str],
) -> dict[str, Any]:
    content = {
        "manifest_schema_version": 1,
        "protocol_id": config["protocol_id"],
        "protocol_version": config["protocol_version"],
        "source_git_commit": source_commit,
        "config_path": config_path.resolve().relative_to(ROOT).as_posix(),
        "config_sha256": sha256_file(config_path),
        "execution_timestamp_utc": timestamp,
        "parent_allocation_run_id": config["source_allocation_run_id"],
        "parent_allocation_manifest_id": config["source_allocation_manifest_id"],
        "operational_units": config["expected_operational_units"],
        "verification_seed_namespace": config["verification"]["perturbation_seed_namespace"],
        "methods": list(config["methods"]),
        "implementation_paths": {
            name: path.as_posix() for name, path in IMPLEMENTATIONS.items()
        },
        "implementation_git_blob_hashes": dict(implementation_hashes),
        "source_artifact_sha256": dict(source_artifact_hashes),
        "dependencies": {
            "python": platform.python_version(),
            "metaworld": _version("metaworld"),
            "mujoco": _version("mujoco"),
            "gymnasium": _version("gymnasium"),
            "numpy": _version("numpy"),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
    }
    manifest_id = canonical_id(content)
    compact = timestamp.replace("+00:00", "Z").replace("-", "").replace(":", "")
    return {
        **content,
        "manifest_id": manifest_id,
        "experiment_run_id": f"intervention_{compact}_{manifest_id[:12]}",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/autoresearch/heldout_intervention_v1.json",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / "outputs/heldout_intervention/runs",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("intervention manifest requires a clean worktree")
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        parent = ROOT / config["source_allocation_directory"]
        sources = {
            "parent_manifest": parent / "manifest.json",
            "parent_case_audit": parent / "oracle_case_audit.jsonl",
            "parent_agent_evidence": parent / "agent_evidence.jsonl",
            "parent_probe_evidence": parent / "agent_probe_evidence.jsonl",
            "recovery_policy_config": ROOT / config["recovery_policy_config"],
        }
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        manifest = build_manifest(
            config,
            config_path=config_path,
            source_commit=_git("rev-parse", "HEAD"),
            timestamp=timestamp,
            implementation_hashes={
                name: _git("hash-object", path.as_posix())
                for name, path in IMPLEMENTATIONS.items()
            },
            source_artifact_hashes={name: sha256_file(path) for name, path in sources.items()},
        )
        directory = args.output_root.resolve() / manifest["experiment_run_id"]
        directory.mkdir(parents=True, exist_ok=False)
        path = directory / "manifest.json"
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
