"""Bind every verifier Demo artifact to immutable run provenance and content hash."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    manifest = json.loads((run_dir / "immutable_manifest.json").read_text(encoding="utf-8"))
    reporting_commit = subprocess.run(
        ["git", "-c", f"safe.directory={Path.cwd().as_posix()}", "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    rows = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path.name == "artifact_provenance.json":
            continue
        rows.append({
            "path": path.relative_to(run_dir).as_posix(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size_bytes": path.stat().st_size,
            "experiment_run_id": manifest["experiment_run_id"],
            "manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "reporting_git_commit": reporting_commit,
        })
    output = {
        "schema_version": 1,
        "experiment_run_id": manifest["experiment_run_id"],
        "manifest_id": manifest["manifest_id"],
        "source_git_commit": manifest["source_git_commit"],
        "reporting_git_commit": reporting_commit,
        "artifacts": rows,
    }
    destination = run_dir / "artifact_provenance.json"
    destination.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"artifact provenance: {destination} ({len(rows)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
