"""Build an accepted-only post-probe snapshot from a frozen selector run."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyze_probemem_paired_utility import _read_csv, _read_jsonl  # noqa: E402
from src.probemem.intervention_memory import (  # noqa: E402
    VERIFIED_INTERVENTION_EPISODE_SCHEMA_VERSION,
    VerifiedInterventionEpisode,
)
from src.probemem.intervention_utility import (  # noqa: E402
    INTERVENTION_APPLICABILITY_FEATURES,
    InterventionApplicabilitySignature,
)
from src.probemem.models import InterventionSkill  # noqa: E402
from src.reasoning import validate_no_oracle_evidence  # noqa: E402


def _signature(record: dict[str, Any]) -> InterventionApplicabilitySignature:
    validate_no_oracle_evidence(record)
    payload = record["applicability_signature"]
    features = payload["features"]
    return InterventionApplicabilitySignature(
        schema_version=int(payload["schema_version"]),
        evidence_id=str(payload["evidence_id"]),
        episode_id=int(payload["episode_id"]),
        values=tuple(float(features[name]) for name in INTERVENTION_APPLICABILITY_FEATURES),
    )


def build_verified_records(
    selector_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    agent_rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    selection_policy_id: str,
) -> tuple[list[VerifiedInterventionEpisode], Counter[str]]:
    evidence = {
        int(row["episode_id"]): row
        for row in agent_rows
        if bool(row["decision_required"])
    }
    candidates = {
        (int(row["episode_id"]), row["candidate_id"]): row
        for row in candidate_rows
    }
    records: list[VerifiedInterventionEpisode] = []
    excluded: Counter[str] = Counter()
    for row in sorted(selector_rows, key=lambda item: int(item["episode_id"])):
        episode_id = int(row["episode_id"])
        selected_skill = InterventionSkill(row["selected_skill"])
        candidate = candidates[(episode_id, selected_skill.value)]
        if candidate["verification_status"] != row["selected_verification_status"]:
            raise ValueError("selector and fresh verification artifacts disagree")
        status = candidate["verification_status"]
        if status != "ACCEPTED":
            excluded[status] += 1
            continue
        record = VerifiedInterventionEpisode(
            schema_version=VERIFIED_INTERVENTION_EPISODE_SCHEMA_VERSION,
            record_id=f"verified_intervention_episode_{episode_id:04d}",
            source_episode_id=episode_id,
            source_run_id=manifest["experiment_run_id"],
            source_manifest_id=manifest["manifest_id"],
            source_git_commit=manifest["source_git_commit"],
            selection_policy_id=selection_policy_id,
            applicability_signature=_signature(evidence[episode_id]),
            selected_skill=selected_skill,
            fresh_verification_status=status,
            final_object_goal_distance=float(candidate["final_object_goal_distance"]),
            verification_steps=int(candidate["verification_steps"]),
            total_interaction_steps=int(row["online_environment_steps"]),
        )
        records.append(record)
    return records, excluded


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--selector-results",
        type=Path,
        default=ROOT / "outputs/probemem_v2/noise_selector_validation_results.csv",
    )
    parser.add_argument(
        "--output-jsonl",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/verified_selected_intervention_episodes.jsonl",
    )
    parser.add_argument(
        "--output-summary",
        type=Path,
        default=ROOT
        / "outputs/probemem_v2/verified_selected_intervention_summary.json",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads((ROOT / manifest["config_path"]).read_text(encoding="utf-8"))
        status = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
        if status.get("status") != "COMPLETED":
            raise ValueError("verified snapshot requires completed immutable run")
        selector_rows = _read_csv(args.selector_results.resolve())
        if {row["manifest_id"] for row in selector_rows} != {manifest["manifest_id"]}:
            raise ValueError("selector results and source manifest differ")
        records, excluded = build_verified_records(
            selector_rows,
            _read_csv(run_dir / "candidate_results.csv"),
            _read_jsonl(run_dir / "agent_evidence.jsonl"),
            manifest,
            config["selector"]["selector_id"],
        )
        output = args.output_jsonl.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            "".join(json.dumps(record.to_dict(), sort_keys=True) + "\n" for record in records),
            encoding="utf-8",
        )
        skill_counts = Counter(record.selected_skill.value for record in records)
        summary = {
            "schema_version": VERIFIED_INTERVENTION_EPISODE_SCHEMA_VERSION,
            "source_run_id": manifest["experiment_run_id"],
            "source_manifest_id": manifest["manifest_id"],
            "source_git_commit": manifest["source_git_commit"],
            "selection_policy_id": config["selector"]["selector_id"],
            "operational_cases": len(selector_rows),
            "verified_episode_count": len(records),
            "verified_skill_counts": dict(skill_counts),
            "excluded_status_counts": dict(excluded),
            "unselected_counterfactuals_exported": 0,
            "oracle_fields_exported": 0,
            "operational_retrieval_enabled": False,
            "snapshot_role": "development_verified_episode_candidate",
            "phase_d_promoted": False,
        }
        args.output_summary.resolve().write_text(
            json.dumps(summary, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(summary, indent=2))
        return 0
    except (KeyError, OSError, TypeError, ValueError) as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
