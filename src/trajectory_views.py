"""Leakage-safe trajectory projections."""
from __future__ import annotations
from typing import Any, Mapping

AGENT_FIELDS=("schema_version","episode_id","seed","step","observation","commanded_action","reward","success","terminated","truncated","task_progress_metrics")
ORACLE_FIELDS=AGENT_FIELDS+("raw_action","perturbed_action","executed_action","perturbation_type","perturbation_parameters","was_clipped","clipped_element_count")

def build_agent_view(record: Mapping[str,Any]) -> dict[str,Any]: return {k:record[k] for k in AGENT_FIELDS if k in record}
def build_oracle_view(record: Mapping[str,Any]) -> dict[str,Any]: return {k:record[k] for k in ORACLE_FIELDS if k in record}
