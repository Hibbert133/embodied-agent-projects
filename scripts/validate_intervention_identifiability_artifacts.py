"""Validate provenance and leakage boundaries of an identifiability run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.reasoning.evidence import validate_no_oracle_evidence  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        run = args.run_dir.resolve()
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        status = json.loads((run / "run_status.json").read_text(encoding="utf-8"))
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError("artifact validation requires a completed run")
        keys = ("experiment_run_id", "source_git_commit", "config_sha256")
        identity = tuple(manifest[key] for key in keys)
        artifacts = [status, summary]
        feature_analysis_path = run / "feature_analysis.json"
        if feature_analysis_path.is_file():
            artifacts.append(
                json.loads(feature_analysis_path.read_text(encoding="utf-8"))
            )
        for artifact in artifacts:
            if tuple(artifact[key] for key in keys) != identity:
                raise ValueError("artifact provenance does not match manifest")

        agent_records = [
            json.loads(line)
            for line in (run / "agent_evidence.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        for record in agent_records:
            validate_no_oracle_evidence(record)
            if record["experiment_run_id"] != identity[0]:
                raise ValueError("Agent evidence references another run")

        with (run / "case_results.csv").open(
            "r", encoding="utf-8", newline=""
        ) as handle:
            cases = list(csv.DictReader(handle))
        operational_ids = {
            row["case_id"] for row in cases if row["decision_required"] == "True"
        }
        if {record["case_id"] for record in agent_records} != operational_ids:
            raise ValueError("Agent evidence and operational populations differ")
        if len(cases) != int(summary["full_collection_units"]):
            raise ValueError("full collection count differs from summary")
        print(
            f"validated run={identity[0]} full={len(cases)} "
            f"operational={len(operational_ids)} agent_leakage=none"
        )
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
