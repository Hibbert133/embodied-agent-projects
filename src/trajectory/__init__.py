"""Public trajectory API and leakage-safe schema-v2 projections."""

from src.trajectory.records import (
    TrajectoryRecorder,
    TrajectoryStep,
    save_agent_jsonl,
    save_jsonl,
)
from src.trajectory.views import (
    AGENT_FIELDS,
    FORBIDDEN_AGENT_FIELDS,
    ORACLE_FIELDS,
    build_agent_view,
    build_oracle_view,
)

__all__ = [
    "AGENT_FIELDS",
    "FORBIDDEN_AGENT_FIELDS",
    "ORACLE_FIELDS",
    "TrajectoryRecorder",
    "TrajectoryStep",
    "build_agent_view",
    "build_oracle_view",
    "save_agent_jsonl",
    "save_jsonl",
]
