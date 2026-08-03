"""Create a compact operational summary without exposing raw model responses."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def summarize(run_dir: Path) -> dict[str, object]:
    audit = json.loads((run_dir / "shadow_audit.json").read_text(encoding="utf-8"))
    attempts = [attempt for result in audit["results"] for attempt in result["audit"]["attempts"]]
    valid = [attempt for attempt in attempts if attempt["valid"]]
    latencies = [float(attempt["latency_ms"]) for attempt in valid]
    result = {
        **audit["summary"],
        "structured_output_rate": audit["summary"]["valid_cases"] / audit["summary"]["cases"],
        "schema_repair_cases": sum(len(row["audit"]["attempts"]) > 1 for row in audit["results"]),
        "latency_ms": {
            "median": statistics.median(latencies), "minimum": min(latencies), "maximum": max(latencies),
        },
        "tokens": {
            "input": sum(item.get("usage", {}).get("input_tokens", 0) for item in valid),
            "output": sum(item.get("usage", {}).get("output_tokens", 0) for item in valid),
        },
        "decision_counts": {
            name: sum(row["decision"]["selected_decision"] == name for row in audit["results"])
            for name in ("REPEAT_STOCHASTIC_RETRY", "SWITCH_TO_BOUNDED_COMPENSATION", "ABSTAIN")
        },
        "qualitative_only": True,
    }
    (run_dir / "operational_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.run_dir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
