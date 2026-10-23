"""Strict, leakage-safe projections for schema-v2 transitions."""
from __future__ import annotations
from typing import Any, Mapping

AGENT_FIELDS = (
    "schema_version", "episode_id", "seed", "step", "observation",
    "next_observation", "commanded_action", "reward", "success",
    "terminated", "truncated", "task_progress_metrics",
)
FORBIDDEN_AGENT_FIELDS = frozenset({
    "raw_action", "perturbed_action", "executed_action", "action",
    "perturbation_type", "perturbation_level", "perturbation_parameters",
    "bias_axis", "bias_direction", "was_clipped", "clipped_element_count",
})
ORACLE_FIELDS = AGENT_FIELDS + (
    "raw_action", "perturbed_action", "executed_action", "perturbation_type",
    "perturbation_parameters", "was_clipped", "clipped_element_count",
)

def _project(record: Mapping[str, Any], fields: tuple[str, ...], view: str) -> dict[str, Any]:
    missing = set(fields) - set(record)
    if missing:
        raise ValueError(f"{view} view missing required fields: {sorted(missing)}")
    if record["schema_version"] != 2:
        raise ValueError(f"{view} view requires schema_version 2")
    return {field: record[field] for field in fields}

def build_agent_view(record: Mapping[str, Any]) -> dict[str, Any]:
    result = _project(record, AGENT_FIELDS, "agent")
    leaked = FORBIDDEN_AGENT_FIELDS & set(result)
    if leaked:
        raise ValueError(f"agent view contains forbidden fields: {sorted(leaked)}")
    return result

def build_oracle_view(record: Mapping[str, Any]) -> dict[str, Any]:
    return _project(record, ORACLE_FIELDS, "oracle")
