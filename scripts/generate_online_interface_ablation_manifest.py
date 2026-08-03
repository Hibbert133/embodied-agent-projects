"""Generate the immutable Gate-A GLM interface-ablation manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("configs/probemem_online/interface_ablation_v1.json")
IMPLEMENTATION = (
    Path("src/probemem/compact_evidence.py"), Path("src/probemem/online_glm_contract.py"),
    Path("scripts/generate_online_interface_ablation_manifest.py"),
    Path("scripts/run_glm_interface_ablation.py"), Path("scripts/analyze_glm_interface_ablation.py"),
)


def _git(*args: str) -> str:
    return subprocess.run(["git", "-c", f"safe.directory={ROOT.as_posix()}", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-run", type=Path, required=True)
    args = parser.parse_args()
    try:
        if _git("status", "--porcelain"):
            raise RuntimeError("interface-ablation manifest requires a clean worktree")
        source = args.source_run.resolve()
        source_status = json.loads((source / "run_status.json").read_text(encoding="utf-8"))
        source_manifest = json.loads((source / "immutable_manifest.json").read_text(encoding="utf-8"))
        if source_status["status"] != "COMPLETED" or int(source_status["operational_cases"]) != 30:
            raise RuntimeError("interface ablation requires a complete 30-case source")
        config = json.loads((ROOT / CONFIG).read_text(encoding="utf-8"))
        commit = _git("rev-parse", "HEAD")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"probemem_online_interface_ablation_{stamp}_{commit[:12]}"
        source_files = ("immutable_manifest.json", "agent_evidence.json", "case_results.csv", "candidate_results.csv", "collection_summary.json")
        manifest = {
            "schema_version": 1, "experiment_run_id": run_id, "source_git_commit": commit,
            "created_at_utc": stamp, "config_path": CONFIG.as_posix(), "config_sha256": _sha(ROOT / CONFIG),
            "implementation_sha256": {path.as_posix(): _sha(ROOT / path) for path in IMPLEMENTATION},
            "source_collection_run": source.relative_to(ROOT).as_posix(),
            "source_collection_manifest_id": source_manifest["manifest_id"],
            "source_artifact_sha256": {name: _sha(source / name) for name in source_files},
            "case_count": 30, "base_call_count": 90, "maximum_api_calls": 105,
        }
        manifest["manifest_id"] = _hash(manifest)
        run_dir = ROOT / "outputs/probemem_online/interface_ablation_runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        (run_dir / "immutable_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"manifest: {run_dir / 'immutable_manifest.json'}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
