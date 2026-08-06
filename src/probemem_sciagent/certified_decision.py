"""Evidence-grounding certificate for SciAgent API Reliability v1.1."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import SciAgentDecision
from src.reasoning.evidence import validate_no_oracle_evidence


DECISION_BASES = (
    "CURRENT_DIRECT_EVIDENCE", "ACTIVE_PRINCIPLE", "MICRO_PROBE_EVIDENCE", "ABSTENTION_SAFETY",
)
GROUNDING_CLAIMS = (
    "REPEATED_RESPONSE_SUPPORTS_COMPENSATION",
    "RESPONSE_VARIABILITY_SUPPORTS_RETRY",
    "ACTION_UTILITY_UNCERTAIN",
    "INSUFFICIENT_EVIDENCE",
)
CERTIFICATE_KEYS = {
    "decision_basis", "bound_decision_mode", "bound_selected_skill", "alternative_skill",
    "current_evidence_id", "supporting_evidence_ids", "supporting_principle_ids",
    "supporting_experience_ids", "supporting_probe_record_ids", "grounding_claim",
    "counterevidence_summary",
}


@dataclass(frozen=True)
class DecisionGroundingCertificate:
    decision_basis: str
    bound_decision_mode: str
    bound_selected_skill: str | None
    alternative_skill: str | None
    current_evidence_id: str
    supporting_evidence_ids: tuple[str, ...]
    supporting_principle_ids: tuple[str, ...]
    supporting_experience_ids: tuple[str, ...]
    supporting_probe_record_ids: tuple[str, ...]
    grounding_claim: str
    counterevidence_summary: str

    def __post_init__(self) -> None:
        if self.decision_basis not in DECISION_BASES or self.grounding_claim not in GROUNDING_CLAIMS:
            raise ValueError("certificate basis or grounding claim is invalid")
        if not self.current_evidence_id.strip() or not self.counterevidence_summary.strip():
            raise ValueError("certificate requires evidence provenance and counterevidence")
        for values in (
            self.supporting_evidence_ids, self.supporting_principle_ids,
            self.supporting_experience_ids, self.supporting_probe_record_ids,
        ):
            if any(not item.strip() for item in values) or len(values) != len(set(values)):
                raise ValueError("certificate IDs must be unique and non-empty")
        validate_no_oracle_evidence(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key, item in tuple(value.items()):
            if isinstance(item, tuple): value[key] = list(item)
        return value


@dataclass(frozen=True)
class CertifiedSciAgentDecision:
    decision: SciAgentDecision
    certificate: DecisionGroundingCertificate

    def to_dict(self) -> dict[str, Any]:
        return {"decision": self.decision.to_dict(), "certificate": self.certificate.to_dict()}


def validate_certificate_mapping(
    value: Mapping[str, Any], *, decision: SciAgentDecision,
    snapshot: ScientificMemorySnapshot, current_evidence_id: str,
    allowed_probe_record_ids: Sequence[str] = (), stage: str = "PRE_PROBE",
) -> DecisionGroundingCertificate:
    if set(value) != CERTIFICATE_KEYS:
        raise ValueError("certificate has unexpected or missing fields")
    certificate = DecisionGroundingCertificate(
        decision_basis=str(value["decision_basis"]),
        bound_decision_mode=str(value["bound_decision_mode"]),
        bound_selected_skill=None if value["bound_selected_skill"] is None else str(value["bound_selected_skill"]),
        alternative_skill=None if value["alternative_skill"] is None else str(value["alternative_skill"]),
        current_evidence_id=str(value["current_evidence_id"]),
        supporting_evidence_ids=tuple(str(item) for item in value["supporting_evidence_ids"]),
        supporting_principle_ids=tuple(str(item) for item in value["supporting_principle_ids"]),
        supporting_experience_ids=tuple(str(item) for item in value["supporting_experience_ids"]),
        supporting_probe_record_ids=tuple(str(item) for item in value["supporting_probe_record_ids"]),
        grounding_claim=str(value["grounding_claim"]),
        counterevidence_summary=str(value["counterevidence_summary"]),
    )
    if certificate.bound_decision_mode != decision.decision_mode or certificate.bound_selected_skill != decision.selected_skill:
        raise ValueError("certificate is not bound to the decision")
    if certificate.current_evidence_id != current_evidence_id or current_evidence_id not in certificate.supporting_evidence_ids:
        raise ValueError("certificate does not cite current direct evidence")
    if set(certificate.supporting_principle_ids) - snapshot.allowed_principle_ids:
        raise ValueError("certificate cites unknown or future principles")
    if set(certificate.supporting_experience_ids) - snapshot.allowed_experience_ids:
        raise ValueError("certificate cites unknown or future experiences")
    if set(certificate.supporting_probe_record_ids) - set(allowed_probe_record_ids):
        raise ValueError("certificate cites unknown probe evidence")
    if set(certificate.supporting_principle_ids) - set(decision.retrieved_principle_ids):
        raise ValueError("certificate principle was not retrieved by the decision")
    if set(certificate.supporting_experience_ids) - set(decision.retrieved_experience_ids):
        raise ValueError("certificate experience was not retrieved by the decision")
    if decision.decision_mode == "ABSTAIN":
        if certificate.decision_basis != "ABSTENTION_SAFETY" or certificate.alternative_skill is not None:
            raise ValueError("abstention certificate semantics are invalid")
    else:
        if certificate.alternative_skill not in REGISTERED_SKILLS or certificate.alternative_skill == decision.selected_skill:
            raise ValueError("action certificate requires the other registered skill")
        if stage == "PRE_PROBE" and certificate.decision_basis not in ("CURRENT_DIRECT_EVIDENCE", "ACTIVE_PRINCIPLE"):
            raise ValueError("pre-probe certificate has unavailable evidence basis")
        if certificate.decision_basis == "ACTIVE_PRINCIPLE" and not certificate.supporting_principle_ids:
            raise ValueError("principle basis requires a cited active principle")
        if certificate.decision_basis == "MICRO_PROBE_EVIDENCE" and not certificate.supporting_probe_record_ids:
            raise ValueError("micro-probe basis requires cited probe evidence")
    return certificate
