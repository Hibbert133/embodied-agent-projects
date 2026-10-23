"""Resumable, append-only experiment campaign infrastructure."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import monotonic
from typing import Any, Callable, Mapping, Sequence


@dataclass(frozen=True)
class CampaignBudget:
    max_jobs: int
    max_environment_steps: int
    max_api_calls: int
    max_wall_time_seconds: float

    def __post_init__(self) -> None:
        if min(self.max_jobs, self.max_environment_steps) <= 0:
            raise ValueError("campaign job and environment budgets must be positive")
        if self.max_api_calls < 0 or self.max_wall_time_seconds <= 0.0:
            raise ValueError("API budget must be non-negative and wall time positive")


@dataclass(frozen=True)
class CampaignJob:
    job_id: str
    method: str
    condition_id: str
    seed: int
    repeat: int
    reserved_environment_steps: int
    reserved_api_calls: int = 0

    def __post_init__(self) -> None:
        if not all((self.job_id.strip(), self.method.strip(), self.condition_id.strip())):
            raise ValueError("campaign jobs require stable IDs, methods, and conditions")
        if self.repeat <= 0 or self.reserved_environment_steps < 0:
            raise ValueError("repeat must be positive and reserved steps non-negative")
        if self.reserved_api_calls < 0:
            raise ValueError("reserved API calls must be non-negative")


@dataclass(frozen=True)
class CampaignOutcome:
    job_id: str
    success: bool
    environment_steps: int
    api_calls: int
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id.strip() or min(self.environment_steps, self.api_calls) < 0:
            raise ValueError("outcomes require an ID and non-negative costs")


@dataclass(frozen=True)
class CampaignRunSummary:
    executed_jobs: int
    skipped_completed_jobs: int
    total_completed_jobs: int
    environment_steps: int
    api_calls: int
    stop_reason: str


class CampaignLedger:
    """Append-only JSONL ledger used as the campaign resume source of truth."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()

    def outcomes(self) -> tuple[CampaignOutcome, ...]:
        if not self.path.exists():
            return ()
        parsed: list[CampaignOutcome] = []
        seen: set[str] = set()
        for line_number, line in enumerate(
            self.path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                outcome = CampaignOutcome(**json.loads(line))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    f"invalid campaign ledger line {line_number}: {exc}"
                ) from exc
            if outcome.job_id in seen:
                raise ValueError(f"duplicate campaign outcome: {outcome.job_id}")
            seen.add(outcome.job_id)
            parsed.append(outcome)
        return tuple(parsed)

    def append(self, outcome: CampaignOutcome) -> None:
        if outcome.job_id in {item.job_id for item in self.outcomes()}:
            raise ValueError(f"campaign outcome already exists: {outcome.job_id}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as file:
            file.write(json.dumps(asdict(outcome), ensure_ascii=False) + "\n")
            file.flush()
            os.fsync(file.fileno())


def run_campaign(
    jobs: Sequence[CampaignJob],
    *,
    ledger: CampaignLedger,
    budget: CampaignBudget,
    executor: Callable[[CampaignJob], CampaignOutcome],
    clock: Callable[[], float] = monotonic,
) -> CampaignRunSummary:
    """Execute unfinished jobs without exceeding declared reservations."""

    if len({job.job_id for job in jobs}) != len(jobs):
        raise ValueError("campaign job IDs must be unique")
    existing = ledger.outcomes()
    completed = {outcome.job_id for outcome in existing}
    environment_steps = sum(item.environment_steps for item in existing)
    api_calls = sum(item.api_calls for item in existing)
    start = clock()
    executed = 0
    skipped = 0
    stop_reason = "all_jobs_completed"

    for job in jobs:
        if job.job_id in completed:
            skipped += 1
            continue
        if len(completed) >= budget.max_jobs:
            stop_reason = "max_jobs"
            break
        if environment_steps + job.reserved_environment_steps > budget.max_environment_steps:
            stop_reason = "max_environment_steps"
            break
        if api_calls + job.reserved_api_calls > budget.max_api_calls:
            stop_reason = "max_api_calls"
            break
        if clock() - start >= budget.max_wall_time_seconds:
            stop_reason = "max_wall_time_seconds"
            break

        outcome = executor(job)
        if outcome.job_id != job.job_id:
            raise ValueError("executor returned an outcome for the wrong job")
        if outcome.environment_steps > job.reserved_environment_steps:
            raise ValueError("executor exceeded the environment-step reservation")
        if outcome.api_calls > job.reserved_api_calls:
            raise ValueError("executor exceeded the API-call reservation")
        ledger.append(outcome)
        completed.add(job.job_id)
        environment_steps += outcome.environment_steps
        api_calls += outcome.api_calls
        executed += 1

    return CampaignRunSummary(
        executed_jobs=executed,
        skipped_completed_jobs=skipped,
        total_completed_jobs=len(completed),
        environment_steps=environment_steps,
        api_calls=api_calls,
        stop_reason=stop_reason,
    )
