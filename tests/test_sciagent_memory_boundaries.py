import unittest

from src.probemem.regime_memory import SIGNATURE_FIELDS
from src.probemem_sciagent.experience_memory import ExperienceMemory, assert_no_counterfactual_write
from src.probemem_sciagent.hypothesis_memory import HypothesisMemory
from src.probemem_sciagent.memory_retrieval import retrieve_scientific_memory
from src.probemem_sciagent.principle_memory import PrincipleMemory
from src.probemem_sciagent.schemas import ExperienceRecord


COMP = "BOUNDED_PLANAR_COMPENSATION"


def signature(value=0.0): return {name: float(value) for name in SIGNATURE_FIELDS}


def experience(identifier="exp1", step=3, status="ACCEPTED", skill=COMP):
    return ExperienceRecord(
        identifier, "episode1", 5300, signature(), skill, "ACCEPTED", 0.8,
        "bounded reasoning", status, 0.1, 100, (), (), step,
    )


class SciAgentMemoryBoundaryTest(unittest.TestCase):
    def test_current_episode_outcome_is_not_retrieved_at_current_decision(self):
        memory = ExperienceMemory([experience(step=3)])
        snapshot = retrieve_scientific_memory(
            query_signature=signature(), current_condition_codes=("CURRENT_FAILURE",),
            created_before_step=3, experiences=memory, hypotheses=HypothesisMemory(),
            principles=PrincipleMemory(),
        )
        self.assertEqual(snapshot.supporting_experiences, ())

    def test_future_experience_id_is_rejected(self):
        memory = ExperienceMemory([experience(step=3)])
        with self.assertRaises(ValueError): memory.validate_ids_before(["exp1"], 3)

    def test_unselected_action_cannot_be_written(self):
        row = experience(skill=COMP)
        with self.assertRaises(ValueError):
            assert_no_counterfactual_write(row, selected_skill="INDEPENDENT_STOCHASTIC_RETRY", selected_experience_id="exp1")

    def test_rejected_and_inconclusive_selected_experience_are_retained(self):
        memory = ExperienceMemory()
        memory.append_selected(experience("rejected", 3, "REJECTED"))
        memory.append_selected(experience("uncertain", 4, "INCONCLUSIVE"))
        self.assertEqual([row.verification_status for row in memory.records], ["REJECTED", "INCONCLUSIVE"])


if __name__ == "__main__": unittest.main()
