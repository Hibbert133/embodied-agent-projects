"""Strict, leakage-safe contracts for the ProbeMem v2 reasoning layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from src.reasoning.evidence import validate_no_oracle_evidence


PROBEMEM_DECISION_SCHEMA_VERSION = 1
MEMORY_SNAPSHOT_SCHEMA_VERSION = 1


class ProbeMemTool(str, Enum):
    REQUEST_DIAGNOSTIC_PROBE = "request_diagnostic_probe"
    SELECT_INTERVENTION_SKILL = "select_intervention_skill"
    ABSTAIN = "abstain"


class InterventionSkill(str, Enum):
    BOUNDED_PLANAR_COMPENSATION = "BOUNDED_PLANAR_COMPENSATION"
    INDEPENDENT_STOCHASTIC_RETRY = "INDEPENDENT_STOCHASTIC_RETRY"
    NO_INTERVENTION = "NO_INTERVENTION"
    ABSTAIN = "ABSTAIN"


class MechanismHypothesis(str, Enum):
    STABLE_BIAS = "stable_bias"
    STOCHASTIC_OR_UNSTABLE_RESPONSE = "stochastic_or_unstable_response"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class PredictedOutcome:
    verification_status: str
    expected_progress: float
    expected_additional_steps: int

    def __post_init__(self) -> None:
        if self.verification_status not in {"ACCEPTED", "INCONCLUSIVE", "REJECTED"}:
            raise ValueError("unsupported predicted verification status")
        if not -1.0 <= self.expected_progress <= 1.0:
            raise ValueError("expected_progress must be in [-1, 1]")
        if self.expected_additional_steps < 0:
            raise ValueError("expected_additional_steps must be non-negative")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PredictedOutcome":
        required = {"verification_status", "expected_progress", "expected_additional_steps"}
        if set(value) != required:
            raise ValueError(f"predicted_outcome fields must be exactly {sorted(required)}")
        return cls(
            verification_status=str(value["verification_status"]),
            expected_progress=float(value["expected_progress"]),
            expected_additional_steps=int(value["expected_additional_steps"]),
        )


@dataclass(frozen=True)
class MemorySnapshot:
    """Chronological retrieval boundary supplied to one online decision."""

    schema_version: int
    snapshot_id: str
    created_before_episode_id: int
    verified_principle_ids: tuple[str, ...] = ()
    verified_episode_ids: tuple[str, ...] = ()
    retrievable_episode_ids: tuple[str, ...] = ()
    memory_mode: str = "empty"

    def __post_init__(self) -> None:
        if self.schema_version not in {MEMORY_SNAPSHOT_SCHEMA_VERSION, 2}:
            raise ValueError("unsupported memory snapshot schema version")
        if not self.snapshot_id.strip() or self.created_before_episode_id <= 0:
            raise ValueError("memory snapshot requires causal provenance")
        if len(set(self.verified_principle_ids)) != len(self.verified_principle_ids):
            raise ValueError("principle IDs must be unique")
        if len(set(self.verified_episode_ids)) != len(self.verified_episode_ids):
            raise ValueError("episode IDs must be unique")
        if len(set(self.retrievable_episode_ids)) != len(self.retrievable_episode_ids):
            raise ValueError("retrievable episode IDs must be unique")
        if self.memory_mode not in {"empty", "raw_development", "verified_episodic"}:
            raise ValueError("unsupported memory snapshot mode")
        if self.schema_version == 1 and self.retrievable_episode_ids:
            raise ValueError("schema-v1 snapshots cannot expose generic retrieval IDs")
        if self.memory_mode == "verified_episodic" and not (
            set(self.retrievable_episode_ids) <= set(self.verified_episode_ids)
        ):
            raise ValueError("verified retrieval may contain only verified episode IDs")

    @classmethod
    def empty_for_episode(cls, episode_id: int) -> "MemorySnapshot":
        return cls(
            schema_version=MEMORY_SNAPSHOT_SCHEMA_VERSION,
            snapshot_id=f"empty_memory_before_episode_{episode_id:04d}",
            created_before_episode_id=episode_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def available_episode_ids(self) -> tuple[str, ...]:
        return self.retrievable_episode_ids or self.verified_episode_ids


@dataclass(frozen=True)
class ProbeMemDecision:
    schema_version: int
    decision_id: str
    evidence_id: str
    memory_snapshot_id: str
    memory_used: bool
    retrieved_principle_ids: tuple[str, ...]
    retrieved_episode_ids: tuple[str, ...]
    principle_applicable: bool
    evidence_sufficient: bool
    requested_tool: ProbeMemTool
    mechanism_hypothesis: MechanismHypothesis
    selected_skill: InterventionSkill | None
    predicted_outcome: PredictedOutcome | None
    reason: str
    confidence: str

    def __post_init__(self) -> None:
        if self.schema_version != PROBEMEM_DECISION_SCHEMA_VERSION:
            raise ValueError("unsupported ProbeMem decision schema version")
        if not all(item.strip() for item in (
            self.decision_id, self.evidence_id, self.memory_snapshot_id, self.reason
        )):
            raise ValueError("decision requires identity, provenance, and reason")
        if self.confidence not in {"low", "medium", "high"}:
            raise ValueError("confidence must be low, medium, or high")
        if self.memory_used != bool(self.retrieved_principle_ids or self.retrieved_episode_ids):
            raise ValueError("memory_used must match retrieved memory IDs")
        if self.principle_applicable and not self.retrieved_principle_ids:
            raise ValueError("principle_applicable requires a retrieved principle")
        if self.requested_tool is ProbeMemTool.REQUEST_DIAGNOSTIC_PROBE:
            if self.evidence_sufficient or self.selected_skill is not None or self.predicted_outcome is not None:
                raise ValueError("probe request requires insufficient evidence and no selected skill")
        elif self.requested_tool is ProbeMemTool.SELECT_INTERVENTION_SKILL:
            if not self.evidence_sufficient or self.selected_skill in {None, InterventionSkill.ABSTAIN}:
                raise ValueError("skill selection requires sufficient evidence and an executable skill")
            if self.predicted_outcome is None:
                raise ValueError("skill selection requires a predicted outcome")
        elif self.requested_tool is ProbeMemTool.ABSTAIN:
            if self.selected_skill not in {None, InterventionSkill.ABSTAIN}:
                raise ValueError("abstention cannot select an executable skill")
            if self.predicted_outcome is not None:
                raise ValueError("abstention cannot predict a verification rollout")
        validate_no_oracle_evidence(self.to_dict())

    def validate_context(
        self,
        *,
        evidence_id: str,
        snapshot: MemorySnapshot,
        allowed_tools: Sequence[ProbeMemTool],
        allowed_skills: Sequence[InterventionSkill],
    ) -> None:
        if self.evidence_id != evidence_id or self.memory_snapshot_id != snapshot.snapshot_id:
            raise ValueError("decision provenance does not match the current evidence context")
        if not set(self.retrieved_principle_ids) <= set(snapshot.verified_principle_ids):
            raise ValueError("decision cites principles outside the current memory snapshot")
        if not set(self.retrieved_episode_ids) <= set(snapshot.available_episode_ids):
            raise ValueError("decision cites episodes outside the current memory snapshot")
        if self.requested_tool not in set(allowed_tools):
            raise ValueError("requested tool is not allowed in the current state")
        if self.selected_skill is not None and self.selected_skill not in set(allowed_skills):
            raise ValueError("selected skill is not allowed in the current state")

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["requested_tool"] = self.requested_tool.value
        result["mechanism_hypothesis"] = self.mechanism_hypothesis.value
        result["selected_skill"] = self.selected_skill.value if self.selected_skill else None
        return result

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ProbeMemDecision":
        required = {
            "schema_version", "decision_id", "evidence_id", "memory_snapshot_id",
            "memory_used", "retrieved_principle_ids", "retrieved_episode_ids",
            "principle_applicable", "evidence_sufficient", "requested_tool",
            "mechanism_hypothesis", "selected_skill", "predicted_outcome", "reason",
            "confidence",
        }
        if set(value) != required:
            raise ValueError(f"decision fields must be exactly {sorted(required)}")
        selected = value["selected_skill"]
        prediction = value["predicted_outcome"]
        return cls(
            schema_version=int(value["schema_version"]),
            decision_id=str(value["decision_id"]),
            evidence_id=str(value["evidence_id"]),
            memory_snapshot_id=str(value["memory_snapshot_id"]),
            memory_used=bool(value["memory_used"]),
            retrieved_principle_ids=tuple(str(item) for item in value["retrieved_principle_ids"]),
            retrieved_episode_ids=tuple(str(item) for item in value["retrieved_episode_ids"]),
            principle_applicable=bool(value["principle_applicable"]),
            evidence_sufficient=bool(value["evidence_sufficient"]),
            requested_tool=ProbeMemTool(str(value["requested_tool"])),
            mechanism_hypothesis=MechanismHypothesis(str(value["mechanism_hypothesis"])),
            selected_skill=None if selected is None else InterventionSkill(str(selected)),
            predicted_outcome=None if prediction is None else PredictedOutcome.from_mapping(prediction),
            reason=str(value["reason"]),
            confidence=str(value["confidence"]),
        )

    @classmethod
    def fail_closed(
        cls, *, decision_id: str, evidence_id: str, memory_snapshot_id: str, reason: str
    ) -> "ProbeMemDecision":
        return cls(
            schema_version=PROBEMEM_DECISION_SCHEMA_VERSION,
            decision_id=decision_id,
            evidence_id=evidence_id,
            memory_snapshot_id=memory_snapshot_id,
            memory_used=False,
            retrieved_principle_ids=(),
            retrieved_episode_ids=(),
            principle_applicable=False,
            evidence_sufficient=False,
            requested_tool=ProbeMemTool.ABSTAIN,
            mechanism_hypothesis=MechanismHypothesis.INSUFFICIENT_EVIDENCE,
            selected_skill=InterventionSkill.ABSTAIN,
            predicted_outcome=None,
            reason=reason,
            confidence="low",
        )
