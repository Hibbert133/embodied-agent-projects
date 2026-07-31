"""Pure summary checks for the MuJoCo endurance preflight."""

from __future__ import annotations

import unittest

from scripts.check_mujoco_endurance import summarize_samples


class MujocoEnduranceTest(unittest.TestCase):
    def test_summary_preserves_start_peak_final_and_minimum(self) -> None:
        summary = summarize_samples(
            [
                {"process_rss_mb": 100.0, "system_available_mb": 1000.0},
                {"process_rss_mb": 140.0, "system_available_mb": 900.0},
                {"process_rss_mb": 120.0, "system_available_mb": 950.0},
            ]
        )
        self.assertEqual(summary["sample_count"], 3)
        self.assertEqual(summary["process_rss_peak_mb"], 140.0)
        self.assertEqual(summary["process_rss_change_mb"], 20.0)
        self.assertEqual(summary["system_available_min_mb"], 900.0)

    def test_empty_samples_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least one"):
            summarize_samples([])


if __name__ == "__main__":
    unittest.main()
