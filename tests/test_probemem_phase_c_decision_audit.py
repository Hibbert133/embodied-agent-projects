"""Tests for the no-API ProbeMem Phase-C decision-trace audit."""

from __future__ import annotations

import unittest
from typing import Any

from scripts.analyze_probemem_phase_c_decisions import build_decision_audit


METHODS = (
    "stateless_online_llm",
    "raw_episodic_retrieval_development_only",
    "verified_episodic_retrieval",
)


def _record(method: str, *, prediction: str, confidence: str = "medium") -> dict[str, Any]:
    retrieved = [] if method == "stateless_online_llm" else [
        {
            "record_id": "record_0",
            "source_episode_id": 0,
            "observed_verification_status": (
                "REJECTED" if method.startswith("raw_") else "ACCEPTED"
            ),
        }
    ]
    memory_used = bool(retrieved)
    return {
        "experiment_run_id": "run_test",
        "manifest_id": "manifest_test",
        "episode_id": 1,
        "seed": 720,
        "method": method,
        "initial_success": False,
        "retrieved_episode_records": retrieved,
        "decision_trace": [
            {
                "decision": {
                    "memory_used": memory_used,
                    "retrieved_episode_ids": [item["record_id"] for item in retrieved],
                    "requested_tool": "request_diagnostic_probe",
                    "mechanism_hypothesis": "insufficient_evidence",
                    "confidence": "medium",
                    "predicted_outcome": None,
                }
            },
            {
                "decision": {
                    "memory_used": memory_used,
                    "retrieved_episode_ids": [item["record_id"] for item in retrieved],
                    "requested_tool": "select_intervention_skill",
                    "mechanism_hypothesis": "stable_bias",
                    "confidence": confidence,
                    "predicted_outcome": {"verification_status": prediction},
                }
            },
        ],
        "selected_skill": "BOUNDED_PLANAR_COMPENSATION",
        "host_execution": {"verification_status": "ACCEPTED"},
    }


class ProbeMemPhaseCDecisionAuditTest(unittest.TestCase):
    def test_reasoning_change_is_separate_from_action_change(self) -> None:
        records = [
            _record("stateless_online_llm", prediction="ACCEPTED"),
            _record(
                "raw_episodic_retrieval_development_only",
                prediction="INCONCLUSIVE",
            ),
            _record(
                "verified_episodic_retrieval",
                prediction="ACCEPTED",
                confidence="high",
            ),
        ]
        _, summaries, audit = build_decision_audit(records, METHODS)
        by_method = {row["method"]: row for row in summaries}

        self.assertEqual(
            by_method["raw_episodic_retrieval_development_only"][
                "prediction_difference_cases"
            ],
            1,
        )
        self.assertEqual(
            by_method["verified_episodic_retrieval"][
                "post_probe_confidence_difference_cases"
            ],
            1,
        )
        self.assertEqual(
            by_method["raw_episodic_retrieval_development_only"][
                "intervention_difference_cases"
            ],
            0,
        )
        self.assertTrue(audit["all_interventions_tied"])

    def test_nonaccepted_exposure_is_counted_only_for_raw_memory(self) -> None:
        records = [
            _record("stateless_online_llm", prediction="ACCEPTED"),
            _record("raw_episodic_retrieval_development_only", prediction="ACCEPTED"),
            _record("verified_episodic_retrieval", prediction="ACCEPTED"),
        ]
        _, summaries, _ = build_decision_audit(records, METHODS)
        by_method = {row["method"]: row for row in summaries}
        self.assertEqual(
            by_method["raw_episodic_retrieval_development_only"][
                "nonaccepted_record_exposures"
            ],
            1,
        )
        self.assertEqual(
            by_method["verified_episodic_retrieval"][
                "nonaccepted_record_exposures"
            ],
            0,
        )

    def test_incomplete_method_group_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "incomplete operational method groups"):
            build_decision_audit(
                [_record("stateless_online_llm", prediction="ACCEPTED")], METHODS
            )


if __name__ == "__main__":
    unittest.main()
