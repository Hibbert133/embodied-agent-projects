from __future__ import annotations

import unittest


class SeveritySelectionPolicyTest(unittest.TestCase):
    def test_selection_tie_break_is_closest_then_lower_magnitude(self) -> None:
        rows = [
            {"perturbation_level": "0.18", "success_rate": "0.6"},
            {"perturbation_level": "0.19", "success_rate": "0.4"},
        ]
        best = min(
            rows,
            key=lambda row: (
                abs((1.0 - float(row["success_rate"])) - 0.5),
                float(row["perturbation_level"]),
            ),
        )
        self.assertEqual(float(best["perturbation_level"]), 0.18)


if __name__ == "__main__":
    unittest.main()
