import unittest

from src.probemem_sciagent.compensation_probe import summarize_compensation_response
from src.probemem_sciagent.probe_registry import ProbeBudget, allow_probe
from src.probemem_sciagent.retry_probe import summarize_retry_repeatability
from src.probemem_sciagent.schemas import MicroProbeRecord, SciAgentDecision


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


def decision(probe="RETRY_REPEATABILITY_PROBE"):
    return SciAgentDecision(
        "evidence", (f"A favors {COMP}", f"B favors {RETRY}"), (), (),
        "RUN_MICRO_PROBE", probe, RETRY, "test action utility", "missing direct evidence", 0.5, None,
        probe_justification_codes=("MISSING_ACTION_CONDITIONED_EVIDENCE",),
    )


def row(progress, objx=0.01, gripdist=0.04):
    observation = [0.0] * 39; observation[4] = 0.0
    return {"observation": observation, "task_progress_metrics": {
        "object_position": [objx, 0.0, 0.0], "goal_position": [1.0, 0.0, 0.0],
        "gripper_object_distance": gripdist, "progress_to_goal": progress,
    }}


class SciAgentProbeTest(unittest.TestCase):
    def test_retry_probe_budget_is_192(self):
        self.assertTrue(allow_probe(decision(), ProbeBudget(192)))
        self.assertFalse(allow_probe(decision(), ProbeBudget(191)))

    def test_illegal_probe_is_rejected(self):
        with self.assertRaises(ValueError): decision("UNKNOWN_PROBE")

    def test_retry_summary_uses_independent_trials(self):
        evidence = summarize_retry_repeatability(([row(0.1)], [row(-0.03)], [row(0.02)]))
        self.assertEqual(evidence.num_trials, 3)
        self.assertAlmostEqual(evidence.positive_progress_rate, 2 / 3)
        self.assertAlmostEqual(evidence.severe_failure_rate, 1 / 3)

    def test_compensation_summary_records_contact_and_alignment(self):
        evidence = summarize_compensation_response([row(0.01, 0.01), row(0.02, 0.02)])
        self.assertGreater(evidence.expected_direction_alignment, 0.9)
        self.assertTrue(evidence.contact_preserved)

    def test_probe_record_requires_source_and_reset_flag_type(self):
        record = MicroProbeRecord("p1", "e1", 5300, "COMPENSATION_RESPONSE_PROBE", "d1", {"temporary_progress": 0.1}, 64, (1,), 2, True)
        self.assertTrue(record.reset_before_formal_recovery)
        with self.assertRaises(ValueError):
            MicroProbeRecord("p2", "e1", 5300, "COMPENSATION_RESPONSE_PROBE", "d1", {"temporary_progress": 0.1}, 64, (2,), 3, False)


if __name__ == "__main__": unittest.main()
