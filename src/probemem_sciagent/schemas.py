"""Strict, leakage-safe schemas for ProbeMem-SciAgent v1."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Mapping

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.reasoning.evidence import validate_no_oracle_evidence


VERIFICATION_STATUSES = ("ACCEPTED", "INCONCLUSIVE", "REJECTED")
DECISION_MODES = ("ACT_DIRECTLY", "RUN_MICRO_PROBE", "ABSTAIN")
DECISION_STAGES = ("PRE_PROBE", "POST_PROBE")
PROBE_TYPES = ("COMPENSATION_RESPONSE_PROBE", "RETRY_REPEATABILITY_PROBE")
HYPOTHESIS_STATUSES = ("PROPOSED", "UNDER_TEST", "SUPPORTED", "CONTRADICTED", "RETIRED")
PRINCIPLE_STATUSES = ("ACTIVE", "RESTRICTED", "SUSPENDED", "RETIRED")
UPDATE_OPERATIONS = (
    "CREATE_HYPOTHESIS", "ADD_HYPOTHESIS_SUPPORT", "ADD_HYPOTHESIS_CONTRADICTION",
    "MARK_HYPOTHESIS_TESTED", "RESTRICT_PRINCIPLE", "SUSPEND_PRINCIPLE",
)
PROBE_JUSTIFICATION_CODES = (
    "PRINCIPLE_CONFLICT", "OUTSIDE_PRINCIPLE_SCOPE", "SMALL_PREDICTED_GAP",
    "HIGH_COUNTEREXAMPLE_RATE", "MISSING_ACTION_CONDITIONED_EVIDENCE",
)
APPLICABILITY_CONDITION_CODES = (
    "CURRENT_FAILURE", "STABLE_DIRECTIONAL_RESPONSE", "VARIABLE_DIRECTIONAL_RESPONSE",
    "COMPENSATION_RESPONSE_ALIGNED", "COMPENSATION_RESPONSE_UNSTABLE",
    "RETRY_PROGRESS_REPEATABLE", "RETRY_PROGRESS_VARIABLE",
    "ACTIVE_PRINCIPLE_CONFLICT", "NO_ACTIVE_PRINCIPLE_APPLIES",
)


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _unique_ids(values: tuple[str, ...], name: str) -> None:
    if any(not item.strip() for item in values) or len(values) != len(set(values)):
        raise ValueError(f"{name} must contain unique non-empty IDs")


def _finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


@dataclass(frozen=True)
class SciAgentDecision:
    evidence_summary: str
    candidate_hypotheses: tuple[str, ...]
    retrieved_principle_ids: tuple[str, ...]
    retrieved_experience_ids: tuple[str, ...]
    decision_mode: str
    selected_probe_type: str | None
    selected_skill: str | None
    expected_effect: str
    uncertainty_reason: str
    predicted_success_probability: float
    stop_reason: str | None
    retrieved_hypothesis_ids: tuple[str, ...] = ()
    tested_hypothesis_ids: tuple[str, ...] = ()
    probe_justification_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_summary.strip() or not self.expected_effect.strip():
            raise ValueError("decision summaries cannot be empty")
        if self.decision_mode not in DECISION_MODES:
            raise ValueError("invalid decision mode")
        if len(self.candidate_hypotheses) < 2 or any(not value.strip() for value in self.candidate_hypotheses):
            raise ValueError("both competing recovery hypotheses are required")
        if not all(any(skill in text for text in self.candidate_hypotheses) for skill in REGISTERED_SKILLS):
            raise ValueError("candidate hypotheses must cover both registered skills")
        for ids, name in (
            (self.retrieved_principle_ids, "principle IDs"),
            (self.retrieved_experience_ids, "experience IDs"),
            (self.retrieved_hypothesis_ids, "hypothesis IDs"),
            (self.tested_hypothesis_ids, "tested hypothesis IDs"),
        ):
            _unique_ids(ids, name)
        if not set(self.tested_hypothesis_ids) <= set(self.retrieved_hypothesis_ids):
            raise ValueError("tested hypotheses must have been retrieved")
        if not 0.0 <= self.predicted_success_probability <= 1.0:
            raise ValueError("predicted probability must be in [0, 1]")
        if self.decision_mode == "RUN_MICRO_PROBE":
            if self.selected_probe_type not in PROBE_TYPES or self.selected_skill not in REGISTERED_SKILLS:
                raise ValueError("probe decisions require a registered probe and provisional skill")
            if not self.uncertainty_reason.strip() or not self.probe_justification_codes:
                raise ValueError("probe decisions require an auditable evidence gap")
        elif self.selected_probe_type is not None or self.probe_justification_codes:
            raise ValueError("non-probe decisions cannot request probe evidence")
        if self.decision_mode == "ACT_DIRECTLY" and self.selected_skill not in REGISTERED_SKILLS:
            raise ValueError("direct decisions require a registered skill")
        if self.decision_mode == "ABSTAIN" and (self.selected_skill is not None or not (self.stop_reason or "").strip()):
            raise ValueError("abstention requires no skill and a stop reason")
        if any(code not in PROBE_JUSTIFICATION_CODES for code in self.probe_justification_codes):
            raise ValueError("unknown probe justification")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key, item in tuple(value.items()):
            if isinstance(item, tuple):
                value[key] = list(item)
        return value

    @classmethod
    def fail_closed(cls, reason: str) -> "SciAgentDecision":
        return cls(
            evidence_summary="Decision unavailable; host failed closed.",
            candidate_hypotheses=(
                f"Insufficient validated evidence for {REGISTERED_SKILLS[0]}",
                f"Insufficient validated evidence for {REGISTERED_SKILLS[1]}",
            ),
            retrieved_principle_ids=(), retrieved_experience_ids=(),
            decision_mode="ABSTAIN", selected_probe_type=None, selected_skill=None,
            expected_effect="Avoid an unsupported recovery execution.",
            uncertainty_reason=reason, predicted_success_probability=0.0,
            stop_reason=reason,
        )


@dataclass(frozen=True)
class ExperienceRecord:
    experience_id: str
    episode_id: str
    seed: int
    evidence_signature: Mapping[str, Any]
    selected_skill: str
    agent_prediction: str
    predicted_success_probability: float
    agent_reasoning_summary: str
    verification_status: str
    final_distance: float
    environment_steps: int
    supporting_principle_ids: tuple[str, ...]
    probe_record_ids: tuple[str, ...]
    created_at_step: int

    def __post_init__(self) -> None:
        _identifier(self.experience_id, "experience ID")
        _identifier(self.episode_id, "episode ID")
        if self.seed < 0 or self.selected_skill not in REGISTERED_SKILLS:
            raise ValueError("invalid seed or selected skill")
        if self.verification_status not in VERIFICATION_STATUSES:
            raise ValueError("invalid verification status")
        if not 0.0 <= self.predicted_success_probability <= 1.0:
            raise ValueError("invalid predicted probability")
        _finite(self.final_distance, "final distance")
        if self.final_distance < 0 or self.environment_steps <= 0 or self.created_at_step <= 0:
            raise ValueError("experience costs, time, and distance must be positive")
        _unique_ids(self.supporting_principle_ids, "supporting principle IDs")
        _unique_ids(self.probe_record_ids, "probe record IDs")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence_signature"] = dict(self.evidence_signature)
        value["supporting_principle_ids"] = list(self.supporting_principle_ids)
        value["probe_record_ids"] = list(self.probe_record_ids)
        return value


@dataclass(frozen=True)
class HypothesisRecord:
    hypothesis_id: str
    statement: str
    applicability_conditions: tuple[str, ...]
    predicted_best_skill: str
    induction_experience_ids: tuple[str, ...] = ()
    supporting_experience_ids: tuple[str, ...] = ()
    contradicting_experience_ids: tuple[str, ...] = ()
    tested_experience_ids: tuple[str, ...] = ()
    targeted_probe_record_ids: tuple[str, ...] = ()
    proposed_probe_type: str | None = None
    verification_count: int = 0
    support_count: int = 0
    contradiction_count: int = 0
    independent_seed_count: int = 0
    targeted_verification_count: int = 0
    most_recent_verification_status: str | None = None
    status: str = "PROPOSED"
    created_at_step: int = 1
    updated_at_step: int = 1

    def __post_init__(self) -> None:
        _identifier(self.hypothesis_id, "hypothesis ID")
        if not self.statement.strip() or not self.applicability_conditions:
            raise ValueError("hypothesis requires a statement and applicability")
        if any(value not in APPLICABILITY_CONDITION_CODES for value in self.applicability_conditions):
            raise ValueError("hypothesis contains unregistered applicability conditions")
        if self.predicted_best_skill not in REGISTERED_SKILLS or self.status not in HYPOTHESIS_STATUSES:
            raise ValueError("invalid hypothesis skill or status")
        if self.proposed_probe_type is not None and self.proposed_probe_type not in PROBE_TYPES:
            raise ValueError("invalid proposed probe")
        for name in (
            "induction_experience_ids", "supporting_experience_ids", "contradicting_experience_ids",
            "tested_experience_ids", "targeted_probe_record_ids",
        ):
            _unique_ids(getattr(self, name), name)
        counts = (self.verification_count, self.support_count, self.contradiction_count,
                  self.independent_seed_count, self.targeted_verification_count)
        if min(counts) < 0 or self.support_count != len(self.supporting_experience_ids) or self.contradiction_count != len(self.contradicting_experience_ids):
            raise ValueError("hypothesis counts disagree with evidence")
        if self.verification_count != len(self.tested_experience_ids):
            raise ValueError("verification count must match tested experiences")
        if self.targeted_verification_count != len(self.targeted_probe_record_ids):
            raise ValueError("targeted verification count must match probe records")
        if self.most_recent_verification_status not in (None, *VERIFICATION_STATUSES):
            raise ValueError("invalid most recent verification status")
        if self.created_at_step <= 0 or self.updated_at_step < self.created_at_step:
            raise ValueError("invalid hypothesis chronology")

    @property
    def support_rate(self) -> float:
        decisive = self.support_count + self.contradiction_count
        return self.support_count / decisive if decisive else 0.0

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["support_rate"] = self.support_rate
        return value


@dataclass(frozen=True)
class PrincipleRecord:
    principle_id: str
    statement: str
    applicability_conditions: tuple[str, ...]
    recommended_skill: str
    support_count: int
    contradiction_count: int
    independent_seed_count: int
    estimated_success_rate: float
    scope_description: str
    known_failure_modes: tuple[str, ...]
    source_hypothesis_ids: tuple[str, ...]
    source_experience_ids: tuple[str, ...]
    confidence_level: str
    status: str
    created_at_step: int
    updated_at_step: int
    most_recent_verification_status: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.principle_id, "principle ID")
        if self.recommended_skill not in REGISTERED_SKILLS or self.status not in PRINCIPLE_STATUSES:
            raise ValueError("invalid principle skill or status")
        if not self.statement.strip() or not self.scope_description.strip() or not self.applicability_conditions:
            raise ValueError("principle requires statement and scope")
        if any(value not in APPLICABILITY_CONDITION_CODES for value in self.applicability_conditions):
            raise ValueError("principle contains unregistered applicability conditions")
        if min(self.support_count, self.contradiction_count, self.independent_seed_count) < 0:
            raise ValueError("principle counts cannot be negative")
        if not 0.0 <= self.estimated_success_rate <= 1.0:
            raise ValueError("invalid principle success rate")
        _unique_ids(self.source_hypothesis_ids, "source hypothesis IDs")
        _unique_ids(self.source_experience_ids, "source experience IDs")
        if self.created_at_step <= 0 or self.updated_at_step < self.created_at_step:
            raise ValueError("invalid principle chronology")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CompensationProbeEvidence:
    expected_direction_alignment: float
    object_response_magnitude: float
    response_consistency: float
    contact_preserved: bool
    temporary_progress: float

    def __post_init__(self) -> None:
        for name in ("expected_direction_alignment", "object_response_magnitude", "response_consistency", "temporary_progress"):
            _finite(float(getattr(self, name)), name)
        if not -1.0 <= self.expected_direction_alignment <= 1.0 or not 0.0 <= self.response_consistency <= 1.0 or self.object_response_magnitude < 0:
            raise ValueError("invalid compensation probe evidence")


@dataclass(frozen=True)
class RetryProbeEvidence:
    num_trials: int
    positive_progress_rate: float
    mean_progress: float
    progress_variance: float
    severe_failure_rate: float

    def __post_init__(self) -> None:
        if self.num_trials <= 1 or not 0.0 <= self.positive_progress_rate <= 1.0 or not 0.0 <= self.severe_failure_rate <= 1.0:
            raise ValueError("invalid retry probe rates")
        _finite(self.mean_progress, "mean progress")
        if not math.isfinite(self.progress_variance) or self.progress_variance < 0:
            raise ValueError("invalid retry probe variance")


@dataclass(frozen=True)
class MicroProbeRecord:
    probe_record_id: str
    episode_id: str
    seed: int
    probe_type: str
    requested_by_decision_id: str
    evidence: Mapping[str, Any]
    environment_steps: int
    random_seed_ids: tuple[int, ...]
    created_at_step: int
    reset_before_formal_recovery: bool

    def __post_init__(self) -> None:
        _identifier(self.probe_record_id, "probe record ID")
        if self.probe_type not in PROBE_TYPES or self.environment_steps <= 0:
            raise ValueError("invalid probe record")
        if not self.random_seed_ids or len(self.random_seed_ids) != len(set(self.random_seed_ids)):
            raise ValueError("probe requires unique random seeds")
        if self.reset_before_formal_recovery is not True:
            raise ValueError("formal recovery reset must be confirmed")
        validate_no_oracle_evidence(dict(self.evidence))


@dataclass(frozen=True)
class KnowledgeUpdateProposal:
    operation: str
    target_id: str | None
    statement: str | None = None
    applicability_conditions: tuple[str, ...] = ()
    predicted_best_skill: str | None = None
    proposed_probe_type: str | None = None
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.operation not in UPDATE_OPERATIONS or not self.rationale.strip():
            raise ValueError("invalid knowledge update operation")
        if self.operation == "CREATE_HYPOTHESIS":
            if self.target_id is not None or not (self.statement or "").strip() or not self.applicability_conditions:
                raise ValueError("new hypotheses require statement and applicability")
            if any(value not in APPLICABILITY_CONDITION_CODES for value in self.applicability_conditions):
                raise ValueError("new hypothesis contains unregistered applicability conditions")
            if self.predicted_best_skill not in REGISTERED_SKILLS:
                raise ValueError("new hypothesis requires registered skill")
        elif not (self.target_id or "").strip():
            raise ValueError("updates require a target ID")
        if self.proposed_probe_type is not None and self.proposed_probe_type not in PROBE_TYPES:
            raise ValueError("invalid hypothesis probe type")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
