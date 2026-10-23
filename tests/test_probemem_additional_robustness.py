import copy
import unittest

from scripts.audit_probemem_additional_robustness import METHODS, paired_counts, validate_tables


class RobustnessAuditTest(unittest.TestCase):
    def setUp(self):
        identity = dict(experiment_run_id="run", manifest_id="manifest", source_git_commit="commit")
        self.status = dict(identity, operational_cases=1)
        self.population = [dict(seed="7200", operational="True", condition_id_oracle="fault_01",
                                mechanism_oracle="stable_bias", initial_state_hash="state")]
        self.decisions = [dict(identity, method=m, episode_id="1", seed="7200",
                               condition_id_oracle="fault_01", mechanism_oracle="stable_bias",
                               verification_status="ACCEPTED", selected_skill="skill",
                               selected_action_signature_id="action") for m in METHODS]
        self.outcomes = [dict(identity, episode_id="1", seed="7200", realization=str(i),
                              action_signature_id="action", skill="skill", evaluator_only="True",
                              initial_state_hash="state", verification_status="ACCEPTED",
                              steps="30", success="True") for i in range(4)]

    def validate(self):
        return validate_tables(self.status, self.population, self.decisions, self.outcomes)

    def test_exact_discordance_and_direction(self):
        result = paired_counts([True] * 4 + [False] * 56, [False] * 60)
        self.assertEqual(result["exact_discordance_p_reference"], 0.125)
        self.assertEqual((result["wins"], result["ties"], result["losses"]), (4, 56, 0))
        self.assertEqual(paired_counts([False], [True])["difference"], -1)
        self.assertEqual(paired_counts([True], [True])["exact_discordance_p_reference"], 1)
        with self.assertRaises(ValueError):
            paired_counts([], [])

    def test_valid_complete_pairs(self):
        methods, outcomes = self.validate()
        self.assertEqual(len(methods), 5)
        self.assertEqual(len(outcomes), 4)

    def test_duplicate_and_missing_decisions_rejected(self):
        self.decisions.append(copy.deepcopy(self.decisions[0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.validate()
        self.decisions = self.decisions[1:-1]
        with self.assertRaisesRegex(ValueError, "missing method"):
            self.validate()

    def test_outcome_corruptions_fail_closed(self):
        for field, value in (("seed", "7201"), ("manifest_id", "wrong"),
                             ("initial_state_hash", "wrong"), ("skill", "wrong"),
                             ("realization", "4"), ("verification_status", "UNKNOWN")):
            with self.subTest(field=field):
                original = self.outcomes[0][field]
                self.outcomes[0][field] = value
                with self.assertRaises(ValueError):
                    self.validate()
                self.outcomes[0][field] = original

    def test_duplicate_and_missing_realizations_rejected(self):
        self.outcomes.append(copy.deepcopy(self.outcomes[0]))
        with self.assertRaisesRegex(ValueError, "duplicate outcome"):
            self.validate()
        self.outcomes = self.outcomes[:-2]
        with self.assertRaisesRegex(ValueError, "missing"):
            self.validate()

    def test_primary_outcome_must_match(self):
        self.outcomes[0]["verification_status"] = "REJECTED"
        with self.assertRaisesRegex(ValueError, "primary outcome mismatch"):
            self.validate()

    def test_nonexecuted_placeholder_stays_failure(self):
        for row in self.decisions:
            row["verification_status"] = "REJECTED"
        for row in self.outcomes:
            row.update(skill="", verification_status="REJECTED", steps="0", success="False")
        self.validate()
        self.outcomes[1]["steps"] = "1"
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
