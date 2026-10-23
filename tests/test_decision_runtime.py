from __future__ import annotations

import unittest

from src.reasoning import (
    AgentDecisionRuntime,
    DecisionRuntimeRecorder,
    summarize_decision_runtimes,
)


class FakeClock:
    def __init__(self, values: list[int]) -> None:
        self.values = iter(values)

    def __call__(self) -> int:
        return next(self.values)


class DecisionRuntimeTest(unittest.TestCase):
    def test_records_monotonic_stages_and_total(self) -> None:
        recorder = DecisionRuntimeRecorder(
            clock_ns=FakeClock([0, 1_000_000, 2_000_000, 5_000_000])
        )
        with recorder.measure("evidence_state_build_ms"):
            pass
        with recorder.measure("evidence_decision_ms"):
            pass
        sample = recorder.snapshot()
        self.assertEqual(sample.evidence_state_build_ms, 1.0)
        self.assertEqual(sample.evidence_decision_ms, 3.0)
        self.assertEqual(sample.total_agent_decision_ms, 4.0)
        self.assertIsNone(sample.memory_retrieval_ms)

    def test_rejects_unknown_duplicate_and_backwards_timing(self) -> None:
        recorder = DecisionRuntimeRecorder(clock_ns=FakeClock([0, 1]))
        with self.assertRaisesRegex(ValueError, "unknown"):
            with recorder.measure("environment_rollout_ms"):
                pass
        with recorder.measure("belief_update_ms"):
            pass
        with self.assertRaisesRegex(ValueError, "already recorded"):
            with recorder.measure("belief_update_ms"):
                pass
        backwards = DecisionRuntimeRecorder(clock_ns=FakeClock([2, 1]))
        with self.assertRaisesRegex(ValueError, "backwards"):
            with backwards.measure("evidence_decision_ms"):
                pass

    def test_summary_excludes_warmup_and_reports_p90(self) -> None:
        samples = [
            AgentDecisionRuntime(evidence_decision_ms=100.0, total_agent_decision_ms=100.0, warmup=True),
            AgentDecisionRuntime(evidence_decision_ms=1.0, total_agent_decision_ms=2.0),
            AgentDecisionRuntime(evidence_decision_ms=3.0, total_agent_decision_ms=4.0),
        ]
        summary = summarize_decision_runtimes(samples)
        decision = summary["evidence_decision_ms"]
        self.assertEqual(decision["count"], 2)
        self.assertEqual(decision["median_ms"], 2.0)
        self.assertAlmostEqual(decision["p90_ms"], 2.8)
        self.assertEqual(decision["max_ms"], 3.0)


if __name__ == "__main__":
    unittest.main()
