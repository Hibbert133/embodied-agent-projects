import unittest

from src.probemem_sciagent.probe_utility import classify_probe_utility, total_online_steps


COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


class ProbeUtilityTest(unittest.TestCase):
    def test_changed_action_with_better_status_is_helpful(self):
        result = classify_probe_utility(
            pre_probe_skill=COMP, post_probe_skill=RETRY,
            candidate_statuses={COMP: "REJECTED", RETRY: "ACCEPTED"},
        )
        self.assertEqual(result.label, "HELPFUL_PROBE")
        self.assertTrue(result.action_changed)

    def test_changed_action_with_worse_status_is_harmful(self):
        result = classify_probe_utility(
            pre_probe_skill=RETRY, post_probe_skill=COMP,
            candidate_statuses={COMP: "REJECTED", RETRY: "INCONCLUSIVE"},
        )
        self.assertEqual(result.label, "HARMFUL_PROBE")

    def test_equal_status_change_is_not_benefit(self):
        result = classify_probe_utility(
            pre_probe_skill=COMP, post_probe_skill=RETRY,
            candidate_statuses={COMP: "ACCEPTED", RETRY: "ACCEPTED"},
        )
        self.assertEqual(result.label, "NO_DECISION_BENEFIT")

    def test_unchanged_action_is_not_benefit(self):
        result = classify_probe_utility(
            pre_probe_skill=COMP, post_probe_skill=COMP,
            candidate_statuses={COMP: "ACCEPTED", RETRY: "REJECTED"},
        )
        self.assertEqual(result.label, "NO_DECISION_BENEFIT")

    def test_abstaining_post_decision_is_not_evaluable(self):
        result = classify_probe_utility(
            pre_probe_skill=COMP, post_probe_skill=None, candidate_statuses={},
        )
        self.assertEqual(result.label, "NOT_EVALUABLE")

    def test_candidate_status_contract_is_complete(self):
        with self.assertRaises(ValueError):
            classify_probe_utility(
                pre_probe_skill=COMP, post_probe_skill=RETRY,
                candidate_statuses={COMP: "ACCEPTED"},
            )

    def test_online_budget_excludes_evaluator_collection(self):
        self.assertEqual(total_online_steps(initial_steps=500, mandatory_probe_steps=64, micro_probe_steps=192), 756)
        with self.assertRaises(ValueError):
            total_online_steps(initial_steps=500, mandatory_probe_steps=64, micro_probe_steps=-1)


if __name__ == "__main__":
    unittest.main()
