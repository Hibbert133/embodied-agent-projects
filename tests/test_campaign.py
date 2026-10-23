from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.evaluation import (
    CampaignBudget,
    CampaignJob,
    CampaignLedger,
    CampaignOutcome,
    run_campaign,
)


def job(index: int, reservation: int = 10) -> CampaignJob:
    return CampaignJob(
        job_id=f"job_{index}", method="passive", condition_id="fault_x",
        seed=index, repeat=1, reserved_environment_steps=reservation,
    )


class CampaignTest(unittest.TestCase):
    def test_resume_skips_completed_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = CampaignLedger(Path(directory) / "ledger.jsonl")
            calls: list[str] = []

            def execute(item: CampaignJob) -> CampaignOutcome:
                calls.append(item.job_id)
                return CampaignOutcome(item.job_id, False, 7, 0, {"real": True})

            budget = CampaignBudget(3, 30, 0, 60)
            first = run_campaign([job(1), job(2)], ledger=ledger, budget=budget, executor=execute)
            second = run_campaign([job(1), job(2)], ledger=ledger, budget=budget, executor=execute)
            self.assertEqual(calls, ["job_1", "job_2"])
            self.assertEqual(first.executed_jobs, 2)
            self.assertEqual(second.skipped_completed_jobs, 2)
            self.assertEqual(second.environment_steps, 14)

    def test_reservation_stops_before_budget_overrun(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = CampaignLedger(Path(directory) / "ledger.jsonl")
            calls: list[str] = []

            def execute(item: CampaignJob) -> CampaignOutcome:
                calls.append(item.job_id)
                return CampaignOutcome(item.job_id, False, 5, 0)

            result = run_campaign(
                [job(1, 8), job(2, 8)], ledger=ledger,
                budget=CampaignBudget(2, 12, 0, 60), executor=execute,
            )
            self.assertEqual(calls, ["job_1"])
            self.assertEqual(result.stop_reason, "max_environment_steps")

    def test_rejects_executor_cost_above_reservation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger = CampaignLedger(Path(directory) / "ledger.jsonl")
            with self.assertRaisesRegex(ValueError, "reservation"):
                run_campaign(
                    [job(1, 3)], ledger=ledger,
                    budget=CampaignBudget(1, 10, 0, 60),
                    executor=lambda item: CampaignOutcome(item.job_id, False, 4, 0),
                )


if __name__ == "__main__":
    unittest.main()
