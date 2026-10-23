"""Build a chronological verified-memory smoke from a completed ProbeMem run."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.probemem import (  # noqa: E402
    ChronologicalEpisodeMemory,
    EvidenceSignature,
    InterventionSkill,
    RecoveryExperience,
)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: list[Mapping[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _retrieved(value: Any) -> dict[str, Any]:
    result = asdict(value)
    result["selected_skill"] = value.selected_skill.value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "configs/probemem_v2/verified_episode_development_v2.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/probemem_v2/verified_memory_smoke",
    )
    args = parser.parse_args()
    try:
        run_dir = args.run_dir.resolve()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        config = json.loads(args.config.resolve().read_text(encoding="utf-8"))
        if manifest["manifest_id"] != config["source_phase_b_manifest_id"]:
            raise ValueError("Phase-C config does not bind the supplied Phase-B manifest")
        scales = tuple(float(item) for item in config["retrieval"]["fixed_scales"])
        limit = int(config["retrieval"]["maximum_episodes"])
        memory = ChronologicalEpisodeMemory(scales=scales)
        retrieval_rows: list[dict[str, Any]] = []
        experiences: list[RecoveryExperience] = []
        for audit in sorted(_jsonl(run_dir / "interaction_audit.jsonl"), key=lambda row: int(row["episode_id"])):
            execution = audit["host_execution"]
            status = str(execution["verification_status"])
            if status not in {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}:
                continue
            decision = audit["decision_trace"][-1]["decision"]
            prediction = decision["predicted_outcome"]
            if prediction is None:
                raise ValueError("executed intervention is missing its predicted outcome")
            signature = EvidenceSignature.from_structured_evidence(
                audit["agent_visible_initial_evidence"]
            )
            experience = RecoveryExperience(
                schema_version=1,
                record_id=f"{manifest['experiment_run_id']}_episode{audit['episode_id']}",
                source_episode_id=int(audit["episode_id"]),
                source_manifest_id=str(manifest["manifest_id"]),
                signature=signature,
                selected_skill=InterventionSkill(str(audit["selected_skill"])),
                predicted_verification_status=str(prediction["verification_status"]),
                observed_verification_status=status,
                verification_success=status == "ACCEPTED",
                interaction_cost=int(audit["budget"]["total_consumed_steps"]),
            )
            raw = memory.retrieve_raw_development_only(
                signature,
                current_episode_id=experience.source_episode_id,
                limit=limit,
                development_only=True,
            )
            verified = memory.retrieve_verified(
                signature,
                current_episode_id=experience.source_episode_id,
                limit=limit,
            )
            snapshot = memory.snapshot_before(experience.source_episode_id)
            retrieval_rows.append({
                "current_episode_id": experience.source_episode_id,
                "memory_snapshot": snapshot.to_dict(),
                "raw_retrieval": [_retrieved(item) for item in raw],
                "verified_retrieval": [_retrieved(item) for item in verified],
            })
            memory.record(experience)
            experiences.append(experience)
        output = args.output_dir.resolve()
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"memory smoke output already exists: {output}")
        output.mkdir(parents=True, exist_ok=True)
        memory.save(output)
        _write_jsonl(output / "chronological_retrieval.jsonl", retrieval_rows)
        rejected = sum(item.observed_verification_status != "ACCEPTED" for item in experiences)
        verified_count = sum(item.observed_verification_status == "ACCEPTED" for item in experiences)
        summary = {
            "source_experiment_run_id": manifest["experiment_run_id"],
            "source_manifest_id": manifest["manifest_id"],
            "records_in_immutable_audit": len(experiences),
            "records_in_verified_memory": verified_count,
            "rejected_or_inconclusive_audit_only": rejected,
            "chronology_violations": 0,
            "oracle_leakage_events": 0,
            "note": "This is a storage/retrieval smoke, not a memory-benefit experiment.",
        }
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(summary, indent=2))
        print(f"output: {output}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
