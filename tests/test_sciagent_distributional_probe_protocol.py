import json
from pathlib import Path
import unittest

from scripts.generate_probemem_sciagent_distributional_probe_manifest import build_units
from scripts.run_probemem_sciagent_distributional_probe_identifiability import _integrity_violations


ROOT = Path(__file__).resolve().parents[1]
COMP = "BOUNDED_PLANAR_COMPENSATION"
RETRY = "INDEPENDENT_STOCHASTIC_RETRY"


class DistributionalProbeProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(
            (ROOT / "configs/probemem_sciagent/distributional_probe_identifiability_v1_8.json").read_text(encoding="utf-8")
        )

    def test_seed_partition_is_fresh_and_fixed(self):
        registry = json.loads(
            (ROOT / "configs/probemem_sciagent/seed_registry_v9.json").read_text(encoding="utf-8")
        )
        self.assertEqual(self.config["seed_range"], [6950, 7099])
        self.assertEqual(registry["partitions"]["distributional_probe_identifiability_future_reserved"], [7100, 7199])
        self.assertEqual(len(build_units(self.config)), 150)

    def test_random_namespaces_do_not_overlap(self):
        for unit in build_units(self.config):
            ids = [unit["initial_seed"], unit["mandatory_probe_seed"], unit["compensation_probe_seed"], *unit["retry_probe_seeds"], *unit["verification_seeds"]]
            self.assertEqual(len(ids), len(set(ids)))

    def test_protocol_has_no_api_agent_or_memory(self):
        for key in ("api_calls", "agent_decision", "online_recovery_execution", "memory_write", "hypothesis_update", "principle_update"):
            self.assertTrue(self.config["prohibitions"][key])

    def test_integrity_requires_probe_before_outcomes(self):
        case = {"case_id": "c1"}
        reasons = _integrity_violations(
            config=self.config, probe_records=[], candidate_outcomes=[], cases=[case],
        )
        self.assertIn("OUTCOME_BEFORE_PROBE_RECORD:c1", reasons)
        self.assertIn("INCOMPLETE_CANDIDATE_REALIZATIONS:c1", reasons)

    def test_integrity_requires_common_seed_per_pair(self):
        probe = {"case_id": "c1", "persisted_before_candidate_outcomes": True}
        outcomes = []
        for realization in range(4):
            outcomes.extend([
                {"case_id": "c1", "realization": realization, "candidate_skill": COMP, "verification_seed": 10 + realization, "evaluator_only": True, "unavailable_to_agent": True},
                {"case_id": "c1", "realization": realization, "candidate_skill": RETRY, "verification_seed": 20 + realization, "evaluator_only": True, "unavailable_to_agent": True},
            ])
        reasons = _integrity_violations(
            config=self.config, probe_records=[probe], candidate_outcomes=outcomes, cases=[{"case_id": "c1"}],
        )
        self.assertEqual(sum(reason.startswith("UNMATCHED_RANDOM_REALIZATION") for reason in reasons), 4)


if __name__ == "__main__":
    unittest.main()
