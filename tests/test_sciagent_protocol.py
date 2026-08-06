import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SciAgentProtocolTest(unittest.TestCase):
    def test_seed_partitions_are_fresh_and_nonoverlapping(self):
        registry = json.loads((ROOT / "configs/probemem_sciagent/seed_registry_v1.json").read_text())
        intervals = list(registry["partitions"].values())
        values = [set(range(start, stop + 1)) for start, stop in intervals]
        self.assertTrue(all(not left & right for index, left in enumerate(values) for right in values[index + 1:]))
        self.assertEqual(intervals[0], [5300, 5349])

    def test_demo_budget_and_call_caps_are_frozen(self):
        config = json.loads((ROOT / "configs/probemem_sciagent/demo_v1.json").read_text())
        self.assertEqual(config["budget"]["total_case_max_steps"], 1256)
        self.assertEqual(config["registered_probes"]["RETRY_REPEATABILITY_PROBE"]["maximum_steps"], 192)
        self.assertEqual(config["glm"]["maximum_total_calls"], 60)

    def test_later_stages_are_blocked(self):
        for name in ("calibration_v1.json", "development_v1.json"):
            config = json.loads((ROOT / "configs/probemem_sciagent" / name).read_text())
            self.assertFalse(config["execution_authorized"])


if __name__ == "__main__": unittest.main()
