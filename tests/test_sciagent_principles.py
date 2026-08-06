import unittest
from dataclasses import replace

from src.probemem.regime_memory import SIGNATURE_FIELDS
from src.probemem_sciagent.experience_memory import ExperienceMemory
from src.probemem_sciagent.principle_memory import PrincipleMemory
from src.probemem_sciagent.principle_promotion import can_promote_hypothesis, promotion_rejection_reasons
from src.probemem_sciagent.schemas import ExperienceRecord, HypothesisRecord


COMP = "BOUNDED_PLANAR_COMPENSATION"


def hypothesis(**changes):
    base = HypothesisRecord(
        hypothesis_id="hyp1", statement="Stable response supports bounded compensation.",
        applicability_conditions=("STABLE_DIRECTIONAL_RESPONSE",), predicted_best_skill=COMP,
        supporting_experience_ids=("e1", "e2", "e3", "e4"),
        contradicting_experience_ids=(), tested_experience_ids=("e1", "e2", "e3", "e4"),
        targeted_probe_record_ids=("p1",), verification_count=4, support_count=4,
        contradiction_count=0, independent_seed_count=3, targeted_verification_count=1,
        most_recent_verification_status="ACCEPTED", status="SUPPORTED", created_at_step=1, updated_at_step=10,
    )
    return replace(base, **changes)


def experience(status):
    return ExperienceRecord(
        "new", "episode5", 5305, {name: 0.0 for name in SIGNATURE_FIELDS}, COMP,
        "ACCEPTED", 0.8, "reason", status, 0.2, 100, ("principle",), (), 20,
    )


class SciAgentPrincipleTest(unittest.TestCase):
    def test_single_success_cannot_promote(self):
        row = hypothesis(
            supporting_experience_ids=("e1",), tested_experience_ids=("e1",),
            verification_count=1, support_count=1, independent_seed_count=1,
        )
        self.assertFalse(can_promote_hypothesis(row))

    def test_insufficient_seeds_support_and_targeted_verification_block(self):
        row = hypothesis(independent_seed_count=2, targeted_probe_record_ids=(), targeted_verification_count=0)
        reasons = promotion_rejection_reasons(row)
        self.assertIn("INSUFFICIENT_INDEPENDENT_SEEDS", reasons)
        self.assertIn("NO_TARGETED_VERIFICATION", reasons)

    def test_too_many_contradictions_block(self):
        row = hypothesis(
            contradicting_experience_ids=("x1", "x2"),
            tested_experience_ids=("e1", "e2", "e3", "e4", "x1", "x2"),
            verification_count=6, contradiction_count=2,
        )
        self.assertFalse(can_promote_hypothesis(row))

    def test_rejected_counterexample_restricts_active_principle(self):
        memory = PrincipleMemory()
        promoted = memory.promote(hypothesis(), step=11)
        row = replace(experience("REJECTED"), supporting_principle_ids=(promoted.principle_id,))
        updated = memory.observe_cited(promoted.principle_id, experience=row, step=21)
        self.assertEqual(updated.status, "RESTRICTED")

    def test_suspended_principle_is_not_actionable(self):
        memory = PrincipleMemory()
        promoted = memory.promote(hypothesis(), step=11)
        first = memory.observe_cited(promoted.principle_id, experience=experience("REJECTED"), step=21)
        second_exp = replace(experience("REJECTED"), experience_id="new2", created_at_step=22)
        # Restricted principles cannot be reused to control another action.
        with self.assertRaises(ValueError): memory.observe_cited(first.principle_id, experience=second_exp, step=23)
        self.assertEqual(memory.active_before(30), ())


if __name__ == "__main__": unittest.main()
