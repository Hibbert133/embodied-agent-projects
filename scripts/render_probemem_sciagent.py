"""Render an auditable SciAgent flow and natural/synthetic casebook."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--synthetic-root", type=Path, default=Path("outputs/probemem_sciagent/demo/synthetic_pathway_audit"))
    args = parser.parse_args(); run = args.run_dir.resolve()
    decisions = _read(run / "decisions.json", []); probes = _read(run / "micro_probes.json", [])
    principles = _read(run / "principle_memory.json", []); experiences = _read(run / "experience_memory.json", [])
    flow = """# ProbeMem-SciAgent v1 flow\n\n```text\nFailure + repeated evidence\n  -> bounded chronological retrieval\n  -> competing hypotheses\n  -> direct action | one micro-probe | abstain\n  -> persisted final selection\n  -> reset + Fresh Verification\n  -> selected experience only\n  -> hypothesis update\n  -> deterministic principle promotion/restriction\n```\n"""
    (run / "sciagent_flow.md").write_text(flow, encoding="utf-8")
    natural = {
        "direct_action": next((row for row in decisions if row["stage"] == "PRE_PROBE" and row["decision_mode"] == "ACT_DIRECTLY"), None),
        "probe_admission": next((row for row in decisions if row["decision_mode"] == "RUN_MICRO_PROBE"), None),
        "probe_action_change": _find_probe_change(decisions),
        "principle_restriction": next((row for row in principles if row["status"] in ("RESTRICTED", "SUSPENDED")), None),
    }
    (run / "natural_casebook.json").write_text(json.dumps(natural, indent=2) + "\n", encoding="utf-8")
    missing = [key for key, value in natural.items() if value is None]
    if missing:
        synthetic = args.synthetic_root.resolve() / run.name
        synthetic.mkdir(parents=True, exist_ok=False)
        rows = [{
            "label": "SYNTHETIC_INTEGRATION_AUDIT", "path": key,
            "research_metric_eligible": False,
            "purpose": "Exercise a missing code path without claiming a natural scientific result.",
        } for key in missing]
        (synthetic / "missing_pathway_fixtures.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    print(f"rendered: {run}")
    return 0


def _read(path: Path, default): return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
def _find_probe_change(rows):
    pre = {row["episode_id"]: row for row in rows if row["stage"] == "PRE_PROBE"}
    return next((row for row in rows if row["stage"] == "POST_PROBE" and row["episode_id"] in pre and row["selected_skill"] != pre[row["episode_id"]]["selected_skill"]), None)


if __name__ == "__main__": raise SystemExit(main())
