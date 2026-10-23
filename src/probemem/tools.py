"""Deterministic registry controlling every tool visible to the online LLM."""

from __future__ import annotations

from dataclasses import dataclass

from src.probemem.models import InterventionSkill, ProbeMemTool


REGISTERED_TOOL_NAMES = (
    "observe_structured_evidence",
    "retrieve_verified_principles",
    "retrieve_verified_episodes",
    "request_diagnostic_probe",
    "list_intervention_skills",
    "select_intervention_skill",
    "run_fresh_verification",
    "record_experience",
    "propose_intervention_hypothesis",
    "inspect_memory_support",
    "abstain",
)


@dataclass(frozen=True)
class ToolRegistry:
    tool_names: tuple[str, ...]
    intervention_skills: tuple[InterventionSkill, ...]

    def __post_init__(self) -> None:
        if self.tool_names != REGISTERED_TOOL_NAMES:
            raise ValueError("ProbeMem v2 tool registry differs from the registered contract")
        if len(set(self.intervention_skills)) != len(self.intervention_skills):
            raise ValueError("intervention skills must be unique")

    def decision_tools(self, *, probe_available: bool) -> tuple[ProbeMemTool, ...]:
        tools = [ProbeMemTool.SELECT_INTERVENTION_SKILL, ProbeMemTool.ABSTAIN]
        if probe_available:
            tools.insert(0, ProbeMemTool.REQUEST_DIAGNOSTIC_PROBE)
        return tuple(tools)

    def available_skills(self, *, probe_collected: bool) -> tuple[InterventionSkill, ...]:
        skills = [
            InterventionSkill.INDEPENDENT_STOCHASTIC_RETRY,
            InterventionSkill.NO_INTERVENTION,
            InterventionSkill.ABSTAIN,
        ]
        if probe_collected:
            skills.insert(0, InterventionSkill.BOUNDED_PLANAR_COMPENSATION)
        return tuple(skills)


def build_default_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        tool_names=REGISTERED_TOOL_NAMES,
        intervention_skills=tuple(InterventionSkill),
    )
