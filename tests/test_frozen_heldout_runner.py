from __future__ import annotations

import json
import unittest

from scripts.run_frozen_heldout_allocation import (
    _request_for_method,
    derive_random_seed,
)


class FrozenHeldoutRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with open(
            "configs/autoresearch/heldout_allocation_v1.json",
            "r",
            encoding="utf-8",
        ) as handle:
            cls.config = json.load(handle)

    def test_random_namespaces_create_reproducible_independent_streams(self) -> None:
        first = derive_random_seed(330, 4097)
        self.assertEqual(first, derive_random_seed(330, 4097))
        self.assertNotEqual(first, derive_random_seed(330, 4099))
        self.assertNotEqual(first, derive_random_seed(331, 4097))

    def test_successful_initial_rollout_never_requests_adaptation(self) -> None:
        row = {
            "case_id": "heldout_case_0001",
            "decision_required": False,
            "diagnostic_probe_needed_oracle": True,
            "temporal_uncertainty": 1.0,
            "phase_gate_action": "REQUEST_DIAGNOSTIC_PROBE",
        }
        for method in (
            "passive",
            "seeded_random_probe",
            "always_probe",
            "global_temporal_gate",
            "frozen_phase_conditioned_gate",
            "oracle_audit",
        ):
            self.assertFalse(
                _request_for_method(
                    method, row, config=self.config, global_threshold=0.5
                )
            )

    def test_phase_and_oracle_decisions_use_separate_fields(self) -> None:
        row = {
            "case_id": "heldout_case_0002",
            "decision_required": True,
            "diagnostic_probe_needed_oracle": False,
            "temporal_uncertainty": 0.1,
            "phase_gate_action": "REQUEST_DIAGNOSTIC_PROBE",
        }
        self.assertTrue(
            _request_for_method(
                "frozen_phase_conditioned_gate",
                row,
                config=self.config,
                global_threshold=0.5,
            )
        )
        self.assertFalse(
            _request_for_method(
                "oracle_audit", row, config=self.config, global_threshold=0.5
            )
        )


if __name__ == "__main__":
    unittest.main()
