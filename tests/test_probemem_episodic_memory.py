from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.probemem import (
    ChronologicalEpisodeMemory,
    EvidenceSignature,
    InterventionSkill,
    RecoveryExperience,
    VerifiedRecoveryEpisode,
)


SCALES = (1.0, 0.3, 1.0, 1.0, 0.02, 0.02, 1.5)


def signature(episode_id: int, offset: float = 0.0) -> EvidenceSignature:
    return EvidenceSignature(
        schema_version=1,
        evidence_id=f"evidence_{episode_id}",
        episode_id=episode_id,
        values=(offset, 0.2 + offset, 0.5, 0.4, 0.01, -0.01, 0.8),
    )


def experience(episode_id: int, status: str) -> RecoveryExperience:
    return RecoveryExperience(
        schema_version=1,
        record_id=f"record_{episode_id}",
        source_episode_id=episode_id,
        source_manifest_id="manifest_dev",
        signature=signature(episode_id, episode_id / 100.0),
        selected_skill=InterventionSkill.BOUNDED_PLANAR_COMPENSATION,
        predicted_verification_status="ACCEPTED",
        observed_verification_status=status,
        verification_success=status == "ACCEPTED",
        interaction_cost=600,
    )


class ProbeMemEpisodicMemoryTest(unittest.TestCase):
    def test_only_accepted_experience_enters_actionable_snapshot(self) -> None:
        memory = ChronologicalEpisodeMemory(scales=SCALES)
        memory.record(experience(1, "REJECTED"))
        memory.record(experience(2, "ACCEPTED"))
        snapshot = memory.snapshot_before(3)
        self.assertEqual(snapshot.verified_episode_ids, ("record_2",))
        self.assertEqual(snapshot.retrievable_episode_ids, ("record_2",))
        self.assertEqual(snapshot.memory_mode, "verified_episodic")

    def test_rejects_nonaccepted_verified_episode(self) -> None:
        with self.assertRaisesRegex(ValueError, "only freshly ACCEPTED"):
            VerifiedRecoveryEpisode(experience(1, "INCONCLUSIVE"))

    def test_retrieval_is_strictly_chronological(self) -> None:
        memory = ChronologicalEpisodeMemory(scales=SCALES)
        memory.record(experience(1, "ACCEPTED"))
        memory.record(experience(2, "ACCEPTED"))
        retrieved = memory.retrieve_verified(signature(2), current_episode_id=2, limit=3)
        self.assertEqual([item.source_episode_id for item in retrieved], [1])
        self.assertTrue(all(item.source_episode_id < 2 for item in retrieved))

    def test_raw_ablation_includes_rejected_but_requires_development_flag(self) -> None:
        memory = ChronologicalEpisodeMemory(scales=SCALES)
        memory.record(experience(1, "REJECTED"))
        with self.assertRaisesRegex(ValueError, "development-only"):
            memory.retrieve_raw_development_only(
                signature(2), current_episode_id=2, limit=1, development_only=False
            )
        rows = memory.retrieve_raw_development_only(
            signature(2), current_episode_id=2, limit=1, development_only=True
        )
        self.assertEqual(rows[0].observed_verification_status, "REJECTED")
        snapshot = memory.raw_snapshot_before(2)
        self.assertEqual(snapshot.memory_mode, "raw_development")
        self.assertEqual(snapshot.retrievable_episode_ids, ("record_1",))

    def test_oracle_fields_cannot_build_signature(self) -> None:
        with self.assertRaisesRegex(ValueError, "Oracle-only"):
            EvidenceSignature.from_structured_evidence({"condition_id": "fault_01"})

    def test_persistence_separates_audit_and_verified_layers(self) -> None:
        memory = ChronologicalEpisodeMemory(scales=SCALES)
        memory.record(experience(1, "REJECTED"))
        memory.record(experience(2, "ACCEPTED"))
        with tempfile.TemporaryDirectory() as directory:
            memory.save(Path(directory))
            audit = (Path(directory) / "interaction_audit.jsonl").read_text().splitlines()
            verified = (Path(directory) / "verified_episodes.jsonl").read_text().splitlines()
        self.assertEqual(len(audit), 2)
        self.assertEqual(len(verified), 1)

    def test_append_order_is_strict_and_record_ids_unique(self) -> None:
        memory = ChronologicalEpisodeMemory(scales=SCALES)
        memory.record(experience(2, "ACCEPTED"))
        with self.assertRaisesRegex(ValueError, "strict episode order"):
            memory.record(experience(1, "ACCEPTED"))


if __name__ == "__main__":
    unittest.main()
