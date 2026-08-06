"""Certified, idempotent and circuit-broken SciAgent GLM interface."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from src.probemem_sciagent.agent_orchestrator import SciAgentCallBudget, SciAgentGlmClient
from src.probemem_sciagent.agent_payload import DECISION_RESPONSE_SCHEMA
from src.probemem_sciagent.certified_decision import CertifiedSciAgentDecision, validate_certificate_mapping
from src.probemem_sciagent.decision_validator import validate_decision_mapping
from src.probemem_sciagent.memory_retrieval import ScientificMemorySnapshot
from src.probemem_sciagent.schemas import SciAgentDecision


CERTIFIED_SYSTEM_PROMPT = """You are a certificate-bearing scientific recovery
reasoner operating in shadow mode. Return exactly one bare JSON object with keys
decision and certificate. The decision must satisfy the supplied strict schema.
The certificate must bind that decision to current Agent-visible evidence and
only supplied IDs. Do not emit continuous actions, Oracle claims, fault truth,
thresholds, or an executable command. No output will control the robot."""


@dataclass(frozen=True)
class CertifiedDecisionResult:
    certified_decision: CertifiedSciAgentDecision | None
    fail_closed_decision: SciAgentDecision
    valid: bool
    repaired: bool
    cache_hit: bool
    request_hash: str
    error: str | None


class ApiReliabilityClient(SciAgentGlmClient):
    def __init__(self, *, maximum_consecutive_failures: int = 2, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if maximum_consecutive_failures <= 0:
            raise ValueError("circuit-breaker threshold must be positive")
        self.maximum_consecutive_failures = maximum_consecutive_failures
        self.consecutive_failures = 0
        self.circuit_open = False
        self._validated_cache: dict[str, CertifiedSciAgentDecision] = {}

    def certified_decide(
        self, payload: Mapping[str, Any], *, snapshot: ScientificMemorySnapshot,
        current_evidence_id: str, stage: str = "PRE_PROBE",
        allowed_probe_record_ids: Sequence[str] = (),
    ) -> CertifiedDecisionResult:
        request_hash = _request_hash(self.model, stage, payload)
        if request_hash in self._validated_cache:
            certified = self._validated_cache[request_hash]
            self.audit.append({"phase": stage, "cache_hit": True, "request_hash": request_hash, "valid_transport": True})
            return CertifiedDecisionResult(certified, certified.decision, True, False, True, request_hash, None)
        if self.circuit_open:
            failure = SciAgentDecision.fail_closed("API reliability circuit breaker is open")
            return CertifiedDecisionResult(None, failure, False, False, False, request_hash, "CIRCUIT_OPEN")
        previous_error: str | None = None
        for attempt in range(2):
            try:
                mapping = self._request(
                    payload, phase=stage, system=CERTIFIED_SYSTEM_PROMPT,
                    repair=attempt == 1, previous_error=previous_error,
                )
                if self.audit: self.audit[-1]["request_hash"] = request_hash
                if set(mapping) != {"decision", "certificate"}:
                    raise ValueError("certified response must contain decision and certificate only")
                decision = validate_decision_mapping(mapping["decision"], snapshot=snapshot, stage=stage)
                certificate = validate_certificate_mapping(
                    mapping["certificate"], decision=decision, snapshot=snapshot,
                    current_evidence_id=current_evidence_id,
                    allowed_probe_record_ids=allowed_probe_record_ids, stage=stage,
                )
                certified = CertifiedSciAgentDecision(decision, certificate)
                self._validated_cache[request_hash] = certified
                self.consecutive_failures = 0
                return CertifiedDecisionResult(certified, decision, True, attempt == 1, False, request_hash, None)
            except Exception as exc:
                previous_error = f"{type(exc).__name__}: {exc}"
                if isinstance(exc, RuntimeError) and "budget exhausted" in str(exc): break
                if attempt == 0: continue
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.maximum_consecutive_failures:
            self.circuit_open = True
        failure = SciAgentDecision.fail_closed(previous_error or "invalid certified output")
        return CertifiedDecisionResult(None, failure, False, previous_error is not None, False, request_hash, previous_error)


def build_health_check_payload() -> dict[str, Any]:
    return certify_payload({
        "stage": "API_HEALTH_CHECK_SHADOW_ONLY",
        "current_agent_evidence": {
            "evidence_id": "api_health_check_evidence",
            "evidence_quality": "INTENTIONALLY_INSUFFICIENT",
        },
        "scientific_memory": {"principles": [], "supporting_experiences": [], "counterexample_experiences": [], "hypotheses": []},
        "registered_skills": ["BOUNDED_PLANAR_COMPENSATION", "INDEPENDENT_STOCHASTIC_RETRY"],
        "required_decision": "ABSTAIN",
        "required_certificate_basis": "ABSTENTION_SAFETY",
        "response_schema": dict(DECISION_RESPONSE_SCHEMA),
        "shadow_only": True,
    })


def certify_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = dict(payload)
    value["certified_response_schema"] = {
        "decision": "exact SciAgentDecision schema supplied by the base payload",
        "certificate": {
            "decision_basis": "CURRENT_DIRECT_EVIDENCE | ACTIVE_PRINCIPLE | MICRO_PROBE_EVIDENCE | ABSTENTION_SAFETY",
            "bound_decision_mode": "must equal decision.decision_mode",
            "bound_selected_skill": "must equal decision.selected_skill",
            "alternative_skill": "other registered skill or null for abstention",
            "current_evidence_id": "exact current evidence ID",
            "supporting_evidence_ids": "list including current evidence ID",
            "supporting_principle_ids": "retrieved IDs only",
            "supporting_experience_ids": "retrieved IDs only",
            "supporting_probe_record_ids": "supplied probe IDs only",
            "grounding_claim": "REPEATED_RESPONSE_SUPPORTS_COMPENSATION | RESPONSE_VARIABILITY_SUPPORTS_RETRY | ACTION_UTILITY_UNCERTAIN | INSUFFICIENT_EVIDENCE",
            "counterevidence_summary": "non-empty string",
        },
    }
    return value


def _request_hash(model: str, stage: str, payload: Mapping[str, Any]) -> str:
    canonical = json.dumps({"model": model, "stage": stage, "payload": payload}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()
