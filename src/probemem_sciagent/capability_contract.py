"""Per-request capability tokens for constrained SciAgent responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.probemem.compact_evidence import REGISTERED_SKILLS
from src.probemem_sciagent.certified_decision import DECISION_BASES, GROUNDING_CLAIMS
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import DECISION_MODES, PROBE_JUSTIFICATION_CODES, PROBE_TYPES
from src.reasoning.evidence import validate_no_oracle_evidence


TOKEN_FIELDS = {
    "decision": {
        "decision_mode": "decision_modes",
        "selected_probe_type": "probe_types",
        "selected_skill": "skills",
        "retrieved_principle_ids": "principle_ids",
        "retrieved_experience_ids": "experience_ids",
        "retrieved_hypothesis_ids": "hypothesis_ids",
        "tested_hypothesis_ids": "hypothesis_ids",
        "probe_justification_codes": "probe_justification_codes",
    },
    "certificate": {
        "decision_basis": "decision_bases",
        "bound_decision_mode": "decision_modes",
        "bound_selected_skill": "skills",
        "alternative_skill": "skills",
        "current_evidence_id": "evidence_ids",
        "supporting_evidence_ids": "evidence_ids",
        "supporting_principle_ids": "principle_ids",
        "supporting_experience_ids": "experience_ids",
        "supporting_probe_record_ids": "probe_record_ids",
        "grounding_claim": "grounding_claims",
    },
}


@dataclass(frozen=True)
class CapabilityContract:
    namespaces: Mapping[str, Mapping[str, str]]

    def __post_init__(self) -> None:
        required = {
            "decision_modes", "skills", "probe_types", "probe_justification_codes",
            "decision_bases", "grounding_claims", "evidence_ids", "principle_ids",
            "experience_ids", "hypothesis_ids", "probe_record_ids",
        }
        if set(self.namespaces) != required:
            raise ValueError("capability contract namespaces are incomplete")
        for namespace, values in self.namespaces.items():
            if len(values) != len(set(values.values())):
                raise ValueError(f"capability namespace {namespace} is not one-to-one")
            if any(not token or not canonical for token, canonical in values.items()):
                raise ValueError("capability tokens and values must be non-empty")
        validate_no_oracle_evidence(self.to_payload())

    def to_payload(self) -> dict[str, Any]:
        return {
            "contract_version": "sciagent_capability_tokens_v1",
            "output_value_mode": "TOKENS_ONLY_FOR_LISTED_FIELDS",
            "unknown_token_policy": "FAIL_CLOSED",
            "null_policy": "null remains null",
            "field_token_namespaces": TOKEN_FIELDS,
            "namespaces": {name: dict(values) for name, values in self.namespaces.items()},
        }


def build_capability_contract(
    *, snapshot: ScientificMemorySnapshot, current_evidence_id: str,
    allowed_probe_record_ids: Sequence[str] = (),
) -> CapabilityContract:
    return CapabilityContract({
        "decision_modes": _fixed("MODE", DECISION_MODES),
        "skills": _fixed("SKILL", REGISTERED_SKILLS),
        "probe_types": _fixed("PROBE", PROBE_TYPES),
        "probe_justification_codes": _fixed("JUST", PROBE_JUSTIFICATION_CODES),
        "decision_bases": _fixed("BASIS", DECISION_BASES),
        "grounding_claims": _fixed("CLAIM", GROUNDING_CLAIMS),
        "evidence_ids": {"EVIDENCE_0": current_evidence_id},
        "principle_ids": _dynamic("PRINCIPLE", sorted(snapshot.allowed_principle_ids)),
        "experience_ids": _dynamic("EXPERIENCE", sorted(snapshot.allowed_experience_ids)),
        "hypothesis_ids": _dynamic("HYPOTHESIS", sorted(snapshot.allowed_hypothesis_ids)),
        "probe_record_ids": _dynamic("PROBE_RECORD", sorted(set(allowed_probe_record_ids))),
    })


def attach_capability_contract(
    payload: Mapping[str, Any], *, snapshot: ScientificMemorySnapshot,
    current_evidence_id: str, allowed_probe_record_ids: Sequence[str] = (),
) -> dict[str, Any]:
    value = dict(payload)
    value["capability_contract"] = build_capability_contract(
        snapshot=snapshot, current_evidence_id=current_evidence_id,
        allowed_probe_record_ids=allowed_probe_record_ids,
    ).to_payload()
    value["capability_instruction"] = (
        "For every field listed in field_token_namespaces, output only a token "
        "key from that namespace; use null only where the schema allows null."
    )
    validate_no_oracle_evidence(value)
    return value


def expand_capability_response(
    value: Mapping[str, Any], contract_payload: Mapping[str, Any],
) -> dict[str, Any]:
    if set(value) != {"decision", "certificate"}:
        raise ValueError("capability response must contain decision and certificate only")
    if contract_payload.get("contract_version") != "sciagent_capability_tokens_v1":
        raise ValueError("unknown capability contract version")
    namespaces = contract_payload.get("namespaces")
    if not isinstance(namespaces, Mapping):
        raise ValueError("capability contract namespaces are missing")
    expanded: dict[str, Any] = {}
    for section in ("decision", "certificate"):
        source = value.get(section)
        if not isinstance(source, Mapping):
            raise ValueError(f"{section} must be an object")
        target = dict(source)
        for field, namespace in TOKEN_FIELDS[section].items():
            if field not in target:
                raise ValueError(f"capability field missing: {section}.{field}")
            mapping = namespaces.get(namespace)
            if not isinstance(mapping, Mapping):
                raise ValueError(f"capability namespace missing: {namespace}")
            target[field] = _expand_value(target[field], mapping, f"{section}.{field}")
        expanded[section] = target
    validate_no_oracle_evidence(expanded)
    return expanded


def _expand_value(value: Any, mapping: Mapping[str, Any], field: str) -> Any:
    if value is None:
        return None
    if isinstance(value, list):
        return [_expand_token(item, mapping, field) for item in value]
    return _expand_token(value, mapping, field)


def _expand_token(value: Any, mapping: Mapping[str, Any], field: str) -> str:
    if not isinstance(value, str) or value not in mapping:
        raise ValueError(f"unknown capability token for {field}")
    return str(mapping[value])


def _fixed(prefix: str, values: Sequence[str]) -> dict[str, str]:
    return {f"{prefix}_{index}": value for index, value in enumerate(values)}


def _dynamic(prefix: str, values: Sequence[str]) -> dict[str, str]:
    return {f"{prefix}_{index}": value for index, value in enumerate(values)}
