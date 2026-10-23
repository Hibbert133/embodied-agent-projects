"""Summarize a SciAgent API Reliability v1.1 shadow run."""
import argparse, json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--run-dir", type=Path, required=True); args = parser.parse_args()
run = args.run_dir.resolve(); status = json.loads((run / "run_status.json").read_text(encoding="utf-8"))
outputs = json.loads((run / "certified_shadow_outputs.json").read_text(encoding="utf-8")) if (run / "certified_shadow_outputs.json").exists() else []
analysis = {
    "status": status.get("status"), "operational_cases": len(outputs),
    "valid_outputs": sum(bool(row["valid"]) for row in outputs),
    "repairs": sum(bool(row["repaired"]) for row in outputs),
    "fail_closed": sum(not bool(row["valid"]) for row in outputs),
    "action_execution_count": status.get("action_execution_count", 0),
    "memory_write_count": status.get("memory_write_count", 0),
    "claim_boundary": "shadow_api_reliability_only",
}
(run / "analysis.json").write_text(json.dumps(analysis, indent=2) + "\n", encoding="utf-8"); print(json.dumps(analysis, indent=2))
