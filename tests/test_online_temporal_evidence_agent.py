import unittest

from scripts.run_online_temporal_evidence_agent import (
    _read_csv,
    build_online_evidence_packet,
    decision_prediction,
    summarize_results,
)
from src.trajectory import FORBIDDEN_AGENT_FIELDS
from src.uncertainty.models import EvidenceAction
from src.uncertainty.online_policy import OnlineEvidenceDecision


class OnlineTemporalEvidenceAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = {
            "case_id": "case",
            "episode_return": "10",
            "final_object_goal_distance": "0.2",
            "progress_to_goal": "0.01",
        }
        self.temporal = {
            "sample_count": "100",
            "temporal_uncertainty": "0.8",
            "normalized_residual_x": "0.5",
            "normalized_residual_y": "0.6",
            "response_gain_x": "0.01",
            "response_gain_y": "0.01",
            "estimated_drift_x": "0.001",
            "estimated_drift_y": "-0.001",
            "action_excitation_x": "0.2",
            "action_excitation_y": "0.3",
        }

    def test_packet_contains_only_allowlisted_agent_evidence(self) -> None:
        packet = build_online_evidence_packet(self.case, self.temporal).to_dict()
        def nested_keys(value: object) -> set[str]:
            if isinstance(value, dict):
                return set(value) | set().union(*(nested_keys(item) for item in value.values()))
            if isinstance(value, (list, tuple)):
                return set().union(*(nested_keys(item) for item in value))
            return set()

        keys = nested_keys(packet)
        for field in FORBIDDEN_AGENT_FIELDS:
            self.assertNotIn(field, keys)
        self.assertNotIn("mechanism_class", keys)
        self.assertNotIn("condition_id", keys)

    def test_request_uses_registered_probe_prediction(self) -> None:
        decision = OnlineEvidenceDecision(
            action=EvidenceAction.REQUEST_PROBE,
            probe_kind="symmetric_xy",
            target_uncertainty="execution repeatability",
            hypothesis_mechanism="insufficient_evidence",
            hypothesis_axis="unknown",
            hypothesis_direction="unknown",
            rationale="global residual mixes phases",
            confidence=0.4,
        )
        self.assertEqual(
            decision_prediction(decision, "stochastic_noise"),
            ("stochastic_noise", True),
        )

    def test_summary_counts_api_and_probe_cost(self) -> None:
        rows = [
            {
                "probe_requested": True,
                "correct": True,
                "prediction": "stable_bias",
                "latency_ms": 10,
            },
            {
                "probe_requested": False,
                "correct": False,
                "prediction": "no_prediction",
                "latency_ms": 20,
            },
        ]
        result = summarize_results(rows)
        self.assertEqual(result["api_calls"], 2)
        self.assertEqual(result["probe_environment_steps"], 64)
        self.assertEqual(result["coverage"], 0.5)
        self.assertEqual(result["endpoint_reported_input_tokens"], 0)

    def test_first_run_accepts_missing_result_checkpoint(self) -> None:
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(_read_csv(Path(directory) / "results.csv"), [])


if __name__ == "__main__":
    unittest.main()
