"""Tests for the post-hoc applicability retrieval feasibility audit."""

from __future__ import annotations

import unittest

from scripts.audit_probemem_applicability_retrieval import (
    fit_reference_scaler,
    retrieve_nearest_reference,
)


class ProbeMemApplicabilityRetrievalAuditTest(unittest.TestCase):
    def test_scaler_and_retrieval_use_reference_values(self) -> None:
        references = [
            {"seed": 1, "x": 0.0, "y": 0.0},
            {"seed": 2, "x": 2.0, "y": 4.0},
        ]
        means, scales = fit_reference_scaler(references, ("x", "y"))
        self.assertEqual(means, {"x": 1.0, "y": 2.0})
        nearest, distance = retrieve_nearest_reference(
            {"x": 0.1, "y": 0.1}, references, ("x", "y"), scales
        )
        self.assertEqual(nearest["seed"], 1)
        self.assertGreaterEqual(distance, 0.0)

    def test_tie_break_is_historical_seed_deterministic(self) -> None:
        references = [
            {"seed": 2, "x": 1.0},
            {"seed": 1, "x": -1.0},
        ]
        _, scales = fit_reference_scaler(references, ("x",))
        nearest, _ = retrieve_nearest_reference(
            {"x": 0.0}, references, ("x",), scales
        )
        self.assertEqual(nearest["seed"], 1)


if __name__ == "__main__":
    unittest.main()
